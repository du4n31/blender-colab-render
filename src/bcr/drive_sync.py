"""Sincronizacion de frames renderizados con Google Drive.

Drive se monta como sistema de archivos via google.colab.drive.mount(),
por lo que 'subir' es una copia de archivo con shutil.
"""

import os
import shutil
from pathlib import Path

from bcr.config import DRIVE_MOUNT_POINT, extract_frame_number


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
    preserve_name: bool = True,
) -> Path:
    """Copia un frame renderizado desde la instancia a Drive.

    Si preserve_name=True (default), usa el nombre original del archivo
    para evitar colisiones cuando hay multiples salidas por frame.
    Si preserve_name=False, usa el patron frame_%06d.ext (compatibilidad).

    Args:
        local_path: Ruta al archivo local del frame renderizado.
        drive_output_dir: Directorio de salida en Drive.
        frame_num: Numero de frame (para naming fallback).
        subdir: Subdirectorio opcional (ej: nombre del nodo).
        preserve_name: Si True, preserva el nombre original del archivo.

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

    # Determinar nombre de destino
    if preserve_name:
        # Usar nombre original para evitar colisiones
        dest_filename = local_path.name
    else:
        # Fallback: patron frame_NNNNNN.ext
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
    """Lista los numeros de frame subidos a Drive.

    Busca recursivamente en subdirectorios archivos cuyo nombre contenga
    exactamente 6 digitos consecutivos (el numero de frame). No asume
    un prefijo especifico como "frame_".

    Args:
        drive_output_dir: Directorio de salida en Drive.

    Returns:
        Lista ordenada de numeros de frame ya subidos (sin duplicados).
    """
    drive_output_dir = Path(drive_output_dir)
    if not drive_output_dir.exists():
        return []

    frames: list[int] = []
    for root, _dirs, files in os.walk(str(drive_output_dir)):
        for entry in files:
            frame_num = extract_frame_number(entry)
            if frame_num is not None:
                frames.append(frame_num)
    return sorted(set(frames))


def _validate_drive_path(path: Path) -> None:
    """Valida que la ruta este dentro de /content/drive."""
    try:
        path.resolve().relative_to(DRIVE_MOUNT_POINT.resolve())
    except ValueError:
        msg = f"La ruta debe estar dentro de {DRIVE_MOUNT_POINT}, got {path}"
        raise DriveSyncError(msg) from None