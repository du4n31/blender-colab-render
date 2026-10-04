"""Synchronize rendered frames with Google Drive.

Drive is mounted as a filesystem through google.colab.drive.mount(),
so uploading is implemented as a file copy using shutil.
"""

import os
import shutil
from pathlib import Path

from bcr.config import DRIVE_MOUNT_POINT, RENDERED_IMAGE_EXTENSIONS, extract_frame_number


class DriveSyncError(Exception):
    """Error raised while synchronizing with Drive."""


def ensure_drive_mounted() -> bool:
    """Check whether Google Drive is mounted at /content/drive.

    Returns:
        True if mounted, otherwise False.
    """
    return DRIVE_MOUNT_POINT.exists() and any(DRIVE_MOUNT_POINT.iterdir())


def ensure_output_dir(drive_path: Path) -> Path:
    """Create the Drive output directory if it does not exist.

    Args:
        drive_path: Full path inside Drive.

    Returns:
        Path to the output directory.

    Raises:
        DriveSyncError: if the path is outside Drive.
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
    """Copy a rendered frame from the runtime to Drive.

    If preserve_name=True (default), preserve the original filename
    para evitar colisiones cuando hay multiples salidas por frame.
    If preserve_name=False, use the frame_%06d.ext pattern for compatibility.

    Args:
        local_path: Local path to the rendered frame.
        drive_output_dir: Drive output directory.
        frame_num: Numero de frame (para naming fallback).
        subdir: Subdirectorio opcional (ej: nombre del nodo).
        preserve_name: If True, preserve the original filename.

    Returns:
        Path to the file in Drive.

    Raises:
        DriveSyncError: if the local file does not exist or copying fails.
    """
    local_path = Path(local_path)
    drive_output_dir = Path(drive_output_dir)

    if not local_path.exists():
        msg = f"Local file does not exist: {local_path}"
        raise DriveSyncError(msg)

    # Determinar nombre de destino
    if preserve_name:
        # Usar nombre original para evitar colisiones
        dest_filename = local_path.name
    else:
        # Fallback: frame_NNNNNN.ext pattern
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
        msg = f"Failed to copy to Drive: {exc}"
        raise DriveSyncError(msg) from exc

    return dest_path


def remove_local(local_path: Path) -> None:
    """Delete a local file from the runtime.

    Args:
        local_path: Path to the file to delete.

    Raises:
        DriveSyncError: if the file cannot be deleted.
    """
    local_path = Path(local_path)
    if not local_path.exists():
        return
    try:
        os.remove(str(local_path))
    except OSError as exc:
        msg = f"Failed to delete local file {local_path}: {exc}"
        raise DriveSyncError(msg) from exc


def list_frames_in_drive(drive_output_dir: Path) -> list[int]:
    """Lista los numeros de frame subidos a Drive.

    Recursively search subdirectories for files whose names contain
    exactly six consecutive digits (the frame number). It does not assume
    un prefijo especifico como "frame_".

    Args:
        drive_output_dir: Drive output directory.

    Returns:
        Sorted list of uploaded frame numbers (without duplicates).
    """
    drive_output_dir = Path(drive_output_dir)
    if not drive_output_dir.exists():
        return []

    frames: list[int] = []
    for root, _dirs, files in os.walk(str(drive_output_dir)):
        for entry in files:
            if Path(entry).suffix.lower() not in RENDERED_IMAGE_EXTENSIONS:
                continue
            frame_num = extract_frame_number(entry)
            if frame_num is not None:
                frames.append(frame_num)
    return sorted(set(frames))


def _validate_drive_path(path: Path) -> None:
    """Validate that the path is inside /content/drive."""
    try:
        path.resolve().relative_to(DRIVE_MOUNT_POINT.resolve())
    except ValueError:
        msg = f"Path must be inside {DRIVE_MOUNT_POINT}, got {path}"
        raise DriveSyncError(msg) from None