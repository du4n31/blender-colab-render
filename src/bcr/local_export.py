"""Empaquetado en .zip y descarga local para el modo "zip_download".

Paralelo a drive_sync.py: en lugar de subir cada frame a Drive
incrementalmente, los mantiene locales y los empaqueta en un solo .zip.
"""

import shutil
from pathlib import Path


class LocalExportError(Exception):
    """Error al empaquetar o descargar la salida local."""


def package_output(output_dir: Path, output_name: str = "render_output") -> Path:
    """Empaqueta el directorio de salida completo en un archivo .zip.

    Args:
        output_dir: Directorio con los frames renderizados (puede tener
            subdirectorios por nodo).
        output_name: Nombre base del .zip (default: "render_output").

    Returns:
        Path al archivo .zip creado.

    Raises:
        LocalExportError: si el directorio no existe o esta vacio.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        msg = f"El directorio de salida no existe: {output_dir}"
        raise LocalExportError(msg)

    if not any(output_dir.iterdir()):
        msg = f"El directorio de salida esta vacio: {output_dir}"
        raise LocalExportError(msg)

    # Colocar el .zip en /tmp para no ocupar espacio en /content
    zip_path = shutil.make_archive(
        base_name=str(Path("/tmp") / output_name),
        format="zip",
        root_dir=output_dir,
    )

    return Path(zip_path)


def trigger_download(zip_path: Path) -> None:
    """Dispara la descarga del .zip en el navegador de Colab.

    Args:
        zip_path: Ruta al archivo .zip a descargar.

    Raises:
        LocalExportError: si el archivo .zip no existe.
    """
    zip_path = Path(zip_path)

    if not zip_path.exists():
        msg = f"El archivo .zip no existe: {zip_path}"
        raise LocalExportError(msg)

    try:
        # google.colab solo esta disponible en entorno Colab
        from google.colab import files  # type: ignore[import-untyped]

        files.download(str(zip_path))
    except ImportError:
        print(f"Entorno no-Colab: el archivo esta en {zip_path}")


def check_disk_space(
    output_dir: Path, min_free_gb: float = 2.0
) -> tuple[bool, str]:
    """Verifica si hay suficiente espacio libre en disco para renderizar.

    Args:
        output_dir: Directorio donde se escribiran los frames.
        min_free_gb: Espacio libre minimo en GB (default: 2.0).

    Returns:
        (ok, mensaje) — ok=True si hay espacio suficiente,
        ok=False con mensaje de advertencia si no.
    """
    output_dir = Path(output_dir)

    if not output_dir.exists():
        return (False, f"El directorio no existe: {output_dir}")

    usage = shutil.disk_usage(output_dir)
    free_gb = usage.free / (1024**3)

    if free_gb >= min_free_gb:
        return (True, "")

    msg = (
        f"Espacio libre insuficiente: {free_gb:.1f} GB disponibles, "
        f"se requieren al menos {min_free_gb:.1f} GB"
    )
    return (False, msg)
