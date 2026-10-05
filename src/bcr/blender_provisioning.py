"""Provision the portable Blender binary.

Download and extract the .tar.xz archive from download.blender.org.
Supports a Drive cache to avoid downloading Blender in every Colab session.
"""

import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Optional

import requests

from bcr.config import (
    BLENDER_BINARY_RELATIVE,
    BLENDER_DEFAULT_VERSION,
    BLENDER_RELEASE_BASE,
    CHUNK_SIZE,
    DOWNLOAD_TIMEOUT_SECONDS,
    build_blender_download_url,
)


class BlenderProvisioningError(Exception):
    """Error raised while provisioning Blender."""


def get_blender_path(
    version: str = BLENDER_DEFAULT_VERSION,
    cache_dir: Optional[Path] = None,
) -> Path:
    """Download (or copy from cache), extract Blender, and return its binary path.

    Args:
        version: Blender semantic version (for example, "5.2.0").
        cache_dir: Drive directory used to cache the .tar.xz archive.
                   If omitted, the archive is downloaded directly.

    Returns:
        Path to the Blender executable.

    Raises:
        BlenderProvisioningError: if download/extraction fails or the binary is missing.
    """
    download_url = build_blender_download_url(version)
    archive_name = f"blender-{version}-linux-x64.tar.xz"
    tmp_dir = Path("/content/blender_install")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    tar_path = tmp_dir / archive_name

    # 1. Get the .tar.xz archive
    if cache_dir is not None:
        cache_path = Path(cache_dir) / archive_name
        if cache_path.exists():
            print(f"[blender] Copying Blender from cache: {cache_path}")
            shutil.copy2(str(cache_path), str(tar_path))
        else:
            print(f"[blender] Downloading Blender from {download_url}")
            _download_file(download_url, tar_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(tar_path), str(cache_path))
            print(f"[blender] Cached at: {cache_path}")
    else:
        print(f"[blender] Downloading Blender from {download_url}")
        _download_file(download_url, tar_path)

    # 2. Extract
    extract_dir = tmp_dir / "extracted"
    if extract_dir.exists():
        shutil.rmtree(str(extract_dir))
    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"[blender] Extracting {tar_path.name}...")
    with tarfile.open(str(tar_path), "r:xz") as tar:
        tar.extractall(path=str(extract_dir))

    # 3. Locate the Blender binary
    blender_bin = _find_blender_binary(extract_dir)
    if not blender_bin:
        msg = f"Blender binary was not found in {extract_dir}"
        raise BlenderProvisioningError(msg)

    os.chmod(str(blender_bin), 0o755)
    print(f"[blender] Binary ready: {blender_bin}")
    return blender_bin


def _download_file(url: str, dest: Path) -> None:
    """Download a file with support for large files."""
    try:
        resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        msg = f"Failed to download {url}: {exc}"
        raise BlenderProvisioningError(msg) from exc

    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                f.write(chunk)

    if not dest.exists() or dest.stat().st_size == 0:
        msg = f"Downloaded file is empty or does not exist: {dest}"
        raise BlenderProvisioningError(msg)


def _find_blender_binary(extract_dir: Path) -> Optional[Path]:
    """Find the Blender binary inside the extracted directory."""
    # Check the known relative path first
    candidate = extract_dir / BLENDER_BINARY_RELATIVE
    if candidate.exists():
        return candidate

    # Fallback: search recursively
    for root, _dirs, files in os.walk(str(extract_dir)):
        for fname in files:
            if fname == "blender" and not os.access(
                os.path.join(root, fname), os.X_OK
            ):
                full = Path(root) / fname
                return full
    return None


def verify_blender_version(blender_path: Path) -> str:
    """Run 'blender --version' and return its output.

    Raises:
        BlenderProvisioningError: if Blender cannot be executed.
    """
    try:
        result = subprocess.run(
            [str(blender_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError) as exc:
        msg = f"Failed to check Blender version: {exc}"
        raise BlenderProvisioningError(msg) from exc


def fetch_available_versions(min_major: int = 5) -> list[str]:
    """Fetch available Blender versions >= min_major.

    Send a GET request to BLENDER_RELEASE_BASE and parse the autoindex HTML for
    version folders matching ``BlenderX.Y/``, filter major >= min_major,
    and inspect each folder for the Linux x64 .tar.xz archive to determine
    el parche exacto.

    Returns:
        Semantic versions sorted in descending order (for example, ["5.3.0", "5.2.0", ...]).

    Raises:
        BlenderProvisioningError: if the connection fails and no versions are found.
    """
    try:
        resp = requests.get(BLENDER_RELEASE_BASE, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise BlenderProvisioningError(
            f"Could not retrieve the version list: {exc}"
        ) from exc

    versions: list[str] = []
    for match in re.finditer(
        r'<a href="Blender(\d+)\.(\d+)/"', resp.text
    ):
        major, minor = int(match.group(1)), int(match.group(2))
        if major < min_major:
            continue

        folder_url = f"{BLENDER_RELEASE_BASE}Blender{major}.{minor}/"
        try:
            folder_resp = requests.get(folder_url, timeout=30)
            folder_resp.raise_for_status()
        except requests.RequestException:
            continue

        for vmatch in re.finditer(
            r"blender-(\d+\.\d+\.\d+)-linux-x64\.tar\.xz",
            folder_resp.text,
        ):
            versions.append(vmatch.group(1))

    if not versions:
        raise BlenderProvisioningError(
            "No available Blender versions were found"
        )

    versions.sort(
        key=lambda v: [int(x) for x in v.split(".")], reverse=True
    )
    return versions


def resolve_blender_version(preferred: Optional[str] = None) -> str:
    """Resolve the Blender version to use.

    If ``preferred`` is provided, try it first (it may come from the
    notebook UI). If the live query fails, return the
    preferred version selector); otherwise use the default with a warning.

    Returns:
        Semantic version (e.g. "5.2.0").
    """
    try:
        available = fetch_available_versions()
    except BlenderProvisioningError:
        print(
            "[blender] WARNING: Could not fetch Blender versions live from "
            "Blender release index; using the default version"
        )
        return preferred or BLENDER_DEFAULT_VERSION

    if preferred is not None:
        return preferred

    return available[0]
