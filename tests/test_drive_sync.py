"""Pruebas para drive_sync.py.

Validan subida de frames, organizacion por subdirectorios (nodos),
y deteccion recursiva de frames en Drive.
"""

from pathlib import Path

import pytest

from bcr.drive_sync import (
    DriveSyncError,
    list_frames_in_drive,
    remove_local,
    upload_frame,
)


class TestUploadFrame:
    """Prueba upload_frame con y sin subdirectorio."""

    def test_upload_basic_preserves_name(self, tmp_drive_dir: Path, tmp_path: Path):
        """Subida basica: archivo se copia con su nombre original."""
        src = tmp_path / "beauty_0001.exr"
        src.write_text("fake-exr")
        result = upload_frame(src, tmp_drive_dir, frame_num=1)
        # Con preserve_name=True (default), usa el nombre original
        assert result == tmp_drive_dir / "beauty_0001.exr"
        assert result.exists()

    def test_upload_with_subdir_preserves_name(self, tmp_drive_dir: Path, tmp_path: Path):
        """Subida con subdir: archivo se copia a subdirectorio con nombre original."""
        src = tmp_path / "beauty_0001.exr"
        src.write_text("fake-exr")
        result = upload_frame(src, tmp_drive_dir, frame_num=1, subdir="Temp")
        expected = tmp_drive_dir / "Temp" / "beauty_0001.exr"
        assert result == expected
        assert result.exists()

    def test_upload_multiple_subdirs_no_collision(self, tmp_drive_dir: Path, tmp_path: Path):
        """Multiples archivos mismo frame -> distintos subdirectorios, sin sobrescribir."""
        src1 = tmp_path / "beauty_0001.exr"
        src1.write_text("beauty-data")
        src2 = tmp_path / "depth_0001.exr"
        src2.write_text("depth-data")

        r1 = upload_frame(src1, tmp_drive_dir, frame_num=1, subdir="beauty")
        r2 = upload_frame(src2, tmp_drive_dir, frame_num=1, subdir="depth")

        assert r1 == tmp_drive_dir / "beauty" / "beauty_0001.exr"
        assert r2 == tmp_drive_dir / "depth" / "depth_0001.exr"
        assert r1.exists()
        assert r2.exists()
        assert r1.read_text() == "beauty-data"
        assert r2.read_text() == "depth-data"

    def test_upload_no_source_file(self, tmp_drive_dir: Path):
        """Archivo local inexistente lanza DriveSyncError."""
        fake = Path("/tmp/nonexistent_file_12345.png")
        with pytest.raises(DriveSyncError, match="no existe"):
            upload_frame(fake, tmp_drive_dir, frame_num=1)

    def test_preserves_file_extension(self, tmp_drive_dir: Path, tmp_path: Path):
        """La extension original se preserva en Drive."""
        src = tmp_path / "output.exr"
        src.write_text("exr-data")
        result = upload_frame(src, tmp_drive_dir, frame_num=42)
        assert result.suffix == ".exr"
        assert result.name == "output.exr"

    def test_fallback_frame_pattern_when_preserve_false(self, tmp_drive_dir: Path, tmp_path: Path):
        """Con preserve_name=False usa patron frame_NNNNNN.ext."""
        src = tmp_path / "output.exr"
        src.write_text("exr-data")
        result = upload_frame(src, tmp_drive_dir, frame_num=42, preserve_name=False)
        assert result.suffix == ".exr"
        assert result.name == "frame_000042.exr"

    def test_defaults_to_png_when_no_extension(self, tmp_drive_dir: Path, tmp_path: Path):
        """Archivo sin extension usa .png por defecto (solo con preserve_name=False)."""
        src = tmp_path / "output"
        src.write_text("data")
        result = upload_frame(src, tmp_drive_dir, frame_num=1, preserve_name=False)
        assert result.suffix == ".png"
        assert result.name == "frame_000001.png"


class TestRemoveLocal:
    """Prueba remove_local."""

    def test_removes_existing_file(self, tmp_path: Path):
        """Archivo existente se borra."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        remove_local(f)
        assert not f.exists()

    def test_no_error_on_missing_file(self):
        """Archivo inexistente no lanza error."""
        remove_local(Path("/tmp/this_does_not_exist_12345.txt"))


class TestListFramesInDrive:
    """Prueba list_frames_in_drive con deteccion recursiva."""

    def test_empty_directory(self, tmp_drive_dir: Path):
        """Directorio vacio devuelve lista vacia."""
        assert list_frames_in_drive(tmp_drive_dir) == []

    def test_detects_frames_in_root(self, tmp_drive_dir: Path):
        """Frames en la raiz son detectados."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "frame_000003.png").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1, 3]

    def test_detects_exr_frames(self, tmp_drive_dir: Path):
        """Frames .exr son detectados."""
        (tmp_drive_dir / "frame_000001.exr").touch()
        (tmp_drive_dir / "frame_000002.exr").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1, 2]

    def test_detects_frames_in_subdirectories(self, tmp_drive_dir: Path):
        """Frames en subdirectorios son detectados."""
        subdir = tmp_drive_dir / "Temp"
        subdir.mkdir()
        (subdir / "frame_000001.exr").touch()
        (subdir / "frame_000002.exr").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1, 2]

    def test_ignores_non_frame_files(self, tmp_drive_dir: Path):
        """Archivos que no son frame_* se ignoran."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "README.txt").touch()
        (tmp_drive_dir / "output.exr").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1]

    def test_mixed_subdirectories(self, tmp_drive_dir: Path):
        """Frames en multiples subdirectorios."""
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "beauty").mkdir()
        (tmp_drive_dir / "beauty" / "frame_000002.exr").touch()
        (tmp_drive_dir / "depth").mkdir()
        (tmp_drive_dir / "depth" / "frame_000003.exr").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1, 2, 3]

    def test_returns_sorted(self, tmp_drive_dir: Path):
        """Retorna frames ordenados."""
        (tmp_drive_dir / "frame_000003.png").touch()
        (tmp_drive_dir / "frame_000001.png").touch()
        (tmp_drive_dir / "frame_000002.png").touch()
        assert list_frames_in_drive(tmp_drive_dir) == [1, 2, 3]