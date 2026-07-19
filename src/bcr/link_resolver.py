"""Resuelve enlaces publicos de distintos proveedores a URLs de descarga directa."""

import re
import urllib.parse
from typing import Optional

import requests


class LinkResolutionError(Exception):
    """Error al resolver un enlace de descarga."""


def resolve_download_url(url: str) -> str:
    """Toma un enlace publico y devuelve la URL real de descarga.

    Soporta: enlaces directos, Dropbox, Google Drive, MediaFire.
    """
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()

    if "dropbox.com" in domain:
        return _resolve_dropbox(url)
    if "drive.google.com" in domain:
        return _resolve_google_drive(url)
    if "mediafire.com" in domain:
        return _resolve_mediafire(url)
    # Enlace directo o proveedor desconocido
    if _is_direct_link(url):
        return url
    msg = f"No se pudo resolver el enlace: proveedor no soportado ({domain})"
    raise LinkResolutionError(msg)


def _is_direct_link(url: str) -> bool:
    """Heuristica basica: enlaces que probablemente sirvan el archivo directamente."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    # Extensiones de archivo tipicas
    direct_extensions = (
        ".blend", ".zip", ".tar.gz", ".tar.xz", ".7z", ".rar",
        ".png", ".jpg", ".jpeg", ".exr", ".tga", ".bmp",
    )
    return any(path.endswith(ext) for ext in direct_extensions)


def _resolve_dropbox(url: str) -> str:
    """Convierte enlace de Dropbox a descarga directa (?dl=0 -> ?dl=1)."""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    # Forzar dl=1
    query["dl"] = ["1"]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def _resolve_google_drive(url: str) -> str:
    """Resuelve un enlace de Google Drive a URL de descarga directa.

    Usa gdown.parse_url() para extraer el file_id, luego construye la URL
    de descarga directa. La descarga real se maneja con requests
    (con el parametro de confirmacion para archivos grandes).
    """
    try:
        import gdown  # type: ignore[import-untyped]
    except ImportError:
        msg = (
            "gdown no esta instalado. Instalalo con: pip install gdown"
        )
        raise LinkResolutionError(msg) from None

    # Extraer file_id usando gdown o regex
    file_id = None
    try:
        parsed = gdown.parse_url(url)
        if isinstance(parsed, dict) and "id" in parsed:
            file_id = parsed["id"]
    except Exception:
        pass

    if not file_id:
        file_id = _extract_google_drive_id(url)

    if not file_id:
        msg = f"No se pudo extraer file_id de la URL de Google Drive: {url}"
        raise LinkResolutionError(msg)

    # URL de descarga directa con confirmacion
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _extract_google_drive_id(url: str) -> Optional[str]:
    """Extrae el file_id de una URL de Google Drive."""
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",  # /file/d/FILE_ID/view
        r"id=([a-zA-Z0-9_-]+)",        # ?id=FILE_ID
        r"open\?id=([a-zA-Z0-9_-]+)",  # /open?id=FILE_ID
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _resolve_mediafire(url: str) -> str:
    """Extrae la URL real de descarga desde la pagina HTML de MediaFire.

    Si la URL ya es un enlace directo (subdominio download*.mediafire.com),
    se devuelve tal cual.
    """
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()

    # Si ya es un enlace directo de MediaFire, devolverlo tal cual
    if host.startswith("download") and ".mediafire.com" in host:
        return url

    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Error al descargar pagina de MediaFire: {exc}"
        raise LinkResolutionError(msg) from exc

    html = resp.text

    # Buscar el enlace de descarga directa en el HTML
    # patron 1: downloadButton[href]
    match = re.search(
        r'<a[^>]*class="[^"]*download[^"]*"[^>]*href="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if match:
        url_str: str = match.group(1)
        if url_str.startswith("//"):
            url_str = "https:" + url_str
        return url_str

    # patron 2: download_link en variable JS o data-*
    match = re.search(
        r'data-download-url=["\']([^"\']+)["\']',
        html,
    )
    if match:
        return match.group(1).replace("\\/", "/")

    # patron 3: kNO = "..."
    match = re.search(r'kNO\s*=\s*["\']([^"\']+)["\']', html)
    if match:
        return match.group(1)

    msg = "No se pudo extraer la URL de descarga de MediaFire"
    raise LinkResolutionError(msg)
