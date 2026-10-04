# Blender Colab Render — Project plan

## Goal

Render Blender scenes in Google Colab sessions while preserving completed work across interruptions. The primary workflow uploads individual frames to Google Drive as rendering progresses, allowing a later session to continue from confirmed output.

## Critical risks

| Risk | Impact | Mitigation |
|---|---|---|
| Colab session ends during a long animation | Lost work or incorrect resume position | Incremental frame uploads, persistent checkpoints, and reconciliation against actual files |
| Blender does not enable the requested GPU in background mode | Render silently falls back to CPU or fails | Explicit device configuration, runtime diagnostics, and actionable warnings |
| Blender command-line arguments are ordered or composed incorrectly | Wrong range, output, or render mode | Tests for exact command construction and argument order |
| Drive is mounted or configured incorrectly | Frames or state are not persisted | Validate storage mode before rendering and reconcile output at completion |
| A source URL cannot be resolved | Scene or script download fails | Provider-specific resolvers, timeouts, and clear error messages |
| Blender's embedded Python lacks orchestration dependencies | Blender-side scripts fail at runtime | Keep Blender-side code limited to `bpy` and the standard library |
| Video textures are missing or unsupported by the selected build | Incorrect output or render failure | Audit media paths and FFmpeg build options, then validate with a real MP4 integration render |
| Compositor nodes use host-specific paths | Output files are written to unexpected locations | Deterministic, sanitized output mapping and path-focused tests |

## Architecture constraints

- The Colab kernel owns user interaction, source acquisition, storage APIs, monitoring, and subprocess management.
- Blender's embedded Python owns scene configuration and rendering; it must not depend on packages installed only in the notebook kernel.
- Mounted Drive and service-account Drive are distinct storage modes with different path semantics.
- The notebook should be a thin user interface over the reusable modules in `src/bcr/`.
- Checkpoint state must not be treated as stronger evidence than the actual rendered files.

## Delivery phases

### Phase 1 — Correctness and regression protection

- Centralize resume logic in the orchestrator to avoid applying resume offsets twice.
- Reconcile the saved checkpoint with a contiguous sequence of actual frame files.
- Cover gaps, stale checkpoints, non-default frame ranges, compositor subdirectories, and already-complete jobs.
- Ensure progress metrics remain relative to the originally requested frame range.

### Phase 2 — English-language consistency

- Translate notebook headings, form descriptions, prompts, logs, comments, docstrings, and user-facing exceptions to English.
- Translate README and developer documentation.
- Preserve identifiers and public configuration names unless a rename is necessary and tested.
- Ensure tests and sample output use the same language.

### Phase 3 — Media and output reliability

- Review compositor output-node mapping and ensure destinations are deterministic.
- Improve diagnostics for missing movie resources and FFmpeg capability.
- Validate MP4 video textures using a real scene and the target Blender build.
- Verify mounted Drive, service-account Drive, and ZIP-download behavior independently.

### Phase 4 — Reproducibility and release readiness

- Run all automated tests in a clean Python environment.
- Add or verify continuous integration for the unit suite.
- Perform short Colab integration runs for rendering, interruption/resume, compositor output, and MP4 media.
- Document the tested Blender versions and known limitations before merging.

## Acceptance criteria

A release candidate is acceptable only when the automated suite passes, resume behavior is correct for gaps and non-default frame starts, outputs land in the expected destinations, user-facing notebook text is in English, and the required Colab integration checks are recorded. Do not claim a live render or MP4 validation unless it has actually been performed.
