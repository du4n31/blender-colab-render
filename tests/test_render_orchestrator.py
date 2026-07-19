"""Pruebas para render_orchestrator.py.

Estas pruebas validan la logica que NO depende de una GPU real:
- Construccion del comando de Blender
- Parseo de stdout (Saved: lineas)
- Calculo de metricas
"""

import re
from pathlib import Path
from datetime import timedelta

import pytest

from bcr.render_orchestrator import RenderOrchestrator


class TestBuildCommand:
    """Prueba la construccion del comando de Blender."""

    def test_basic_command_structure(self):
        """El comando incluye los argumentos minimos necesarios."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/scene.blend"),
            output_dir=Path("/tmp/render"),
            drive_output_dir=Path("/drive/output"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=250,
        )
        cmd = orch.build_command()

        assert cmd[0] == "/blender"
        assert "--background" in cmd
        assert "/scene.blend" in cmd
        assert "--engine" in cmd
        assert "CYCLES" in cmd

    def test_render_anim_vs_render_frame(self):
        """Rango de frames usa --render-anim, frame unico usa --render-frame."""
        # Rango
        orch_anim = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=250,
        )
        cmd_anim = orch_anim.build_command()
        assert "--render-anim" in cmd_anim
        assert "--frame-start" in cmd_anim
        assert "--frame-end" in cmd_anim

        # Frame unico
        orch_single = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=42,
            frame_end=42,
        )
        cmd_single = orch_single.build_command()
        assert "--render-frame" in cmd_single
        assert "42" in cmd_single

    def test_argument_order_correct(self):
        """Verifica el orden critical de argumentos.

        El .blend debe ir ANTES de --render-output y --render-anim
        debe ir AL FINAL (antes de --).
        """
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/scene.blend"),
            output_dir=Path("/tmp/render"),
            drive_output_dir=Path("/drive/output"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=100,
        )
        cmd = orch.build_command()

        # Encontrar indices
        idx_background = cmd.index("--background")
        idx_blend = cmd.index("/scene.blend")
        idx_render_output = cmd.index("--render-output")
        idx_render_anim = cmd.index("--render-anim") if "--render-anim" in cmd else -1
        idx_ddash = cmd.index("--")
        idx_device = cmd.index("--cycles-device") if "--cycles-device" in cmd else -1

        # El .blend debe ir despues de --background
        assert idx_blend > idx_background

        # --render-output debe ir DESPUES de .blend
        assert idx_render_output > idx_blend

        # --render-anim debe ir DESPUES de --render-output y ANTES de --
        if idx_render_anim >= 0:
            assert idx_render_anim > idx_render_output
            assert idx_ddash == -1 or idx_render_anim < idx_ddash or idx_ddash < 0

        # -- debe ser uno de los ultimos
        assert idx_ddash > idx_render_output

        # --cycles-device debe ir DESPUES de --
        assert idx_device > idx_ddash

    def test_custom_scripts_included(self):
        """Scripts personalizados se anaden como --python."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
            custom_script_paths=[
                Path("/scripts/custom1.py"),
                Path("/scripts/custom2.py"),
            ],
        )
        cmd = orch.build_command()

        assert "--python" in cmd
        assert "/scripts/custom1.py" in cmd
        assert "/scripts/custom2.py" in cmd

    def test_device_and_output_mode_after_ddash(self):
        """--cycles-device y --output-mode van despues de --."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
            device="OPTIX",
            output_mode="compositor",
        )
        cmd = orch.build_command()

        idx_ddash = cmd.index("--")
        idx_device = cmd.index("--cycles-device")
        idx_mode = cmd.index("--output-mode")

        assert idx_device > idx_ddash
        assert idx_mode > idx_ddash

        device_idx = cmd.index("--cycles-device")
        assert cmd[device_idx + 1] == "OPTIX"
        mode_idx = cmd.index("--output-mode")
        assert cmd[mode_idx + 1] == "compositor"

    def test_output_format_args(self):
        """Verifica --render-format PNG y --use-extension 1."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
        )
        cmd = orch.build_command()

        fmt_idx = cmd.index("--render-format")
        assert cmd[fmt_idx + 1] == "PNG"

        ext_idx = cmd.index("--use-extension")
        assert cmd[ext_idx + 1] == "1"


class TestParseSavedLine:
    """Prueba el parseo de lineas 'Saved:' del stdout de Blender."""

    def test_saved_line_standard(self):
        """Linea Saved: estandar."""
        line = "Saved: '/content/render_tmp/frame_00001.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result == 1

    def test_saved_line_high_number(self):
        """Linea Saved: con numero de frame alto."""
        line = "Saved: '/content/render_tmp/frame_12345.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result == 12345

    def test_not_a_saved_line(self):
        """Linea que no es de Saved: devuelve None."""
        line = "Fra:1 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.53"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is None

    def test_saved_with_timestamp(self):
        """Linea Saved con path temporal."""
        line = "Saved: '/tmp/blender_XXXXXX/frame_00001.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result == 1

    def test_saved_blender_stdout_pattern(self):
        """Patron real de stdout de Blender."""
        lines = [
            "Fra:1 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.53",
            "Saved: '/content/render_tmp/frame_00001.png'",
            " Time: 00:00.53 (Saving: 00:00.08)",
            "",
            "Fra:2 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.48",
            "Saved: '/content/render_tmp/frame_00002.png'",
            " Time: 00:00.48 (Saving: 00:00.06)",
        ]
        frames = []
        for line in lines:
            result = RenderOrchestrator._parse_saved_line(line)
            if result is not None:
                frames.append(result)
        assert frames == [1, 2]

    def test_no_frame_number_in_path(self):
        """Path sin numero de frame devuelve None."""
        line = "Saved: '/tmp/output_abc.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is None
