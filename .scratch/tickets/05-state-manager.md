# 05 — Gestor de estado / reanudacion (state_manager.py)

**What to build:** Lee y escribe un archivo JSON de estado en la ruta de Drive (`<ruta_drive>/_estado/render_state.json`) que registra el ultimo frame completado. Al reanudar, reconcilia contra los archivos realmente presentes en Drive y usa el valor mas conservador.

**Blocked by:** None — independiente (solo IO de archivos)

**Status:** ready-for-agent

- [ ] `save_state(drive_path: str, last_frame: int, total_frames: int) -> None`
- [ ] `load_state(drive_path: str, total_frames: int) -> int` — devuelve el frame desde el cual reanudar
- [ ] `reconcile_with_files(drive_path: str, state_last_frame: int) -> int` — verifica archivos reales en Drive
- [ ] Formato del JSON: `{last_frame, total_frames, timestamp, session_id}`
- [ ] Pruebas con archivos temporales (pytest, tmp_path)
