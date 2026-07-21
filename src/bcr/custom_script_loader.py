"""Carga y gestion de scripts Python personalizados para el render.

Los scripts se adquieren desde URLs, subida directa o Drive usando
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
    """Error al adquirir o cargar un script personalizado."""


def acquire_script(method: str, value: str, dest_dir: Path) -> Path:
    """Adquiere un script Python desde un enlace, subida o ruta de Drive.

    Args:
        method: ``"link"``, ``"upload"`` o ``"drive_path"``.
        value: URL, ruta en Drive, o ignorado para ``"upload"``.
        dest_dir: Directorio destino.

    Returns:
        Ruta al archivo .py adquirido.

    Raises:
        ScriptLoadError: si falla la adquisicion o el archivo no es .py.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = dest_dir / "_src"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        local_path = acquire_source(method, value, tmp_dir)
    except SourceAcquisitionError as exc:
        raise ScriptLoadError(str(exc)) from exc

    # Si es .zip, extraer y localizar entry point
    if local_path.suffix == ".zip":
        try:
            result = resolve_zip_contents(local_path, dest_dir, kind="script")
        except SourceAcquisitionError as exc:
            raise ScriptLoadError(str(exc)) from exc
        # result = [entry_point, extracted_dir]
        entry_point, extracted_dir = result[0], result[1]
        # Agregar el directorio extraido a sys.path para imports relativos
        sys.path.insert(0, str(extracted_dir))
        return entry_point

    # Si no es .py, renombrar
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
            value: URL, ruta en Drive, o ``""`` para ``"upload"``.
        tmp_dir: Directorio temporal donde adquirir los scripts.

    Returns:
        Lista de argumentos para subprocess: ``['--python', '/ruta/script1.py', ...]``
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
