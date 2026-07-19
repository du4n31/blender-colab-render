# Arquitectura

## Vision general

Blender Colab Render es un pipeline de render que ejecuta Blender en Google Colab
y entrega los frames a Google Drive uno por uno. La arquitectura separa tres
entornos de ejecucion distintos:

```
[Notebook Colab]            [Kernel Python]                [Python embebido Blender]
  (ipywidgets, pip)            (src/bcr/)                    (bpy + stdlib)
       |                            |                              |
  Config user                  Resolver enlace                Configurar dispositivo
  Montar Drive                 Aprovisionar Blender          Configurar output mode
  UI de progreso               Orquestar subproceso          Render
  Resumen final                Leer stdout
                               Subir frames a Drive
```

## Principios de diseno

1. **El notebook es una capa delgada**: las celdas importan y configuran,
   no reimplementan logica. Todo lo importante vive en `src/bcr/`.

2. **Dos entornos Python distintos** (ver SEccion 6.1 del PLAN):
   - El kernel del notebook tiene pip completo (`requests`, `ipywidgets`, `gdown`)
   - El script que Blender ejecuta con `--python` usa solo stdlib + `bpy`
   - El puente entre ambos es el stdout de Blender y los archivos en disco

3. **Un solo proceso de Blender por trabajo**: no se relanza Blender por cada frame.
   La paralelizacion es entre render (GPU) y subida a Drive (CPU/IO).

## Modulos

### src/bcr/config.py
Constantes (version de Blender, URLs, patrones de archivo) y funciones de validacion
(frame range, ruta de Drive, URL). No tiene dependencias externas.

### src/bcr/link_resolver.py
Resuelve enlaces de distintos proveedores a URLs de descarga directa.
- Directo: pasa tal cual
- Dropbox: ?dl=0 -> ?dl=1
- Google Drive: extrae file_id, construye URL de descarga
- MediaFire: parsea HTML de la pagina de descarga

### src/bcr/blender_provisioning.py
Descarga el .tar.xz de Blender desde download.blender.org, lo extrae y devuelve
la ruta al binario. Soporta cache en Drive.

### src/bcr/device_config.py
Configuracion de GPU/CPU/OptiX para Cycles, disenado para ejecutarse dentro de
Blender. Obligatorio llamar a `get_devices()` en background mode.

### src/bcr/state_manager.py
Archivo JSON de estado en Drive para reanudacion. La reconciliacion contra archivos
reales en Drive previene estados corruptos por caidas a mitad de escritura.

### src/bcr/render_orchestrator.py
Corazon del sistema. Lanza Blender con los argumentos en el orden correcto
(verificable por test), parsea stdout buscando `Saved:`, y encola la subida
a Drive en un ThreadPoolExecutor mientras Blender sigue renderizando.

### src/bcr/drive_sync.py
Capa fina sobre shutil/os para copiar frames a Drive y borrarlos localmente.
Drive esta montado como sistema de archivos, no se necesita API.

### src/bcr/progress_ui.py
Widgets ipywidgets para monitor en vivo. Sin emojis, etiquetas en espanol.

### src/bcr/custom_script_loader.py
Descarga scripts .py desde URLs y los prepara para pasarlos a Blender.

## blender_scripts/render_frame_driver.py
Unico script que se ejecuta dentro de Blender. Parsea `--output-mode` y
`--cycles-device` de `sys.argv` (despues de `--`) y configura todo antes del render.

## Flujo de datos

```
1. [Notebook] Config user -> src/bcr/config.py (validacion)
2. [Notebook] Resolver enlace -> link_resolver.resolve_download_url()
3. [Paralelo] Descargar .blend + Aprovisionar Blender
4. [Notebook] Montar Drive
5. [Notebook] RenderOrchestrator.build_command() -> list[str]
6. [Orch] subprocess.Popen(blender, ...) con stdout pipe
7. [Orch] readline() loop: detectar "Saved: '/ruta/frame_NNNNNN.png'"
8. [Orch] Por cada frame: ThreadPoolExecutor.submit(upload_and_cleanup)
9. [Upload] shutil.copy2() a Drive + os.remove() local + save_state()
10. [Orch] Al terminar: reconciliacion de frames pendientes
```

## Seguridad

- Todos los comandos se construyen como listas (nunca shell=True)
- Las URLs y rutas de usuario se validan antes de usar
- No se hardcodean credenciales (Drive usa OAuth interactivo)
- Backlog limitado a BACKLOG_LIMIT frames locales
