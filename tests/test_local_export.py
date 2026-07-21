"""Pruebas para local_export.py.

Validan empaquetado en .zip, descarga local y verificacion de espacio en disco.
"""

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from bcr.local_export import (
    LocalExportError,
    check_disk_space,
    package_output,
    trigger_download,
)


class TestPackageOutput(unittest.TestCase):
    """Prueba la funcion package_output."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_non_existent_directory_raises_error(self) -> None:
        """Non-existent directory raises LocalExportError."""
        with self.assertRaises(LocalExportError):
            package_output(Path("/nonexistent_path_12345"))

    def test_empty_directory_raises_error(self) -> None:
        """Empty directory raises LocalExportError."""
        with self.assertRaises(LocalExportError):
            package_output(self._tmpdir)

    def test_happy_path_creates_zip(self) -> None:
        """Creates .zip in /tmp/, returns Path, zip contains files."""
        (self._tmpdir / "frame_000001.exr").write_text("fake exr 1")
        (self._tmpdir / "frame_000002.exr").write_text("fake exr 2")

        result = package_output(self._tmpdir)

        self.assertIsInstance(result, Path)
        self.assertTrue(result.exists())
        self.assertEqual(result.suffix, ".zip")
        self.assertTrue(str(result).startswith("/tmp/"))

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
            self.assertIn("frame_000001.exr", names)
            self.assertIn("frame_000002.exr", names)

    def test_subdirectory_structure_preserved(self) -> None:
        """Subdirectory structure is preserved in the zip."""
        subdir = self._tmpdir / "Temp"
        subdir.mkdir()
        (subdir / "beauty_0001.exr").write_text("beauty")
        (self._tmpdir / "frame_000001.exr").write_text("root frame")

        result = package_output(self._tmpdir)

        with zipfile.ZipFile(result, "r") as zf:
            names = zf.namelist()
            self.assertIn("frame_000001.exr", names)
            self.assertIn("Temp/beauty_0001.exr", names)


class TestTriggerDownload(unittest.TestCase):
    """Prueba la funcion trigger_download."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._zip_path = self._tmpdir / "test_output.zip"

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_non_existent_zip_raises_error(self) -> None:
        """Non-existent .zip raises LocalExportError."""
        with self.assertRaises(LocalExportError):
            trigger_download(Path("/nonexistent_file_12345.zip"))

    @patch("builtins.print")
    def test_non_colab_environment_no_error(self, mock_print: MagicMock) -> None:
        """In non-Colab environment, ImportError is caught, just prints."""
        self._zip_path.write_text("dummy zip content")

        # Ensure google.colab is not importable (simulates non-Colab env)
        saved_modules: dict[str, object] = {}
        for mod_name in list(sys.modules):
            if "google.colab" in mod_name:
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        try:
            trigger_download(self._zip_path)
        finally:
            sys.modules.update(saved_modules)

        mock_print.assert_called_once()


class TestCheckDiskSpace(unittest.TestCase):
    """Prueba la funcion check_disk_space."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_non_existent_directory_returns_false(self) -> None:
        """Non-existent directory returns (False, message)."""
        ok, msg = check_disk_space(Path("/nonexistent_path_12345"), min_free_gb=2.0)
        self.assertFalse(ok)
        self.assertIn("no existe", msg.lower())

    @patch("shutil.disk_usage")
    def test_sufficient_space_returns_true(
        self, mock_disk_usage: MagicMock
    ) -> None:
        """Sufficient space returns (True, '')."""
        mock_disk_usage.return_value = MagicMock(free=10 * 1024**3)
        ok, msg = check_disk_space(self._tmpdir, min_free_gb=2.0)
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    @patch("shutil.disk_usage")
    def test_insufficient_space_returns_false(
        self, mock_disk_usage: MagicMock
    ) -> None:
        """Insufficient space returns (False, message) with reasonable message."""
        mock_disk_usage.return_value = MagicMock(free=0.5 * 1024**3)
        ok, msg = check_disk_space(self._tmpdir, min_free_gb=2.0)
        self.assertFalse(ok)
        self.assertIn("insuficiente", msg.lower())
        self.assertIn("GB", msg)
