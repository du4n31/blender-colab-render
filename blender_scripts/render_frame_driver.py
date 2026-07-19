"""Script driver que se ejecuta DENTRO del Python embebido de Blender.

Configura el dispositivo (GPU/CPU/OptiX) y el modo de salida (compositor/sequencer)
antes de que comience el render.

Usa SOLO la libreria estandar de Python + bpy. No importa nada del paquete src/bcr/
porque Blender no tiene acceso a ese entorno pip.

Uso (desde linea de comandos de Blender):
    blender --background scene.blend --python render_frame_driver.py \\
        --render-output /tmp/frame_##### --render-anim -- \\
        --cycles-device OPTIX --output-mode compositor

Los argumentos despues de -- se reciben en sys.argv.
"""

import sys
from pathlib import Path


def main() -> None:
    """Punto de entrada: configura y lanza el render."""
    import bpy

    # Parsear argumentos personalizados (despues de --)
    device = "OPTIX"
    output_mode = "compositor"

    args = _parse_custom_args(sys.argv)
    if args.get("cycles-device"):
        device = args["cycles-device"]
    if args.get("output-mode"):
        output_mode = args["output-mode"]

    # 1. Configurar dispositivo
    _configure_device(device)

    # 2. Configurar modo de salida (compositor vs sequencer)
    _configure_output_mode(output_mode)

    print(f"[driver] Dispositivo: {device}")
    print(f"[driver] Modo de salida: {output_mode}")
    print("[driver] Render listo para comenzar.")


def _parse_custom_args(argv: list[str]) -> dict[str, str]:
    """Parsea argumentos --clave valor de sys.argv.

    Blender pasa sus propios args primero; los nuestros llegan despues de --.
    Buscamos especificamente --cycles-device y --output-mode.
    """
    result: dict[str, str] = {}

    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:]  # quitar --
            value = argv[i + 1]
            # Solo nos interesan nuestros argumentos
            if key in ("cycles-device", "output-mode"):
                result[key] = value
                i += 2
                continue
        i += 1

    return result


def _configure_device(backend: str) -> None:
    """Configura el dispositivo de render GPU/CPU/OptiX.

    En background mode, Blender no puebla la lista de dispositivos
    automaticamente -- hay que llamar a get_devices() explicitamente.
    """
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    cprefs = bpy.context.preferences.addons["cycles"].preferences

    use_cpu = backend.upper() == "CPU"

    if use_cpu:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        print("[driver] Dispositivo: CPU")
        return

    # Extraer backend limpio (ej: "OPTIX+CPU" -> "OPTIX")
    clean_backend = backend.upper().replace("+CPU", "")
    cprefs.compute_device_type = clean_backend

    # Obligatorio en background mode
    cprefs.get_devices()

    has_gpu = False
    for device in cprefs.devices:
        is_gpu = device.type != "CPU"
        device.use = is_gpu
        if is_gpu:
            has_gpu = True

    if has_gpu:
        scene.cycles.device = "GPU"
        print(f"[driver] Dispositivo: GPU ({clean_backend})")
    else:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        print(
            f"[driver] ADVERTENCIA: no se detecto GPU ({clean_backend}), "
            "se continua en CPU"
        )


def _configure_output_mode(mode: str) -> None:
    """Configura si el output usa el compositor o el sequencer.

    Args:
        mode: 'compositor' o 'sequencer'
    """
    import bpy

    scene = bpy.context.scene

    if mode == "compositor":
        scene.render.use_compositing = True
        scene.render.use_sequencer = False
    elif mode == "sequencer":
        scene.render.use_compositing = False
        scene.render.use_sequencer = True
    else:
        print(
            f"[driver] Modo de salida desconocido '{mode}', "
            "usando compositor por defecto"
        )
        scene.render.use_compositing = True
        scene.render.use_sequencer = False


if __name__ == "__main__":
    main()
