"""Local ZIP packaging and download for zip_download mode.

Like drive_sync.py, but packages frames locally instead of uploading each frame to Drive.
incrementally; it keeps them local and packages them into a single .zip archive.
"""

import shutil
from pathlib import Path


class LocalExportError(Exception):
    """Error raised while packaging or downloading local output."""


def package_output(output_dir: Path, output_name: str = "render_output") -> Path:
    """Package the complete output directory into a .zip archive.

    Args:
        output_dir: Directory containing rendered frames (may include
            subdirectorios por nodo).
        output_name: Nombre base del .zip (default: "render_output").

    Returns:
        Path to the created .zip archive.

    Raises:
        LocalExportError: if the directory does not exist or is empty.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        msg = f"Output directory does not exist: {output_dir}"
        raise LocalExportError(msg)

    if not any(output_dir.iterdir()):
        msg = f"Output directory is empty: {output_dir}"
        raise LocalExportError(msg)

    # Colocar el .zip en /tmp para no ocupar espacio en /content
    zip_path = shutil.make_archive(
        base_name=str(Path("/tmp") / output_name),
        format="zip",
        root_dir=output_dir,
    )

    return Path(zip_path)


def trigger_download(zip_path: Path) -> None:
    """Trigger the .zip download in the Colab browser.

    Args:
        zip_path: Path to the .zip archive to download.

    Raises:
        LocalExportError: if the .zip archive does not exist.
    """
    zip_path = Path(zip_path)

    if not zip_path.exists():
        msg = f"The .zip archive does not exist: {zip_path}"
        raise LocalExportError(msg)

    try:
        # google.colab is only available in the Colab environment
        from google.colab import files  # type: ignore[import-untyped]

        files.download(str(zip_path))
    except ImportError:
        print(f"Non-Colab environment: the archive is at {zip_path}")


def check_disk_space(
    output_dir: Path, min_free_gb: float = 2.0
) -> tuple[bool, str]:
    """Check whether enough disk space is available for rendering.

    Args:
        output_dir: Directory where frames will be written.
        min_free_gb: Espacio libre minimo en GB (default: 2.0).

    Returns:
        (ok, mensaje) — ok=True si hay espacio suficiente,
        ok=False with a warning message otherwise.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        return (False, f"Directory does not exist: {output_dir}")

    usage = shutil.disk_usage(output_dir)
    free_gb = usage.free / (1024**3)

    if free_gb >= min_free_gb:
        return (True, "")

    msg = (
        f"Insufficient free space: {free_gb:.1f} GB available, "
        f"se requieren al menos {min_free_gb:.1f} GB"
    )
    return (False, msg)
