"""Backend alternativo de Drive via API (service account), sin necesidad
de montar Drive interactivamente con google.colab.drive.mount().

Se activa como opcion (DRIVE_ACCESS_MODE="service_account" en el notebook);
el modo por defecto (Drive montado) sigue funcionando exactamente igual,
sin cambios -- ver render_orchestrator.py y state_manager.py, que aceptan
un backend opcional (por defecto None = comportamiento actual).

Requiere dos secretos de Colab:
  - GDRIVE_SERVICE_ACCOUNT_JSON: contenido completo del JSON de la
    service account (con la Drive API habilitada en el proyecto de GCP).
  - GDRIVE_FOLDER_ID: ID de la carpeta de Drive (compartida con el email
    de la service account, client_email dentro del JSON) que actua como
    raiz para este backend.
"""

import json
from pathlib import Path
from typing import Optional

from bcr.config import STATE_DIR_NAME, STATE_FILE_NAME, extract_frame_number
from bcr.state_manager import RenderState

_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
_SA_SECRET_NAME = "GDRIVE_SERVICE_ACCOUNT_JSON"
_FOLDER_SECRET_NAME = "GDRIVE_FOLDER_ID"


class DriveBackendError(Exception):
    """Error al usar el backend de Drive via API (service account)."""


class ServiceAccountDriveBackend:
    """Backend de Drive que usa la API v3 con una service account.

    Cumple el mismo rol que drive_sync.py + state_manager.py cuando Drive
    esta montado (subir frames, crear carpetas, listar frames existentes,
    guardar/cargar estado), pero sin drive.mount() ni intervencion humana:
    la autenticacion es por service account, leida desde secretos de Colab.
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
        """Construye el backend leyendo credenciales desde secretos de Colab.

        Raises:
            DriveBackendError: si falta un secreto, el JSON es invalido,
                las librerias no estan instaladas, o la carpeta no es
                accesible con esas credenciales.
        """
        try:
            from google.colab import userdata
        except ImportError as exc:
            msg = "ServiceAccountDriveBackend solo esta disponible en Google Colab."
            raise DriveBackendError(msg) from exc

        try:
            sa_raw = userdata.get(_SA_SECRET_NAME)
        except Exception as exc:
            msg = (
                f"No se pudo leer el secreto '{_SA_SECRET_NAME}'. Creal en "
                "Colab -> Secretos, con el JSON completo de la service "
                "account, y activa el acceso para este notebook."
            )
            raise DriveBackendError(msg) from exc

        try:
            folder_id = userdata.get(_FOLDER_SECRET_NAME)
        except Exception as exc:
            msg = (
                f"No se pudo leer el secreto '{_FOLDER_SECRET_NAME}'. Creal "
                "en Colab -> Secretos, con el ID de la carpeta de Drive "
                "(la parte final de su URL)."
            )
            raise DriveBackendError(msg) from exc

        try:
            sa_info = json.loads(sa_raw)
        except json.JSONDecodeError as exc:
            msg = f"El secreto '{_SA_SECRET_NAME}' no contiene JSON valido."
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
            msg = f"No se pudo autenticar con la service account: {exc}"
            raise DriveBackendError(msg) from exc

        backend = cls(service, folder_id)
        backend.ensure_connected()
        return backend

    def ensure_connected(self) -> bool:
        """Verifica que la carpeta raiz sea accesible con estas credenciales.

        Returns:
            True si la carpeta es accesible.

        Raises:
            DriveBackendError: si la carpeta no existe, no es una carpeta,
                o no fue compartida con el email de la service account.
        """
        try:
            meta = (
                self._service.files()
                .get(fileId=self._root_folder_id, fields="id, name, mimeType")
                .execute()
            )
        except Exception as exc:
            msg = (
                f"No se pudo acceder a la carpeta {self._root_folder_id}. "
                "Verifica que la compartiste con el email de la service "
                f"account (client_email dentro del JSON). Detalle: {exc}"
            )
            raise DriveBackendError(msg) from exc

        if meta.get("mimeType") != _FOLDER_MIME_TYPE:
            msg = f"{self._root_folder_id} no es una carpeta de Drive."
            raise DriveBackendError(msg)
        return True

    # ------------------------------------------------------------------
    # Carpetas
    # ------------------------------------------------------------------

    def ensure_output_dir(self, relative_path: str = "") -> str:
        """Encuentra o crea una ruta de carpetas anidada bajo la raiz.

        Args:
            relative_path: Subcarpetas separadas por "/", relativas a la
                carpeta raiz (GDRIVE_FOLDER_ID). Cadena vacia = la raiz.

        Returns:
            El folder_id (str) de la carpeta final. Se puede pasar donde
            drive_sync/state_manager esperan un Path -- este backend solo
            necesita el string, nunca lo trata como ruta de filesystem.
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
            msg = f"Error al crear la carpeta '{name}' en Drive: {exc}"
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
            msg = f"Error al buscar '{name}' en Drive: {exc}"
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
        """Sube un frame renderizado a Drive via API.

        Misma logica de nombrado que drive_sync.upload_frame: preserva el
        nombre original por defecto (evita colisiones entre multiples
        salidas por frame), o usa frame_%06d.ext si preserve_name=False.

        Args:
            local_path: Ruta local al archivo renderizado.
            folder_id: folder_id (str) de la carpeta de salida en Drive.
            frame_num: Numero de frame (para el nombre fallback).
            subdir: Subcarpeta opcional (ej: nombre del nodo File Output).
            preserve_name: Si True, preserva el nombre original.

        Raises:
            DriveBackendError: si el archivo local no existe o falla la subida.
        """
        local_path = Path(local_path)
        if not local_path.exists():
            msg = f"El archivo local no existe: {local_path}"
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
            msg = "Falta google-api-python-client para subir archivos."
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
            msg = f"Error al subir '{dest_filename}' a Drive: {exc}"
            raise DriveBackendError(msg) from exc

        return result

    def list_frame_numbers(self, folder_id) -> list:
        """Lista numeros de frame ya subidos, recorriendo subcarpetas.

        Usa extract_frame_number() (exactamente 6 digitos) -- la misma
        funcion que usa el orquestador para detectar "Saved:" y que usa
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
                    msg = f"Error al listar archivos en Drive: {exc}"
                    raise DriveBackendError(msg) from exc

                for entry in resp.get("files", []):
                    if entry.get("mimeType") == _FOLDER_MIME_TYPE:
                        stack.append(entry["id"])
                    else:
                        frame_num = extract_frame_number(entry["name"])
                        if frame_num is not None:
                            frames.append(frame_num)

                page_token = resp.get("nextPageToken")
                if not page_token:
                    break

        return sorted(set(frames))

    # ------------------------------------------------------------------
    # Estado (para reanudacion)
    # ------------------------------------------------------------------

    def save_state(self, folder_id, last_frame: int, total_frames: int) -> RenderState:
        """Guarda el estado del render en Drive via API (equivalente a
        state_manager.save_state, pero sin filesystem montado)."""
        state_folder_id = self._find_or_create_folder(str(folder_id), STATE_DIR_NAME)
        state = RenderState(last_frame=last_frame, total_frames=total_frames)
        content = json.dumps(state.to_dict(), indent=2).encode("utf-8")

        try:
            from googleapiclient.http import MediaInMemoryUpload
        except ImportError as exc:
            msg = "Falta google-api-python-client para guardar el estado."
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
            msg = f"Error al guardar el estado en Drive: {exc}"
            raise DriveBackendError(msg) from exc

        return state

    def load_state(self, folder_id, total_frames: int) -> int:
        """Carga el ultimo frame confirmado desde el estado en Drive.

        Igual que state_manager.load_state: devuelve 0 si no hay estado
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
