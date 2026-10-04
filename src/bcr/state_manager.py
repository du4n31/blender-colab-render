"""Manage render checkpoints for resuming interrupted jobs.

The state file is stored in Drive (not on local disk) so it persists
between Colab sessions.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bcr.config import STATE_DIR_NAME, STATE_FILE_NAME, extract_frame_number


class RenderState:
    """Serializable state for a render job."""

    def __init__(
        self,
        last_frame: int = 0,
        total_frames: int = 0,
        timestamp: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.last_frame = last_frame
        self.total_frames = total_frames
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.session_id = session_id or f"ses_{int(time.time())}"

    @classmethod
    def from_dict(cls, data: dict) -> "RenderState":
        return cls(
            last_frame=data.get("last_frame", 0),
            total_frames=data.get("total_frames", 0),
            timestamp=data.get("timestamp"),
            session_id=data.get("session_id"),
        )

    def to_dict(self) -> dict:
        return {
            "last_frame": self.last_frame,
            "total_frames": self.total_frames,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }


def _state_path(drive_path: Path) -> Path:
    """Return the full path to the state file inside Drive."""
    return drive_path / STATE_DIR_NAME / STATE_FILE_NAME


def save_state(
    drive_path: Path, last_frame: int, total_frames: int, backend=None
) -> RenderState:
    """Save render state to Drive, creating the state directory if needed.

    Args:
        drive_path: Drive output path, or the output folder ID when a backend
            is supplied (see drive_backend.py).
        last_frame: Last completed frame.
        total_frames: Total number of frames in the job.
        backend: Optional backend such as ServiceAccountDriveBackend for API
            persistence instead of the mounted filesystem.

    Returns:
        The saved RenderState object.
    """
    if backend is not None:
        return backend.save_state(drive_path, last_frame, total_frames)

    state = RenderState(
        last_frame=last_frame,
        total_frames=total_frames,
    )
    path = _state_path(drive_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)

    return state


def load_state(drive_path: Path, total_frames: int, backend=None) -> int:
    """Load the last confirmed frame from the state file.

    Args:
        drive_path: Drive output path, or folder ID when a backend is supplied.
        total_frames: Expected number of frames for this job.
        backend: Optional backend for reading state through the Drive API.

    Returns:
        The last completed frame (0 when no prior state exists). A checkpoint
        from a job with a different frame count is ignored.
    """
    if backend is not None:
        return backend.load_state(drive_path, total_frames)

    path = _state_path(drive_path)

    if not path.exists():
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = RenderState.from_dict(data)

        # Ignore checkpoints from jobs with a different frame count.
        if state.total_frames != total_frames:
            return 0

        return max(0, state.last_frame)
    except (json.JSONDecodeError, OSError):
        return 0


def reconcile_with_files(drive_path: Path, state_last_frame: int, backend=None, frame_start: int = 1) -> int:
    """Return the last contiguous frame confirmed by stored image files.

    state_last_frame is retained for API compatibility, but the files are
    authoritative because checkpoints can be stale or ahead of durable output.
    The sentinel frame_start - 1 means no contiguous frame is present.
    """
    if backend is not None:
        frames_on_disk = backend.list_frame_numbers(drive_path)
    else:
        frames_on_disk = _list_frame_numbers(drive_path)

    ordered = sorted(set(frames_on_disk))
    if not ordered:
        return frame_start - 1

    # Never skip a missing frame after a partially completed parallel upload.
    contiguous_last = frame_start - 1
    for frame_number in ordered:
        if frame_number < frame_start:
            continue
        if frame_number != contiguous_last + 1:
            break
        contiguous_last = frame_number
    # Actual image files are authoritative; a missing or stale checkpoint must not disable resume.
    return contiguous_last

def _list_frame_numbers(drive_path: Path) -> list[int]:
    """Find frame numbers in rendered images, including compositor subfolders."""
    if not drive_path.exists():
        return []

    image_extensions = {".png", ".exr", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
    frames: set[int] = set()
    for root, _dirs, files in os.walk(str(drive_path)):
        for entry in files:
            if Path(entry).suffix.lower() not in image_extensions:
                continue
            frame_number = extract_frame_number(entry)
            if frame_number is not None:
                frames.add(frame_number)
    return sorted(frames)
