# Changelog

## 1.1 — Sapphire/Indigo palette and scrolling

- Restyled app with four Color Hunt palette anchors: `#2F2FE4`, `#162E93`, `#1A1953`, `#080616`.
- Retained the neutral app name **Anatomy Stress Test** and **Credit to Tahmid Ullah** in the footer.
- Added mouse-wheel navigation over the axial, coronal, and sagittal CT panels (one slice per wheel event, Shift for five).
- Added arrow-key navigation when a CT panel is keyboard-focused.
- Updated overlaid mask colors to light purple (original) and blue (perturbed).
- Added `AGENTS.md` and `CODEX_START_HERE.md` for iterative development in Codex.

### Verification

- 14 automated Python tests passed.
- JavaScript syntax and CSS parse validation passed.
- Live browser E2E navigation was not confirmed in this sandbox (local navigation blocked by browser policy); please verify when running on your Mac.

### Not implemented

- Browser drag-and-drop CT upload, interactive manual organ painting, and automatic segmentation remain future improvements.
