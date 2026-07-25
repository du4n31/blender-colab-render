"""Pruebas para render_orchestrator.py.

Estas pruebas validan la logica que NO depende de una GPU real:
- Construccion del comando de Blender
- Parseo de stdout (Saved: lineas)
- Calculo de metricas
"""

import re
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        """--cycles-device, --output-mode y --output-dir van despues de --."""
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
        idx_outdir = cmd.index("--output-dir")

        assert idx_device > idx_ddash
        assert idx_mode > idx_ddash
        assert idx_outdir > idx_ddash

        device_idx = cmd.index("--cycles-device")
        assert cmd[device_idx + 1] == "OPTIX"
        mode_idx = cmd.index("--output-mode")
        assert cmd[mode_idx + 1] == "compositor"
        outdir_idx = cmd.index("--output-dir")
        assert cmd[outdir_idx + 1] == "/tmp/r"

    def test_output_has_render_output(self):
        """Verifica --render-output para la salida directa del render."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
        )
        cmd = orch.build_command()

        out_idx = cmd.index("--render-output")
        assert cmd[out_idx + 1] == "/tmp/r/frame_#####"

    def test_no_render_format_forced(self):
        """NO se fuerza --render-format; el .blend y File Output nodes deciden."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/r"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
        )
        cmd = orch.build_command()

        # No debe contener --render-format ni --use-extension
        assert "--render-format" not in cmd
        assert "--use-extension" not in cmd


class TestParseSavedLine:
    """Prueba el parseo de lineas 'Saved:' del stdout de Blender.

    Ahora _parse_saved_line devuelve tuple (frame_num, Path) con la
    ruta exacta que Blender reporta, para poder soportar multiples
    archivos por frame (varios File Output nodes).
    """

    def test_saved_line_standard(self):
        """Linea Saved: estandar."""
        line = "Saved: '/content/render_tmp/frame_000001.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert str(path) == "/content/render_tmp/frame_000001.png"

    def test_saved_line_high_number(self):
        """Linea Saved: con numero de frame alto."""
        line = "Saved: '/content/render_tmp/frame_012345.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 12345
        assert str(path) == "/content/render_tmp/frame_012345.png"

    def test_not_a_saved_line(self):
        """Linea que no es de Saved: devuelve None."""
        line = "Fra:1 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.53"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is None

    def test_saved_with_timestamp(self):
        """Linea Saved con path temporal."""
        line = "Saved: '/tmp/blender_XXXXXX/frame_000001.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert str(path) == "/tmp/blender_XXXXXX/frame_000001.png"

    def test_saved_blender_stdout_pattern(self):
        """Patron real de stdout de Blender."""
        lines = [
            "Fra:1 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.53",
            "Saved: '/content/render_tmp/frame_000001.png'",
            " Time: 00:00.53 (Saving: 00:00.08)",
            "",
            "Fra:2 Mem:42.35M ( Peak: 45.12M ) | Time: 00:00.48",
            "Saved: '/content/render_tmp/frame_000002.png'",
            " Time: 00:00.48 (Saving: 00:00.06)",
        ]
        frames = []
        paths = []
        for line in lines:
            result = RenderOrchestrator._parse_saved_line(line)
            if result is not None:
                frame_num, path = result
                frames.append(frame_num)
                paths.append(str(path))
        assert frames == [1, 2]
        assert paths == [
            "/content/render_tmp/frame_000001.png",
            "/content/render_tmp/frame_000002.png",
        ]

    def test_no_frame_number_in_path(self):
        """Path sin numero de frame devuelve None."""
        line = "Saved: '/tmp/output_abc.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is None

    def test_saved_exr_standard(self):
        """Linea Saved: con archivo EXR (File Output node)."""
        line = "Saved: '/content/render_tmp/File_Output_node000001.exr'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert str(path) == "/content/render_tmp/File_Output_node000001.exr"

    def test_saved_exr_with_frame_in_name(self):
        """Linea Saved: con EXR que tiene frame_ en el nombre."""
        line = "Saved: '/content/render_tmp/my_slot_frame_000001.exr'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert str(path) == "/content/render_tmp/my_slot_frame_000001.exr"

    def test_saved_exr_high_frame_number(self):
        """Linea Saved: con EXR de frame alto."""
        line = "Saved: '/content/render_tmp/beauty_000128.exr'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 128
        assert str(path) == "/content/render_tmp/beauty_000128.exr"

    def test_discard_file_ignored(self):
        """Archivos _discard_ o _render_result_ se ignoran (salida directa)."""
        line = "Saved: '/content/render_tmp/_discard_0001.png'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is None

        line2 = "Saved: '/content/render_tmp/_render_result_0001.png'"
        result2 = RenderOrchestrator._parse_saved_line(line2)
        assert result2 is None

    def test_saved_exr_multiple_digits(self):
        """Linea Saved: con EXR que tiene digitos multiples en el path."""
        line = "Saved: '/content/render_tmp/Result_000001.exr'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert str(path) == "/content/render_tmp/Result_000001.exr"

    def test_saved_multiple_formats_same_frame(self):
        """Multiples formatos para el mismo frame."""
        lines = [
            "Saved: '/content/render_tmp/_discard_000001.png'",
            "Saved: '/content/render_tmp/beauty_000001.exr'",
            "Saved: '/content/render_tmp/light_000001.exr'",
        ]
        frames = []
        paths = []
        for line in lines:
            result = RenderOrchestrator._parse_saved_line(line)
            if result is not None:
                frame_num, path = result
                frames.append(frame_num)
                paths.append(str(path))
        # Solo los EXR, no el discard
        assert frames == [1, 1]
        assert paths == [
            "/content/render_tmp/beauty_000001.exr",
            "/content/render_tmp/light_000001.exr",
        ]

    def test_windows_path_still_parsed(self):
        """Rutas Windows se parsean como tuple aunque luego se filtran.

        _parse_saved_line extrae el frame de cualquier path con patron valido.
        El filtrado de paths invalidos ocurre en _is_valid_output_path (en run()),
        no en el parseo.
        """
        # Usar un patron que SÍ se pueda parsear (underscore + digitos + .ext)
        line = "Saved: 'C:\\\\Users\\\\artista\\\\Documents\\\\file_name_000001.exr'"
        result = RenderOrchestrator._parse_saved_line(line)
        assert result is not None
        frame_num, path = result
        assert frame_num == 1
        assert "C:" in str(path)


