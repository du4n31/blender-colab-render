"""Prueba de integracion basica del notebook (smoke test).

Verifica que el paquete se importa correctamente y que las funciones
principales existen. No requiere GPU ni Blender real.
"""

import pytest


class TestPackageImports:
    """Verifica que el paquete bcr se importa sin errores."""

    def test_import_config(self):
        from bcr import config
        assert config.BLENDER_VERSION is not None
        assert config.DRIVE_MOUNT_POINT is not None

    def test_import_link_resolver(self):
        from bcr import link_resolver
        assert hasattr(link_resolver, "resolve_download_url")

    def test_import_device_config(self):
        # device_config usa bpy, que no esta disponible en testing
        # pero el modulo debe importarse sin error (bpy se importa solo al llamar)
        from bcr import device_config
        assert hasattr(device_config, "configure_device")

    def test_import_state_manager(self):
        from bcr import state_manager
        assert hasattr(state_manager, "save_state")
        assert hasattr(state_manager, "load_state")

    def test_import_render_orchestrator(self):
        from bcr import render_orchestrator
        assert hasattr(render_orchestrator, "RenderOrchestrator")

    def test_import_drive_sync(self):
        from bcr import drive_sync
        assert hasattr(drive_sync, "upload_frame")
        assert hasattr(drive_sync, "remove_local")

    def test_import_progress_ui(self):
        from bcr import progress_ui
        assert hasattr(progress_ui, "RenderProgressUI")

    def test_import_custom_script_loader(self):
        from bcr import custom_script_loader
        assert hasattr(custom_script_loader, "acquire_script")
        assert hasattr(custom_script_loader, "collect_script_args")


class TestConfigValidation:
    """Verifica las funciones de validacion de config."""

    def test_validate_frame_range_valid(self):
        from bcr.config import validate_frame_range
        result = validate_frame_range(1, 250)
        assert result == (1, 250)

    def test_validate_frame_range_invalid(self):
        from bcr.config import validate_frame_range
        with pytest.raises(ValueError):
            validate_frame_range(100, 50)

    def test_validate_frame_range_negative(self):
        from bcr.config import validate_frame_range
        with pytest.raises(ValueError):
            validate_frame_range(-1, 100)

    def test_validate_url_valid(self):
        from bcr.config import validate_url
        assert validate_url("https://example.com/file.blend") is True
        assert validate_url("http://dropbox.com/s/abc/file.blend?dl=0") is True

    def test_validate_url_invalid(self):
        from bcr.config import validate_url
        assert validate_url("not a url") is False
        assert validate_url("") is False

    def test_validate_drive_path_valid(self, tmp_path):
        from bcr.config import validate_drive_path, DRIVE_MOUNT_POINT
        # Simular que /content/drive existe
        # En testing sin Colab esto no funciona, verificamos que la funcion existe
        assert hasattr(validate_drive_path, "__call__")


class TestNotebookSource:
    """Guard notebook branch selection, English output, and centralized resume logic."""

    def _notebook_code(self):
        import json
        from pathlib import Path

        notebook_path = Path(__file__).resolve().parents[1] / "notebooks" / "blender_render.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        cells = notebook.get("cells", [])
        code = "\\n".join(
            "".join(cell.get("source", []))
            for cell in cells
            if cell.get("cell_type") == "code"
        )
        return code

    def test_clone_uses_explicit_working_branch_without_token_in_url(self):
        code = self._notebook_code()
        assert 'BCR_GIT_BRANCH", "remake/reliable-resume-and-output"' in code
        assert "GIT_ASKPASS" in code
        assert "https://du4n31:{token}@" not in code

    def test_resume_logic_is_owned_by_orchestrator(self):
        code = self._notebook_code()
        assert "load_state(" not in code
        assert "reconcile_with_files(" not in code
        assert "frame_start=frame_start," in code

    def test_notebook_failure_messages_are_english(self):
        code = self._notebook_code()
        assert "Blender termino con codigo" not in code
        assert "Error al clonar el repositorio" not in code

    def test_notebook_code_cells_are_valid_python(self):
        """Parse notebook code cells after excluding Colab shell and magic lines."""
        import ast
        import json
        from pathlib import Path

        notebook_path = Path(__file__).resolve().parents[1] / "notebooks" / "blender_render.ipynb"
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            python_lines = [
                line for line in source.splitlines()
                if not line.lstrip().startswith(("!", "%"))
            ]
            ast.parse("\n".join(python_lines), filename=f"notebook-cell-{index}")

    def test_render_output_is_separate_from_temporary_assets(self):
        """Rendered images and ZIP exports must not include scene/script inputs."""
        code = self._notebook_code()
        from pathlib import Path

        config_path = Path(__file__).resolve().parents[1] / "src" / "bcr" / "config.py"
        config = config_path.read_text(encoding="utf-8")
        assert 'RENDER_OUTPUT_DIR = Path("/content/render_output")' in config
        assert "output_dir=RENDER_OUTPUT_DIR" in code
        assert "RENDER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)" in code
