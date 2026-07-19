"""Configuracion del dispositivo de render (GPU/CPU/OptiX) dentro de Blender.

Este script esta disenado para ejecutarse DENTRO del Python embebido de Blender
via blender --python device_config.py. Usa solo bpy + stdlib.
"""

import sys
from typing import Optional


def configure_device(backend: str) -> None:
    """Configura el dispositivo de render para Cycles.

    Args:
        backend: 'CPU', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI', o 'METAL'.
                 Se puede anadir +CPU para usar ambos (ej: 'OPTIX+CPU').

    Returns:
        None. Imprime advertencias si no se encuentra la GPU solicitada.

    Raises:
        ImportError: si bpy no esta disponible.
    """
    try:
        import bpy
    except ImportError:
        print("ERROR: bpy no esta disponible. Este script debe ejecutarse dentro de Blender.")
        sys.exit(1)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    cprefs = bpy.context.preferences.addons["cycles"].preferences

    use_cpu = backend.upper() == "CPU"

    if use_cpu:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        print("[device_config] Dispositivo configurado: CPU")
        return

    # Extraer el backend limpio (ej: "OPTIX+CPU" -> "OPTIX")
    clean_backend = backend.upper().replace("+CPU", "")
    cprefs.compute_device_type = clean_backend

    # Obligatorio en background mode: get_devices() puebla la lista
    cprefs.get_devices()

    _enable_gpu_devices(cprefs, clean_backend)


def _enable_gpu_devices(cprefs, backend: str) -> None:
    """Habilita dispositivos GPU y maneja fallback a CPU."""
    import bpy

    scene = bpy.context.scene
    has_gpu = False

    for device in cprefs.devices:
        is_gpu = device.type != "CPU"
        device.use = is_gpu
        if is_gpu:
            has_gpu = True

    if has_gpu:
        scene.cycles.device = "GPU"
        print(f"[device_config] Dispositivo configurado: GPU ({backend})")
    else:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        msg = (
            f"ADVERTENCIA: no se detecto GPU ({backend}). "
            "Se continua en CPU. Verifica que la T4 de Colab este disponible."
        )
        print(f"[device_config] {msg}")


def parse_device_args(argv: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Parsea `--cycles-device` y `--output-mode` de sys.argv.

    Los argumentos personalizados llegan despues de `--` en la linea de comandos
    de Blender.

    Returns:
        (device, output_mode) donde ambos pueden ser None si no se especificaron.
    """
    device: Optional[str] = None
    output_mode: Optional[str] = None

    i = 0
    while i < len(argv):
        if argv[i] == "--cycles-device" and i + 1 < len(argv):
            device = argv[i + 1].upper()
            i += 2
        elif argv[i] == "--output-mode" and i + 1 < len(argv):
            output_mode = argv[i + 1].lower()
            i += 2
        else:
            i += 1

    return device, output_mode
