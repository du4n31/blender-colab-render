"""Load and manage custom Python scripts for rendering.

Scripts are acquired from URLs, direct upload, or Drive using
source_resolver, y se pasan a Blender via --python adicional.
"""

import sys
from pathlib import Path
from typing import Optional

from bcr.source_resolver import (
    SourceAcquisitionError,
    acquire_source,
    resolve_zip_contents,
)


class ScriptLoadError(Exception):
    """Error raised while acquiring or loading a custom script."""


def acquire_script(method: str, value: str, dest_dir: Path) -> Path:
    """Acquire a Python script from a URL, upload, or Drive path.

    Args:
        method: ``"link"``, ``"upload"`` o ``"drive_path"``.
        value: URL or Drive path; ignored for ``"upload"``.
        dest_dir: Destination directory.

    Returns:
        Path to the acquired .py file.

    Raises:
        ScriptLoadError: if acquisition fails or the file is not a .py file.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = dest_dir / "_src"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        local_path = acquire_source(method, value, tmp_dir)
    except SourceAcquisitionError as exc:
        raise ScriptLoadError(str(exc)) from exc

    # If this is a .zip archive, extract it and locate the entry point
    if local_path.suffix == ".zip":
        try:
            result = resolve_zip_contents(local_path, dest_dir, kind="script")
        except SourceAcquisitionError as exc:
            raise ScriptLoadError(str(exc)) from exc
        # result = [entry_point, extracted_dir]
        entry_point, extracted_dir = result[0], result[1]
        # Add the extracted directory to sys.path for relative imports
        sys.path.insert(0, str(extracted_dir))
        return entry_point

    # If it is not a .py file, rename it
    if local_path.suffix != ".py":
        new_path = local_path.with_suffix(".py")
        local_path.rename(new_path)
        local_path = new_path

    return local_path


def collect_script_args(
    sources: list[tuple[str, str]],
    tmp_dir: Path,
) -> list[str]:
    """Genera argumentos --python adicionales para pasar a Blender.

    Args:
        sources: Lista de ``(method, value)``.
            method: ``"link"``, ``"upload"`` o ``"drive_path"``.
            value: URL or Drive path; use ``""`` for ``"upload"``.
        tmp_dir: Temporary directory for acquiring scripts.

    Returns:
        List of subprocess arguments: ``['--python', '/path/script1.py', ...]``
    """
    args: list[str] = []
    for method, value in sources:
        if not method or not method.strip():
            continue
        method = method.strip()
        value = (value or "").strip()
        script_path = acquire_script(method, value, tmp_dir)
        args.append("--python")
        args.append(str(script_path))
    return args
