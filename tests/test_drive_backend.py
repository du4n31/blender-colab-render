"""Pruebas para drive_backend.py (backend de Drive via API / service account).

Todo se prueba contra un objeto `service` mockeado -- nunca se llama a la
Drive API real. Cubre resolucion/creacion de carpetas, nombrado de frames
(misma logica que drive_sync.upload_frame), listado recursivo via
extract_frame_number, guardado/carga de estado, y los errores claros al
leer secretos de Colab.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from bcr.drive_backend import DriveBackendError, ServiceAccountDriveBackend


def _make_service() -> MagicMock:
    """Mock de 'service' con la cadena service.files().<verbo>().execute()."""
    return MagicMock()


class TestEnsureConnected(unittest.TestCase):
    def test_success(self) -> None:
        service = _make_service()
        service.files.return_value.get.return_value.execute.return_value = {
            "id": "root123",
            "name": "BlenderColabRender",
            "mimeType": "application/vnd.google-apps.folder",
        }
        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertTrue(backend.ensure_connected())

    def test_not_a_folder_raises(self) -> None:
        service = _make_service()
        service.files.return_value.get.return_value.execute.return_value = {
            "id": "root123",
            "name": "algo.blend",
            "mimeType": "application/octet-stream",
        }
        backend = ServiceAccountDriveBackend(service, "root123")
        with self.assertRaises(DriveBackendError):
            backend.ensure_connected()

    def test_api_error_raises(self) -> None:
        service = _make_service()
        service.files.return_value.get.return_value.execute.side_effect = Exception(
            "403 forbidden"
        )
        backend = ServiceAccountDriveBackend(service, "root123")
        with self.assertRaises(DriveBackendError):
            backend.ensure_connected()


class TestEnsureOutputDir(unittest.TestCase):
    def test_root_returns_root_id_without_api_call(self) -> None:
        service = _make_service()
        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertEqual(backend.ensure_output_dir(""), "root123")
        service.files.return_value.list.assert_not_called()

    def test_creates_folder_when_missing(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "salida_id"
        }

        backend = ServiceAccountDriveBackend(service, "root123")
        result = backend.ensure_output_dir("salida")

        self.assertEqual(result, "salida_id")
        created_body = service.files.return_value.create.call_args.kwargs["body"]
        self.assertEqual(created_body["name"], "salida")
        self.assertEqual(created_body["parents"], ["root123"])
        self.assertEqual(created_body["mimeType"], "application/vnd.google-apps.folder")

    def test_reuses_existing_folder_instead_of_creating(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "existing_id",
                    "name": "salida",
                    "mimeType": "application/vnd.google-apps.folder",
                }
            ]
        }
        backend = ServiceAccountDriveBackend(service, "root123")
        result = backend.ensure_output_dir("salida")
        self.assertEqual(result, "existing_id")
        service.files.return_value.create.assert_not_called()

    def test_caches_repeated_calls(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "salida_id"
        }
        backend = ServiceAccountDriveBackend(service, "root123")

        backend.ensure_output_dir("salida")
        backend.ensure_output_dir("salida")

        self.assertEqual(service.files.return_value.create.call_count, 1)

    def test_creates_multi_level_nested_path(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        created_ids = iter(["id_a", "id_b"])
        service.files.return_value.create.return_value.execute.side_effect = (
            lambda: {"id": next(created_ids)}
        )

        backend = ServiceAccountDriveBackend(service, "root123")
        result = backend.ensure_output_dir("a/b")

        self.assertEqual(result, "id_b")
        self.assertEqual(service.files.return_value.create.call_count, 2)


class TestUploadFrame(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_missing_local_file_raises(self) -> None:
        service = _make_service()
        backend = ServiceAccountDriveBackend(service, "root123")
        with self.assertRaises(DriveBackendError):
            backend.upload_frame(self._tmpdir / "nope.png", "root123", frame_num=1)

    def test_creates_new_file_when_not_existing(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "file1",
            "name": "frame_000001.png",
        }
        src = self._tmpdir / "frame_000001.png"
        src.write_bytes(b"fake-png")

        backend = ServiceAccountDriveBackend(service, "root123")
        result = backend.upload_frame(src, "root123", frame_num=1)

        self.assertEqual(result["name"], "frame_000001.png")
        service.files.return_value.create.assert_called_once()
        service.files.return_value.update.assert_not_called()

    def test_updates_existing_file_instead_of_duplicating(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {"id": "existing_file", "name": "frame_000001.png", "mimeType": "image/png"}
            ]
        }
        service.files.return_value.update.return_value.execute.return_value = {
            "id": "existing_file",
            "name": "frame_000001.png",
        }
        src = self._tmpdir / "frame_000001.png"
        src.write_bytes(b"fake-png")

        backend = ServiceAccountDriveBackend(service, "root123")
        backend.upload_frame(src, "root123", frame_num=1)

        service.files.return_value.update.assert_called_once()
        service.files.return_value.create.assert_not_called()

    def test_preserve_name_false_uses_frame_pattern(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {"id": "f1"}
        src = self._tmpdir / "anything.png"
        src.write_bytes(b"x")

        backend = ServiceAccountDriveBackend(service, "root123")
        backend.upload_frame(src, "root123", frame_num=42, preserve_name=False)

        created_body = service.files.return_value.create.call_args.kwargs["body"]
        self.assertEqual(created_body["name"], "frame_000042.png")

    def test_subdir_creates_nested_folder_first(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        create_calls = []

        def fake_create(**kwargs):
            body = kwargs["body"]
            create_calls.append(body)
            mock_result = MagicMock()
            if body.get("mimeType") == "application/vnd.google-apps.folder":
                mock_result.execute.return_value = {"id": "subdir_id"}
            else:
                mock_result.execute.return_value = {"id": "file_id", "name": body["name"]}
            return mock_result

        service.files.return_value.create.side_effect = fake_create
        src = self._tmpdir / "beauty_000001.exr"
        src.write_bytes(b"x")

        backend = ServiceAccountDriveBackend(service, "root123")
        backend.upload_frame(src, "root123", frame_num=1, subdir="beauty")

        self.assertEqual(len(create_calls), 2)
        self.assertEqual(create_calls[0]["name"], "beauty")
        self.assertEqual(create_calls[1]["parents"], ["subdir_id"])


class TestListFrameNumbers(unittest.TestCase):
    def test_lists_frames_recursively_through_subfolders(self) -> None:
        service = _make_service()

        def fake_list(**kwargs):
            q = kwargs["q"]
            mock_result = MagicMock()
            if "'root123' in parents" in q:
                mock_result.execute.return_value = {
                    "files": [
                        {
                            "id": "sub1",
                            "name": "beauty",
                            "mimeType": "application/vnd.google-apps.folder",
                        },
                        {"id": "f1", "name": "frame_000001.png", "mimeType": "image/png"},
                    ]
                }
            elif "'sub1' in parents" in q:
                mock_result.execute.return_value = {
                    "files": [
                        {
                            "id": "f2",
                            "name": "beauty_000002.exr",
                            "mimeType": "image/x-exr",
                        },
                        {"id": "f3", "name": "notes.txt", "mimeType": "text/plain"},
                    ]
                }
            else:
                mock_result.execute.return_value = {"files": []}
            return mock_result

        service.files.return_value.list.side_effect = fake_list

        backend = ServiceAccountDriveBackend(service, "root123")
        result = backend.list_frame_numbers("root123")

        self.assertEqual(result, [1, 2])

    def test_empty_folder_returns_empty_list(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertEqual(backend.list_frame_numbers("root123"), [])


class TestSaveLoadState(unittest.TestCase):
    def test_save_creates_state_folder_and_file(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "estado_folder"
        }

        backend = ServiceAccountDriveBackend(service, "root123")
        state = backend.save_state("root123", last_frame=5, total_frames=10)

        self.assertEqual(state.last_frame, 5)
        self.assertEqual(state.total_frames, 10)
        # una create() para la carpeta _estado, otra para render_state.json
        self.assertEqual(service.files.return_value.create.call_count, 2)

    def test_load_state_no_existing_file_returns_zero(self) -> None:
        service = _make_service()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}
        service.files.return_value.create.return_value.execute.return_value = {
            "id": "estado_folder"
        }
        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertEqual(backend.load_state("root123", total_frames=10), 0)

    def test_load_state_mismatched_total_frames_returns_zero(self) -> None:
        service = _make_service()

        def fake_list(**kwargs):
            q = kwargs["q"]
            mock_result = MagicMock()
            if "render_state.json" in q:
                mock_result.execute.return_value = {
                    "files": [
                        {
                            "id": "state_file",
                            "name": "render_state.json",
                            "mimeType": "application/json",
                        }
                    ]
                }
            else:
                mock_result.execute.return_value = {"files": []}
            return mock_result

        service.files.return_value.list.side_effect = fake_list
        stored = json.dumps(
            {"last_frame": 7, "total_frames": 99, "timestamp": "x", "session_id": "y"}
        ).encode("utf-8")
        service.files.return_value.get_media.return_value.execute.return_value = stored

        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertEqual(backend.load_state("root123", total_frames=10), 0)

    def test_load_state_matching_total_frames_returns_last_frame(self) -> None:
        service = _make_service()

        def fake_list(**kwargs):
            q = kwargs["q"]
            mock_result = MagicMock()
            if "render_state.json" in q:
                mock_result.execute.return_value = {
                    "files": [
                        {
                            "id": "state_file",
                            "name": "render_state.json",
                            "mimeType": "application/json",
                        }
                    ]
                }
            else:
                mock_result.execute.return_value = {"files": []}
            return mock_result

        service.files.return_value.list.side_effect = fake_list
        stored = json.dumps(
            {"last_frame": 7, "total_frames": 10, "timestamp": "x", "session_id": "y"}
        ).encode("utf-8")
        service.files.return_value.get_media.return_value.execute.return_value = stored

        backend = ServiceAccountDriveBackend(service, "root123")
        self.assertEqual(backend.load_state("root123", total_frames=10), 7)


class TestFromColabSecrets(unittest.TestCase):
    def test_raises_outside_colab(self) -> None:
        with patch.dict(sys.modules, {"google.colab": None, "google": None}):
            with self.assertRaises(DriveBackendError) as ctx:
                ServiceAccountDriveBackend.from_colab_secrets()
            self.assertIn("Colab", str(ctx.exception))

    def test_raises_on_invalid_json_secret(self) -> None:
        fake_userdata = MagicMock()
        fake_userdata.get.side_effect = lambda name: (
            "not-valid-json{" if name == "GDRIVE_SERVICE_ACCOUNT_JSON" else "folder123"
        )
        fake_colab = MagicMock()
        fake_colab.userdata = fake_userdata
        with patch.dict(sys.modules, {"google.colab": fake_colab}):
            with self.assertRaises(DriveBackendError) as ctx:
                ServiceAccountDriveBackend.from_colab_secrets()
            self.assertIn("JSON", str(ctx.exception))

    def test_raises_when_secret_missing(self) -> None:
        fake_userdata = MagicMock()
        fake_userdata.get.side_effect = Exception("secret no encontrado")
        fake_colab = MagicMock()
        fake_colab.userdata = fake_userdata
        with patch.dict(sys.modules, {"google.colab": fake_colab}):
            with self.assertRaises(DriveBackendError) as ctx:
                ServiceAccountDriveBackend.from_colab_secrets()
            self.assertIn("GDRIVE_SERVICE_ACCOUNT_JSON", str(ctx.exception))

    def test_happy_path_builds_and_verifies_backend(self) -> None:
        fake_sa_info = {
            "type": "service_account",
            "client_email": "bot@example.iam.gserviceaccount.com",
        }
        fake_userdata = MagicMock()
        fake_userdata.get.side_effect = lambda name: (
            json.dumps(fake_sa_info)
            if name == "GDRIVE_SERVICE_ACCOUNT_JSON"
            else "folder123"
        )
        fake_colab = MagicMock()
        fake_colab.userdata = fake_userdata

        fake_service = _make_service()
        fake_service.files.return_value.get.return_value.execute.return_value = {
            "id": "folder123",
            "name": "BlenderColabRender",
            "mimeType": "application/vnd.google-apps.folder",
        }

        with patch.dict(sys.modules, {"google.colab": fake_colab}), patch(
            "google.oauth2.service_account.Credentials.from_service_account_info"
        ) as mock_creds, patch(
            "googleapiclient.discovery.build", return_value=fake_service
        ) as mock_build:
            mock_creds.return_value = MagicMock()
            backend = ServiceAccountDriveBackend.from_colab_secrets()

        self.assertIsInstance(backend, ServiceAccountDriveBackend)
        mock_build.assert_called_once()
        fake_service.files.return_value.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
