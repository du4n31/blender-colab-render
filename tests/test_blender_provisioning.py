"""Pruebas para blender_provisioning.py: fetch_available_versions y resolve_blender_version."""

import unittest
from unittest.mock import Mock, patch

import requests

from bcr.blender_provisioning import (
    BlenderProvisioningError,
    fetch_available_versions,
    resolve_blender_version,
)
from bcr.config import BLENDER_DEFAULT_VERSION, BLENDER_RELEASE_BASE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_html_response(text: str, status: int = 200) -> Mock:
    """Crea un Mock de respuesta HTTP con .text y .raise_for_status() no-op."""
    mock = Mock(spec=requests.Response)
    mock.text = text
    mock.status_code = status
    mock.raise_for_status = Mock()
    return mock


def _make_side_effect(
    responses: dict[str, str],
) -> Mock:
    """Construye una funcion side_effect que mapea URL a HTML de respuesta."""

    def side_effect(url: str, **kwargs: object) -> Mock:
        html = responses.get(url)
        if html is None:
            raise ValueError(f"Unexpected GET: {url}")
        return _mock_html_response(html)

    return side_effect


# ---------------------------------------------------------------------------
# HTML fragments simulando autoindex de download.blender.org
# ---------------------------------------------------------------------------

TOP_HTML = """<html><body>
<a href="Blender5.0/">Blender5.0/</a>
<a href="Blender5.1/">Blender5.1/</a>
<a href="Blender4.2/">Blender4.2/</a>
</body></html>"""

FOLDER_5_0_HTML = """<html><body>
<a href="blender-5.0.0-linux-x64.tar.xz">blender-5.0.0-linux-x64.tar.xz</a>
<a href="blender-5.0.1-linux-x64.tar.xz">blender-5.0.1-linux-x64.tar.xz</a>
</body></html>"""

FOLDER_5_1_HTML = """<html><body>
<a href="blender-5.1.0-linux-x64.tar.xz">blender-5.1.0-linux-x64.tar.xz</a>
</body></html>"""

FOLDER_5_2_HTML = """<html><body>
<a href="blender-5.2.0-linux-x64.tar.xz">blender-5.2.0-linux-x64.tar.xz</a>
</body></html>"""

# URLs construidas igual que en el codigo productivo
FOLDER_5_0_URL = f"{BLENDER_RELEASE_BASE}Blender5.0/"
FOLDER_5_1_URL = f"{BLENDER_RELEASE_BASE}Blender5.1/"
FOLDER_5_2_URL = f"{BLENDER_RELEASE_BASE}Blender5.2/"


# ---------------------------------------------------------------------------
# TestFetchAvailableVersions
# ---------------------------------------------------------------------------


