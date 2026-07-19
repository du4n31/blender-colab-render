"""Orquestador del proceso de render.

Lanza Blender como subproceso no bloqueante, lee su stdout en tiempo real,
y para cada frame detectado lo sube a Drive en un hilo separado mientras
Blender renderiza el siguiente.
"""

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from bcr.config import BACKLOG_LIMIT, RENDER_OUTPUT_PATTERN
from bcr.drive_sync import DriveSyncError, remove_local, upload_frame
from bcr.state_manager import reconcile_with_files, save_state


class RenderError(Exception):
    """Error durante el proceso de render."""


# Callback type for progress updates
ProgressCallback = Callable[
    [
        int,   # frame
        int,   # total
        Optional[float],  # last_time
        Optional[float],  # avg_time
        Optional[timedelta],  # eta
        int,   # upload_queue_size
    ],
    None,
]


class RenderOrchestrator:
    """Orquesta el proceso completo de render."""

    def __init__(
        self,
        blender_path: Path,
        blend_file: Path,
        output_dir: Path,
        drive_output_dir: Path,
        blender_scripts_dir: Path,
        frame_start: int = 1,
        frame_end: int = 1,
        device: str = "OPTIX",
        output_mode: str = "compositor",
        custom_script_paths: Optional[list[Path]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.blender_path = Path(blender_path)
        self.blend_file = Path(blend_file)
        self.output_dir = Path(output_dir)
        self.drive_output_dir = Path(drive_output_dir)
        self.blender_scripts_dir = Path(blender_scripts_dir)
        self.frame_start = frame_start
        self.frame_end = frame_end
        self.device = device
        self.output_mode = output_mode
        self.custom_script_paths = custom_script_paths or []
        self.progress_callback = progress_callback

        # Estado interno
        self._process: Optional[subprocess.Popen] = None
        self._current_frame = 0
        self._frame_times: list[float] = []
        self._last_time: Optional[float] = None
        self._avg_time: Optional[float] = None
        self._upload_futures: list = []
        self._reconcile_done = False
        self._pending_frames: set[int] = set()
        self._uploaded_paths: set[str] = set()

    # ------------------------------------------------------------------
    # Construccion del comando
    # ------------------------------------------------------------------

    def build_command(self) -> list[str]:
        """Construye la lista de argumentos para Blender en el ORDEN correcto.

        El orden critical (ver docs de Blender):
            1. --background
            2. archivo .blend  (despues del .blend, --render-output no se sobreescribe)
            3. motor, python scripts, output
            4. render trigger (--render-anim o --render-frame) AL FINAL
            5. -- seguido de opciones de Cycles
        """
        cmd: list[str] = [
            str(self.blender_path),
            "--background",
            str(self.blend_file),
            "--engine", "CYCLES",
        ]

        # Script driver (device + output mode)
        driver_script = self.blender_scripts_dir / "render_frame_driver.py"
        cmd.extend(["--python", str(driver_script)])

        # Scripts personalizados adicionales
        for script_path in self.custom_script_paths:
            cmd.extend(["--python", str(script_path)])

        # Output: usar directorio descartable para la salida directa del render.
        # Los File Output nodes del compositor son remapeados por el driver
        # (render_frame_driver.py -> _remap_file_output_nodes()).
        output_pattern = str(self.output_dir / RENDER_OUTPUT_PATTERN)
        cmd.extend(["--render-output", output_pattern])

        # Audio desactivado (por defecto en background mode, pero explicito no duele)
        cmd.append("-noaudio")

        # Rango de frames y trigger de render
        total_frames = self.frame_end - self.frame_start + 1
        if total_frames == 1:
            cmd.extend(["--render-frame", str(self.frame_start)])
        else:
            cmd.extend(["--frame-start", str(self.frame_start)])
            cmd.extend(["--frame-end", str(self.frame_end)])
            cmd.append("--render-anim")

        # Opciones de Cycles (despues de --)
        cmd.append("--")
        cmd.extend(["--cycles-device", self.device])
        cmd.extend(["--output-mode", self.output_mode])

        return cmd

    # ------------------------------------------------------------------
    # Ejecucion
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Ejecuta el proceso de render completo.

        Lanza Blender como subproceso, monitoriza stdout en tiempo real,
        y sube frames a Drive concurrentemente.
        """
        cmd = self.build_command()
        print(f"[orchestrator] Comando: {' '.join(cmd)}")

        total_frames = self.frame_end - self.frame_start + 1

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            msg = f"Error al lanzar Blender: {exc}"
            raise RenderError(msg) from exc

        self._current_frame = 0
        self._uploaded_paths: set[str] = set()  # rutas ya subidas
        upload_pool = ThreadPoolExecutor(max_workers=2)

        try:
            for line in self._process.stdout or []:
                line = line.rstrip("\n")
                print(line, file=sys.stderr)  # re-enviar a stderr para visibilidad

                # Detectar frames completados (usa la ruta exacta de Blender)
                result = self._parse_saved_line(line)
                if result is not None:
                    frame_num, local_path = result

                    # Saltar si ya subimos esta ruta exacta
                    path_key = str(local_path)
                    if path_key in self._uploaded_paths:
                        continue
                    self._uploaded_paths.add(path_key)

                    # Actualizar metricas solo cuando cambia el frame
                    if frame_num != self._current_frame:
                        self._current_frame = frame_num
                        now = time.time()
                        self._frame_times.append(now)
                        self._update_metrics()

                    # Encolar subida (usa la ruta exacta, no busca por frame)
                    if local_path.exists():
                        self._pending_frames.add(frame_num)
                        future = upload_pool.submit(
                            self._upload_and_cleanup,
                            local_path,
                            frame_num,
                        )
                        self._upload_futures.append(future)

                    # Verificar backlog
                    self._wait_if_backlogged()

            # Esperar a que terminen todas las subidas
            for future in as_completed(self._upload_futures):
                try:
                    future.result()
                except Exception as exc:
                    print(f"[orchestrator] Error en subida: {exc}", file=sys.stderr)

        finally:
            upload_pool.shutdown(wait=True)
            self._cleanup_process()

        # Reconciliacion final
        self._reconcile_pending()

    # ------------------------------------------------------------------
    # Parseo de stdout
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_saved_line(
        line: str,
    ) -> Optional[tuple[int, Path]]:
        """Detecta lineas 'Saved: '<ruta>'' y extrae (frame, ruta_exacta).

        Blender imprime lineas como:
            Saved: '/content/render_tmp/frame_00001.png'
            Saved: '/content/render_tmp/slot_name0001.exr'
            Time: 00:00.53 (Saving: 00:00.08)

        Ignora archivos descartables (_discard_, _render_result_) que
        son la salida directa del render (no de File Output nodes).

        Returns:
            tuple (int, Path) con numero de frame y ruta exacta,
            o None si no se pudo extraer o es descartable.
        """
        match = re.search(r"Saved:\s*'([^']+)'", line)
        if not match:
            return None

        path_str = match.group(1)

        # Ignorar archivos descartables (salida directa del render,
        # no de File Output nodes).
        if "_discard_" in path_str or "_render_result_" in path_str:
            return None

        path = Path(path_str)

        # Extraer numero de frame del archivo (PNG: frame_00001)
        frame_match = re.search(r"frame_(\d+)", path_str)
        if frame_match:
            return int(frame_match.group(1)), path

        # Extraer numero de frame de EXR: patron como "slot_name0001.exr"
        # Toma el ultimo grupo de digitos antes de la extension.
        frame_match = re.search(r"_(\d+)(?=\.\w+$)", path_str)
        if frame_match:
            return int(frame_match.group(1)), path

        # Fallback: cualquier grupo de digitos al final del nombre
        frame_match = re.search(r"(\d+)(?=\.\w+$)", path_str)
        if frame_match:
            return int(frame_match.group(1)), path

        return None

    def _find_frame_file(self, frame_num: int) -> Optional[Path]:
        """Busca el archivo de frame renderizado en el directorio temporal.

        Busca primero PNG con el patron frame_NNNNNN, luego EXR
        cuyos nombres contengan el numero de frame.
        """
        # 1. Buscar PNG con patron frame_NNNNNN
        pattern = f"frame_{frame_num:06d}.png"
        candidate = self.output_dir / pattern
        if candidate.exists():
            return candidate

        # 2. Buscar cualquier archivo que contenga el numero de frame
        #    (EXR de File Output nodes, etc.)
        for f in self.output_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name
            # Ignorar descartables
            if name.startswith("_discard") or name.startswith("_render_result"):
                continue
            # Extraer el ultimo numero antes de la extension
            m = re.search(r"_?(\d+)(?=\.\w+$)", name)
            if m and int(m.group(1)) == frame_num:
                return f
            m = re.search(r"(\d+)(?=\.\w+$)", name)
            if m and int(m.group(1)) == frame_num:
                return f

        return None

    # ------------------------------------------------------------------
    # Subida a Drive
    # ------------------------------------------------------------------

    def _upload_and_cleanup(self, local_path: Path, frame_num: int) -> None:
        """Sube un frame a Drive y lo borra localmente."""
        try:
            upload_frame(local_path, self.drive_output_dir, frame_num)
            remove_local(local_path)
            # Actualizar estado en Drive
            save_state(
                self.drive_output_dir,
                frame_num,
                self.frame_end - self.frame_start + 1,
            )
            self._pending_frames.discard(frame_num)
        except DriveSyncError as exc:
            print(
                f"[orchestrator] Error al subir frame {frame_num}: {exc}",
                file=sys.stderr,
            )

    def _wait_if_backlogged(self) -> None:
        """Espera a que la cola de subida baje del limite si hay backlog."""
        while len(self._pending_frames) >= BACKLOG_LIMIT:
            print(
                f"[orchestrator] Backlog de subida ({len(self._pending_frames)}), "
                "esperando...",
                file=sys.stderr,
            )
            time.sleep(2)

    # ------------------------------------------------------------------
    # Metricas
    # ------------------------------------------------------------------

    def _update_metrics(self) -> None:
        """Actualiza metricas de tiempo y notifica al callback."""
        if len(self._frame_times) < 2:
            return

        # Tiempo del ultimo frame (diferencia entre detecciones consecutivas)
        if len(self._frame_times) >= 2:
            self._last_time = self._frame_times[-1] - self._frame_times[-2]
        else:
            self._last_time = None

        # Tiempo promedio desde el segundo frame en adelante
        if len(self._frame_times) >= 2:
            diffs = [
                self._frame_times[i] - self._frame_times[i - 1]
                for i in range(1, len(self._frame_times))
            ]
            self._avg_time = sum(diffs) / len(diffs)
        else:
            self._avg_time = None

        # Notificar
        if self.progress_callback:
            remaining = (self.frame_end - self.frame_start + 1) - self._current_frame
            eta = None
            if self._avg_time and self._avg_time > 0:
                eta = timedelta(seconds=int(self._avg_time * remaining))

            self.progress_callback(
                frame=self._current_frame - self.frame_start + 1,
                total=self.frame_end - self.frame_start + 1,
                last_time=self._last_time,
                avg_time=self._avg_time,
                eta=eta,
                upload_queue_size=len(self._pending_frames),
            )

    # ------------------------------------------------------------------
    # Reconciliacion y limpieza
    # ------------------------------------------------------------------

    def _reconcile_pending(self) -> None:
        """Al finalizar (o si el proceso se cae), sube frames pendientes."""
        if self._reconcile_done:
            return
        self._reconcile_done = True

        print("[orchestrator] Reconciliando frames pendientes...", file=sys.stderr)

        # Subir frames locales que no se hayan subido
        # Usa rglob para encontrar archivos en subdirectorios (los File Output
        # nodes remapeados pueden crear subdirectorios en output_dir).
        if self.output_dir.exists():
            for f in sorted(self.output_dir.rglob("*")):
                if not f.is_file():
                    continue
                # Saltar descartables
                if f.name.startswith("_discard") or f.name.startswith("_render_result"):
                    continue
                # Detectar PNG con patron frame_NNNNNN
                frame_match = re.search(r"frame_(\d+)", f.name)
                if frame_match:
                    frame_num = int(frame_match.group(1))
                else:
                    # Detectar EXR: ultimo grupo de digitos antes de la extension
                    frame_match = re.search(r"_?(\d+)(?=\.\w+$)", f.name)
                    if not frame_match:
                        frame_match = re.search(r"(\d+)(?=\.\w+$)", f.name)
                    if not frame_match:
                        continue
                    frame_num = int(frame_match.group(1))
                try:
                    upload_frame(f, self.drive_output_dir, frame_num)
                    remove_local(f)
                    print(
                        f"[orchestrator] Frame {frame_num} recuperado y subido: {f.name}",
                        file=sys.stderr,
                    )
                except DriveSyncError as exc:
                    print(
                        f"[orchestrator] Error en reconciliacion: {exc}",
                        file=sys.stderr,
                    )

    def _cleanup_process(self) -> None:
        """Limpia el proceso de Blender si sigue vivo."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

    def get_exit_code(self) -> Optional[int]:
        """Devuelve el codigo de salida del proceso de Blender, o None si sigue corriendo."""
        if self._process is None:
            return None
        return self._process.poll()
