# Blender Colab Render

Render Blender scenes in Google Colab, with optional GPU acceleration and incremental delivery of rendered frames to Google Drive.

Each completed frame can be uploaded individually while Blender renders subsequent frames. For Drive output, the project can reconcile saved state with existing output files to resume an interrupted render. Resume behavior depends on the selected output destination and must be validated against the actual scene and storage backend.

## Requirements

- A Google account with access to Google Drive.
- A Blender `.blend` scene with its required assets available.
- A public or otherwise accessible scene URL, a Drive path, or a local upload.
- A Google Colab runtime. GPU availability depends on the runtime assigned by Google.

## Quick start

1. Open [`notebooks/blender_render.ipynb`](notebooks/blender_render.ipynb) in Google Colab.
2. Run the cells in order.
3. Choose the Google Drive access mode and configure the scene source, frame range, output path, output mode, and render device.
4. Install the notebook dependencies and wait for scene acquisition and Blender provisioning to finish.
5. Run the render cell and monitor progress and output synchronization.

## Google Drive access modes

- **Mounted Drive** uses Colab's interactive Drive mount and filesystem paths.
- **Service account** uses the Google Drive API and Colab secrets. Configure `GDRIVE_SERVICE_ACCOUNT_JSON` and `GDRIVE_FOLDER_ID` before selecting this mode. Drive filesystem paths and the mounted-drive Blender cache are not available in this mode.

Never commit access tokens, service-account JSON, or other credentials to the repository. Prefer Colab Secrets for credentials. The notebook should not print secrets in command output.

## Output and resuming

- **Drive output** is intended for incremental upload and resumable rendering.
- **ZIP download** packages local output at the end and does not provide the same cross-session resume guarantee.
- Resume reconciliation should treat actual rendered image files as evidence of completed frames, while respecting the requested frame range and any gaps in the sequence.
- Compositor File Output nodes may write into separate subdirectories. Verify the resulting paths and frame numbering for your scene.

The project cannot guarantee that every arbitrary compositor graph, third-party add-on, or external media dependency will work without scene-specific testing.

## Video textures and FFmpeg

Blender must be built with the required media support, and the source video must be accessible from the scene's runtime environment. A diagnostic message that detects movie resources is not proof that a particular MP4 decodes correctly. Validate video textures with a small render using the actual scene and Blender build.

## Development and tests

The project targets Python 3.10 or later for its orchestration code. Install development dependencies and run:

```bash
python -m pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests/ -v
```

Most automated tests mock Blender and Google Drive; passing them does not replace a live Colab render test.

See [Architecture](docs/ARCHITECTURE.md), [Testing](docs/TESTING.md), and [Plan](docs/PLAN.md) for implementation details and known validation requirements.
