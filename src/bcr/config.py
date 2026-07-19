"""Configuracion y constantes del proyecto."""

import re
from pathlib import Path

# --- Blender ---
BLENDER_VERSION = "5.2.0"
BLENDER_DOWNLOAD_URL = (
    f"https://download.blender.org/release/Blender{BLENDER_VERSION[:3]}/"
    f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"
)
BLENDER_DIR_NAME = f"blender-{BLENDER_VERSION}-linux-x64"

# El binario dentro del .tar.xz (Blender >= 4.0 lo movio de sitio)
BLENDER_BINARY_RELATIVE = Path(f"blender-{BLENDER_VERSION}-linux-x64/blender")

# --- Directorios ---
DRIVE_MOUNT_POINT = Path("/content/drive")
RENDER_TMP_DIR = Path("/content/render_tmp")
PROJECT_DIR_IN_DRIVE = Path("MyDrive/BlenderColabRender")
STATE_DIR_NAME = "_estado"
STATE_FILE_NAME = "render_state.json"

# Patron para los frames renderizados (Blender reemplaza ##### por el numero)
RENDER_OUTPUT_PATTERN = "frame_#####"

# --- Subida ---
BACKLOG_LIMIT = 5  # max frames locales pendientes de subir antes de pausar

# --- URLs de descarga ---
DOWNLOAD_TIMEOUT_SECONDS = 120
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


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
