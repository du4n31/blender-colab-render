# Blender Colab Render

Renderiza escenas de Blender usando las GPUs T4 gratuitas de Google Colab.

Cada frame se sube a Drive individualmente apenas termina, en paralelo con el render del frame siguiente. Si la sesion de Colab se interrumpe, puedes reanudar desde el ultimo frame confirmado.

## Requisitos

- Cuenta de Google con Google Drive
- Una escena de Blender lista para renderizar
- Enlace publico al archivo `.blend` (subido a Drive, Dropbox, MediaFire o enlace directo)

## Como usar

1. Abre `notebooks/blender_render.ipynb` en Google Colab.
2. Monta tu Google Drive cuando el notebook lo solicite.
3. Pega el enlace de tu archivo `.blend`.
4. Configura las opciones de render (rango de frames, dispositivo, modo de salida).
5. Ejecuta todas las celdas.

Los frames renderizados apareceran en la ruta de Drive que hayas elegido.

## Estructura del proyecto

```
src/bcr/          Paquete Python con la logica de orquestacion
blender_scripts/  Scripts que se ejecutan dentro de Blender
notebooks/        Notebook de Colab (punto de entrada)
tests/            Pruebas automatizadas (pytest)
docs/             Documentacion
```
