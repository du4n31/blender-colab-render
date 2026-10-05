"""Pruebas para drive_sync.py.

Validan subida de frames, organizacion por subdirectorios (nodos),
y deteccion recursiva de frames en Drive.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from bcr.drive_sync import (
    DriveSyncError,
    list_frames_in_drive,
    remove_local,
    upload_frame,
)


class TestUploadFrame(unittest.TestCase):
    """Test upload_frame with and without a subdirectory."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._drive = self._tmpdir / "drive"
        self._drive.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_upload_basic_preserves_name(self) -> None:
        """Basic upload: preserve the original file name."""
        src = self._tmpdir / "beauty_0001.exr"
        src.write_text("fake-exr")
        result = upload_frame(src, self._drive, frame_num=1)
        self.assertEqual(result, self._drive / "beauty_0001.exr")
        self.assertTrue(result.exists())

    def test_upload_with_subdir_preserves_name(self) -> None:
        """Subdirectory upload: preserve the original file name."""
        src = self._tmpdir / "beauty_0001.exr"
        src.write_text("fake-exr")
        result = upload_frame(src, self._drive, frame_num=1, subdir="Temp")
        expected = self._drive / "Temp" / "beauty_0001.exr"
        self.assertEqual(result, expected)
        self.assertTrue(result.exists())

    def test_upload_multiple_subdirs_no_collision(self) -> None:
        """Multiple files for one frame use distinct subdirectories without overwriting."""
        src1 = self._tmpdir / "beauty_0001.exr"
        src1.write_text("beauty-data")
        src2 = self._tmpdir / "depth_0001.exr"
        src2.write_text("depth-data")

        r1 = upload_frame(src1, self._drive, frame_num=1, subdir="beauty")
        r2 = upload_frame(src2, self._drive, frame_num=1, subdir="depth")

        self.assertEqual(r1, self._drive / "beauty" / "beauty_0001.exr")
        self.assertEqual(r2, self._drive / "depth" / "depth_0001.exr")
        self.assertTrue(r1.exists())
        self.assertTrue(r2.exists())
        self.assertEqual(r1.read_text(), "beauty-data")
        self.assertEqual(r2.read_text(), "depth-data")

    def test_upload_no_source_file(self) -> None:
        """A missing local file raises DriveSyncError."""
        fake = Path("/tmp/nonexistent_file_12345.png")
        with self.assertRaises(DriveSyncError):
            upload_frame(fake, self._drive, frame_num=1)

    def test_preserves_file_extension(self) -> None:
        """La extension original se preserva en Drive."""
        src = self._tmpdir / "output.exr"
        src.write_text("exr-data")
        result = upload_frame(src, self._drive, frame_num=42)
        self.assertEqual(result.suffix, ".exr")
        self.assertEqual(result.name, "output.exr")

    def test_fallback_frame_pattern_when_preserve_false(self) -> None:
        """Con preserve_name=False usa patron frame_NNNNNN.ext."""
        src = self._tmpdir / "output.exr"
        src.write_text("exr-data")
        result = upload_frame(src, self._drive, frame_num=42, preserve_name=False)
        self.assertEqual(result.suffix, ".exr")
        self.assertEqual(result.name, "frame_000042.exr")

    def test_defaults_to_png_when_no_extension(self) -> None:
        """An extensionless file defaults to .png only when preserve_name=False."""
        src = self._tmpdir / "output"
        src.write_text("data")
        result = upload_frame(src, self._drive, frame_num=1, preserve_name=False)
        self.assertEqual(result.suffix, ".png")
        self.assertEqual(result.name, "frame_000001.png")


class TestRemoveLocal(unittest.TestCase):
    """Test remove_local."""

    def test_removes_existing_file(self) -> None:
        """An existing file is removed."""
        f = Path(tempfile.mkstemp()[1])
        f.write_text("hello")
        remove_local(f)
        self.assertFalse(f.exists())

    def test_no_error_on_missing_file(self) -> None:
        """Removing a missing file does not raise an error."""
        remove_local(Path("/tmp/this_does_not_exist_12345.txt"))


