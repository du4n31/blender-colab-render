"""Alternative Drive API backend (service account), without requiring
de montar Drive interactivamente con google.colab.drive.mount().

Enable this option with DRIVE_ACCESS_MODE="service_account" in the notebook;
the default mode (mounted Drive) to change its existing behavior,
see render_orchestrator.py and state_manager.py, which accept
an optional backend (None by default, preserving current behavior).

Two Colab Secrets are required:
  - GDRIVE_SERVICE_ACCOUNT_JSON: the full JSON contents for the
    service account (con la Drive API habilitada en el proyecto de GCP).
  - GDRIVE_FOLDER_ID: Drive folder ID (shared with the service-account email
    service account; client_email in that JSON) that acts as
    raiz para este backend.
"""

import json
from pathlib import Path
from typing import Optional

from bcr.config import RENDERED_IMAGE_EXTENSIONS, STATE_DIR_NAME, STATE_FILE_NAME, extract_frame_number
from bcr.state_manager import RenderState

_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
_SA_SECRET_NAME = "GDRIVE_SERVICE_ACCOUNT_JSON"
_FOLDER_SECRET_NAME = "GDRIVE_FOLDER_ID"


class DriveBackendError(Exception):
    """Error raised by the Drive API backend (service account)."""


class ServiceAccountDriveBackend:
    """Drive backend that uses the v3 API with a service account.

    It serves the same role as drive_sync.py + state_manager.py when Drive
    is mounted (upload frames, create folders, list existing frames,
    save/load state), without drive.mount() or interactive authorization:
    authentication uses a service account read from Colab Secrets.
    """

    def __init__(self, service, root_folder_id: str):
        self._service = service
        self._root_folder_id = root_folder_id
        # Cache de rutas relativas ya resueltas -> folder_id, para no
        # repetir busquedas en cada frame.
        self._folder_cache: dict[str, str] = {"": root_folder_id}

    # ------------------------------------------------------------------
    # Conexion
    # ------------------------------------------------------------------

    @classmethod
    def from_colab_secrets(cls) -> "ServiceAccountDriveBackend":
        """Build the backend by reading credentials from Colab Secrets.

        Raises:
            DriveBackendError: if a secret is missing, the JSON is invalid,
                required libraries are not installed, or the folder is not
                accesible con esas credenciales.
        """
        try:
            from google.colab import userdata
        except ImportError as exc:
            msg = "ServiceAccountDriveBackend is only available in Google Colab."
            raise DriveBackendError(msg) from exc

        try:
            sa_raw = userdata.get(_SA_SECRET_NAME)
        except Exception as exc:
            msg = (
                f"Could not read the secret '{_SA_SECRET_NAME}'. Create it in "
                "Colab -> Secrets, with the complete service-account JSON "
                "account, y activa el acceso para este notebook."
            )
            raise DriveBackendError(msg) from exc

        try:
            folder_id = userdata.get(_FOLDER_SECRET_NAME)
        except Exception as exc:
            msg = (
                f"Could not read the secret '{_FOLDER_SECRET_NAME}'. Create it "
                "in Colab -> Secrets, with the Drive folder ID "
                "(la parte final de su URL)."
            )
            raise DriveBackendError(msg) from exc

        try:
            sa_info = json.loads(sa_raw)
        except json.JSONDecodeError as exc:
            msg = f"Secret '{_SA_SECRET_NAME}' does not contain valid JSON."
            raise DriveBackendError(msg) from exc

        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            msg = (
                "Faltan las librerias google-auth / google-api-python-client. "
                "Instalalas con pip antes de usar este backend."
            )
            raise DriveBackendError(msg) from exc

        try:
            creds = Credentials.from_service_account_info(sa_info, scopes=_DRIVE_SCOPES)
            service = build("drive", "v3", credentials=creds, cache_discovery=False)
        except Exception as exc:
            msg = f"Could not authenticate with the service account: {exc}"
            raise DriveBackendError(msg) from exc

        backend = cls(service, folder_id)
        backend.ensure_connected()
        return backend

    def ensure_connected(self) -> bool:
        """Verify that the root folder is accessible with these credentials.

        Returns:
            True if the folder is accessible.

        Raises:
            DriveBackendError: if the folder does not exist, is not a folder,
                or has not been shared with the service-account email.
        """
        try:
            meta = (
                self._service.files()
                .get(fileId=self._root_folder_id, fields="id, name, mimeType")
                .execute()
            )
        except Exception as exc:
            msg = (
                f"Could not access folder {self._root_folder_id}. "
                "Verifica que la compartiste con el email de la service "
                f"account (client_email dentro del JSON). Detalle: {exc}"
            )
            raise DriveBackendError(msg) from exc

        if meta.get("mimeType") != _FOLDER_MIME_TYPE:
            msg = f"{self._root_folder_id} is not a Google Drive folder."
            raise DriveBackendError(msg)
        return True

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    def ensure_output_dir(self, relative_path: str = "") -> str:
        """Find or create a nested folder path under the root.

        Args:
            relative_path: Subfolders separated by "/", relative to the
                root folder (GDRIVE_FOLDER_ID). An empty string means the root folder.

        Returns:
            The final folder_id (str). Pass it wherever
            drive_sync/state_manager esperan un Path -- este backend solo
            the ID string is needed; it is never treated as a filesystem path.
        """
        relative_path = relative_path.strip("/")
        if relative_path in self._folder_cache:
            return self._folder_cache[relative_path]

        parts = [p for p in relative_path.split("/") if p]
        current_id = self._root_folder_id
        accumulated = ""
        for part in parts:
            accumulated = f"{accumulated}/{part}" if accumulated else part
            if accumulated in self._folder_cache:
                current_id = self._folder_cache[accumulated]
                continue
            current_id = self._find_or_create_folder(current_id, part)
            self._folder_cache[accumulated] = current_id

        self._folder_cache[relative_path] = current_id
        return current_id

    def _find_or_create_folder(self, parent_id: str, name: str) -> str:
        existing = self._find_child(parent_id, name, mime_type=_FOLDER_MIME_TYPE)
        if existing is not None:
            return existing["id"]
        metadata = {"name": name, "mimeType": _FOLDER_MIME_TYPE, "parents": [parent_id]}
        try:
            created = self._service.files().create(body=metadata, fields="id").execute()
        except Exception as exc:
            msg = f"Failed to create folder '{name}' en Drive: {exc}"
            raise DriveBackendError(msg) from exc
        return created["id"]

    def _find_child(
        self, parent_id: str, name: str, mime_type: Optional[str] = None
    ) -> Optional[dict]:
        safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{parent_id}' in parents and trashed = false and name = '{safe_name}'"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        try:
            resp = (
                self._service.files()
                .list(q=query, fields="files(id, name, mimeType)", pageSize=10)
                .execute()
            )
        except Exception as exc:
            msg = f"Failed to find '{name}' en Drive: {exc}"
            raise DriveBackendError(msg) from exc
        files = resp.get("files", [])
        return files[0] if files else None

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    def upload_frame(
        self,
        local_path: Path,
        folder_id,
        frame_num: int,
        subdir: str = "",
        preserve_name: bool = True,
    ) -> dict:
        """Sube un frame rendering a Drive via API.

        Misma logica de nombrado que drive_sync.upload_frame: preserva el
        original name by default (avoids collisions between multiple
        salidas por frame), o usa frame_%06d.ext si preserve_name=False.

        Args:
            local_path: Local path to the rendered file.
            folder_id: folder ID (str) of the Drive output folder.
            frame_num: Numero de frame (para el nombre fallback).
            subdir: Optional subfolder (e.g. a File Output node name).
            preserve_name: Si True, preserva el nombre original.

        Raises:
            DriveBackendError: if the local file does not exist or upload fails.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            msg = f"Local file does not exist: {local_path}"
            raise DriveBackendError(msg)

        if preserve_name:
            dest_filename = local_path.name
        else:
            suffix = local_path.suffix if local_path.suffix else ".png"
            dest_filename = f"frame_{frame_num:06d}{suffix}"

        target_folder_id = str(folder_id)
        if subdir:
            target_folder_id = self._find_or_create_folder(target_folder_id, subdir)

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            msg = "google-api-python-client is required to upload files."
            raise DriveBackendError(msg) from exc

        try:
            media = MediaFileUpload(str(local_path), resumable=False)
            existing = self._find_child(target_folder_id, dest_filename)
            if existing is not None:
                result = (
                    self._service.files()
                    .update(fileId=existing["id"], media_body=media, fields="id, name")
                    .execute()
                )
            else:
                metadata = {"name": dest_filename, "parents": [target_folder_id]}
                result = (
                    self._service.files()
                    .create(body=metadata, media_body=media, fields="id, name")
                    .execute()
                )
        except DriveBackendError:
            raise
        except Exception as exc:
            msg = f"Failed to upload '{dest_filename}' a Drive: {exc}"
            raise DriveBackendError(msg) from exc

        return result

    def list_frame_numbers(self, folder_id) -> list:
        """List uploaded frame numbers by traversing subfolders.

        Uses extract_frame_number() (exactly six digits), the same
        function used by the orchestrator to detect "Saved:" lines and by
        drive_sync.list_frames_in_drive -- para mantener consistencia.
        """
        frames: list = []
        stack = [str(folder_id)]
        while stack:
            current = stack.pop()
            page_token = None
            while True:
                try:
                    resp = (
                        self._service.files()
                        .list(
                            q=f"'{current}' in parents and trashed = false",
                            fields="nextPageToken, files(id, name, mimeType)",
                            pageToken=page_token,
                            pageSize=100,
                        )
                        .execute()
                    )
                except Exception as exc:
                    msg = f"Failed to list files in Drive: {exc}"
                    raise DriveBackendError(msg) from exc

                for entry in resp.get("files", []):
                    if entry.get("mimeType") == _FOLDER_MIME_TYPE:
                        stack.append(entry["id"])
                    else:
                        if Path(entry["name"]).suffix.lower() not in RENDERED_IMAGE_EXTENSIONS:
                            continue
                        frame_num = extract_frame_number(entry["name"])
                        if frame_num is not None:
                            frames.append(frame_num)

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

        return sorted(set(frames))

    # ------------------------------------------------------------------
    # State (for resuming)
    # ------------------------------------------------------------------

    def save_state(self, folder_id, last_frame: int, total_frames: int) -> RenderState:
        """Save render state to Drive through the API (equivalent to
        state_manager.save_state, but without a mounted filesystem)."""
        state_folder_id = self._find_or_create_folder(str(folder_id), STATE_DIR_NAME)
        state = RenderState(last_frame=last_frame, total_frames=total_frames)
        content = json.dumps(state.to_dict(), indent=2).encode("utf-8")

        try:
            from googleapiclient.http import MediaInMemoryUpload
        except ImportError as exc:
            msg = "google-api-python-client is required to save state."
            raise DriveBackendError(msg) from exc

        media = MediaInMemoryUpload(content, mimetype="application/json")
        try:
            existing = self._find_child(state_folder_id, STATE_FILE_NAME)
            if existing is not None:
                self._service.files().update(fileId=existing["id"], media_body=media).execute()
            else:
                metadata = {"name": STATE_FILE_NAME, "parents": [state_folder_id]}
                self._service.files().create(body=metadata, media_body=media).execute()
        except Exception as exc:
            msg = f"Failed to save state to Drive: {exc}"
            raise DriveBackendError(msg) from exc

        return state

    def load_state(self, folder_id, total_frames: int) -> int:
        """Load the last confirmed frame from the state stored in Drive.

        Like state_manager.load_state: return 0 if no state exists
        previo, si el JSON esta corrupto, o si total_frames no coincide
        (trabajo nuevo con distinta duracion).
        """
        try:
            state_folder_id = self._find_or_create_folder(str(folder_id), STATE_DIR_NAME)
            existing = self._find_child(state_folder_id, STATE_FILE_NAME)
            if existing is None:
                return 0
            raw = self._service.files().get_media(fileId=existing["id"]).execute()
            data = json.loads(raw)
            state = RenderState.from_dict(data)
        except DriveBackendError:
            raise
        except Exception:
            return 0

        if state.total_frames != total_frames:
            return 0
        return max(0, state.last_frame)
