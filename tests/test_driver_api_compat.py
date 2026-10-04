"""Regression tests for deprecated Blender APIs in the driver.

Read blender_scripts/render_frame_driver.py as plain text
and fail if it contains references to properties removed
in Blender 5.0. This prevents accidental reintroduction of the old API.


Las propiedades prohibidas son:
  - scene.node_tree           -> usar scene.compositing_node_group
  - .base_path                -> usar .directory
  - .file_slots               -> usar .file_output_items
  - .layer_slots              -> usar .file_output_items (deprecada)
  - scene.use_nodes           -> deprecada; usar scene.render.use_compositing
  - node.inputs["File Name"]  -> usar node.file_name

These tests do not require Blender or Colab; they inspect source text only.
"""

import re
import unittest
from pathlib import Path

DRIVER_PATH = Path(__file__).resolve().parents[1] / "blender_scripts" / "render_frame_driver.py"


def _is_comment_or_docstring(line: str) -> bool:
    """Determine whether a line is a comment or docstring."""
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return True
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return True
    return False


def _find_violations(name: str, pattern: str) -> list[str]:
    """Find driver violations for a pattern, ignoring comments.

    Returns:
        List of violating lines (empty when there are none).
    """
    if not DRIVER_PATH.exists():
        return [f"File not found: {DRIVER_PATH}"]

    violations: list[str] = []
    compiled = re.compile(pattern)

    source = DRIVER_PATH.read_text(encoding="utf-8")
    for lineno, line in enumerate(source.splitlines(), start=1):
        if _is_comment_or_docstring(line):
            continue
        if compiled.search(line):
            violations.append(f"  Linea {lineno}: {line.strip()}")

    return violations


class TestDriverApiCompat(unittest.TestCase):
    """Detecta APIs deprecadas en el driver de render."""

    def test_sanitized_compositor_folder_names_do_not_collide(self) -> None:
        """Different node names that sanitize identically receive distinct folders."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("render_frame_driver", DRIVER_PATH)
        assert spec is not None and spec.loader is not None
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)

        used: set[str] = set()
        first = driver._unique_safe_node_name("Beauty Pass", used)
        second = driver._unique_safe_node_name("Beauty-Pass", used)
        third = driver._unique_safe_node_name("Beauty Pass", used)

        self.assertEqual(first, "Beauty_Pass")
        self.assertEqual(second, "Beauty_Pass_2")
        self.assertEqual(third, "Beauty_Pass_3")

    def test_driver_source_exists(self) -> None:
        """El archivo del driver debe existir."""
        self.assertTrue(DRIVER_PATH.exists(), f"Driver no encontrado: {DRIVER_PATH}")

    def test_no_deprecated_scene_node_tree(self) -> None:
        """No debe usar scene.node_tree (usar scene.compositing_node_group)."""
        violations = _find_violations("scene.node_tree", r"scene\.node_tree")
        self.assertFalse(
            violations,
            f"Se encontro 'scene.node_tree' en el driver. "
            f"Usar scene.compositing_node_group en su lugar.\n"
            + "\n".join(violations),
        )

    def test_no_deprecated_base_path(self) -> None:
        """No debe usar .base_path (usar .directory)."""
        violations = _find_violations(".base_path", r"\.base_path")
        self.assertFalse(
            violations,
            f"Se encontro '.base_path' en el driver. "
            f"Usar .directory en su lugar.\n"
            + "\n".join(violations),
        )

    def test_no_deprecated_file_slots(self) -> None:
        """No debe usar .file_slots (usar .file_output_items)."""
        violations = _find_violations(".file_slots", r"\.file_slots")
        self.assertFalse(
            violations,
            f"Se encontro '.file_slots' en el driver. "
            f"Usar .file_output_items en su lugar.\n"
            + "\n".join(violations),
        )

    def test_no_deprecated_layer_slots(self) -> None:
        """No debe usar .layer_slots (usar .file_output_items)."""
        violations = _find_violations(".layer_slots", r"\.layer_slots")
        self.assertFalse(
            violations,
            f"Se encontro '.layer_slots' en el driver. "
            f"Usar .file_output_items en su lugar.\n"
            + "\n".join(violations),
        )

    def test_no_deprecated_scene_use_nodes(self) -> None:
        """No debe usar scene.use_nodes (usar scene.render.use_compositing)."""
        violations = _find_violations("scene.use_nodes", r"scene\.use_nodes")
        self.assertFalse(
            violations,
            f"Se encontro 'scene.use_nodes' en el driver. "
            f"Usar scene.render.use_compositing en su lugar.\n"
            + "\n".join(violations),
        )

    def test_no_node_inputs_file_name(self) -> None:
        """No debe usar node.inputs['File Name'] (usar node.file_name)."""
        violations = _find_violations(
            "node.inputs[",
            r"""node\.inputs\["File Name"\]|node\.inputs\['File Name'\]""",
        )
        self.assertFalse(
            violations,
            f"Se encontro 'node.inputs[\"File Name\"]' en el driver. "
            f"Usar node.file_name en su lugar.\n"
            + "\n".join(violations),
        )