class TestValidateOutputPath:
    """Prueba _is_valid_output_path: filtrado de rutas no-Colab."""

    def make_orch(self, tmp_output_dir: Path) -> RenderOrchestrator:
        return RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=tmp_output_dir,
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
        )

    def test_accepts_path_under_output_dir(self, tmp_output_dir: Path):
        """Ruta bajo output_dir es valida."""
        orch = self.make_orch(tmp_output_dir)
        valid_path = tmp_output_dir / "Temp" / "beauty_0001.exr"
        assert orch._is_valid_output_path(valid_path)

    def test_accepts_path_direct_in_output_dir(self, tmp_output_dir: Path):
        """Ruta directamente en output_dir es valida."""
        orch = self.make_orch(tmp_output_dir)
        valid_path = tmp_output_dir / "frame_00001.png"
        assert orch._is_valid_output_path(valid_path)

    def test_rejects_windows_path(self, tmp_output_dir: Path):
        """Ruta Windows C:\\... es rechazada."""
        orch = self.make_orch(tmp_output_dir)
        bad_path = Path("C:\\Users\\artista\\Documents\\file_name1frane.exr")
        assert not orch._is_valid_output_path(bad_path)

    def test_rejects_unrelated_path(self, tmp_output_dir: Path):
        """Ruta fuera de output_dir es rechazada."""
        orch = self.make_orch(tmp_output_dir)
        bad_path = Path("/tmp/unrelated/file.exr")
        assert not orch._is_valid_output_path(bad_path)

    def test_rejects_root_path(self, tmp_output_dir: Path):
        """Ruta absoluta fuera de todo es rechazada."""
        orch = self.make_orch(tmp_output_dir)
        bad_path = Path("/etc/passwd")
        assert not orch._is_valid_output_path(bad_path)


