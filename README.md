# Blender Colab Render

Renderiza escenas de Blender usando las GPUs T4 gratuitas de Google Colab.

Cada frame se sube a Drive individualmente apenas termina, en paralelo con el render del frame siguiente. Si la sesion de Colab se interrumpe, puedes reanudar desde el ultimo frame confirmado.

## Requisitos

- Cuenta de Google con Google Drive
- Una escena de Blender lista para renderizar
- Enlace publico al archivo `.blend` (subido a Drive, Dropbox, MediaFire o enlace directo)

## Como usar

### 1. Abrir el notebook en Colab

Abre `notebooks/blender_render.ipynb` en [Google Colab](https://colab.research.google.com/)
y selecciona un runtime con GPU (T4).

### 2. Ejecutar las celdas en orden

1. **Montar Google Drive**: la primera celda te pedira autorizacion OAuth.
2. **Configurar parametros**: pega el enlace de tu `.blend`, el rango de frames,
   la ruta de destino en Drive, el modo de salida (compositor o sequencer) y
   el dispositivo (CPU/CUDA/OptiX).
3. **Instalar dependencias**: se instalan `requests`, `gdown` e `ipywidgets`.
4. **Preparacion**: el notebook descarga el `.blend` y aprovisiona Blender.
   El binario de Blender se cachea en Drive para sesiones futuras.
5. **Render**: el monitor muestra en vivo el progreso, tiempo por frame,
   promedio, tiempo restante y hora estimada de finalizacion.

### 3. Reanudacion

Si la sesion de Colab se interrumpe (limite de 5h), vuelve a ejecutar el notebook
con la misma configuracion. La reanudacion es automatica: detecta el ultimo frame
completado y continua desde ahi.

## Ajustes de render

Todos los ajustes de la escena (samples, resolucion, motor, formato de imagen)
se configuran **en el archivo `.blend`**, no en el notebook. El notebook solo
expone:

| Ajuste | Donde se configura |
|---|---|
| Samples, resolucion, motor, formato | En el `.blend` desde Blender en tu PC |
| Compositor vs. secuenciador | En el notebook (afecta el ensamblado de salida) |
| GPU/CPU/OptiX | En el notebook (son preferencias de la maquina, no de la escena) |
| Rango de frames | En el notebook |
| Scripts personalizados | En el notebook (opcional) |

## Estructura del proyecto

```
src/bcr/              Paquete Python con la logica de orquestacion
  config.py           Constantes y validacion
  link_resolver.py    Resolucion de enlaces por proveedor
  blender_provisioning.py  Descarga y cache de Blender
  device_config.py    Configuracion GPU/CPU/OptiX (para ejecutar dentro de Blender)
  state_manager.py    Archivo de estado para reanudacion
  render_orchestrator.py  Lanzamiento de Blender, monitoreo y subida paralela
  drive_sync.py       Copia de frames a Drive
  progress_ui.py      Widgets de progreso con ipywidgets
  custom_script_loader.py  Carga de scripts .py personalizados
blender_scripts/      Scripts que se ejecutan dentro de Blender
  render_frame_driver.py  Configura dispositivo y modo de salida
notebooks/            Notebook de Colab (punto de entrada)
  blender_render.ipynb
tests/                Pruebas automatizadas (pytest, sin GPU)
docs/                 Documentacion
```

## Desarrollo

```bash
# Entorno virtual
python3 -m venv venv
source venv/bin/activate

# Dependencias de desarrollo
pip install pytest pytest-mock requests gdown

# Ejecutar pruebas
PYTHONPATH=src python -m pytest tests/ -v
```

## Arquitectura

Ver `docs/ARCHITECTURE.md` para una descripcion detallada de los modulos,
el flujo de datos y las decisiones de diseno.

## Licencia

MIT
