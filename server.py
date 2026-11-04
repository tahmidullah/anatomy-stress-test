"""Run with: python server.py  (or uvicorn server:app --reload)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from io import BytesIO
import json
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from contextvars import ContextVar
from functools import wraps
import uuid
import tempfile
import zipfile
import csv
import gzip
import nibabel as nib
from anatomy_lab.importers import read_ct, build_dataset, MAX_BYTES
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from anatomy_lab.dataset import load_configured_dataset, PALETTE
from anatomy_lab.geometry import StressExperiment, mask_centroid, mesh_geometry
from anatomy_lab.imaging import slice_png

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA = load_configured_dataset()
SESSIONS = {}
CURRENT = ContextVar('dataset', default=DEFAULT_DATA)
SESSION_KEY = ContextVar('session_key', default='demo')
class DatasetProxy:
    def __getattr__(self, key):
        return getattr(CURRENT.get(), key)
DATA = DatasetProxy()

def dataset_cache(maxsize):
    def decorate(fn):
        cached = lru_cache(maxsize=maxsize)(lambda session, *args: fn(*args))
        @wraps(fn)
        def wrapped(*args):
            return cached(SESSION_KEY.get(), *args)
        wrapped.cache_clear = cached.cache_clear
        return wrapped
    return decorate
app = FastAPI(title="Anatomy Stress Test", version="1.1.0", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def local_session(request: Request, call_next):
    key = request.cookies.get('anatomy_session', '')
    data_token = CURRENT.set(SESSIONS.get(key, DEFAULT_DATA))
    key_token = SESSION_KEY.set(key if key in SESSIONS else 'demo')
    try:
        return await call_next(request)
    finally:
        CURRENT.reset(data_token)
        SESSION_KEY.reset(key_token)


@app.post('/api/import')
async def import_scan(request: Request):
    # Browser uploads are sent only to this local server.
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Cross-origin imports are not allowed.')
    try:
        async with request.form(max_files=10002, max_fields=10) as form:
            scans = form.getlist('ct')
            masks = form.getlist('mask')
            if not scans or not masks:
                raise ValueError('Choose a CT and at least one mask.')
            with tempfile.TemporaryDirectory(prefix='anatomy-import-') as temp:
                root = Path(temp)
                (root / 'ct').mkdir(); (root / 'masks').mkdir()
                total = 0
                async def save(files, directory):
                    nonlocal total
                    paths = []
                    for index, upload in enumerate(files):
                        name = Path(upload.filename or 'file').name
                        path = directory / (str(index) + '_' + name)
                        with path.open('wb') as out:
                            while True:
                                block = await upload.read(1024 * 1024)
                                if not block: break
                                total += len(block)
                                if total > MAX_BYTES:
                                    raise ValueError('Uploads exceed the 1 GiB limit.')
                                out.write(block)
                        paths.append(path)
                    return paths
                ct_paths = await save(scans, root / 'ct')
                mask_paths = await save(masks, root / 'masks')
                if any(not str(path).lower().endswith(('.nii', '.nii.gz', '.nrrd')) for path in mask_paths):
                    raise ValueError('Masks must be NIfTI or self-contained NRRD files.')
                from starlette.concurrency import run_in_threadpool
                ct, choices = await run_in_threadpool(read_ct, ct_paths, root, str(form.get('series_uid', '')))
                if choices:
                    return {'series': choices}
                dataset = await run_in_threadpool(build_dataset, ct, mask_paths)
            old = request.cookies.get('anatomy_session', '')
            if len(SESSIONS) >= 4 and old not in SESSIONS:
                raise ValueError('Four scan sessions are already open. Restart the server to clear them.')
            key = uuid.uuid4().hex
            SESSIONS.pop(old, None)
            SESSIONS[key] = dataset
            experiment.cache_clear(); _mesh.cache_clear()
            from fastapi.responses import JSONResponse
            response = JSONResponse({'ok': True})
            response.set_cookie('anatomy_session', key, httponly=True, samesite='strict')
            return response
    except (ValueError, RuntimeError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get('/api/export')
def export_bundle(organ: str, offset: float = 0, label: str = ''):
    offset = checked_offset(offset)
    exp = experiment(organ)
    full = np.zeros(DATA.image.shape, dtype=np.uint8)
    full[tuple(slice(a, b) for a, b in zip(exp.start, exp.stop))] = exp.offset_mask(offset)
    nii = nib.Nifti1Image(full, DATA.affine)
    nii.header.set_xyzt_units('mm')
    from io import StringIO
    table = StringIO()
    points = exp.curve()
    writer = csv.DictWriter(table, fieldnames=list(points[0]))
    writer.writeheader(); writer.writerows(points)
    settings = {'organ': organ, 'label': label[:120] or organ, 'offset_mm': offset,
                'spacing_mm': DATA.spacing, 'affine_ras_mm': DATA.affine.tolist(),
                'shape': list(DATA.image.shape), 'source': DATA.kind,
                'method': 'Euclidean voxel-center dilation/erosion',
                'version': app.version, 'metrics': exp.metrics(offset)}
    result = BytesIO()
    with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('segmentation.nii.gz', gzip.compress(nii.to_bytes()))
        bundle.writestr('measurements.csv', table.getvalue())
        bundle.writestr('settings.json', json.dumps(settings, indent=2))
    return Response(result.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="anatomy_stress_test.zip"'})


@dataset_cache(maxsize=10)
def experiment(name: str) -> StressExperiment:
    if name not in DATA.structures:
        raise HTTPException(404, f"Unknown structure: {name}")
    try:
        return StressExperiment.from_mask(DATA.mask(name), DATA.spacing)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc


def checked_offset(value: float) -> float:
    if not np.isfinite(value) or abs(value) > 3.0001 or abs(value * 2 - round(value * 2)) > 1e-4:
        raise HTTPException(422, "Offset must be between -3 and +3 mm in 0.5 mm increments")
    return round(value * 2) / 2


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "source": DATA.kind}


@app.get("/api/meta")
def metadata():
    return {
        "name": "Anatomy Stress Test", "version": app.version,
        "source": DATA.kind, "source_label": DATA.label,
        "structures": [{"name": x, "label": x.replace("_", " ").title(),
                        "color": PALETTE.get(x, "#a3bdcf")} for x in DATA.structures],
        "shape": DATA.image.shape, "spacing_mm": DATA.spacing,
        "window": {"level_hu": 50, "width_hu": 400},
        "notes": [
            "Educational segmentation sensitivity experiment; not actual uncertainty estimation.",
            "Volume is calculated from original-resolution binary voxels, not the display mesh.",
            "Static CT geometry alone does not determine patient-specific physiology or diagnosis.",
        ],
    }


@app.get("/api/metrics")
def metrics(organ: str, offset: float = 0):
    offset = checked_offset(offset)
    exp = experiment(organ)
    mask = DATA.mask(organ)
    val = exp.metrics(offset)
    val.update({"organ": organ, "centroid_ijk": mask_centroid(mask),
                "spacing_mm": exp.spacing,
                "boundary_method": "Euclidean voxel-center distance transform"})
    return val


@app.get("/api/curve")
def curve(organ: str):
    return {"organ": organ, "points": experiment(organ).curve()}


@dataset_cache(maxsize=24)
def _mesh(organ: str, offset: float, step: int = 2) -> dict:
    exp = experiment(organ)
    mask = exp.offset_mask(offset)
    return mesh_geometry(mask, exp.start, DATA.affine, step_size=step)


@app.get("/api/scene")
def scene(organ: str, offset: float = 0):
    offset = checked_offset(offset)
    exp = experiment(organ)
    traces = []
    if DATA.kind == "synthetic":
        center = np.array(mask_centroid(DATA.mask(organ)), dtype=float) * np.array(DATA.spacing)
        others = [n for n in DATA.structures if n != organ]
        others.sort(key=lambda n: np.linalg.norm(
            np.array(mask_centroid(DATA.mask(n))) * np.array(DATA.spacing) - center))
        for name in others[:4]:
            traces.append({"name": name.replace("_", " ").title(),
                           "color": PALETTE.get(name, "#9aadc0"), "opacity": 0.12,
                           "mesh": _mesh(name, 0.0, 3)})
    if offset != 0:
        traces.append({"name": "Original boundary", "color": "#e0c6ff", "opacity": .25,
                       "mesh": _mesh(organ, 0.0, 2)})
    traces.append({"name": "Perturbed boundary" if offset else "Original segmentation",
                   "color": "#8da3ff", "opacity": .77,
                   "mesh": _mesh(organ, offset, 2)})
    return {"traces": traces, "offset_mm": offset, "touches_fov": exp.touches_fov}


@app.get("/api/slice")
def slice_view(
    organ: str, axis: str = Query("axial", pattern="^(axial|coronal|sagittal)$"),
    index: int = 0, offset: float = 0, i: int = 0, j: int = 0, k: int = 0,
):
    offset = checked_offset(offset)
    exp = experiment(organ)
    shape = DATA.image.shape
    axis_dimension = {"axial": 2, "coronal": 1, "sagittal": 0}[axis]
    if not 0 <= index < shape[axis_dimension]:
        raise HTTPException(422, "Slice index is out of range")
    if any(c < 0 or c >= d for c, d in zip((i, j, k), shape)):
        raise HTTPException(422, "Crosshair must lie inside the scan")
    try:
        png = slice_png(DATA.image, DATA.mask(organ), exp, axis, index, offset, (i, j, k))
    except Exception as exc:
        raise HTTPException(500, f"Could not render image: {exc}") from exc
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
