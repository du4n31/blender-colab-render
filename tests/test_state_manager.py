"""Tests for state_manager.py."""

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
    """Tests for the RenderState model."""

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
    """Tests for state persistence."""

    def test_save_and_load(self, tmp_drive_dir: Path):
        """Saving and loading state works correctly."""
        save_state(tmp_drive_dir, last_frame=42, total_frames=250)
        result = load_state(tmp_drive_dir, total_frames=250)
        assert result == 42

    def test_load_no_state_file(self, tmp_drive_dir: Path):
        """Return 0 when no state file exists."""
        result = load_state(tmp_drive_dir, total_frames=100)
        assert result == 0

    def test_load_different_total_frames(self, tmp_drive_dir: Path):
        """Ignore the previous checkpoint when total_frames changes."""
        save_state(tmp_drive_dir, last_frame=30, total_frames=100)
        result = load_state(tmp_drive_dir, total_frames=200)
        assert result == 0

    def test_state_file_created(self, tmp_drive_dir: Path):
        """The state file is created at the expected path."""
        save_state(tmp_drive_dir, last_frame=1, total_frames=10)
        state_file = tmp_drive_dir / "_estado" / "render_state.json"
        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert data["last_frame"] == 1

    def test_save_multiple_times(self, tmp_drive_dir: Path):
        """Saving multiple times updates the file."""
        save_state(tmp_drive_dir, last_frame=1, total_frames=10)
        save_state(tmp_drive_dir, last_frame=5, total_frames=10)
        result = load_state(tmp_drive_dir, total_frames=10)
        assert result == 5

    def test_load_corrupted_state(self, tmp_drive_dir: Path):
        """A corrupted state file returns 0."""
        state_dir = tmp_drive_dir / "_estado"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / "render_state.json"
        state_file.write_text("not valid json")
        result = load_state(tmp_drive_dir, total_frames=100)
        assert result == 0


class TestReconcileWithFiles:
    """Tests reconciliation against actual output files."""

    def test_no_files_returns_zero(self, tmp_drive_dir: Path):
        """Return the no-frame sentinel when Drive contains no files."""
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 0

    def test_empty_output_with_frame_start_zero_returns_sentinel(self, tmp_drive_dir: Path):
        """An empty output directory must not imply that frame zero is complete."""
        result = reconcile_with_files(
            tmp_drive_dir, state_last_frame=0, frame_start=0
        )
        assert result == -1

    def test_non_default_frame_start(self, tmp_drive_dir: Path):
        """Resume reconciliation supports ranges that start above frame one."""
        (tmp_drive_dir / "frame_000010.png").touch()
        (tmp_drive_dir / "frame_000011.png").touch()
        (tmp_drive_dir / "frame_000013.png").touch()
        result = reconcile_with_files(
            tmp_drive_dir, state_last_frame=13, frame_start=10
        )
        assert result == 11

    def test_frame_zero_is_detected(self, tmp_drive_dir: Path):
        """Frame zero is a valid rendered frame when explicitly requested."""
        (tmp_drive_dir / "frame_000000.png").touch()
        result = reconcile_with_files(
            tmp_drive_dir, state_last_frame=0, frame_start=0
        )
        assert result == 0

    def test_non_image_assets_with_frame_numbers_are_ignored(self, tmp_drive_dir: Path):
        """Scene files and scripts with six-digit names are not rendered frames."""
        (tmp_drive_dir / "scene_000001.blend").touch()
        (tmp_drive_dir / "script_000002.py").touch()
        (tmp_drive_dir / "frame_000003.png").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=3)
        assert result == 0

    def test_state_ahead_of_files(self, tmp_drive_dir: Path):
        """If the checkpoint says frame 10 but files only reach frame 5, use 5."""
        for i in range(1, 6):
            (tmp_drive_dir / f"frame_{i:06d}.png").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 5

    def test_files_ahead_of_state(self, tmp_drive_dir: Path):
        """Verified contiguous files remain usable when the checkpoint is stale."""
        for i in range(1, 11):
            (tmp_drive_dir / f"frame_{i:06d}.png").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=5)
        assert result == 10

    def test_mixed_file_types(self, tmp_drive_dir: Path):
        """Compositor-style names are recognized and frame gaps are not skipped."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "frame_000003.png").touch()
        (tmp_drive_dir / "README.txt").touch()
        (tmp_drive_dir / "output.exr").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 1

    def test_exr_files_detected(self, tmp_drive_dir: Path):
        """Detect .exr files whose names use the frame_* pattern."""
        (tmp_drive_dir / "frame_000001.exr").touch()
        (tmp_drive_dir / "frame_000002.exr").touch()
        (tmp_drive_dir / "log.txt").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 2

    def test_frames_in_subdirectories(self, tmp_drive_dir: Path):
        """Detect frames in subdirectories organized by compositor node."""
        subdir = tmp_drive_dir / "Temp"
        subdir.mkdir()
        (subdir / "frame_000001.exr").touch()
        (subdir / "frame_000002.exr").touch()
        result = reconcile_with_files(tmp_drive_dir, state_last_frame=10)
        assert result == 2


class TestBackendDelegation:
    """Delegate to the supplied backend instead of using the local filesystem."""

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
