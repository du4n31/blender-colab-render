"""Generalize file acquisition for Blender Colab Render.

Replaces link_resolver.py as the external acquisition layer.
link_resolver.py se mantiene como detalle interno de la implementacion.
"""

import shutil
import zipfile
from pathlib import Path
from typing import Union

import requests

from bcr import link_resolver
from bcr.config import CHUNK_SIZE, DOWNLOAD_TIMEOUT_SECONDS, DRIVE_MOUNT_POINT


class SourceAcquisitionError(Exception):
    """Error raised while acquiring or processing a file."""


def acquire_source(method: str, value: str, working_dir: Path) -> Path:
    """Acquire a file from a URL, Colab upload, or Drive path.

    Args:
        method: ``"link"``, ``"upload"`` o ``"drive_path"``.
        value: URL or Drive path; ignored for ``"upload"``.
        working_dir: Directory where the file will be stored.

    Returns:
        Resolved path to the acquired file.

    Raises:
        SourceAcquisitionError: if acquisition fails.
    """
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)

    if method == "link":
        return _acquire_from_link(value, working_dir)
    if method == "upload":
        return _acquire_from_upload(working_dir)
    if method == "drive_path":
        return _acquire_from_drive(value, working_dir)

    msg = f"Unknown acquisition method: '{method}'. Use 'link', 'upload', or 'drive_path'."
    raise SourceAcquisitionError(msg)


