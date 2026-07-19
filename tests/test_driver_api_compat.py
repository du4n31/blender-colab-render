"""Prueba de regresion: detecta APIs deprecadas de Blender en el driver.

Lee el codigo fuente de blender_scripts/render_frame_driver.py como texto
plano y falla si contiene cadenas que corresponden a propiedades eliminadas
en Blender 5.0. Esto evita que alguien reintroduzca la API vieja sin darse
cuenta.

Las propiedades prohibidas son:
  - scene.node_tree      -> usar scene.compositing_node_group
  - .base_path           -> usar .directory
  - .file_slots          -> usar .file_output_items
  - .layer_slots         -> usar .file_output_items (deprecada en la misma version)
  - scene.use_nodes      -> deprecada; usar scene.render.use_compositing

Esta prueba NO necesita Blender ni Colab: solo parsea texto.
"""

import re
from pathlib import Path

DRIVER_PATH = Path(__file__).resolve().parents[1] / "blender_scripts" / "render_frame_driver.py"

# Patrones prohibidos: tupla de (nombre_amigable, regex_pattern)
# Usamos regex para evitar falsos positivos con substring (ej: ".base_path"
# no debe coincidir con ".base_path_old" que no existe, pero es mas seguro).
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ("scene.node_tree", r"scene\.node_tree"),
    (".base_path", r"\.base_path"),
    (".file_slots", r"\.file_slots"),
    (".layer_slots", r"\.layer_slots"),
    ("scene.use_nodes", r"scene\.use_nodes"),
]

# Comentarios o cadenas literales donde aparecen estas cadenas como
# referencia (ej: un comentario "NO usar scene.node_tree") son aceptables.
# Este test ignora comentarios (#) y docstrings ("""). Para mantenerlo
# simple, solo verificamos lineas que NO son comentarios ni docstrings.


def _is_comment_or_docstring(line: str) -> bool:
    """Determina si una linea es comentario o docstring."""
    stripped = line.lstrip()
    # Comentario
    if stripped.startswith("#"):
        return True
    # Docstring (triple comilla)
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    return False


def test_no_deprecated_scene_node_tree() -> None:
    """No debe usar scene.node_tree (usar scene.compositing_node_group)."""
    violations = _find_violations("scene.node_tree", r"scene\.node_tree")
    assert not violations, (
        f"Se encontro 'scene.node_tree' en el driver. "
        f"Usar scene.compositing_node_group en su lugar.\n"
        f"Lineas: {violations}"
    )


def test_no_deprecated_base_path() -> None:
    """No debe usar .base_path (usar .directory)."""
    violations = _find_violations(".base_path", r"\.base_path")
    assert not violations, (
        f"Se encontro '.base_path' en el driver. "
        f"Usar .directory en su lugar.\n"
        f"Lineas: {violations}"
    )


def test_no_deprecated_file_slots() -> None:
    """No debe usar .file_slots (usar .file_output_items)."""
    violations = _find_violations(".file_slots", r"\.file_slots")
    assert not violations, (
        f"Se encontro '.file_slots' en el driver. "
        f"Usar .file_output_items en su lugar.\n"
        f"Lineas: {violations}"
    )


def test_no_deprecated_layer_slots() -> None:
    """No debe usar .layer_slots (deprecada, usar .file_output_items)."""
    violations = _find_violations(".layer_slots", r"\.layer_slots")
    assert not violations, (
        f"Se encontro '.layer_slots' en el driver. "
        f"Usar .file_output_items en su lugar.\n"
        f"Lineas: {violations}"
    )


def test_no_deprecated_scene_use_nodes() -> None:
    """No debe usar scene.use_nodes (usar scene.render.use_compositing)."""
    violations = _find_violations("scene.use_nodes", r"scene\.use_nodes")
    assert not violations, (
        f"Se encontro 'scene.use_nodes' en el driver. "
        f"Usar scene.render.use_compositing en su lugar.\n"
        f"Lineas: {violations}"
    )


def test_driver_source_exists() -> None:
    """El archivo del driver debe existir."""
    assert DRIVER_PATH.exists(), (
        f"Archivo del driver no encontrado: {DRIVER_PATH}"
    )


# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _find_violations(name: str, pattern: str) -> list[str]:
    """Busca violaciones de un patron en el driver, ignorando comentarios.

    Returns:
        Lista de lineas con violacion (vacia si no hay).
    """
    if not DRIVER_PATH.exists():
        return [f"Archivo no encontrado: {DRIVER_PATH}"]

    violations: list[str] = []
    compiled = re.compile(pattern)

    source = DRIVER_PATH.read_text(encoding="utf-8")
    for lineno, line in enumerate(source.splitlines(), start=1):
        if _is_comment_or_docstring(line):
            continue
        if compiled.search(line):
            violations.append(f"  Linea {lineno}: {line.strip()}")

    return violations
