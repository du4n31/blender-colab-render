"""Configure the render device (GPU/CPU/OptiX) inside Blender.

Este script esta disenado para ejecutarse DENTRO del Python embebido de Blender
via blender --python device_config.py. Usa solo bpy + stdlib.
"""

import sys
from typing import Optional


def configure_device(backend: str) -> None:
    """Configure the render device for Cycles.

    Args:
        backend: 'CPU', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI', o 'METAL'.
                 Se puede anadir +CPU para usar ambos (ej: 'OPTIX+CPU').

    Returns:
        None. Prints warnings if the requested GPU is not found.

    Raises:
        ImportError: if bpy is unavailable.
    """
    try:
        import bpy
    except ImportError:
        print("ERROR: bpy is unavailable. This script must run inside Blender.")
        sys.exit(1)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    cprefs = bpy.context.preferences.addons["cycles"].preferences

    use_cpu = backend.upper() == "CPU"

    if use_cpu:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        print("[device_config] Device configured: CPU")
        return

    # Extract the base backend (e.g. "OPTIX+CPU" -> "OPTIX")
    clean_backend = backend.upper().replace("+CPU", "")
    cprefs.compute_device_type = clean_backend

    # Required in background mode: get_devices() puebla la lista
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
        print(f"[device_config] Device configured: GPU ({backend})")
    else:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        msg = (
            f"WARNING: requested GPU was not detected ({backend}). "
            "Continuing on CPU. Verify that a Colab T4 GPU is available."
        )
        print(f"[device_config] {msg}")


def parse_device_args(argv: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Parsea `--cycles-device` y `--output-mode` de sys.argv.

    Los argumentos personalizados llegan despues de `--` en la linea de comandos
    de Blender.

    Returns:
        (device, output_mode), either of which may be None if not specified.
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
