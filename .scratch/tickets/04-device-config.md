# 04 — Configuracion de dispositivo (device_config.py)

**What to build:** Script que se ejecuta DENTRO de Blender (`--python`) para configurar GPU/CPU/OptiX. En background mode Blender no puebla la lista de dispositivos sin `get_devices()`. Advertir si se pidio GPU y no esta disponible, con fallback a CPU.

**Blocked by:** None — independiente (solo usa bpy)

**Status:** ready-for-agent

- [ ] `configure_device(backend: str) -> None` — configura Cycles para CPU, CUDA u OPTIX
- [ ] Deteccion de dispositivos via `cprefs.get_devices()`
- [ ] Fallback CPU con advertencia si no hay GPU disponible
- [ ] Pruebas: validar que construye bien los argumentos (no requiere GPU real)