def _acquire_from_link(url: str, working_dir: Path) -> Path:
    """Download a file from a URL resolved by link_resolver."""
    try:
        direct_url = link_resolver.resolve_download_url(url)
    except link_resolver.LinkResolutionError as exc:
        msg = f"Failed to resolve URL '{url}': {exc}"
        raise SourceAcquisitionError(msg) from exc

    # Extract the filename from the URL (last segment, without query parameters)
    filename = url.rstrip("/").split("/")[-1].split("?")[0]
    if not filename:
        filename = "downloaded_file"

    dest_path = working_dir / filename

    try:
        resp = requests.get(direct_url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Failed to download '{direct_url}': {exc}"
        raise SourceAcquisitionError(msg) from exc

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    return dest_path.resolve()


def _acquire_from_upload(working_dir: Path) -> Path:
    """Sube un archivo via ``google.colab.files.upload()``.

    NOTE: This function is **blocking** and requires the user to select
    un archivo en el navegador de Colab. Solo funciona en Google Colab.
    """
    try:
        from google.colab import files  # type: ignore[import-untyped]
    except ImportError:
        msg = (
            "The 'upload' method is only available in Google Colab. "
            "Usa 'link' o 'drive_path' en su lugar."
        )
        raise SourceAcquisitionError(msg) from None

    uploaded = files.upload()
    if not uploaded:
        msg = "No file was uploaded."
        raise SourceAcquisitionError(msg)

    filename = next(iter(uploaded))
    content = uploaded[filename]
    dest_path = working_dir / filename
    with open(dest_path, "wb") as f:
        f.write(content)

    return dest_path.resolve()


def _acquire_from_drive(value: str, working_dir: Path) -> Path:
    """Copy a file from Google Drive mounted at ``/content/drive``.

    ``value`` may be a path relative to the Drive mount point
    (p.ej. "MyDrive/escenas/mi_escena.blend", que es lo que el notebook
    prompting the user) or an absolute path inside it. Before copying,
    Path(value).resolve() resolvia las rutas relativas contra el
    the path must be resolved against the Drive mount, not the process working directory (e.g. /content),
    because a relative path that looks correct according to the instructions
    notebook nunca se encontraba.
    """
    candidate = Path(value)
    drive_root = DRIVE_MOUNT_POINT.resolve()
    if not candidate.is_absolute():
        candidate = drive_root / candidate
    source = candidate.resolve()

    try:
        source.relative_to(drive_root)
    except ValueError:
        msg = f"Path must be inside {drive_root}, got {source}"
        raise SourceAcquisitionError(msg) from None

    if not source.exists():
        msg = f"File does not exist in Drive: {source}"
        raise SourceAcquisitionError(msg)

    dest_path = working_dir / source.name
    try:
        shutil.copy2(str(source), str(dest_path))
    except OSError as exc:
        msg = f"Failed to copy '{source}' to '{dest_path}': {exc}"
        raise SourceAcquisitionError(msg) from exc

    return dest_path.resolve()


def resolve_zip_contents(
    local_path: Path,
    working_dir: Path,
    kind: str,
) -> Union[Path, list[Path]]:
    """Extrae y resuelve el contenido de un archivo ZIP segun el tipo solicitado.

    Si ``local_path`` no tiene extension ``.zip`` se devuelve tal cual
    (como Path para ``kind="blend"`` o ``[Path]`` para ``kind="script"``).

    Args:
        local_path: Path to the file (may be a .zip archive or another type).
        working_dir: Directory where the ZIP will be extracted.
        kind: ``"blend"`` para buscar archivos .blend,
              ``"script"`` para buscar entry point .py.

    Returns:
        Para ``"blend"``: Path al unico archivo .blend encontrado.
        Para ``"script"``: ``[entry_point_path, extracted_dir_path]``.

    Raises:
        SourceAcquisitionError: if the expected content cannot be found
            o se detecta un intento de zip slip.
    """
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_path.resolve()

    if local_path.suffix != ".zip":
        if kind == "blend":
            return local_path
        return [local_path]

    extract_dir = working_dir / local_path.stem
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(str(local_path), "r") as zf:
            _check_zip_slip(zf, extract_dir)
            zf.extractall(str(extract_dir))
    except zipfile.BadZipFile as exc:
        msg = f"File is not a valid ZIP archive: {local_path}"
        raise SourceAcquisitionError(msg) from exc

    if kind == "blend":
        return _resolve_blend_in_dir(extract_dir)
    if kind == "script":
        return _resolve_script_in_dir(extract_dir)

    msg = f"Unknown content type: '{kind}'. Use 'blend' or 'script'."
    raise SourceAcquisitionError(msg)


def _check_zip_slip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    """Verify that no ZIP entry attempts to escape the destination directory."""
    resolved_base = extract_dir.resolve()
    for member_name in zf.namelist():
        target_path = (extract_dir / member_name).resolve()
        try:
            target_path.relative_to(resolved_base)
        except ValueError:
            msg = (
                f"ZIP slip detected: entry '{member_name}' "
                "would extract outside the target directory"
            )
            raise SourceAcquisitionError(msg)


def _resolve_blend_in_dir(extract_dir: Path) -> Path:
    """Find a single .blend file in the extracted directory."""
    blend_files = sorted(extract_dir.rglob("*.blend"))

    if len(blend_files) == 1:
        return blend_files[0].resolve()

    if len(blend_files) > 1:
        available = ", ".join(str(p) for p in blend_files)
        msg = (
            f"Found {len(blend_files)} .blend files; specify which one to use: "
            f"{available}"
        )
        raise SourceAcquisitionError(msg)

    msg = f"No .blend files were found in {extract_dir}"
    raise SourceAcquisitionError(msg)


def _resolve_script_in_dir(extract_dir: Path) -> list[Path]:
    """Find the .py entry point in the extracted directory.

    If ``entry_point.txt`` exists, use its contents as a relative path.
    Otherwise, find a single .py file. If multiple files exist, require
    an ``entry_point.txt`` file and raise an actionable error.
    """
    entry_point_file = extract_dir / "entry_point.txt"
    if entry_point_file.exists():
        entry_rel = entry_point_file.read_text(encoding="utf-8").strip()
        entry_path = (extract_dir / entry_rel).resolve()
        if not entry_path.exists():
            msg = (
                f"entry_point.txt points to '{entry_rel}' "
                f"but it does not exist in {extract_dir}"
            )
            raise SourceAcquisitionError(msg)
        return [entry_path, extract_dir.resolve()]

    py_files = sorted(extract_dir.rglob("*.py"))
    if len(py_files) == 1:
        return [py_files[0].resolve(), extract_dir.resolve()]

    if len(py_files) > 1:
        msg = (
            f"Found {len(py_files)} .py files in {extract_dir}. "
            "Create an entry_point.txt file containing the relative path to the entry point."
        )
        raise SourceAcquisitionError(msg)

    msg = f"No .py files were found in {extract_dir}"
    raise SourceAcquisitionError(msg)
