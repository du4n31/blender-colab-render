"""Render process orchestrator.

Launches Blender as a subprocess, reads stdout in real time,
and uploads each detected frame to Drive on a separate thread while
Blender renders the next frame.
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

from bcr.config import BACKLOG_LIMIT, RENDER_OUTPUT_PATTERN, extract_frame_number
from bcr.drive_backend import DriveBackendError
from bcr.drive_sync import DriveSyncError, remove_local, upload_frame
from bcr.local_export import LocalExportError, check_disk_space, package_output, trigger_download
from bcr.state_manager import load_state, reconcile_with_files, save_state


class RenderError(Exception):
    """Error during the render process."""


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
    """Orchestrate the complete render job."""

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
        output_target: str = "drive",
        custom_script_paths: Optional[list[Path]] = None,
        progress_callback: Optional[ProgressCallback] = None,
        drive_backend: Optional[object] = None,
    ):
        self.blender_path = Path(blender_path)
        self.blend_file = Path(blend_file)
        self.output_dir = Path(output_dir)
        self.drive_output_dir = Path(drive_output_dir)
        self.blender_scripts_dir = Path(blender_scripts_dir)
        self.frame_start = frame_start
        self.frame_end = frame_end
        self._requested_frame_start = frame_start
        self._requested_frame_end = frame_end
        self._requested_total_frames = frame_end - frame_start + 1
        self.device = device
        self.output_mode = output_mode
        self.output_target = output_target
        self.custom_script_paths = custom_script_paths or []
        self.progress_callback = progress_callback
        # Backend opcional de Drive (ej. ServiceAccountDriveBackend). Si es
        # If None (default), frame uploads and state persistence use the
        # mounted filesystem as before; see _dispatch_upload
        # y _dispatch_save_state.
        self.drive_backend = drive_backend

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
            2. blend file (after the .blend file, --render-output is not overwritten)
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

        # Use a disposable directory for direct render output.
        # Compositor File Output nodes are remapped by the driver
        # (render_frame_driver.py -> _remap_file_output_nodes()).
        output_pattern = str(self.output_dir / RENDER_OUTPUT_PATTERN)
        cmd.extend(["--render-output", output_pattern])

        # Audio desactivado (por defecto en background mode, pero explicito no duele)
        cmd.append("-noaudio")

        # Frame range and render trigger
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
        cmd.extend(["--output-dir", str(self.output_dir)])

        return cmd

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the complete render process.

        Launch Blender as a subprocess and monitor stdout in real time,
        uploading frames to Drive incrementally according to ``output_target``
        o los mantiene locales para empaquetar al final.
        """
        if self.output_target == "zip_download":
            ok, msg = check_disk_space(self.output_dir)
            if not ok:
                print(f"[orchestrator] WARNING: {msg}", file=sys.stderr)

        total_frames = self.frame_end - self.frame_start + 1

        # Resume from durable Drive output, not from the state file alone.
        # Reconcile the checkpoint against files actually present in storage.
        if self.output_target == "drive":
            saved_frame = load_state(
                self.drive_output_dir, total_frames, backend=self.drive_backend
            )
            confirmed_frame = reconcile_with_files(
                self.drive_output_dir, saved_frame, backend=self.drive_backend,
                frame_start=self.frame_start
            )
            if confirmed_frame >= self.frame_start:
                if confirmed_frame >= self.frame_end:
                    print("[orchestrator] All requested frames are already present; nothing to render.")
                    return
                self.frame_start = confirmed_frame + 1
                print(f"[orchestrator] Resuming from frame {self.frame_start} (frame {confirmed_frame} is confirmed).")

        cmd = self.build_command()
        print(f"[orchestrator] Command: {' '.join(cmd)}")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            msg = f"Failed to launch Blender: {exc}"
            raise RenderError(msg) from exc

        self._current_frame = 0
        self._uploaded_paths: set[str] = set()  # paths already processed
        upload_pool = ThreadPoolExecutor(max_workers=2)

        try:
            for line in self._process.stdout or []:
                line = line.rstrip("\n")
                print(line, file=sys.stderr)  # re-enviar a stderr para visibilidad

                # Detect completed frames using the exact path reported by Blender
                result = self._parse_saved_line(line)
                if result is not None:
                    frame_num, local_path = result

                    # Validate that the path is under output_dir (filters
                    # paths Windows como C:\Users\... que Blender imprime
                    # si los File Output nodes no fueron remapeados).
                    if not self._is_valid_output_path(local_path):
                        continue

                    # Skip this path if it has already been processed
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

                    if self.output_target == "drive":
                        # Queue upload to Drive (in parallel with rendering)
                        if local_path.exists():
                            self._pending_frames.add(frame_num)
                            subdir = self._compute_subdir(local_path)
                            future = upload_pool.submit(
                                self._upload_and_cleanup,
                                local_path,
                                frame_num,
                                subdir,
                            )
                            self._upload_futures.append(future)
                    elif self.output_target == "zip_download":
                        # In zip_download mode, frames remain on disk
                        pass

                    # Check the upload backlog (Drive mode only)
                    if self.output_target == "drive":
                        self._wait_if_backlogged()

            # Esperar a que terminen todas las subidas (modo drive)
            for future in as_completed(self._upload_futures):
                try:
                    future.result()
                except Exception as exc:
                    print(f"[orchestrator] Upload error: {exc}", file=sys.stderr)

        finally:
            upload_pool.shutdown(wait=True)
            self._cleanup_process()

        # Finalizar segun modo
        if self.output_target == "drive":
            self._reconcile_pending()
        elif self.output_target == "zip_download":
            self._finalize_zip_download()

    # ------------------------------------------------------------------
    # Parseo de stdout
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_saved_line(
        line: str,
    ) -> Optional[tuple[int, Path]]:
        """Detecta lineas 'Saved: '<ruta>'' y extrae (frame, ruta_exacta).

        Blender imprime lineas como:
            Saved: '/content/render_tmp/Result_000001.exr'
            Saved: '/content/render_tmp/File_Output_001_000001.exr'
            Time: 00:00.53 (Saving: 00:00.08)

        The frame number is extracted as a block of exactly six digits
        en cualquier posicion del nombre (no solo antes de la extension).
        Esto cubre tanto nodos single-layer (item.name + ######) como
        nodos multilayer (file_name + ######).

        Ignore disposable files (_discard_, _render_result_) that
        are direct render output (not File Output node output).

        Returns:
            tuple (int, Path) containing the frame number and exact path,
            or None if extraction fails or the file is disposable.
        """
        match = re.search(r"Saved:\s*'([^']+)'", line)
        if not match:
            return None

        path_str = match.group(1)

        # Ignore disposable files (direct render output,
        # no de File Output nodes).
        if "_discard_" in path_str or "_render_result_" in path_str:
            return None

        path = Path(path_str)
        frame_num = extract_frame_number(path_str)
        if frame_num is not None:
            return frame_num, path

        return None

    def _is_valid_output_path(self, path: Path) -> bool:
        r"""Validate that a path is inside the managed output directory.

        Reject Windows paths (C:\\...), arbitrary paths outside output_dir,
        and files from compositor nodes that were not remapped correctly.
        """
        try:
            path.relative_to(self.output_dir)
            return True
        except ValueError:
            return False

    def _compute_subdir(self, path: Path) -> str:
        """Deriva el subdirectorio relativo para organizar en Drive.

        Si el archivo esta en output_dir/subdir/archivo.ext, retorna
        'subdir' (el nodo que lo produjo). Si esta directamente en
        output_dir, retorna '' (raiz).

        Ejemplos:
            path=/content/render_tmp/Temp/beauty_0001.exr
            output_dir=/content/render_tmp
            -> retorna 'Temp'

            path=/content/render_tmp/frame_00001.png
            output_dir=/content/render_tmp
            -> retorna ''
        """
        try:
            rel = path.relative_to(self.output_dir)
            parent = rel.parent
            return str(parent) if str(parent) != "." else ""
        except ValueError:
            return ""

    def _find_frame_file(self, frame_num: int) -> Optional[Path]:
        """Find the rendered frame file in the temporary directory.

        Find any file whose name contains exactly six digits
        que coincidan con frame_num.
        """
        if not self.output_dir.exists():
            return None

        for f in self.output_dir.rglob("*"):
            if not f.is_file():
                continue
            name = f.name
            # Ignorar descartables
            if name.startswith("_discard") or name.startswith("_render_result"):
                continue
            nf = extract_frame_number(name)
            if nf is not None and nf == frame_num:
                return f

        return None

    # ------------------------------------------------------------------
    # Subida a Drive
    # ------------------------------------------------------------------

    def _dispatch_upload(self, local_path: Path, frame_num: int, subdir: str = "") -> None:
        """Upload a frame using the active backend (API) or mounted Drive sync."""
        if self.drive_backend is not None:
            self.drive_backend.upload_frame(local_path, self.drive_output_dir, frame_num, subdir)
        else:
            upload_frame(local_path, self.drive_output_dir, frame_num, subdir)

    def _dispatch_save_state(self, last_frame: int, total_frames: int) -> None:
        """Save state using the active backend (API) or state_manager (mounted Drive)."""
        save_state(self.drive_output_dir, last_frame, total_frames, backend=self.drive_backend)

    def _upload_and_cleanup(
        self,
        local_path: Path,
        frame_num: int,
        subdir: str = "",
    ) -> None:
        """Upload a frame to Drive and remove its local copy.

        Args:
            local_path: Local path to the rendered file.
            frame_num: Numero de frame.
            subdir: Subdirectorio en Drive para organizar multiples
                salidas (ej: nombre del nodo File Output).
        """
        try:
            self._dispatch_upload(local_path, frame_num, subdir)
            remove_local(local_path)
            # Actualizar estado en Drive
            self._dispatch_save_state(
                frame_num,
                self._requested_total_frames,
            )
            self._pending_frames.discard(frame_num)
        except (DriveSyncError, DriveBackendError) as exc:
            print(
                f"[orchestrator] Failed to upload frame {frame_num}: {exc}",
                file=sys.stderr,
            )

    def _wait_if_backlogged(self) -> None:
        """Wait for the upload queue to fall below the limit when backlogged."""
        while len(self._pending_frames) >= BACKLOG_LIMIT:
            print(
                f"[orchestrator] Upload backlog ({len(self._pending_frames)}), "
                "waiting...",
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

        # Last-frame duration (difference between consecutive detections)
        if len(self._frame_times) >= 2:
            self._last_time = self._frame_times[-1] - self._frame_times[-2]
        else:
            self._last_time = None

        # Average frame duration, starting with the second frame
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
            remaining = self._requested_frame_end - self._current_frame
            eta = None
            if self._avg_time and self._avg_time > 0:
                eta = timedelta(seconds=int(self._avg_time * remaining))

            self.progress_callback(
                frame=self._current_frame - self._requested_frame_start + 1,
                total=self._requested_total_frames,
                last_time=self._last_time,
                avg_time=self._avg_time,
                eta=eta,
                upload_queue_size=len(self._pending_frames),
            )

    # ------------------------------------------------------------------
    # Finalizacion zip_download
    # ------------------------------------------------------------------

    def _finalize_zip_download(self) -> None:
        """Package and download all output as a .zip in zip_download mode."""
        print("[orchestrator] Packaging output as .zip...", file=sys.stderr)
        if not self.output_dir.exists():
            print(
                f"[orchestrator] Output directory does not exist: {self.output_dir}",
                file=sys.stderr,
            )
            return
        try:
            zip_path = package_output(self.output_dir)
            print(
                f"[orchestrator] .zip created: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)",
                file=sys.stderr,
            )
            trigger_download(zip_path)
        except LocalExportError as exc:
            print(
                f"[orchestrator] Packaging error: {exc}",
                file=sys.stderr,
            )

    # ------------------------------------------------------------------
    # Reconciliacion y limpieza
    # ------------------------------------------------------------------

    def _reconcile_pending(self) -> None:
        """Al finalizar (o si el proceso se cae), sube frames pendientes."""
        if self._reconcile_done:
            return
        self._reconcile_done = True

        print("[orchestrator] Reconciling pending frames...", file=sys.stderr)

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
                frame_num = extract_frame_number(f.name)
                if frame_num is None:
                    continue
                try:
                    subdir = self._compute_subdir(f)
                    self._dispatch_upload(f, frame_num, subdir)
                    remove_local(f)
                    print(
                        f"[orchestrator] Frame {frame_num} recovered and uploaded: {f.name}",
                        file=sys.stderr,
                    )
                except (DriveSyncError, DriveBackendError) as exc:
                    print(
                        f"[orchestrator] Reconciliation error: {exc}",
                        file=sys.stderr,
                    )

    def _cleanup_process(self) -> None:
        """Clean up the Blender process if it is still running."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

    def get_exit_code(self) -> Optional[int]:
        """Return the Blender process exit code, or None if it is still running."""
        if self._process is None:
            return None
        return self._process.poll()