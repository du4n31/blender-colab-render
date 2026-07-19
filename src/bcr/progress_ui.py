"""Interfaz de progreso en vivo usando ipywidgets para Google Colab.

Sin emojis, etiquetas en espanol, informacion clara de un vistazo.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional


class RenderProgressUI:
    """Widgets de progreso para el monitor en vivo del render."""

    def __init__(self) -> None:
        self._widgets_created = False
        self._output_widget = None
        self._progress_bar = None
        self._label_frame = None
        self._label_time = None
        self._label_avg = None
        self._label_eta = None
        self._label_upload = None
        self._label_warning = None

    def create_widgets(self) -> None:
        """Crea los widgets ipywidgets (llamar una vez al inicio)."""
        try:
            import ipywidgets as widgets  # type: ignore[import-untyped]
            from IPython.display import display
        except ImportError:
            self._output_widget = None
            self._widgets_created = False
            return

        self._progress_bar = widgets.FloatProgress(
            value=0,
            min=0,
            max=100,
            description="Progreso:",
            bar_style="info",
            style={"description_width": "initial"},
        )

        self._label_frame = widgets.HTML(value="Frame: -- / --")
        self._label_time = widgets.HTML(value="Ultimo frame: --")
        self._label_avg = widgets.HTML(value="Promedio: --")
        self._label_eta = widgets.HTML(value="Tiempo restante: --")
        self._label_upload = widgets.HTML(value="Cola de subida: --")

        self._label_warning = widgets.HTML(
            value="",
            layout=widgets.Layout(display="none"),
        )

        self._output_widget = widgets.VBox(
            children=[
                self._progress_bar,
                self._label_frame,
                self._label_time,
                self._label_avg,
                self._label_eta,
                self._label_upload,
                self._label_warning,
            ]
        )

        display(self._output_widget)
        self._widgets_created = True

    def update(
        self,
        frame: int,
        total: int,
        last_time: Optional[float] = None,
        avg_time: Optional[float] = None,
        eta: Optional[timedelta] = None,
        upload_queue_size: int = 0,
    ) -> None:
        """Actualiza todos los campos del monitor.

        Args:
            frame: Frame actual.
            total: Total de frames.
            last_time: Tiempo del ultimo frame en segundos.
            avg_time: Tiempo promedio por frame en segundos.
            eta: Tiempo restante estimado.
            upload_queue_size: Frames pendientes de subir a Drive.
        """
        if not self._widgets_created:
            return

        porcentaje = (frame / total * 100) if total > 0 else 0

        self._progress_bar.value = porcentaje  # type: ignore[union-attr]
        self._label_frame.value = f"Frame: {frame} / {total} ({porcentaje:.1f}%)"

        if last_time is not None:
            self._label_time.value = f"Ultimo frame: {last_time:.1f}s"

        if avg_time is not None:
            self._label_avg.value = f"Promedio: {avg_time:.1f}s"

        if eta is not None:
            eta_str = self._format_timedelta(eta)
            finish_time = datetime.now(timezone.utc) + eta
            finish_str = finish_time.strftime("%H:%M UTC")
            self._label_eta.value = (
                f"Tiempo restante: {eta_str} (fin estimado: {finish_str})"
            )

        self._label_upload.value = f"Cola de subida: {upload_queue_size} frames"

    def show_warning(self, message: str) -> None:
        """Muestra una advertencia no bloqueante."""
        if not self._widgets_created:
            return
        self._label_warning.value = (
            f'<p style="color: #cc7700; font-weight: bold;">{message}</p>'
        )
        self._label_warning.layout.display = ""  # type: ignore[union-attr]

    def show_error(self, message: str) -> None:
        """Muestra un error fatal."""
        if not self._widgets_created:
            return
        self._label_warning.value = (
            f'<p style="color: #cc0000; font-weight: bold;">ERROR: {message}</p>'
        )
        self._label_warning.layout.display = ""  # type: ignore[union-attr]

    def show_completion(self) -> None:
        """Muestra resumen de finalizacion."""
        if not self._widgets_created:
            return
        self._progress_bar.bar_style = "success"  # type: ignore[union-attr]
        self._label_warning.value = (
            '<p style="color: #007700; font-weight: bold;">Render completado.</p>'
        )
        self._label_warning.layout.display = ""  # type: ignore[union-attr]

    @staticmethod
    def _format_timedelta(td: timedelta) -> str:
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