class TestFetchAvailableVersions(unittest.TestCase):
    """Pruebas para fetch_available_versions."""

    @patch("bcr.blender_provisioning.requests.get")
    def test_returns_versions_ge_min_major(self, mock_get: Mock) -> None:
        """Versiones con major >= 5 se devuelven, las menores se filtran."""
        mock_get.side_effect = _make_side_effect(
            {
                BLENDER_RELEASE_BASE: TOP_HTML,
                FOLDER_5_0_URL: FOLDER_5_0_HTML,
                FOLDER_5_1_URL: FOLDER_5_1_HTML,
            }
        )

        result = fetch_available_versions(min_major=5)

        self.assertIn("5.0.0", result)
        self.assertIn("5.0.1", result)
        self.assertIn("5.1.0", result)
        for v in result:
            major = int(v.split(".")[0])
            self.assertGreaterEqual(major, 5)

    @patch("bcr.blender_provisioning.requests.get")
    def test_returns_descending_order(self, mock_get: Mock) -> None:
        """La lista se devuelve ordenada descendente (mas reciente primero)."""
        mock_get.side_effect = _make_side_effect(
            {
                BLENDER_RELEASE_BASE: TOP_HTML,
                FOLDER_5_0_URL: FOLDER_5_0_HTML,
                FOLDER_5_1_URL: FOLDER_5_1_HTML,
            }
        )

        result = fetch_available_versions(min_major=5)

        self.assertEqual(result, sorted(result, reverse=True))

    @patch("bcr.blender_provisioning.requests.get")
    def test_multiple_patches_per_version(self, mock_get: Mock) -> None:
        """Multiples .tar.xz en una misma carpeta de version se capturan todos."""
        mock_get.side_effect = _make_side_effect(
            {
                BLENDER_RELEASE_BASE: TOP_HTML,
                FOLDER_5_0_URL: FOLDER_5_0_HTML,
                FOLDER_5_1_URL: FOLDER_5_1_HTML,
            }
        )

        result = fetch_available_versions(min_major=5)

        five_oh_patches = [v for v in result if v.startswith("5.0.")]
        self.assertIn("5.0.0", five_oh_patches)
        self.assertIn("5.0.1", five_oh_patches)

    @patch("bcr.blender_provisioning.requests.get")
    def test_no_matching_folders_raises(self, mock_get: Mock) -> None:
        """HTML sin carpetas BlenderX.Y/ lanza BlenderProvisioningError."""
        no_versions_html = "<html><body>No Blender folders here</body></html>"
        mock_get.return_value = _mock_html_response(no_versions_html)

        with self.assertRaises(BlenderProvisioningError):
            fetch_available_versions(min_major=5)

    @patch("bcr.blender_provisioning.requests.get")
    def test_network_error_raises(self, mock_get: Mock) -> None:
        """Error de red en la peticion principal lanza BlenderProvisioningError."""
        mock_get.side_effect = requests.RequestException("connection failed")

        with self.assertRaises(BlenderProvisioningError):
            fetch_available_versions(min_major=5)

    @patch("bcr.blender_provisioning.requests.get")
    def test_folder_network_error_skipped(self, mock_get: Mock) -> None:
        """Error de red al pedir una carpeta la salta sin interrumpir."""
        mock_get.side_effect = [
            _mock_html_response(TOP_HTML),
            _mock_html_response(FOLDER_5_0_HTML),
            requests.RequestException("folder unreachable"),
        ]

        result = fetch_available_versions(min_major=5)

        self.assertIn("5.0.0", result)
        self.assertIn("5.0.1", result)
        self.assertNotIn("5.1.0", result)


# ---------------------------------------------------------------------------
# TestResolveBlenderVersion
# ---------------------------------------------------------------------------


class TestResolveBlenderVersion(unittest.TestCase):
    """Pruebas para resolve_blender_version."""

    @patch("bcr.blender_provisioning.fetch_available_versions")
    def test_preferred_version_returned(self, mock_fetch: Mock) -> None:
        """Si se pasa preferred, se devuelve esa version exacta."""
        mock_fetch.return_value = ["5.2.0", "5.1.0", "5.0.0"]

        result = resolve_blender_version(preferred="5.1.0")

        self.assertEqual(result, "5.1.0")

    @patch("bcr.blender_provisioning.fetch_available_versions")
    def test_latest_version_when_no_preferred(self, mock_fetch: Mock) -> None:
        """Sin preferred, devuelve la primera (mas reciente) de la lista."""
        mock_fetch.return_value = ["5.2.0", "5.1.0", "5.0.0"]

        result = resolve_blender_version()

        self.assertEqual(result, "5.2.0")

    @patch("bcr.blender_provisioning.fetch_available_versions")
    def test_fallback_on_exception(self, mock_fetch: Mock) -> None:
        """Si fetch_available_versions lanza, retorna BLENDER_DEFAULT_VERSION."""
        mock_fetch.side_effect = BlenderProvisioningError("fail")

        result = resolve_blender_version()

        self.assertEqual(result, BLENDER_DEFAULT_VERSION)

    @patch("bcr.blender_provisioning.fetch_available_versions")
    def test_fallback_with_preferred(self, mock_fetch: Mock) -> None:
        """Si fetch falla y hay preferred, retorna preferred en vez del default."""
        mock_fetch.side_effect = BlenderProvisioningError("fail")

        result = resolve_blender_version(preferred="5.0.0")

        self.assertEqual(result, "5.0.0")

    @patch("bcr.blender_provisioning.fetch_available_versions")
    def test_never_raises(self, mock_fetch: Mock) -> None:
        """resolve_blender_version nunca lanza excepcion (siempre retorna str)."""
        # Happy path
        mock_fetch.return_value = ["5.2.0"]
        result = resolve_blender_version()
        self.assertIsInstance(result, str)

        # Fallback sin preferred
        mock_fetch.side_effect = BlenderProvisioningError("fail")
        result = resolve_blender_version()
        self.assertIsInstance(result, str)

        # Fallback con preferred
        result = resolve_blender_version(preferred="5.0.0")
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
