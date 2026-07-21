"""Generaliza la adquisicion de archivos para Blender Colab Render.

Reemplaza link_resolver.py como capa de adquisicion externa.
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
    """Error al adquirir o procesar un archivo."""


def acquire_source(method: str, value: str, working_dir: Path) -> Path:
    """Adquiere un archivo desde un enlace, subida de Colab o ruta de Drive.

    Args:
        method: ``"link"``, ``"upload"`` o ``"drive_path"``.
        value: URL, ruta en Drive, o ignorado para ``"upload"``.
        working_dir: Directorio donde se almacenara el archivo.

    Returns:
        Ruta resuelta al archivo adquirido.

    Raises:
        SourceAcquisitionError: si falla la adquisicion.
    """
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)

    if method == "link":
        return _acquire_from_link(value, working_dir)
    if method == "upload":
        return _acquire_from_upload(working_dir)
    if method == "drive_path":
        return _acquire_from_drive(value, working_dir)

    msg = f"Metodo de adquisicion desconocido: '{method}'. Usa 'link', 'upload' o 'drive_path'."
    raise SourceAcquisitionError(msg)


def _acquire_from_link(url: str, working_dir: Path) -> Path:
    """Descarga un archivo desde una URL resuelta por link_resolver."""
    try:
        direct_url = link_resolver.resolve_download_url(url)
    except link_resolver.LinkResolutionError as exc:
        msg = f"Error al resolver URL '{url}': {exc}"
        raise SourceAcquisitionError(msg) from exc

    # Extraer nombre de archivo de la URL (ultimo segmento, sin query params)
    filename = url.rstrip("/").split("/")[-1].split("?")[0]
    if not filename:
        filename = "downloaded_file"

    dest_path = working_dir / filename

    try:
        resp = requests.get(direct_url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Error al descargar '{direct_url}': {exc}"
        raise SourceAcquisitionError(msg) from exc

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    return dest_path.resolve()


def _acquire_from_upload(working_dir: Path) -> Path:
    """Sube un archivo via ``google.colab.files.upload()``.

    NOTA: Esta funcion es **bloqueante** y requiere que el usuario seleccione
    un archivo en el navegador de Colab. Solo funciona en Google Colab.
    """
    try:
        from google.colab import files  # type: ignore[import-untyped]
    except ImportError:
        msg = (
            "El metodo 'upload' solo esta disponible en Google Colab. "
            "Usa 'link' o 'drive_path' en su lugar."
        )
        raise SourceAcquisitionError(msg) from None

    uploaded = files.upload()
    if not uploaded:
        msg = "No se subio ningun archivo."
        raise SourceAcquisitionError(msg)

    filename = next(iter(uploaded))
    content = uploaded[filename]
    dest_path = working_dir / filename
    with open(dest_path, "wb") as f:
        f.write(content)

    return dest_path.resolve()


def _acquire_from_drive(value: str, working_dir: Path) -> Path:
    """Copia un archivo desde Google Drive montado en ``/content/drive``."""
    source = Path(value).resolve()
    drive_root = DRIVE_MOUNT_POINT.resolve()

    try:
        source.relative_to(drive_root)
    except ValueError:
        msg = f"La ruta debe estar dentro de {drive_root}, got {source}"
        raise SourceAcquisitionError(msg) from None

    if not source.exists():
        msg = f"El archivo no existe en Drive: {source}"
        raise SourceAcquisitionError(msg)

    dest_path = working_dir / source.name
    try:
        shutil.copy2(str(source), str(dest_path))
    except OSError as exc:
        msg = f"Error al copiar '{source}' a '{dest_path}': {exc}"
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
        local_path: Ruta al archivo (puede ser .zip u otro).
        working_dir: Directorio donde extraer el ZIP.
        kind: ``"blend"`` para buscar archivos .blend,
              ``"script"`` para buscar entry point .py.

    Returns:
        Para ``"blend"``: Path al unico archivo .blend encontrado.
        Para ``"script"``: ``[entry_point_path, extracted_dir_path]``.

    Raises:
        SourceAcquisitionError: si no se encuentra el contenido esperado
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
        msg = f"El archivo no es un ZIP valido: {local_path}"
        raise SourceAcquisitionError(msg) from exc

    if kind == "blend":
        return _resolve_blend_in_dir(extract_dir)
    if kind == "script":
        return _resolve_script_in_dir(extract_dir)

    msg = f"Tipo desconocido: '{kind}'. Usa 'blend' o 'script'."
    raise SourceAcquisitionError(msg)


def _check_zip_slip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    """Verifica que ninguna entrada del ZIP intente escapar del directorio destino."""
    resolved_base = extract_dir.resolve()
    for member_name in zf.namelist():
        target_path = (extract_dir / member_name).resolve()
        if not str(target_path).startswith(str(resolved_base)):
            msg = (
                f"Zip slip detected: entry '{member_name}' "
                "would extract outside target directory"
            )
            raise SourceAcquisitionError(msg)


def _resolve_blend_in_dir(extract_dir: Path) -> Path:
    """Busca un unico archivo .blend dentro del directorio extraido."""
    blend_files = sorted(extract_dir.rglob("*.blend"))

    if len(blend_files) == 1:
        return blend_files[0].resolve()

    if len(blend_files) > 1:
        disponibles = ", ".join(str(p) for p in blend_files)
        msg = (
            f"Se encontraron {len(blend_files)} archivos .blend, "
            f"especifica cual usar: {disponibles}"
        )
        raise SourceAcquisitionError(msg)

    msg = f"No se encontraron archivos .blend en {extract_dir}"
    raise SourceAcquisitionError(msg)


def _resolve_script_in_dir(extract_dir: Path) -> list[Path]:
    """Busca el entry point .py dentro del directorio extraido.

    Si existe ``entry_point.txt`` usa su contenido como ruta relativa.
    Si no, busca un unico archivo .py. Si hay multiples, pide
    ``entry_point.txt`` via error.
    """
    entry_point_file = extract_dir / "entry_point.txt"
    if entry_point_file.exists():
        entry_rel = entry_point_file.read_text(encoding="utf-8").strip()
        entry_path = (extract_dir / entry_rel).resolve()
        if not entry_path.exists():
            msg = (
                f"entry_point.txt senala a '{entry_rel}' "
                f"pero no existe en {extract_dir}"
            )
            raise SourceAcquisitionError(msg)
        return [entry_path, extract_dir.resolve()]

    py_files = sorted(extract_dir.rglob("*.py"))
    if len(py_files) == 1:
        return [py_files[0].resolve(), extract_dir.resolve()]

    if len(py_files) > 1:
        msg = (
            f"Se encontraron {len(py_files)} archivos .py en {extract_dir}. "
            "Crea un archivo entry_point.txt con la ruta relativa al entry point."
        )
        raise SourceAcquisitionError(msg)

    msg = f"No se encontraron archivos .py en {extract_dir}"
    raise SourceAcquisitionError(msg)
