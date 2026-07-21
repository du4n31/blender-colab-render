"""Aprovisionamiento del binario portable de Blender.

Descarga el .tar.xz desde download.blender.org y lo extrae.
Soporta cache en Drive para no re-descargar en cada sesion de Colab.
"""

import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

import requests

from bcr.config import (
    BLENDER_BINARY_RELATIVE,
    BLENDER_DEFAULT_VERSION,
    BLENDER_RELEASE_BASE,
    CHUNK_SIZE,
    DOWNLOAD_TIMEOUT_SECONDS,
    build_blender_download_url,
)


class BlenderProvisioningError(Exception):
    """Error al aprovisionar Blender."""


def get_blender_path(
    version: str = BLENDER_DEFAULT_VERSION,
    cache_dir: Optional[Path] = None,
) -> Path:
    """Descarga (o copia desde cache) y extrae Blender, devuelve ruta al binario.

    Args:
        version: Version semantica de Blender (ej. "5.2.0").
        cache_dir: Directorio en Drive donde cachear el .tar.xz.
                   Si no se provee, se descarga directamente.

    Returns:
        Path al ejecutable de Blender.

    Raises:
        BlenderProvisioningError: si falla la descarga, extraccion o el binario no existe.
    """
    download_url = build_blender_download_url(version)
    archive_name = f"blender-{version}-linux-x64.tar.xz"
    tmp_dir = Path("/content/blender_install")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tar_path = tmp_dir / archive_name

    # 1. Obtener el .tar.xz
    if cache_dir is not None:
        cache_path = Path(cache_dir) / archive_name
        if cache_path.exists():
            print(f"[blender] Copiando Blender desde cache: {cache_path}")
            shutil.copy2(str(cache_path), str(tar_path))
        else:
            print(f"[blender] Descargando Blender desde {download_url}")
            _download_file(download_url, tar_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(tar_path), str(cache_path))
            print(f"[blender] Cacheado en: {cache_path}")
    else:
        print(f"[blender] Descargando Blender desde {download_url}")
        _download_file(download_url, tar_path)

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


def fetch_available_versions(min_major: int = 5) -> list[str]:
    """Obtiene la lista de versiones de Blender disponibles >= min_major.

    Hace GET a BLENDER_RELEASE_BASE, parsea el HTML autoindex en busca de
    carpetas con patron ``BlenderX.Y/``, filtra major >= min_major,
    y para cada carpeta busca el .tar.xz de Linux x64 para conocer
    el parche exacto.

    Returns:
        Lista de versiones semanticas ordenadas descendente (ej. ["5.3.0", "5.2.0", ...]).

    Raises:
        BlenderProvisioningError: si falla la conexion y no se pudo obtener nada.
    """
    try:
        resp = requests.get(BLENDER_RELEASE_BASE, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise BlenderProvisioningError(
            f"No se pudo obtener el listado de versiones: {exc}"
        ) from exc

    versions: list[str] = []
    for match in re.finditer(
        r'<a href="Blender(\d+)\.(\d+)/"', resp.text
    ):
        major, minor = int(match.group(1)), int(match.group(2))
        if major < min_major:
            continue

        folder_url = f"{BLENDER_RELEASE_BASE}Blender{major}.{minor}/"
        try:
            folder_resp = requests.get(folder_url, timeout=30)
            folder_resp.raise_for_status()
        except requests.RequestException:
            continue

        for vmatch in re.finditer(
            r"blender-(\d+\.\d+\.\d+)-linux-x64\.tar\.xz",
            folder_resp.text,
        ):
            versions.append(vmatch.group(1))

    if not versions:
        raise BlenderProvisioningError(
            "No se encontraron versiones de Blender disponibles"
        )

    versions.sort(
        key=lambda v: [int(x) for x in v.split(".")], reverse=True
    )
    return versions


def resolve_blender_version(preferred: Optional[str] = None) -> str:
    """Resuelve la version de Blender a usar.

    Si se provee ``preferred``, lo intenta primero (puede venir del selector
    UI del notebook). Si la consulta en vivo falla, retorna la version
    preferida o la default con una advertencia.

    Returns:
        Version semantica (ej. "5.2.0").
    """
    try:
        available = fetch_available_versions()
    except BlenderProvisioningError:
        print(
            "[blender] WARNING: No se pudo obtener lista de versiones en "
            f"vivo, usando version por defecto"
        )
        return preferred or BLENDER_DEFAULT_VERSION

    if preferred is not None:
        return preferred

    return available[0]
