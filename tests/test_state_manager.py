"""Pruebas para state_manager.py."""

import json
from pathlib import Path
from unittest.mock import Mock

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
        """Archivos que no son frame_* se ignoran."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "frame_000003.png").touch()
        (tmp_drive_dir / "README.txt").touch()
        (tmp_drive_dir / "output.exr").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 3

    def test_exr_files_detected(self, tmp_drive_dir: Path):
        """Archivos .exr con nombre frame_* son detectados."""
        (tmp_drive_dir / "frame_000001.exr").touch()
        (tmp_drive_dir / "frame_000002.exr").touch()
        (tmp_drive_dir / "log.txt").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 2

    def test_frames_in_subdirectories(self, tmp_drive_dir: Path):
        """Frames en subdirectorios (organizados por nodo) son detectados."""
        subdir = tmp_drive_dir / "Temp"
        subdir.mkdir()
        (subdir / "frame_000001.exr").touch()
        (subdir / "frame_000002.exr").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 2


class TestBackendDelegation:
    """Cuando se pasa un backend, se delega en el en vez de usar el filesystem."""

    def test_save_state_delegates_to_backend(self):
        backend = Mock()
        backend.save_state.return_value = RenderState(last_frame=3, total_frames=10)
        result = save_state("folder_id_123", 3, 10, backend=backend)
        backend.save_state.assert_called_once_with("folder_id_123", 3, 10)
        assert result.last_frame == 3

    def test_load_state_delegates_to_backend(self):
        backend = Mock()
        backend.load_state.return_value = 7
        result = load_state("folder_id_123", 10, backend=backend)
        backend.load_state.assert_called_once_with("folder_id_123", 10)
        assert result == 7

    def test_reconcile_with_files_delegates_to_backend(self):
        backend = Mock()
        backend.list_frame_numbers.return_value = [1, 2, 3]
        result = reconcile_with_files("folder_id_123", state_last_frame=5, backend=backend)
        backend.list_frame_numbers.assert_called_once_with("folder_id_123")
        assert result == 3

    def test_reconcile_with_files_backend_empty_returns_zero(self):
        backend = Mock()
        backend.list_frame_numbers.return_value = []
        result = reconcile_with_files("folder_id_123", state_last_frame=5, backend=backend)
        assert result == 0
