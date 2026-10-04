"""Tests for source_resolver.py.

Validate link, upload, drive_path, and ZIP acquisition.
"""

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from bcr.source_resolver import (
    SourceAcquisitionError,
    acquire_source,
    resolve_zip_contents,
)


class TestAcquireSourceLink(unittest.TestCase):
    """Test the "link" method acquisition."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    @patch("bcr.source_resolver.link_resolver.resolve_download_url")
    @patch("bcr.source_resolver.requests.get")
    def test_happy_path_downloads_file(
        self, mock_get: Mock, mock_resolve: Mock
    ) -> None:
        """A valid link downloads the file into working_dir."""
        mock_resolve.return_value = "https://direct.example.com/file.blend"
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.iter_content.return_value = [b"blend data"]
        mock_get.return_value = mock_response

        result = acquire_source(
            "link", "https://example.com/file.blend", self._tmpdir
        )

        mock_resolve.assert_called_once_with("https://example.com/file.blend")
        mock_get.assert_called_once_with(
            "https://direct.example.com/file.blend",
            stream=True,
            timeout=120,
        )
        expected = (self._tmpdir / "file.blend").resolve()
        self.assertEqual(result, expected)
        self.assertTrue(expected.exists())
        self.assertEqual(expected.read_bytes(), b"blend data")

    @patch("bcr.source_resolver.link_resolver.resolve_download_url")
    def test_link_resolution_error_raises(self, mock_resolve: Mock) -> None:
        """Error en link_resolver lanza SourceAcquisitionError."""
        from bcr.link_resolver import LinkResolutionError

        mock_resolve.side_effect = LinkResolutionError("Bad link")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            acquire_source("link", "https://example.com/bad", self._tmpdir)
        self.assertIn("Failed to resolve URL", str(ctx.exception))

    @patch("bcr.source_resolver.link_resolver.resolve_download_url")
    @patch("bcr.source_resolver.requests.get")
    def test_request_failure_raises(
        self, mock_get: Mock, mock_resolve: Mock
    ) -> None:
        """Error HTTP en requests lanza SourceAcquisitionError."""
        mock_resolve.return_value = "https://direct.example.com/file.blend"
        mock_get.side_effect = __import__("requests").RequestException(
            "Connection timeout"
        )

        with self.assertRaises(SourceAcquisitionError) as ctx:
            acquire_source("link", "https://example.com/file.blend", self._tmpdir)
        self.assertIn("Failed to download", str(ctx.exception))


class TestAcquireSourceDrivePath(unittest.TestCase):
    """Test the "drive_path" method."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._drive_root = self._tmpdir / "drive"
        self._drive_root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_happy_path_copies_file(self) -> None:
        """A file inside Drive is copied successfully."""
        source_file = self._drive_root / "test.blend"
        source_file.write_text("blend data")

        with patch("bcr.source_resolver.DRIVE_MOUNT_POINT") as mock_drive:
            mock_drive.resolve.return_value = self._drive_root
            result = acquire_source(
                "drive_path", str(source_file), self._tmpdir
            )

        expected = (self._tmpdir / "test.blend").resolve()
        self.assertEqual(result, expected)
        self.assertTrue(expected.exists())
        self.assertEqual(expected.read_text(), "blend data")

    def test_relative_path_resolves_against_drive_root(self) -> None:
        """A relative path (such as the path requested by the notebook, e.g.
        "MyDrive/escenas/mi_escena.blend") must be resolved against the
        punto de montaje de Drive, no contra el cwd del proceso."""
        (self._drive_root / "MyDrive" / "escenas").mkdir(parents=True)
        source_file = self._drive_root / "MyDrive" / "escenas" / "mi_escena.blend"
        source_file.write_text("blend data")

        with patch("bcr.source_resolver.DRIVE_MOUNT_POINT") as mock_drive:
            mock_drive.resolve.return_value = self._drive_root
            result = acquire_source(
                "drive_path", "MyDrive/escenas/mi_escena.blend", self._tmpdir
            )

        expected = (self._tmpdir / "mi_escena.blend").resolve()
        self.assertEqual(result, expected)
        self.assertEqual(expected.read_text(), "blend data")

    def test_path_outside_drive_raises(self) -> None:
        """A path outside the Drive mount point raises an error."""
        outside_file = self._tmpdir / "outside.blend"
        outside_file.write_text("data")

        with patch("bcr.source_resolver.DRIVE_MOUNT_POINT") as mock_drive:
            mock_drive.resolve.return_value = self._drive_root
            with self.assertRaises(SourceAcquisitionError) as ctx:
                acquire_source(
                    "drive_path", str(outside_file), self._tmpdir
                )
            self.assertIn("Path must be inside", str(ctx.exception))

    def test_nonexistent_file_raises(self) -> None:
        """A missing file inside Drive raises an error."""
        nonexistent = self._drive_root / "missing.blend"

        with patch("bcr.source_resolver.DRIVE_MOUNT_POINT") as mock_drive:
            mock_drive.resolve.return_value = self._drive_root
            with self.assertRaises(SourceAcquisitionError) as ctx:
                acquire_source(
                    "drive_path", str(nonexistent), self._tmpdir
                )
            self.assertIn("does not exist", str(ctx.exception))


