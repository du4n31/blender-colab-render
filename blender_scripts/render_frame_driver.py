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

import re
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
    if args.get("render-output"):
        # Ruta de salida para File Output nodes (opcional, default: /content/render_tmp)
        output_dir = args["render-output"]
    else:
        output_dir = "/content/render_tmp"

    # 1. Configurar dispositivo
    _configure_device(device)

    # 2. Configurar modo de salida (compositor vs sequencer)
    _configure_output_mode(output_mode)

    # 3. Remapear nodos File Output a una ruta Linux valida
    _remap_file_output_nodes(output_dir, output_mode)

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
            if key in ("cycles-device", "output-mode", "render-output"):
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
        # IMPORTANTE: En background mode, el node tree del compositor
        # solo existe si use_nodes = True
        scene.use_nodes = True
    elif mode == "sequencer":
        scene.render.use_compositing = False
        scene.render.use_sequencer = True
        scene.use_nodes = False
    else:
        print(
            f"[driver] Modo de salida desconocido '{mode}', "
            "usando compositor por defecto"
        )
        scene.render.use_compositing = True
        scene.render.use_sequencer = False
        scene.use_nodes = True


def _remap_file_output_nodes(
    output_dir: str = "/content/render_tmp",
    output_mode: str = "compositor",
) -> None:
    """Remapea todos los nodos File Output del compositor a output_dir.

    Los .blend suelen tener rutas absolutas del sistema local del artista
    (Windows: C:\\Users\\...). En Colab (Linux) esas rutas no funcionan.
    Esta funcion reescribe base_path de cada nodo File Output a una ruta
    valida en Linux.

    Ademas, desactiva la salida directa del render (scene.render.filepath)
    para que solo los File Output nodes generen archivos.

    Args:
        output_dir: Directorio base para los archivos de salida.
        output_mode: Modo de salida ('compositor' o 'sequencer').
    """
    import bpy

    scene = bpy.context.scene

    # En modo sequencer no hay nodos de compositor que remapear
    if output_mode == "sequencer":
        print("[driver] Modo sequencer: no se remapean File Output nodes")
        return

    # Guardar la ruta original (la que puso --render-output) por si
    # no hay File Output nodes y tenemos que usarla como fallback.
    original_filepath = scene.render.filepath

    # Redirigir la salida directa del render a un directorio descartable
    # para que no genere un archivo extra ademas de los File Output nodes.
    scene.render.filepath = f"{output_dir}/_render_result_"

    # Remapear nodos File Output en el compositor
    # En Blender 5.2 background mode, scene.node_tree puede no existir
    # si use_nodes=False o el tipo de escena no soporta compositor.
    # Incluso con use_nodes=True, en background mode hay que crearlo explícitamente.
    node_tree = getattr(scene, "node_tree", None)
    if node_tree is None:
        # Intentar crear el node tree del compositor
        try:
            node_tree = bpy.data.node_groups.new("CompositorNodeTree", "CompositorNodeTree")
            scene.node_tree = node_tree
            print("[driver] Node tree del compositor creado explícitamente")
        except Exception as e:
            print(f"[driver] No se pudo crear node_tree: {e}")
            scene.render.filepath = original_filepath
            return

    # Asegurar que el node tree tiene nodos (puede estar vacio)
    if not node_tree.nodes:
        print(f"[driver] Node tree vacio, no se remapean File Outputs")
        scene.render.filepath = original_filepath
        return

    remapped = 0
    warn_no_slots = 0
    for node in node_tree.nodes:
        if node.type != "OUTPUT_FILE":
            continue

        node_name = node.name
        old_base = getattr(node, "base_path", "")

        # Limpiar la ruta original: eliminar prefijos Windows y normalizar
        # P. ej. "C:\\Users\\..." -> "Users/...", "/tmp\\" -> "tmp"
        cleaned = old_base.replace("\\", "/")
        # Extraer solo la parte relativa (quitar C:/, etc.)
        parts = [p for p in cleaned.split("/") if p and not p.endswith(":")]
        suffix = "_".join(parts) if parts else node_name

        new_base = f"{output_dir}/{suffix}"
        node.base_path = new_base

        # Imprimir cada slot del nodo para que el orquestador lo detecte
        for slot in node.file_slots:
            slot_path = slot.path
            # Asegurar que el nombre del slot incluya marcador de frame
            # para que el orquestador pueda extraer el numero.
            slot_path_clean = slot_path.rstrip("_")
            if not re.search(r"#+", slot_path_clean):
                slot_path_clean = f"{slot_path_clean}_######"
                slot.path = slot_path_clean
            print(
                f"[driver] File output: {new_base}/{slot_path_clean} "
                f"(frame %d.{slot.format.file_format.lower()})"
            )

        remapped += 1
        if not node.file_slots:
            warn_no_slots += 1

        print(
            f"[driver] Nodo '{node_name}' remapeado: "
            f"'{old_base}' -> '{new_base}'"
        )

    if remapped == 0:
        # Restaurar la salida directa del render como fallback
        scene.render.filepath = original_filepath
        print(
            "[driver] No se encontraron nodos File Output en el compositor, "
            "se usara la salida directa del render."
        )
    else:
        print(
            f"[driver] {remapped} nodo(s) File Output remapeado(s) "
            f"a {output_dir}/"
        )
        if warn_no_slots:
            print(
                f"[driver] ADVERTENCIA: {warn_no_slots} nodo(s) "
                "no tienen file_slots"
            )


if __name__ == "__main__":
    main()