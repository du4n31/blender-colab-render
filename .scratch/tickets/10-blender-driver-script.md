# 10 — Script driver de Blender (blender_scripts/render_frame_driver.py)

**What to build:** El unico script que se ejecuta DENTRO del Python embebido de Blender (§6.1). Recibe argumentos via sys.argv (despues de `--`): `--output-mode` (compositor/sequencer) y `--cycles-device` (OPTIX/CUDA/CPU). Configura el dispositivo y el output, y se asegura de que el render se ejecute correctamente.

Usa solo stdlib + bpy — sin dependencias pip.

**Blocked by:** 04-device-config (usa la logica de configuracion de dispositivo)

**Status:** ready-for-agent

- [ ] Parsear sys.argv para `--output-mode` y `--cycles-device`
- [ ] Configurar scene.render.use_compositing / use_sequencer
- [ ] Configurar dispositivo via device_config.py (importable desde la ruta del proyecto)
- [ ] Blender imprime `Saved:` al completar cada frame — no necesita logica extra
- [ ] Manejo de errores: si falla la configuracion, abortar con codigo de salida != 0
