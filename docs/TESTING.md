# Testing strategy

## Automated tests

The unit test suite is intended to run without Blender or a GPU, using Python 3.10 or later.

Run the suite from the repository root:

```bash
python -m pip install -e ".[dev]"
PYTHONPATH=src python -m pytest tests/ -v
```

If using a virtual environment directly, install at least `pytest`, `pytest-mock`, and `requests`. Tests for the service-account backend also require the Google API and authentication packages declared in the development dependencies.

## Coverage areas

| Area | Test module | Expected coverage |
|---|---|---|
| Configuration | `test_config.py`, `test_notebook_smoke.py` | Frame-range validation, URL and Drive-path validation, notebook structure |
| Source acquisition | `test_source_resolver.py`, `test_link_resolver.py` | Provider URL handling, archive extraction, HTTP failures |
| Blender provisioning | `test_blender_provisioning.py` | Version discovery, download paths, extraction and error handling |
| Device setup | `test_driver_api_compat.py` | Compatibility checks for Blender-side device configuration |
| State management | `test_state_manager.py` | Checkpoint persistence, corrupted state, actual-file reconciliation, gaps and non-default frame starts |
| Orchestration | `test_render_orchestrator.py` | Blender command construction, stdout parsing, progress metrics, upload coordination, resume behavior |
| Drive storage | `test_drive_backend.py`, `test_drive_sync.py` | Mocked folder creation, frame upload/listing, state persistence and synchronization |
| Export | `test_local_export.py` | Disk-space checks, packaging, download behavior |
| Progress UI | `test_progress_ui.py` | UI behavior and operation when optional widgets are unavailable |

## Test design

- Mock network requests and external API calls.
- Avoid requiring a real Blender process for unit tests; test command construction separately.
- Include resume cases for stale checkpoints, files ahead of the checkpoint, missing intermediate frames, non-default frame starts, and already-complete ranges.
- Verify that progress totals are calculated against the original requested range.
- Test compositor outputs in nested directories and ensure unrelated files are ignored.

## Required integration checks

A passing unit suite is not sufficient for release. Before merging changes that affect rendering, run a small job in Google Colab and record the Blender version, runtime type, output destination, and results.

1. Render a short image sequence to mounted Drive.
2. Interrupt after at least one frame, restart the render cell, and verify that the first missing frame is rendered without skipping gaps.
3. Repeat the resume check with a requested frame range that does not start at frame 1.
4. Exercise compositor File Output nodes whose original paths contain Windows-style prefixes.
5. Render a scene with an MP4 video texture and confirm that the resulting image visibly contains the expected video frame.
6. Verify that service-account mode and ZIP-download mode either work as documented or fail with an explicit, actionable message.

Do not describe FFmpeg or MP4 support as validated until a real video-texture render succeeds in the target Blender build.
