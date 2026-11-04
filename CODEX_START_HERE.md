# Open this project with Codex

There is **no need to paste the entire project into a chat**. Codex can work with local source files.

1. Extract this ZIP so the `Anatomy_Stress_Test` folder appears on your Mac.
2. Open Terminal, type `cd ` (with a space), drag the folder into Terminal, then press Return.
3. Run `codex`. If Codex is not installed, see https://developers.openai.com/codex/ for the latest installation instructions.
4. Paste the task below. You can then keep asking for edits; Codex will modify files in the folder.

## Paste this into Codex

Read `AGENTS.md`, `README.md`, and the existing source code. This is my ongoing Anatomy Stress Test project. Preserve all working functionality and the four-color palette (`#2F2FE4`, `#162E93`, `#1A1953`, `#080616`). Keep the title "Anatomy Stress Test" and footer "Credit to Tahmid Ullah". I want to iteratively improve this existing project; do not rebuild it from scratch. First inspect the code, explain how its parts fit together, run the automated tests, and tell me which features are already implemented versus missing. Then suggest one small next improvement and ask me which feature I want to work on. For any change, show the files you modify and run the tests.

## Suggested follow-up prompts

- Make the axial, coronal, and sagittal slice viewers support smooth wheel navigation without scrolling the webpage; preserve synchronized crosshairs. (Already implemented in this ZIP — ask Codex to review or customize it.)
- Add a browser upload UI for an anonymized NIfTI CT and its existing binary segmentation mask. Validate shape/affine alignment and file size. Do not accept clinical files publicly, and do not store uploads by default.
- Add a manual slice-painting mode to define and edit a binary organ mask, with undo/redo and save as NIfTI. Require users to confirm that they have permission to use the data.
- Add a simple automated test showing that changing the mask boundary does not change CT pixel intensity.
- Refactor CSS and frontend code for easier maintenance without changing behavior.

## macOS run command

```bash
./run_mac_linux.sh
```

Open http://127.0.0.1:8000 and keep Terminal running.
