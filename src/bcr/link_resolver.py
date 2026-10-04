"""Resolve public links from supported providers to direct-download URLs."""

import re
import urllib.parse
from typing import Optional

import requests


class LinkResolutionError(Exception):
    """Error raised while resolving a download link."""


def resolve_download_url(url: str) -> str:
    """Convert a public link into its actual download URL.

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
    # Direct link or unknown provider
    if _is_direct_link(url):
        return url
    msg = f"Could not resolve link: unsupported provider ({domain})"
    raise LinkResolutionError(msg)


def _is_direct_link(url: str) -> bool:
    """Basic heuristic for links that likely serve the file directly."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    # Extensiones de archivo tipicas
    direct_extensions = (
        ".blend", ".zip", ".tar.gz", ".tar.xz", ".7z", ".rar",
        ".png", ".jpg", ".jpeg", ".exr", ".tga", ".bmp",
    )
    return any(path.endswith(ext) for ext in direct_extensions)


def _resolve_dropbox(url: str) -> str:
    """Convert a Dropbox link to a direct download URL (?dl=0 -> ?dl=1)."""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    # Forzar dl=1
    query["dl"] = ["1"]
    new_query = urllib.parse.urlencode(query, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def _resolve_google_drive(url: str) -> str:
    """Resolve a Google Drive link to a direct download URL.

    Use gdown.parse_url() to extract the file_id, then build the URL
    for direct download. The actual download is handled by requests
    (con el parametro de confirmacion para archivos grandes).
    """
    try:
        import gdown  # type: ignore[import-untyped]
    except ImportError:
        msg = (
            "gdown no esta instalado. Instalalo con: pip install gdown"
        )
        raise LinkResolutionError(msg) from None

    # Extract file_id using gdown or a regular expression
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
        msg = f"Could not extract file_id from the Google Drive URL: {url}"
        raise LinkResolutionError(msg)

    # Direct-download URL with confirmation
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
    """Extract the actual download URL from MediaFire's HTML page.

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
        msg = f"Failed to download pagina de MediaFire: {exc}"
        raise LinkResolutionError(msg) from exc

    html = resp.text

    # Find the direct-download link in the HTML
    # pattern 1: downloadButton[href]
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

    # pattern 2: download_link en variable JS o data-*
    match = re.search(
        r'data-download-url=["\']([^"\']+)["\']',
        html,
    )
    if match:
        return match.group(1).replace("\\/", "/")

    # pattern 3: kNO = "..."
    match = re.search(r'kNO\s*=\s*["\']([^"\']+)["\']', html)
    if match:
        return match.group(1)

    msg = "Could not extract the MediaFire download URL"
    raise LinkResolutionError(msg)
