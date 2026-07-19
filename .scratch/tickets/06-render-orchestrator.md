# 06 — Orquestador de render (render_orchestrator.py)

**What to build:** Corazon del sistema. Lanza Blender como subproceso no bloqueante, lee su stdout en tiempo real buscando lineas `Saved: '<ruta>'`, y por cada frame detectado lo encola para subir a Drive en un ThreadPoolExecutor. Calcula metricas de progreso (tiempo/frame, promedio, restante, ETA, porcentaje). Al finalizar o si el proceso se cae, hace reconciliacion de frames pendientes.

**Blocked by:** 03-blender-provisioning (necesita ruta al binario), 04-device-config (usa el script), 05-state-manager (guarda/recupera estado)

**Status:** ready-for-agent

- [ ] `RenderOrchestrator` class con config, blender_path, drive_path
- [ ] `build_command()` — construye la lista de args de blender en el ORDEN correcto (§6.2)
- [ ] `run()` — lanza subprocess.Popen con stdout en pipe
- [ ] `_parse_stdout()` — iterador que detecta lineas `Saved:` por frame
- [ ] `_upload_worker()` — ThreadPoolExecutor que copia a Drive + borra local
- [ ] `_reconcile_pending()` — al finalizar, sube frames que falten
- [ ] `_compute_metrics()` — tiempo/frame, promedio, pendiente, ETA
- [ ] Control de backlog local (limite de frames pendientes de subir)
- [ ] Callbacks para actualizar UI de progreso
- [ ] Pruebas: build_command con distintas configs, parseo de stdout con fixtures
