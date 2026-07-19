"""Carga y gestion de scripts Python personalizados para el render.

Los scripts se descargan desde URLs y se pasan a Blender via --python adicional.
"""

import os
from pathlib import Path
from typing import Optional

import requests


class ScriptLoadError(Exception):
    """Error al descargar o cargar un script personalizado."""


def download_custom_script(url: str, dest_dir: Path, filename: Optional[str] = None) -> Path:
    """Descarga un script Python desde una URL.

    Args:
        url: URL del script .py.
        dest_dir: Directorio destino.
        filename: Nombre opcional para el archivo (default: ultimo segmento de la URL).

    Returns:
        Ruta al archivo descargado.

    Raises:
        ScriptLoadError: si la descarga falla o el contenido no es .py.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        filename = url.rstrip("/").split("/")[-1]
    if not filename.endswith(".py"):
        filename += ".py"

    dest_path = dest_dir / filename

    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Error al descargar script {url}: {exc}"
        raise ScriptLoadError(msg) from exc

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    # Validacion basica
    if not dest_path.exists():
        msg = f"El archivo descargado no existe: {dest_path}"
        raise ScriptLoadError(msg)

    file_size = dest_path.stat().st_size
    if file_size == 0:
        os.remove(str(dest_path))
        msg = f"El archivo descargado esta vacio: {url}"
        raise ScriptLoadError(msg)

    return dest_path


def collect_script_args(script_urls: list[str], tmp_dir: Path) -> list[str]:
    """Genera argumentos --python adicionales para pasar a Blender.

    Args:
        script_urls: Lista de URLs de scripts .py.
        tmp_dir: Directorio temporal donde descargar los scripts.

    Returns:
        Lista de argumentos para subprocess: ['--python', '/ruta/script1.py', ...]
    """
    args: list[str] = []
    for url in script_urls:
        if not url or not url.strip():
            continue
        url = url.strip()
        script_path = download_custom_script(url, tmp_dir)
        args.append("--python")
        args.append(str(script_path))
    return args
