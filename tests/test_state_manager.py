"""Pruebas para state_manager.py."""

import json
from pathlib import Path

import pytest

from bcr.state_manager import (
    RenderState,
    load_state,
    reconcile_with_files,
    save_state,
)


class TestRenderState:
    """Pruebas del modelo RenderState."""

    def test_to_dict(self):
        state = RenderState(last_frame=5, total_frames=100)
        d = state.to_dict()
        assert d["last_frame"] == 5
        assert d["total_frames"] == 100
        assert "timestamp" in d
        assert "session_id" in d

    def test_from_dict(self):
        d = {"last_frame": 10, "total_frames": 200, "timestamp": "2026-01-01T00:00:00"}
        state = RenderState.from_dict(d)
        assert state.last_frame == 10
        assert state.total_frames == 200

    def test_from_dict_empty(self):
        state = RenderState.from_dict({})
        assert state.last_frame == 0
        assert state.total_frames == 0


class TestSaveLoadState:
    """Pruebas de persistencia del estado."""

    def test_save_and_load(self, tmp_drive_dir: Path):
        """Guardar y cargar estado funciona correctamente."""
        save_state(tmp_drive_dir, last_frame=42, total_frames=250)
        result = load_state(tmp_drive_dir, total_frames=250)
        assert result == 42

    def test_load_no_state_file(self, tmp_drive_dir: Path):
        """Sin archivo de estado, devuelve 0."""
        result = load_state(tmp_drive_dir, total_frames=100)
        assert result == 0

    def test_load_different_total_frames(self, tmp_drive_dir: Path):
        """Si total_frames cambio, se ignora el estado previo."""
        save_state(tmp_drive_dir, last_frame=30, total_frames=100)
        result = load_state(tmp_drive_dir, total_frames=200)
        assert result == 0

    def test_state_file_created(self, tmp_drive_dir: Path):
        """El archivo de estado se crea en la ruta correcta."""
        save_state(tmp_drive_dir, last_frame=1, total_frames=10)
        state_file = tmp_drive_dir / "_estado" / "render_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["last_frame"] == 1

    def test_save_multiple_times(self, tmp_drive_dir: Path):
        """Guardar multiples veces actualiza el archivo."""
        save_state(tmp_drive_dir, last_frame=1, total_frames=10)
        save_state(tmp_drive_dir, last_frame=5, total_frames=10)
        result = load_state(tmp_drive_dir, total_frames=10)
        assert result == 5

    def test_load_corrupted_state(self, tmp_drive_dir: Path):
        """Archivo de estado corrupto devuelve 0."""
        state_dir = tmp_drive_dir / "_estado"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "render_state.json"
        state_file.write_text("not valid json")
        result = load_state(tmp_drive_dir, total_frames=100)
        assert result == 0


class TestReconcileWithFiles:
    """Pruebas de reconciliacion contra archivos reales."""

    def test_no_files_returns_zero(self, tmp_drive_dir: Path):
        """Sin archivos en Drive, devuelve 0."""
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 0

    def test_state_ahead_of_files(self, tmp_drive_dir: Path):
        """Si el estado dice frame 10 pero solo hay hasta 5, usa 5."""
        for i in range(1, 6):
            (tmp_drive_dir / f"frame_{i:06d}.png").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 5

    def test_files_ahead_of_state(self, tmp_drive_dir: Path):
        """Si hay archivos hasta 10 pero el estado dice 5, usa 5."""
        for i in range(1, 11):
            (tmp_drive_dir / f"frame_{i:06d}.png").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=5)
        assert result == 5

    def test_mixed_file_types(self, tmp_drive_dir: Path):
        """Archivos que no son frame_*.png se ignoran."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "frame_000003.png").touch()
        (tmp_drive_dir / "README.txt").touch()
        (tmp_drive_dir / "output.exr").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 3

    def test_no_png_files(self, tmp_drive_dir: Path):
        """Sin archivos .png, devuelve 0 incluso si hay otros archivos."""
        (tmp_drive_dir / "output.exr").touch()
        (tmp_drive_dir / "log.txt").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=5)
        assert result == 0
