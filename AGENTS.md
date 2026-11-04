# Codex instructions — Anatomy Stress Test

This is a local educational CT-segmentation sensitivity prototype, NOT a diagnostic or mechanical tissue-stress simulator.

## Application
- Backend: Python 3.11+, FastAPI (`server.py`), dataset (`anatomy_lab/dataset.py`), geometry (`anatomy_lab/geometry.py`), PNG slices (`anatomy_lab/imaging.py`).
- Frontend: vanilla JS (`static/app.js`), HTML (`static/index.html`), CSS (`static/styles.css`), locally bundled Plotly.
- Tests: `python -m pytest -q` and manual checks at `http://127.0.0.1:8000`.
- Use `./run_mac_linux.sh` on macOS/Linux.

## Preservation requirements
- The application title stays **Anatomy Stress Test** (not the user's name).
- The footer must say **Credit to Tahmid Ullah**.
- Preserve the palette in `static/styles.css`: `#2F2FE4`, `#162E93`, `#1A1953`, `#080616`.
- Keep axial/coronal/sagittal views, synchronized crosshairs, mouse-wheel slice navigation and slice sliders.
- Retain clear distinction between synthetic demonstration data and clinical data.
- No patient data in the repository; no transmission to cloud services.
- Measurements: full-resolution voxel counts using physical voxel spacing, not downsampled 3D meshes.
- Boundary displacement is a Euclidean voxel-center morphological experiment, NOT a clinical estimate of segmentation uncertainty or tissue stress.
- Do not claim a novel research method without a genuine literature evaluation.

## Planned extensions, not currently delivered
- Browser drag-and-drop NIfTI/DICOM import.
- Manual drawing or editing of a segmentation mask.
- Optional automated segmentation of organs.
Implement these incrementally, add tests, and do not claim support until verified.

## Review workflow
1. Inspect existing code and summarize the change.
2. Implement the minimum working change.
3. Run tests, report pass/fail, and identify untested behavior.
4. Do not remove current functionality.
