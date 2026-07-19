# 11 — Notebook de Colab (notebooks/blender_render.ipynb)

**What to build:** El notebook final que se ejecuta en Google Colab. Capa delgada sobre src/bcr: las celdas importan y configuran, no reimplementan logica. Incluye: celdas de formulario (#@param) para config, montaje de Drive, descarga de .blend + aprovisionamiento de Blender (en paralelo), ejecucion del orquestador, UI de progreso. Sin emojis.

**Blocked by:** 01-config, 02-link-resolver, 03-blender-provisioning, 05-state-manager, 06-render-orchestrator, 07-drive-sync, 08-progress-ui, 09-custom-script-loader, 10-blender-driver-script (todo el paquete debe estar implementado)

**Status:** ready-for-agent

- [ ] Celda 1: Montaje de Google Drive
- [ ] Celda 2: Formularios de configuracion (#@param)
- [ ] Celda 3: Instalacion de dependencias pip (gdown, ipywidgets)
- [ ] Celda 4: Descarga del .blend + aprovisionamiento de Blender (en paralelo)
- [ ] Celda 5: Validacion y preparacion
- [ ] Celda 6: Ejecucion del render con UI de progreso
- [ ] Celda 7: Resumen final y verificacion
