# 08 — Interfaz de progreso (progress_ui.py)

**What to build:** Widgets ipywidgets para mostrar en vivo: frame actual/total, porcentaje, tiempo del ultimo frame, promedio, tiempo restante estimado, hora estimada de finalizacion, estado de la cola de subida. Texto limpio, sin emojis.

**Blocked by:** None — independiente (solo UI, recibe datos por callback)

**Status:** ready-for-agent

- [ ] `RenderProgressUI` — clase que crea y actualiza widgets
- [ ] `update(frame, total, last_time, avg_time, eta, upload_queue_size)` — actualiza todos los campos
- [ ] `show_warning(message)` — muestra advertencia (ej: GPU no disponible)
- [ ] `show_error(message)` — muestra error fatal
- [ ] `show_completion()` — muestra resumen final
- [ ] Pruebas: verificar que los widgets se crean y actualizan sin error
