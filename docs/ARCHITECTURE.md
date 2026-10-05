# Architecture

## Overview

Blender Colab Render orchestrates Blender in Google Colab and transfers rendered frames to Google Drive. The system separates notebook interaction, Python orchestration, and Blender's embedded Python runtime.

```text
[Colab notebook]       [Python orchestration]       [Blender Python runtime]
 ipywidgets / config      src/bcr/                   bpy + standard library
       |                     |                              |
 Mount Drive              Resolve scene source          Configure device
 Collect settings         Provision Blender             Configure outputs
 Show progress            Launch subprocess             Execute render
                          Parse stdout                  Write frame files
                          Upload completed frames
                          Persist/reconcile state
```

## Design principles

1. **Keep the notebook thin.** The notebook should collect configuration and coordinate user-visible steps; reusable behavior belongs in `src/bcr/`.
2. **Treat the Python environments separately.** The Colab kernel can use installed packages such as `requests`, `ipywidgets`, and Google API clients. Scripts executed by Blender must not assume those packages exist in Blender's embedded Python.
3. **Use one Blender process per render job where possible.** The orchestration layer monitors stdout and coordinates uploads while rendering continues.
4. **Make output files and checkpoints consistent.** A saved state file is a checkpoint, not sufficient evidence that every preceding frame exists. Resume logic should reconcile the checkpoint with actual output files and never silently skip a gap.
5. **Keep storage backends explicit.** Mounted Drive uses filesystem paths; service-account mode uses Drive API operations. Code must not treat these interfaces as interchangeable.
6. **Keep credentials out of logs and source control.** Tokens and service-account credentials should be supplied through Colab Secrets or secure prompts.

## Main modules

- `config.py`: constants, frame-range validation, path validation, and frame-number parsing.
- `source_resolver.py` and `link_resolver.py`: acquire scene files and supported source URLs.
- `blender_provisioning.py`: discover available Blender releases and provision a selected build.
- `device_config.py`: configure the render device from the requested backend.
- `state_manager.py`: load/save checkpoints and reconcile state against existing frame files.
- `render_orchestrator.py`: build the Blender command, monitor output, track progress, upload completed frames, and handle resume.
- `drive_backend.py` and `drive_sync.py`: storage operations for API-backed and mounted Drive modes.
- `local_export.py`: local output packaging and download support.
- `progress_ui.py`: optional notebook progress display.

The notebook separates temporary inputs and helper scripts under `/content/render_tmp` from rendered images under `/content/render_output`. ZIP export packages only the render-output directory, not the original scene or custom-script staging directory.
- `blender_scripts/render_frame_driver.py`: configure Blender-side rendering and output paths.

## Resume contract

The requested frame range is the source of truth for the job's boundaries. Resume logic should:

1. Enumerate valid rendered image files in the selected output location, including supported compositor subdirectories.
2. Interpret frame numbers consistently with the requested absolute frame range.
3. Find the highest contiguous completed frame starting at the requested start frame.
4. Resume at the first missing frame, rather than skipping gaps because a later file exists.
5. Complete without launching Blender only when all requested frames are confirmed.
6. Keep progress counters relative to the original requested range, even if the effective render start changes.

ZIP-only output is local to the current runtime and cannot provide the same persistence guarantee as Drive output.

## Media and compositor paths

Video texture diagnostics should report Blender's FFmpeg build capability, unresolved media paths, and relevant movie/image resources. Diagnostics are not a substitute for decoding and rendering a real sample video. Compositor File Output nodes may use arbitrary path prefixes; output remapping must avoid leaking host-specific Windows paths into the Colab filesystem and must preserve distinct node destinations.

## Validation boundaries

Unit tests can verify argument construction, checkpoint reconciliation, path mapping, and mocked storage behavior. They cannot establish that a real Blender build decodes a given MP4, that a Colab GPU is available, or that Google Drive permissions are correct. Those require integration tests in the target runtime.
