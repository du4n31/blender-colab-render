"""Pruebas para link_resolver.py."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from bcr.link_resolver import (
    LinkResolutionError,
    resolve_download_url,
)


class TestResolveDownloadUrl:
    """Prueba la funcion principal de resolucion de enlaces."""

    def test_direct_link_passthrough(self):
        """Enlace directo .blend se devuelve tal cual."""
        url = "https://ejemplo.com/escena.blend"
        assert resolve_download_url(url) == url

    def test_direct_link_zip(self):
        """Enlace directo .zip se devuelve tal cual."""
        url = "https://ejemplo.com/archivo.zip"
        assert resolve_download_url(url) == url

    @patch("bcr.link_resolver.urllib.parse.urlparse")
    def test_dropbox_conversion(self, mock_parse):
        """Dropbox: dl=0 debe convertirse a dl=1."""
        from urllib.parse import ParseResult

        mock_parse.return_value = ParseResult(
            scheme="https",
            netloc="www.dropbox.com",
            path="/s/abc123/escena.blend",
            params="",
            query="dl=0",
            fragment="",
        )
        result = resolve_download_url(
            "https://www.dropbox.com/s/abc123/escena.blend?dl=0"
        )
        assert "dl=1" in result

    @patch("bcr.link_resolver.urllib.parse.urlparse")
    def test_dropbox_no_dl_param(self, mock_parse):
        """Dropbox sin dl=0 anade dl=1."""
        from urllib.parse import ParseResult

        mock_parse.return_value = ParseResult(
            scheme="https",
            netloc="www.dropbox.com",
            path="/s/abc123/escena.blend",
            params="",
            query="",
            fragment="",
        )
        result = resolve_download_url(
            "https://www.dropbox.com/s/abc123/escena.blend"
        )
        assert "dl=1" in result

    @patch("bcr.link_resolver._resolve_google_drive")
    def test_google_drive_delegates(self, mock_resolve):
        """Google Drive delega a gdown."""
        mock_resolve.return_value = "https://drive.google.com/uc?id=FILE_ID"
        result = resolve_download_url(
            "https://drive.google.com/file/d/FILE_ID/view"
        )
        assert "FILE_ID" in result

    @patch("bcr.link_resolver.requests.get")
    def test_mediafire_resolution(self, mock_get):
        """MediaFire extrae URL del HTML."""
        mock_response = Mock()
        mock_response.text = """
        <html>
        <a class="downloadButton" href="https://download.mediafire.com/archivo.blend">
        </html>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = resolve_download_url("https://www.mediafire.com/file/abc123")
        assert "mediafire.com" in result or "download" in result

    @patch("bcr.link_resolver.requests.get")
    def test_mediafire_data_download_url(self, mock_get):
        """MediaFire con data-download-url en el HTML."""
        mock_response = Mock()
        mock_response.text = """
        <div data-download-url="https://download.mediafire.com/archivo.blend">
        </div>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = resolve_download_url("https://www.mediafire.com/file/abc123")
        assert "mediafire.com" in result

    def test_unsupported_provider_raises(self):
        """Proveedor no soportado lanza LinkResolutionError."""
        with pytest.raises(LinkResolutionError):
            resolve_download_url("https://mega.nz/file/SECRET")


class TestGoogleDriveResolution:
    """Pruebas para resolucion de Google Drive."""

    def test_gdrive_file_id_extraction(self):
        """Extrae file_id de URL /file/d/."""
        result = resolve_download_url(
            "https://drive.google.com/file/d/ABC123xyz/view?usp=sharing"
        )
        assert "ABC123xyz" in result
        assert "export=download" in result

    def test_gdrive_open_url(self):
        """Enlace open?id= tambien funciona."""
        result = resolve_download_url(
            "https://drive.google.com/open?id=FILE_ID"
        )
        assert "FILE_ID" in result
        assert "export=download" in result


class TestMediafireResolution:
    """Pruebas para resolucion de MediaFire."""

    @patch("bcr.link_resolver.requests.get")
    def test_mediafire_kno_pattern(self, mock_get):
        """MediaFire con patron kNO=."""
        mock_response = Mock()
        mock_response.text = """
        <script>
        kNO = "https://download.mediafire.com/archivo_v4.blend";
        </script>
        """
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = resolve_download_url("https://www.mediafire.com/file/abc")
        assert "archivo_v4.blend" in result

    @patch("bcr.link_resolver.requests.get")
    def test_mediafire_http_error(self, mock_get):
        """Error HTTP en MediaFire lanza LinkResolutionError."""
        mock_get.side_effect = __import__("requests").RequestException(
            "Connection error"
        )
        with pytest.raises(LinkResolutionError):
            resolve_download_url("https://www.mediafire.com/file/abc")

    @patch("bcr.link_resolver.requests.get")
    def test_mediafire_no_matches(self, mock_get):
        """HTML sin patron de descarga lanza LinkResolutionError."""
        mock_response = Mock()
        mock_response.text = "<html><p>File not found</p></html>"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with pytest.raises(LinkResolutionError):
            resolve_download_url("https://www.mediafire.com/file/abc")
