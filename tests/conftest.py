"""Configuracion compartida de pytest."""

from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Directorio temporal para simular output de render."""
    d = tmp_path / "render_output"
    d.mkdir()
    return d


@pytest.fixture
def tmp_drive_dir(tmp_path: Path) -> Path:
    """Directorio temporal para simular Drive montado."""
    d = tmp_path / "drive"
    d.mkdir()
    return d
