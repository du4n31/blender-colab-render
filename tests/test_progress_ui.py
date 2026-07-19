"""Pruebas para progress_ui.py."""

from datetime import timedelta

import pytest

from bcr.progress_ui import RenderProgressUI


class TestRenderProgressUI:
    """Prueba la logica de RenderProgressUI (sin ipywidgets real)."""

    def test_create_without_ipywidgets(self):
        """Sin ipywidgets, create_widgets no falla."""
        ui = RenderProgressUI()
        # No deberia lanzar error aunque ipywidgets no este disponible
        ui.create_widgets()
        assert ui._widgets_created is False

    def test_update_safe_without_widgets(self):
        """update() no falla si no hay widgets creados."""
        ui = RenderProgressUI()
        # Simular que no hay widgets
        ui._widgets_created = False
        # No deberia lanzar error
        ui.update(
            frame=1,
            total=100,
            last_time=30.5,
            avg_time=28.3,
            eta=timedelta(minutes=45),
            upload_queue_size=2,
        )

    def test_show_warning_safe_without_widgets(self):
        """show_warning() no falla sin widgets."""
        ui = RenderProgressUI()
        ui.show_warning("Test warning")

    def test_show_error_safe_without_widgets(self):
        """show_error() no falla sin widgets."""
        ui = RenderProgressUI()
        ui.show_error("Test error")

    def test_show_completion_safe_without_widgets(self):
        """show_completion() no falla sin widgets."""
        ui = RenderProgressUI()
        ui.show_completion()

    def test_format_timedelta_hours(self):
        """_format_timedelta con horas."""
        td = timedelta(hours=2, minutes=30, seconds=15)
        result = RenderProgressUI._format_timedelta(td)
        assert result == "2h 30m 15s"

    def test_format_timedelta_minutes(self):
        """_format_timedelta solo minutos."""
        td = timedelta(minutes=5, seconds=45)
        result = RenderProgressUI._format_timedelta(td)
        assert result == "5m 45s"

    def test_format_timedelta_seconds(self):
        """_format_timedelta solo segundos."""
        td = timedelta(seconds=30)
        result = RenderProgressUI._format_timedelta(td)
        assert result == "30s"

    def test_format_timedelta_zero(self):
        """_format_timedelta con 0."""
        td = timedelta(seconds=0)
        result = RenderProgressUI._format_timedelta(td)
        assert result == "0s"
