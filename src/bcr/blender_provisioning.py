"""Aprovisionamiento del binario portable de Blender.

Descarga el .tar.xz desde download.blender.org y lo extrae.
Soporta cache en Drive para no re-descargar en cada sesion de Colab.
"""

import os
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

import requests

from bcr.config import (
    BLENDER_BINARY_RELATIVE,
    BLENDER_DOWNLOAD_URL,
    CHUNK_SIZE,
    DOWNLOAD_TIMEOUT_SECONDS,
)


class BlenderProvisioningError(Exception):
    """Error al aprovisionar Blender."""


def _blender_archive_name() -> str:
    return BLENDER_DOWNLOAD_URL.rstrip("/").split("/")[-1]


def get_blender_path(cache_dir: Optional[Path] = None) -> Path:
    """Descarga (o copia desde cache) y extrae Blender, devuelve ruta al binario.

    Args:
        cache_dir: Directorio en Drive donde cachear el .tar.xz.
                   Si no se provee, se descarga directamente.

    Returns:
        Path al ejecutable de Blender.

    Raises:
        BlenderProvisioningError: si falla la descarga, extraccion o el binario no existe.
    """
    tmp_dir = Path("/content/blender_install")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tar_path = tmp_dir / _blender_archive_name()

    # 1. Obtener el .tar.xz
    if cache_dir is not None:
        cache_path = Path(cache_dir) / _blender_archive_name()
        if cache_path.exists():
            print(f"[blender] Copiando Blender desde cache: {cache_path}")
            shutil.copy2(str(cache_path), str(tar_path))
        else:
            print(f"[blender] Descargando Blender desde {BLENDER_DOWNLOAD_URL}")
            _download_file(BLENDER_DOWNLOAD_URL, tar_path)
            # Copiar a cache para futuras sesiones
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(tar_path), str(cache_path))
            print(f"[blender] Cacheado en: {cache_path}")
    else:
        print(f"[blender] Descargando Blender desde {BLENDER_DOWNLOAD_URL}")
        _download_file(BLENDER_DOWNLOAD_URL, tar_path)

    # 2. Extraer
    extract_dir = tmp_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(str(extract_dir))
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"[blender] Extrayendo {tar_path.name}...")
    with tarfile.open(str(tar_path), "r:xz") as tar:
        tar.extractall(path=str(extract_dir))

    # 3. Localizar binario
    blender_bin = _find_blender_binary(extract_dir)
    if not blender_bin:
        msg = f"No se encontro el binario de Blender en {extract_dir}"
        raise BlenderProvisioningError(msg)

    os.chmod(str(blender_bin), 0o755)
    print(f"[blender] Binario listo: {blender_bin}")
    return blender_bin


def _download_file(url: str, dest: Path) -> None:
    """Descarga un archivo con soporte para archivos grandes."""
    try:
        resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Error al descargar {url}: {exc}"
        raise BlenderProvisioningError(msg) from exc

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    if not dest.exists() or dest.stat().st_size == 0:
        msg = f"Archivo descargado vacio o no existe: {dest}"
        raise BlenderProvisioningError(msg)


def _find_blender_binary(extract_dir: Path) -> Optional[Path]:
    """Busca el binario 'blender' dentro del directorio extraido."""
    # Buscar por la ruta relativa conocida
    candidate = extract_dir / BLENDER_BINARY_RELATIVE
    if candidate.exists():
        return candidate

    # Fallback: buscar recursivamente
    for root, _dirs, files in os.walk(str(extract_dir)):
        for fname in files:
            if fname == "blender" and not os.access(
                os.path.join(root, fname), os.X_OK
            ):
                full = Path(root) / fname
                return full
    return None


def verify_blender_version(blender_path: Path) -> str:
    """Ejecuta 'blender --version' y devuelve la salida.

    Raises:
        BlenderProvisioningError: si no se puede ejecutar.
    """
    try:
        result = subprocess.run(
            [str(blender_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        msg = f"Error al verificar version de Blender: {exc}"
        raise BlenderProvisioningError(msg) from exc
