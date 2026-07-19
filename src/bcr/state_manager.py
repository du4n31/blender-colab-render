"""Gestion del archivo de estado para reanudacion de renders interrumpidos.

El archivo de estado se guarda en Drive (no en disco local) para que sobreviva
entre sesiones de Colab.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bcr.config import STATE_DIR_NAME, STATE_FILE_NAME


class RenderState:
    """Estado serializable de un trabajo de render."""

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
    """Ruta completa al archivo de estado dentro de Drive."""
    return drive_path / STATE_DIR_NAME / STATE_FILE_NAME


def save_state(drive_path: Path, last_frame: int, total_frames: int) -> RenderState:
    """Guarda el estado del render en Drive.

    Crea el directorio de estado si no existe.

    Args:
        drive_path: Ruta base de salida en Drive.
        last_frame: Ultimo frame completado.
        total_frames: Total de frames del trabajo.

    Returns:
        El objeto RenderState guardado.
    """
    state = RenderState(
        last_frame=last_frame,
        total_frames=total_frames,
    )
    path = _state_path(drive_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2)

    return state


def load_state(drive_path: Path, total_frames: int) -> int:
    """Carga el ultimo frame confirmado desde el archivo de estado.

    Returns:
        El ultimo frame completado (0 si no hay estado previo).
        Si total_frames cambio (nuevo trabajo con distinta duracion),
        se ignora el estado previo.
    """
    path = _state_path(drive_path)

    if not path.exists():
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        state = RenderState.from_dict(data)

        # Si el total de frames cambio, el estado previo no es valido
        if state.total_frames != total_frames:
            return 0

        return max(0, state.last_frame)
    except (json.JSONDecodeError, OSError):
        return 0


def reconcile_with_files(drive_path: Path, state_last_frame: int) -> int:
    """Reconcilia el ultimo frame contra los archivos realmente presentes en Drive.

    Usa el valor mas conservador (menor) entre el estado y los archivos
    fisicos, por si el archivo de estado quedo desactualizado por una
    caida a mitad de escritura.

    Args:
        drive_path: Ruta de salida en Drive.
        state_last_frame: Ultimo frame segun el archivo de estado.

    Returns:
        El ultimo frame confirmado (0 si no hay frames).
    """
    frames_on_disk = _list_frame_numbers(drive_path)

    if not frames_on_disk:
        return 0

    max_on_disk = max(frames_on_disk)
    return min(state_last_frame, max_on_disk)


def _list_frame_numbers(drive_path: Path) -> list[int]:
    """Lista los numeros de frame de archivos frame_NNNNNN.* en drive_path.

    Busca recursivamente en subdirectorios (para frames organizados
    por nodo File Output). Soporta .png y .exr.
    """
    if not drive_path.exists():
        return []

    frames: list[int] = []
    for root, _dirs, files in os.walk(str(drive_path)):
        for entry in files:
            if entry.startswith("frame_") and (
                entry.endswith(".png") or entry.endswith(".exr")
            ):
                base = entry.replace(".png", "").replace(".exr", "")
                parts = base.split("_")
                if len(parts) >= 2:
                    num_part = parts[-1]
                    try:
                        frames.append(int(num_part))
                    except ValueError:
                        continue
    return sorted(frames)