class TestAcquireSourceUpload(unittest.TestCase):
    """Test the "upload" method."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_upload_raises_outside_colab(self) -> None:
        """Fuera de Colab, upload lanza SourceAcquisitionError.

        Se simula la ausencia de google.colab poniendo su entrada en
        sys.modules en None (comportamiento estandar de Python: cualquier
        import de ese nombre lanza ImportError). Esto es preferible a
        parchear builtins.__import__ globalmente, que intercepta tambien
        imports internos no relacionados (p. ej. el import diferido de
        ntpath dentro de pathlib) y puede producir fallos espurios.
        """
        with patch.dict(sys.modules, {"google.colab": None, "google": None}):
            with self.assertRaises(SourceAcquisitionError) as ctx:
                acquire_source("upload", "", self._tmpdir)
            self.assertIn(
                "only available in Google Colab",
                str(ctx.exception),
            )


class TestResolveZipContents(unittest.TestCase):
    """Test ZIP extraction and resolution."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_blend_zip_single_blend_returns_path(self) -> None:
        """A ZIP containing one .blend file returns its path."""
        zip_path = self._tmpdir / "scene.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("model.blend", b"blend content")

        result = resolve_zip_contents(zip_path, self._tmpdir, "blend")

        expected = (self._tmpdir / "scene" / "model.blend").resolve()
        self.assertEqual(result, expected)
        self.assertTrue(expected.exists())

    def test_blend_zip_multiple_blends_raises(self) -> None:
        """ZIP con multiples .blend lanza error listando disponibles."""
        zip_path = self._tmpdir / "models.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("model1.blend", b"content1")
            zf.writestr("model2.blend", b"content2")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            resolve_zip_contents(zip_path, self._tmpdir, "blend")
        msg = str(ctx.exception)
        self.assertIn(".blend files", msg)
        self.assertIn("model1.blend", msg)
        self.assertIn("model2.blend", msg)

    def test_blend_zip_no_blend_raises(self) -> None:
        """ZIP sin .blend lanza error."""
        zip_path = self._tmpdir / "no_blend.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("readme.txt", b"no blends here")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            resolve_zip_contents(zip_path, self._tmpdir, "blend")
        self.assertIn("No .blend files were found", str(ctx.exception))

    def test_script_zip_with_entry_point(self) -> None:
        """ZIP script con entry_point.txt devuelve [entry, dir]."""
        zip_path = self._tmpdir / "script.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("entry_point.txt", "main.py")
            zf.writestr("main.py", b"print('hello')")
            zf.writestr("utils.py", b"def helper(): pass")

        result = resolve_zip_contents(zip_path, self._tmpdir, "script")

        expected_entry = (self._tmpdir / "script" / "main.py").resolve()
        expected_dir = (self._tmpdir / "script").resolve()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], expected_entry)
        self.assertEqual(result[1], expected_dir)
        self.assertTrue(expected_entry.exists())

    def test_script_zip_single_py_without_entry_point(self) -> None:
        """A script ZIP without entry_point.txt and one .py returns [py, dir]."""
        zip_path = self._tmpdir / "simple_script.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("main.py", b"print('hello')")

        result = resolve_zip_contents(zip_path, self._tmpdir, "script")

        expected_entry = (self._tmpdir / "simple_script" / "main.py").resolve()
        expected_dir = (self._tmpdir / "simple_script").resolve()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], expected_entry)
        self.assertEqual(result[1], expected_dir)

    def test_script_zip_multiple_py_no_entry_point_raises(self) -> None:
        """A ZIP with multiple .py files and no entry_point.txt raises an error."""
        zip_path = self._tmpdir / "multi_script.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("main.py", b"print('hello')")
            zf.writestr("utils.py", b"def helper(): pass")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            resolve_zip_contents(zip_path, self._tmpdir, "script")
        self.assertIn(".py files", str(ctx.exception))

    def test_zip_slip_rejected_before_extraction(self) -> None:
        """Entrada ZIP con ../ que intenta zip slip es rechazada."""
        zip_path = self._tmpdir / "slip.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("../evil.txt", b"malicious")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            resolve_zip_contents(zip_path, self._tmpdir, "blend")
        self.assertIn("ZIP slip", str(ctx.exception))

        # Verify that no files were extracted outside the destination directory
        extract_dir = self._tmpdir / "slip"
        self.assertTrue(extract_dir.exists())
        self.assertEqual(list(extract_dir.iterdir()), [])

    def test_zip_slip_rejects_sibling_with_shared_path_prefix(self) -> None:
        """Reject traversal into a sibling whose path shares the target prefix."""
        zip_path = self._tmpdir / "prefix-slip.zip"
        extract_dir = self._tmpdir / "prefix-slip"
        extract_dir.mkdir()
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("../prefix-slip-escape/evil.txt", b"malicious")

        with self.assertRaises(SourceAcquisitionError) as ctx:
            resolve_zip_contents(zip_path, self._tmpdir, "blend")
        self.assertIn("ZIP slip", str(ctx.exception))
        self.assertFalse((self._tmpdir / "prefix-slip-escape").exists())

    def test_non_zip_blend_returns_path(self) -> None:
        """A non-ZIP file with kind='blend' is returned unchanged."""
        non_zip = self._tmpdir / "scene.blend"
        non_zip.write_text("blend")
        result = resolve_zip_contents(non_zip, self._tmpdir, "blend")
        self.assertEqual(result, non_zip)

    def test_non_zip_script_returns_list(self) -> None:
        """A non-ZIP file with kind='script' is returned as [path]."""
        non_zip = self._tmpdir / "script.py"
        non_zip.write_text("print('hello')")
        result = resolve_zip_contents(non_zip, self._tmpdir, "script")
        self.assertEqual(result, [non_zip])


class TestAcquireSourceUnknownMethod(unittest.TestCase):
    """Test that an unknown method raises SourceAcquisitionError."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    def test_unknown_method_raises(self) -> None:
        """An unknown method raises SourceAcquisitionError."""
        with self.assertRaises(SourceAcquisitionError) as ctx:
            acquire_source("invalid", "value", self._tmpdir)
        self.assertIn(
            "Unknown acquisition method", str(ctx.exception)
        )
