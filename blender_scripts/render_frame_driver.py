"""Driver script executed INSIDE Blender's embedded Python runtime.

Configure the device (GPU/CPU/OptiX) and output mode (compositor/sequencer)
before rendering begins.

Use ONLY the Python standard library and bpy. Do not import from src/bcr/
because Blender cannot access the notebook kernel's pip environment.

Usage (from the Blender command line):
    blender --background scene.blend --python render_frame_driver.py \\
        --render-output /tmp/frame_##### --render-anim -- \\
        --cycles-device OPTIX --output-mode compositor

Arguments after -- are received in sys.argv.
"""

import re
import sys
from pathlib import Path


def main() -> None:
    """Entry point: configure and launch the render."""
    import bpy

    # Parse custom arguments (after --)
    device = "OPTIX"
    output_mode = "compositor"

    args = _parse_custom_args(sys.argv)
    if args.get("cycles-device"):
        device = args["cycles-device"]
    if args.get("output-mode"):
        output_mode = args["output-mode"]

    # Determine the clean base directory (without Blender's # pattern)
    if args.get("output-dir"):
        # --output-dir takes precedence: explicit clean output path
        output_dir = args["output-dir"]
    elif args.get("render-output"):
        # Fallback: derive from --render-output by removing the # pattern
        raw = args["render-output"]
        if re.search(r"#+", raw):
            output_dir = str(Path(raw).parent)
        else:
            output_dir = raw
    else:
        output_dir = "/content/render_tmp"

    # 1. Configure device
    _configure_device(device)

    # 2. Configure output mode and force the direct render path into the managed directory.
    _configure_output_mode(output_mode)
    if output_mode == "sequencer":
        bpy.context.scene.render.filepath = str(Path(output_dir) / "frame_######")

    # 3. Audit movie media before rendering so missing paths/codecs are visible in logs.
    _audit_video_media()

    # 4. Remap compositor File Output nodes into clean, managed output folders.
    _remap_file_output_nodes(output_dir, output_mode)

    print(f"[driver] Device: {device}")
    print(f"[driver] Modo de salida: {output_mode}")
    print("[driver] Render is ready to start.")


def _parse_custom_args(argv: list[str]) -> dict[str, str]:
    """Parse --key value arguments from sys.argv.

    Blender passes its own arguments first; ours arrive after --.
    We specifically look for --cycles-device, --output-mode, --output-dir,
    and --render-output.
    """
    result: dict[str, str] = {}

    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:]  # quitar --
            value = argv[i + 1]
            # Solo nos interesan nuestros argumentos
            if key in (
                "cycles-device",
                "output-mode",
                "output-dir",
                "render-output",
            ):
                result[key] = value
                i += 2
                continue
        i += 1

    return result


def _audit_video_media() -> None:
    """Report video-media support, packing status, and unresolved paths."""
    import bpy

    ffmpeg_available = bool(getattr(bpy.app.build_options, "ffmpeg", False))
    print(f"[media] Blender FFmpeg support: {ffmpeg_available}")
    if not ffmpeg_available:
        print("[media] WARNING: this Blender build has no FFmpeg support; video textures may fail.", file=sys.stderr)

    checked = 0
    for image in bpy.data.images:
        if getattr(image, "source", "") != "MOVIE":
            continue
        checked += 1
        packed = getattr(image, "packed_file", None) is not None
        resolved = bpy.path.abspath(image.filepath, library=image.library)
        exists = Path(resolved).is_file()
        status = "packed" if packed else ("available on disk" if exists else "MISSING")
        print(f"[media] Movie image {image.name!r}: {status}; path={resolved}")
        if not packed and not exists:
            print("[media] WARNING: movie media is not packed and its resolved path does not exist in this runtime.", file=sys.stderr)

    for clip in bpy.data.movieclips:
        checked += 1
        resolved = bpy.path.abspath(clip.filepath, library=clip.library)
        exists = Path(resolved).is_file()
        packed = getattr(clip, "packed_file", None) is not None
        status = "packed" if packed else ("available on disk" if exists else "MISSING")
        print(f"[media] Movie clip {clip.name!r}: {status}; path={resolved}")
        if not packed and not exists:
            print("[media] WARNING: movie clip is not packed and its resolved path does not exist in this runtime.", file=sys.stderr)

    if checked == 0:
        print("[media] No movie textures or movie clips found.")


def _configure_device(backend: str) -> None:
    """Configure the GPU/CPU/OptiX render device.

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
        print("[driver] Device: CPU")
        return

    # Extract the base backend (e.g. "OPTIX+CPU" -> "OPTIX")
    clean_backend = backend.upper().replace("+CPU", "")
    cprefs.compute_device_type = clean_backend

    # Required in background mode
    cprefs.get_devices()

    has_gpu = False
    for device in cprefs.devices:
        is_gpu = device.type != "CPU"
        device.use = is_gpu
        if is_gpu:
            has_gpu = True

    if has_gpu:
        scene.cycles.device = "GPU"
        print(f"[driver] Device: GPU ({clean_backend})")
    else:
        scene.cycles.device = "CPU"
        cprefs.compute_device_type = "NONE"
        print(
            f"[driver] WARNING: no GPU detected ({clean_backend}); "
            "continuing on CPU"
        )


def _configure_output_mode(mode: str) -> None:
    """Configure whether output uses the compositor or sequencer.

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


