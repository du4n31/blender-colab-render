"""Sincronizacion de frames renderizados con Google Drive.

Drive se monta como sistema de archivos via google.colab.drive.mount(),
por lo que 'subir' es una copia de archivo con shutil.
"""

import os
import shutil
from pathlib import Path

from bcr.config import DRIVE_MOUNT_POINT


class DriveSyncError(Exception):
    """Error al sincronizar con Drive."""


def ensure_drive_mounted() -> bool:
    """Verifica que Google Drive esta montado en /content/drive.

    Returns:
        True si esta montado, False en caso contrario.
    """
    return DRIVE_MOUNT_POINT.exists() and any(DRIVE_MOUNT_POINT.iterdir())


def ensure_output_dir(drive_path: Path) -> Path:
    """Crea el directorio de salida en Drive si no existe.

    Args:
        drive_path: Ruta completa dentro de Drive.

    Returns:
        Path al directorio de salida.

    Raises:
        DriveSyncError: si la ruta no esta bajo Drive.
    """
    drive_path = Path(drive_path)
    _validate_drive_path(drive_path)
    drive_path.mkdir(parents=True, exist_ok=True)
    return drive_path


def upload_frame(
    local_path: Path,
    drive_output_dir: Path,
    frame_num: int,
    subdir: str = "",
) -> Path:
    """Copia un frame renderizado desde la instancia a Drive.

    El archivo se nombra como frame_%06d.png en el directorio de salida.
    Si se especifica subdir, se crea un subdirectorio para organizar
    multiples salidas (ej: nodos File Output).

    Args:
        local_path: Ruta al archivo local del frame renderizado.
        drive_output_dir: Directorio de salida en Drive.
        frame_num: Numero de frame (para nombrar el archivo).
        subdir: Subdirectorio opcional (ej: nombre del nodo).

    Returns:
        Path al archivo en Drive.

    Raises:
        DriveSyncError: si el archivo local no existe o falla la copia.
    """
    local_path = Path(local_path)
    drive_output_dir = Path(drive_output_dir)

    if not local_path.exists():
        msg = f"El archivo local no existe: {local_path}"
        raise DriveSyncError(msg)

    # Preservar la extension original del archivo (.exr, .png, etc.)
    suffix = local_path.suffix if local_path.suffix else ".png"
    dest_filename = f"frame_{frame_num:06d}{suffix}"

    if subdir:
        dest_dir = drive_output_dir / subdir
    else:
        dest_dir = drive_output_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / dest_filename

    try:
        shutil.copy2(str(local_path), str(dest_path))
    except OSError as exc:
        msg = f"Error al copiar a Drive: {exc}"
        raise DriveSyncError(msg) from exc

    return dest_path


def remove_local(local_path: Path) -> None:
    """Borra un archivo local de la instancia.

    Args:
        local_path: Ruta al archivo a borrar.

    Raises:
        DriveSyncError: si no se puede borrar.
    """
    local_path = Path(local_path)
    if not local_path.exists():
        return
    try:
        os.remove(str(local_path))
    except OSError as exc:
        msg = f"Error al borrar archivo local {local_path}: {exc}"
        raise DriveSyncError(msg) from exc


def list_frames_in_drive(drive_output_dir: Path) -> list[int]:
    """Lista los numeros de frame de archivos frame_%06d.* en Drive.

    Busca recursivamente en subdirectorios para encontrar frames
    organizados por nodo (File Output remapeados).

    Args:
        drive_output_dir: Directorio de salida en Drive.

    Returns:
        Lista ordenada de numeros de frame ya subidos.
    """
    drive_output_dir = Path(drive_output_dir)
    if not drive_output_dir.exists():
        return []

    frames: list[int] = []
    for root, _dirs, files in os.walk(str(drive_output_dir)):
        for entry in files:
            if entry.startswith("frame_"):
                # Extraer numero de frame (formato: frame_NNNNNN.ext)
                base = entry.replace(".png", "").replace(".exr", "")
                parts = base.split("_")
                if len(parts) >= 2:
                    num_str = parts[-1]
                    try:
                        frames.append(int(num_str))
                    except ValueError:
                        continue
    return sorted(frames)


def _validate_drive_path(path: Path) -> None:
    """Valida que la ruta este dentro de /content/drive."""
    try:
        path.resolve().relative_to(DRIVE_MOUNT_POINT.resolve())
    except ValueError:
        msg = f"La ruta debe estar dentro de {DRIVE_MOUNT_POINT}, got {path}"
        raise DriveSyncError(msg) from None
