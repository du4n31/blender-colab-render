# 07 — Sincronizacion con Drive (drive_sync.py)

**What to build:** capa fina sobre shutil/os para operaciones de archivo contra Drive montado. Validar que Drive este montado, copiar archivos con nombre estandarizado (`frame_%06d.png`), borrar locales, crear estructura de directorios.

**Blocked by:** 01-config (usa OUTPUT_DIR_PATTERN, DRIVE_MOUNT_POINT)

**Status:** ready-for-agent

- [ ] `ensure_drive_mounted() -> bool` — verifica que /content/drive existe
- [ ] `ensure_output_dir(drive_path: str) -> Path` — crea directorio si no existe
- [ ] `upload_frame(local_path: str, drive_path: str, frame_num: int) -> Path` — copia con nombre estandarizado
- [ ] `remove_local(local_path: str) -> None` — borra archivo local post-subida
- [ ] `list_frames_in_drive(drive_path: str) -> list[int]` — lista frames ya subidos
- [ ] Pruebas con tmp_path simulando la estructura de Drive
