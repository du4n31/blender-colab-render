"""Project configuration and constants."""

import re
from pathlib import Path
from typing import Optional

# --- Blender ---
BLENDER_VERSION = "5.2.0"
BLENDER_DEFAULT_VERSION = BLENDER_VERSION

# Base URL for downloading the version and file listings
BLENDER_RELEASE_BASE = "https://download.blender.org/release/"


def build_blender_download_url(version: str) -> str:
    """Build the download URL for a specific Blender version.

    Args:
        version: Semantic version (e.g. "5.2.0").

    Returns:
        Full URL to the Linux x64 .tar.xz archive.
    """
    major_minor = ".".join(version.split(".")[:2])
    return (
        f"{BLENDER_RELEASE_BASE}Blender{major_minor}/"
        f"blender-{version}-linux-x64.tar.xz"
    )


BLENDER_DOWNLOAD_URL = build_blender_download_url(BLENDER_VERSION)
BLENDER_DIR_NAME = f"blender-{BLENDER_VERSION}-linux-x64"

# Binary path inside the .tar.xz archive (moved in Blender >= 4.0)
BLENDER_BINARY_RELATIVE = Path(f"blender-{BLENDER_VERSION}-linux-x64/blender")

# --- Directories ---
DRIVE_MOUNT_POINT = Path("/content/drive")
RENDER_TMP_DIR = Path("/content/render_tmp")
PROJECT_DIR_IN_DRIVE = Path("MyDrive/BlenderColabRender")
STATE_DIR_NAME = "_estado"
STATE_FILE_NAME = "render_state.json"

# Pattern for rendered frames (Blender replaces ##### with the frame number)
RENDER_OUTPUT_PATTERN = "frame_######"

# --- Uploads ---
BACKLOG_LIMIT = 5  # maximum local frames waiting for upload before pausing

# --- Download URLs ---
DOWNLOAD_TIMEOUT_SECONDS = 120
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


def extract_frame_number(name: str) -> Optional[int]:
    """Extrae un numero de frame de 6 digitos de un nombre de archivo.

    Busca exactamente 6 digitos consecutivos que no esten pegados a otros
    digitos (regex: lookbehind/lookahead para digitos). El numero de frame
    puede estar en cualquier posicion del nombre. Si hay multiples bloques
    de 6 digitos, toma el ULTIMO (el que agrega _###### al final).

    Examples:
        >>> extract_frame_number("Result_000001.exr")
        1
        >>> extract_frame_number("File_Output_001_000001.exr")
        1
        >>> extract_frame_number("frame_00001.png")   # 5 digitos
        None
        >>> extract_frame_number("file_name0000001.exr")  # 7 digitos
        None
        >>> extract_frame_number("file_name1frane.exr")   # 1 digito
        None
        >>> extract_frame_number("File_Output_000023_000001.exr")  # ultimo bloque
        1
    """
    import re

    matches = list(re.finditer(r"(?<!\d)(\d{6})(?!\d)", name))
    if not matches:
        return None
    # Tomar el ULTIMO bloque de 6 digitos (el que agrega _######)
    return int(matches[-1].group(1))


def validate_frame_range(frame_start: int, frame_end: int) -> tuple[int, int]:
    """Valida y retorna un rango de frames [start, end] normalizado.

    Raises:
        ValueError: si el rango es invalido.
    """
    if frame_start < 0 or frame_end < 0:
        msg = f"Los frames deben ser >= 0, got start={frame_start}, end={frame_end}"
        raise ValueError(msg)
    if frame_end < frame_start:
        msg = f"frame_end ({frame_end}) debe ser >= frame_start ({frame_start})"
        raise ValueError(msg)
    if frame_end - frame_start + 1 > 1_000_000:
        msg = "Rango de frames demasiado grande (max 1_000_000)"
        raise ValueError(msg)
    return frame_start, frame_end


def validate_drive_path(path: str) -> Path:
    """Normaliza y valida una ruta dentro de /content/drive.

    Raises:
        ValueError: si la ruta no esta bajo /content/drive.
    """
    p = Path(path).resolve()
    drive_root = DRIVE_MOUNT_POINT.resolve()
    try:
        p.relative_to(drive_root)
    except ValueError:
        msg = f"La ruta debe estar dentro de {drive_root}, got {p}"
        raise ValueError(msg)
    return p


def validate_url(url: str) -> bool:
    """Valida formato basico de URL."""
    pattern = r"^https?://[^\s/$.?#].[^\s]*$"
    return bool(re.match(pattern, url))
