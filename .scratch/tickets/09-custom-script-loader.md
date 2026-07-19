# 09 — Carga de scripts personalizados (custom_script_loader.py)

**What to build:** Permite al usuario subir uno o mas scripts Python que se ejecutan dentro de Blender via `--python` adicional, o se importan dinamicamente e invocan hooks en puntos del render (render_pre, render_post, etc.) usando bpy.app.handlers.

**Blocked by:** None — independiente

**Status:** ready-for-agent

- [ ] `download_custom_script(url: str, dest_dir: str) -> str` — descarga script desde URL
- [ ] `collect_script_args(script_urls: list[str], tmp_dir: str) -> list[str]` — genera args `--python` adicionales
- [ ] Soporte para multiples scripts
- [ ] Validacion basica de que el archivo existe y es .py
