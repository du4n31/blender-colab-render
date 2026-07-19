# 01 — Modulo de configuracion (config.py)

**What to build:** Constantes de configuracion (version de Blender, URLs de descarga, rutas por defecto) y funciones de validacion de entrada (URL, rango de frames, ruta de Drive). El resto del paquete importa las constantes desde aqui.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] Constantes: BLENDER_VERSION, BLENDER_DOWNLOAD_URL, RENDER_OUTPUT_PATTERN, DRIVE_MOUNT_POINT, OUTPUT_DIR_PATTERN, BACKLOG_LIMIT
- [ ] Funcion `validate_frame_range(start, end) -> tuple[int, int]`
- [ ] Funcion `validate_drive_path(path: str) -> str` (normaliza y verifica que sea bajo /content/drive)
- [ ] Funcion `validate_url(url: str) -> bool` (valida formato basico)
