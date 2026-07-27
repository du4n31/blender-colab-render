# Estrategia de pruebas

## Automatizado (pytest)

Se ejecuta con `pytest` sin necesidad de Blender ni GPU. Corre en cualquier
maquina con Python 3.10+.

### Que se prueba

| Modulo | Archivo | Que cubre |
|---|---|---|
| config | test_notebook_smoke.py | Validacion de frame range, URL, ruta Drive |
| link_resolver | test_link_resolver.py | Resolucion por proveedor, Dropbox, GDrive, MediaFire, errores HTTP |
| state_manager | test_state_manager.py | CRUD de estado, reconciliacion contra archivos, corrupcion |
| progress_ui | test_progress_ui.py | Creacion segura sin ipywidgets, format_timedelta |
| render_orchestrator | test_render_orchestrator.py | Construccion y orden de args, parseo de stdout, deteccion de Saved: |
| drive_backend | test_drive_backend.py | Backend de Drive via API (service account): carpetas, subida de frames, listado recursivo, estado, lectura de secretos |

### Como ejecutar

```bash
# Usando uv (recomendado en desarrollo)
uv run --with pytest,pytest-mock,requests,gdown,google-api-python-client,google-auth python -m pytest tests/ -v

# O con pip en un venv
python3 -m venv venv
source venv/bin/activate
pip install pytest pytest-mock requests gdown
PYTHONPATH=src python -m pytest tests/ -v
```

### Estrategia de mocking

- Las llamadas HTTP se mockean con `unittest.mock.patch`
- El subproceso de Blender no se ejecuta (solo se prueba la construccion de args)
- `bpy` no esta disponible en testing (los modulos que lo usan lo importan dentro
  de las funciones, no al nivel del modulo)

## Manual (sin automatizar)

Estas pruebas requieren una GPU T4 real en Colab y no se pueden automatizar
en una maquina de desarrollo normal.

### Checklist manual

- [ ] **Deteccion de GPU**: Ejecutar el notebook con DEVICE=OPTIX en una
      instancia T4 de Colab. Verificar que el log muestra "GPU (OPTIX)".
- [ ] **Deteccion de GPU faltante**: Ejecutar en CPU runtime. Verificar que
      muestra la advertencia de fallback a CPU.
- [ ] **Render de un frame**: Renderizar 1 frame. Confirmar que aparece en Drive.
- [ ] **Render de animacion**: Renderizar 10 frames. Confirmar que todos aparecen
      en Drive, numerados secuencialmente.
- [ ] **Subida incremental**: Durante un render de varios frames, verificar que
      los frames aparecen en Drive antes de que termine el render completo.
- [ ] **Reanudacion**: Interrumpir un render a mitad de camino. Volver a ejecutar
      el notebook. Verificar que continua desde el frame siguiente al ultimo
      completado.
- [ ] **Toggle compositor/sequencer**: Renderizar con OUTPUT_MODE=compositor y
      OUTPUT_MODE=sequencer. Verificar diferencia en el output.
- [ ] **Toggle CPU/CUDA/OptiX**: Verificar que cada opcion produce un render
      valido (aunque CPU sea mucho mas lento).
- [ ] **Script personalizado**: Subir un script .py que modifique un ajuste de
      render y verificar que se aplique.
- [ ] **MediaFire**: Probar con un enlace real de MediaFire.
- [ ] **Dropbox**: Probar con un enlace real de Dropbox.
- [ ] **Google Drive**: Probar con un enlace real de Google Drive.
- [ ] **Enlace directo**: Probar con una URL que termine en .blend.
- [ ] **Ruta de Drive personalizada**: Verificar que los frames se guardan en
      la ruta exacta configurada.
- [ ] **Sesion completa**: Una corrida completa de principio a fin en una sesion
      nueva de Colab sin editar codigo en las celdas.