class TestListFramesInDrive(unittest.TestCase):
    """Test recursive frame discovery in list_frames_in_drive."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._drive = self._tmpdir / "drive"
        self._drive.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_empty_directory(self) -> None:
        """An empty directory returns an empty list."""
        self.assertEqual(list_frames_in_drive(self._drive), [])

    def test_detects_frames_in_root(self) -> None:
        """Detect frames in the root directory."""
        (self._drive / "frame_000001.png").touch()
        (self._drive / "frame_000003.png").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 3])

    def test_detects_exr_frames(self) -> None:
        """Detect .exr frames."""
        (self._drive / "frame_000001.exr").touch()
        (self._drive / "frame_000002.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 2])

    def test_detects_frames_in_subdirectories(self) -> None:
        """Detect frames in subdirectories."""
        subdir = self._drive / "Temp"
        subdir.mkdir()
        (subdir / "frame_000001.exr").touch()
        (subdir / "frame_000002.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 2])

    def test_ignores_non_frame_files(self) -> None:
        """Ignore files that are not rendered frames."""
        (self._drive / "frame_000001.png").touch()
        (self._drive / "README.txt").touch()
        (self._drive / "output.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1])

    def test_ignores_non_image_assets_with_six_digit_names(self) -> None:
        """Scene files, scripts, and videos must not be mistaken for rendered frames."""
        (self._drive / "frame_000001.png").touch()
        (self._drive / "scene_000002.blend").touch()
        (self._drive / "script_000003.py").touch()
        (self._drive / "texture_000004.mp4").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1])

    def test_mixed_subdirectories(self) -> None:
        """Detect frames across multiple subdirectories."""
        (self._drive / "frame_000001.png").touch()
        (self._drive / "beauty").mkdir()
        (self._drive / "beauty" / "frame_000002.exr").touch()
        (self._drive / "depth").mkdir()
        (self._drive / "depth" / "frame_000003.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 2, 3])

    def test_returns_sorted(self) -> None:
        """Return sorted frame numbers."""
        (self._drive / "frame_000003.png").touch()
        (self._drive / "frame_000001.png").touch()
        (self._drive / "frame_000002.png").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 2, 3])

    def test_detects_single_layer_node_names(self) -> None:
        """Recognize actual single-layer node filenames such as Result_000001.exr."""
        (self._drive / "tmp").mkdir()
        (self._drive / "tmp" / "Result_000001.exr").touch()
        (self._drive / "tmp" / "Result_000002.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 2])

    def test_detects_multilayer_node_names(self) -> None:
        """Recognize actual multilayer node filenames such as File_Output_001_000001.exr."""
        (self._drive / "salida").mkdir()
        (self._drive / "salida" / "File_Output_001_000001.exr").touch()
        (self._drive / "salida" / "File_Output_001_000005.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1, 5])

    def test_detects_mixed_node_names_in_subdirs(self) -> None:
        """Recognize the same frame in different node subdirectories."""
        (self._drive / "tmp").mkdir()
        (self._drive / "salida").mkdir()
        (self._drive / "tmp" / "Result_000001.exr").touch()
        (self._drive / "salida" / "File_Output_001_000001.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1])

    def test_five_digit_names_are_ignored(self) -> None:
        """Do not confuse five-digit filenames (frame_00001) with six-digit frames."""
        (self._drive / "frame_00001.png").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [])

    def test_ignores_non_frame_files_without_6_digits(self) -> None:
        """Ignore filenames without exactly six consecutive digits."""
        (self._drive / "Result_000001.exr").touch()
        (self._drive / "README.txt").touch()
        (self._drive / "output.exr").touch()
        self.assertEqual(list_frames_in_drive(self._drive), [1])