class TestComputeSubdir:
    """Prueba _compute_subdir: derivar subdirectorio del path."""

    def make_orch(self, tmp_output_dir: Path) -> RenderOrchestrator:
        return RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=tmp_output_dir,
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
        )

    def test_file_in_subdirectory(self, tmp_output_dir: Path):
        """Archivo en subdirectorio -> nombre del subdirectorio."""
        orch = self.make_orch(tmp_output_dir)
        path = tmp_output_dir / "Temp" / "beauty_0001.exr"
        assert orch._compute_subdir(path) == "Temp"

    def test_file_in_nested_subdirectory(self, tmp_output_dir: Path):
        """Archivo en subdirectorio anidado -> ruta relativa completa."""
        orch = self.make_orch(tmp_output_dir)
        path = tmp_output_dir / "Temp" / "beauty" / "beauty_0001.exr"
        assert orch._compute_subdir(path) == "Temp/beauty"

    def test_file_direct_in_output_dir(self, tmp_output_dir: Path):
        """Archivo directamente en output_dir -> string vacio."""
        orch = self.make_orch(tmp_output_dir)
        path = tmp_output_dir / "frame_00001.png"
        assert orch._compute_subdir(path) == ""

    def test_file_outside_output_dir(self, tmp_output_dir: Path):
        """Archivo fuera de output_dir -> string vacio."""
        orch = self.make_orch(tmp_output_dir)
        path = Path("/tmp/unrelated/file.exr")
        assert orch._compute_subdir(path) == ""


class TestOutputTarget(unittest.TestCase):
    """Prueba el parametro output_target de RenderOrchestrator."""

    def test_default_output_target_is_drive(self) -> None:
        """Default output_target is 'drive'."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/render"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
        )
        self.assertEqual(orch.output_target, "drive")

    def test_explicit_drive_accepted(self) -> None:
        """Explicit 'drive' is accepted."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/render"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            output_target="drive",
        )
        self.assertEqual(orch.output_target, "drive")

    def test_explicit_zip_download_accepted(self) -> None:
        """Explicit 'zip_download' is accepted (no crash)."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/tmp/render"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            output_target="zip_download",
        )
        self.assertEqual(orch.output_target, "zip_download")

    def test_imports_without_error(self) -> None:
        """Orchestrator imports when both drive_sync and local_export are available."""
        from bcr import drive_sync
        from bcr import local_export

        self.assertIsNotNone(drive_sync)
        self.assertIsNotNone(local_export)


class TestFinalizeZipDownload(unittest.TestCase):
    """Prueba _finalize_zip_download en modo zip_download."""

    def setUp(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp())
        self._output_dir = self._tmpdir / "render_output"
        self._output_dir.mkdir()
        (self._output_dir / "frame_000001.exr").write_text("test frame")

        self.orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=self._output_dir,
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
            output_target="zip_download",
        )

    def tearDown(self) -> None:
        shutil.rmtree(str(self._tmpdir), ignore_errors=True)

    @patch("bcr.render_orchestrator.package_output")
    @patch("bcr.render_orchestrator.trigger_download")
    def test_finalize_calls_package_output(
        self, mock_trigger: MagicMock, mock_package: MagicMock
    ) -> None:
        """_finalize_zip_download calls package_output with correct output_dir."""
        zip_result = self._tmpdir / "test_output.zip"
        zip_result.write_text("dummy zip")
        mock_package.return_value = zip_result

        self.orch._finalize_zip_download()

        mock_package.assert_called_once_with(self._output_dir)

    @patch("bcr.render_orchestrator.package_output")
    @patch("bcr.render_orchestrator.trigger_download")
    def test_finalize_calls_trigger_download(
        self, mock_trigger: MagicMock, mock_package: MagicMock
    ) -> None:
        """_finalize_zip_download calls trigger_download with the zip path."""
        zip_result = self._tmpdir / "test_output.zip"
        zip_result.write_text("dummy zip")
        mock_package.return_value = zip_result

        self.orch._finalize_zip_download()

        mock_trigger.assert_called_once_with(zip_result)

    @patch("bcr.render_orchestrator.package_output")
    @patch("bcr.render_orchestrator.trigger_download")
    def test_graceful_handling_missing_output_dir(
        self, mock_trigger: MagicMock, mock_package: MagicMock
    ) -> None:
        """When output_dir doesn't exist, no crash and no packaging."""
        orch = RenderOrchestrator(
            blender_path=Path("/blender"),
            blend_file=Path("/s.blend"),
            output_dir=Path("/nonexistent/path"),
            drive_output_dir=Path("/drive/o"),
            blender_scripts_dir=Path("/scripts"),
            frame_start=1,
            frame_end=10,
            output_target="zip_download",
        )

        # Should not raise any exception
        orch._finalize_zip_download()

        mock_package.assert_not_called()
        mock_trigger.assert_not_called()