def _remap_file_output_nodes(
    output_dir: str = "/content/render_tmp",
    output_mode: str = "compositor",
) -> None:
    """Remapea todos los nodos File Output del compositor a output_dir.

    Los .blend suelen tener rutas absolutas del sistema local del artista
    (Windows: C:\\Users\\...). En Colab (Linux) esas rutas no funcionan.
    Esta funcion reescribe directory de cada nodo File Output a una ruta
    valida en Linux.

    Ademas, desactiva la salida directa del render (scene.render.filepath)
    para que solo los File Output nodes generen archivos.

    Para nodos EXR Multilayer, preserva los nombres de item (que son nombres
    de capa dentro del .exr). Para nodos single-layer, agrega marcador de
    frame _###### a cada item.name.

    Args:
        output_dir: Directorio base limpio (sin patron # de Blender) para
            los archivos de salida de File Output nodes.
        output_mode: Modo de salida ('compositor' o 'sequencer').
    """
    import bpy

    scene = bpy.context.scene

    # En modo sequencer no hay nodos de compositor que remapear
    if output_mode == "sequencer":
        print("[driver] Sequencer mode: File Output nodes are not remapped")
        return

    # Guardar la ruta original (la que puso --render-output) por si
    # no hay File Output nodes y tenemos que usarla como fallback.
    original_filepath = scene.render.filepath

    # Redirigir la salida directa del render a un directorio descartable
    # para que no genere un archivo extra ademas de los File Output nodes.
    scene.render.filepath = f"{output_dir}/_render_result_"

    # En Blender 5.0+, el arbol de nodos del compositor se accede mediante
    # scene.compositing_node_group. scene.node_tree ya no existe como atributo.
    node_tree = scene.compositing_node_group

    if node_tree is None:
        print(
            "[driver] No compositor node tree is available; "
            "no se remapean File Outputs"
        )
        scene.render.filepath = original_filepath
        return

    # Asegurar que el node tree tiene nodos (puede estar vacio)
    if not node_tree.nodes:
        print(f"[driver] Empty node tree; File Output nodes will not be remapped")
        scene.render.filepath = original_filepath
        return

    remapped = 0
    warn_no_slots = 0
    for node in node_tree.nodes:
        if node.type != "OUTPUT_FILE":
            continue

        node_name = node.name
        old_base = getattr(node, "directory", "")

        # Limpiar la ruta original: eliminar prefijos Windows y normalizar
        # P. ej. "C:\\Users\\..." -> "Users/...", "/tmp\\" -> "tmp"
        # Use the node name, never the artist workstation path, for output folders.
        safe_node_name = re.sub(r"[^A-Za-z0-9_]+", "_", node_name).strip("_") or "compositor_output"
        new_base = str(Path(output_dir) / safe_node_name)
        node.directory = new_base

        # Multilayer output stores layer names inside a single EXR file.
        is_multilayer = (
            getattr(node.format, "file_format", "") == "OPEN_EXR_MULTILAYER"
        )

        if is_multilayer:
            # En EXR multilayer, el marcador de frame va en file_name (que
            # es la unica propiedad que determina el nombre fisico del
            # archivo). item.name son capas internas y no se tocan.
            node.file_name = f"{safe_node_name}_######"
            print(
                f"[driver] Nodo '{node_name}' es EXR multilayer, "
                f"file_name -> '{node.file_name}' "
                f"({len(node.file_output_items)} capas preservadas)"
            )
        else:
            # En nodos single-layer, cada item es un archivo separado.
            # file_name debe quedar vacio para no duplicar marcador.
            node.file_name = ""
            for item in node.file_output_items:
                item_name_clean = item.name.rstrip("_")
                if not re.search(r"#+", item_name_clean):
                    item_name_clean = f"{item_name_clean}_######"
                    item.name = item_name_clean
                print(
                    f"[driver] File output: {new_base}/{item_name_clean}"
                )

        remapped += 1
        if not node.file_output_items:
            warn_no_slots += 1

        print(
            f"[driver] Nodo '{node_name}' remapeado: "
            f"'{old_base}' -> '{new_base}'"
        )

    if remapped == 0:
        # Restaurar la salida directa del render como fallback
        scene.render.filepath = original_filepath
        print(
            "[driver] ERROR: No File Output nodes were found in the compositor. "
            "Ensure the .blend contains compositor File Output nodes "
            "accessible through scene.compositing_node_group.",
            file=sys.stderr,
        )
        sys.exit(1)
    else:
        print(
            f"[driver] {remapped} nodo(s) File Output remapeado(s) "
            f"a {output_dir}/"
        )
        if warn_no_slots:
            print(
                f"[driver] WARNING: {warn_no_slots} nodo(s) "
                "no tienen file_output_items"
            )


if __name__ == "__main__":
    main()