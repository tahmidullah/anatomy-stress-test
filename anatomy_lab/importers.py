"""Local volume import. Geometry is preserved; masks are never interpolated."""
from pathlib import Path
import re
import zipfile
import numpy as np
import nibabel as nib
import SimpleITK as sitk
import nrrd
from .dataset import ScanDataset

MAX_VOXELS = 100_000_000
MAX_BYTES = 1024 ** 3


def canonical(array, affine):
    if array.ndim != 3 or array.size > MAX_VOXELS:
        raise ValueError('Expected a 3D volume with at most 100 million voxels.')
    if not np.isfinite(array).all() or not np.isfinite(affine).all():
        raise ValueError('Volume contains non-finite values.')
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    if np.any(spacing <= 0):
        raise ValueError('Invalid voxel spacing.')
    directions = affine[:3, :3] / spacing
    if not np.allclose(directions.T @ directions, np.eye(3), atol=1e-4):
        raise ValueError('Sheared grids are unsupported. Resample in Slicer first.')
    img = nib.as_closest_canonical(nib.Nifti1Image(array, affine))
    return np.asarray(img.dataobj), img.affine


def check_nrrd(path):
    if str(path).lower().endswith('.nrrd'):
        header = nrrd.read_header(str(path))
        if 'data file' in header or 'datafile' in header:
            raise ValueError('Detached NRRD data is unsupported; upload a self-contained .nrrd file.')
        if np.prod(header['sizes'], dtype=np.float64) > MAX_VOXELS:
            raise ValueError('NRRD exceeds the 100 million voxel limit.')


def volume(path):
    check_nrrd(path)
    if str(path).lower().endswith(('.nii', '.nii.gz')):
        img = nib.load(str(path))
        if len(img.shape) != 3 or np.prod(img.shape) > MAX_VOXELS:
            raise ValueError('Expected a 3D volume with at most 100 million voxels.')
        unit = img.header.get_xyzt_units()[0]
        affine = img.affine.copy()
        affine[:3] *= {'meter': 1000, 'micron': .001}.get(unit, 1)
        return canonical(img.get_fdata(dtype=np.float32), affine)
    img = sitk.ReadImage(str(path))
    return sitk_volume(img)


def sitk_volume(img):
    if img.GetDimension() != 3 or img.GetNumberOfComponentsPerPixel() != 1:
        raise ValueError('Only scalar 3D volumes are supported.')
    affine = np.eye(4)
    affine[:3, :3] = np.asarray(img.GetDirection()).reshape(3, 3) @ np.diag(img.GetSpacing())
    affine[:3, 3] = img.GetOrigin()
    affine[:2] *= -1  # LPS to RAS
    return canonical(sitk.GetArrayFromImage(img).transpose(2, 1, 0).astype(np.float32), affine)


def unpack_zip(path, destination):
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError('DICOM ZIP exceeds the 1 GiB / 10,000-file limit.')
        for index, info in enumerate(infos):
            if '__MACOSX' in info.filename or Path(info.filename).name.startswith('.'):
                continue
            # Flatten and assign server names: archive paths are never extracted.
            with archive.open(info) as source, (destination / str(index)).open('wb') as target:
                import shutil
                shutil.copyfileobj(source, target)


def dicom_series(folder):
    ids = sitk.ImageSeriesReader.GetGDCMSeriesIDs(str(folder)) or []
    return [(uid, sitk.ImageSeriesReader.GetGDCMSeriesFileNames(str(folder), uid)) for uid in ids]


def read_ct(paths, folder, series_uid=''):
    if len(paths) == 1 and str(paths[0]).lower().endswith(('.nii', '.nii.gz', '.nrrd')):
        return volume(paths[0]), None
    if len(paths) == 1 and str(paths[0]).lower().endswith('.zip'):
        expanded = folder / 'dicom'
        expanded.mkdir()
        unpack_zip(paths[0], expanded)
    else:
        expanded = paths[0].parent
    series = dicom_series(expanded)
    if not series:
        raise ValueError('No readable DICOM series found. Upload a CT series or a NIfTI/NRRD volume.')
    if not series_uid and len(series) > 1:
        return None, [{'uid': uid, 'slices': len(files)} for uid, files in series]
    selected = next((files for uid, files in series if not series_uid or uid == series_uid), None)
    if selected is None:
        raise ValueError('Selected DICOM series was not found.')
    # Reject non-CT, multiframe, and irregular series rather than inventing spacing.
    positions = []
    orientations = []
    for filename in selected:
        reader = sitk.ImageFileReader()
        reader.SetFileName(filename)
        reader.ReadImageInformation()
        if not reader.HasMetaDataKey('0008|0060') or reader.GetMetaData('0008|0060').strip() != 'CT':
            raise ValueError('Only CT DICOM series are supported.')
        if reader.HasMetaDataKey('0028|0008') and int(reader.GetMetaData('0028|0008')) > 1:
            raise ValueError('Enhanced multiframe DICOM is not supported; export NIfTI from Slicer.')
        positions.append([float(x) for x in reader.GetMetaData('0020|0032').split('\\')])
        orientations.append([float(x) for x in reader.GetMetaData('0020|0037').split('\\')])
    if len(positions) < 2:
        raise ValueError('A CT series must contain at least two slices.')
    diffs = np.diff(positions, axis=0)
    normal = np.cross(orientations[0][:3], orientations[0][3:])
    if (not np.allclose(orientations, orientations[0], atol=1e-4)
        or not np.allclose(diffs, diffs[0], atol=.025)
        or np.linalg.norm(diffs[0]) < .001
        or not np.allclose(diffs[0], normal * np.dot(diffs[0], normal), atol=.025)):
        raise ValueError('Irregular, duplicate, or tilted DICOM slices: resample in Slicer first.')
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(selected)
    return sitk_volume(reader.Execute()), None


def mask_segments(path):
    check_nrrd(path)
    if str(path).lower().endswith('.seg.nrrd'):
        data, header = nrrd.read(str(path))
        directions = np.asarray(header['space directions'])
        spatial = np.isfinite(directions).all(axis=1)
        affine = np.eye(4)
        affine[:3, :3] = directions[spatial].T
        affine[:3, 3] = header['space origin']
        space = header.get('space', '').lower()
        if space in ('left-posterior-superior', 'lps'):
            affine[:2] *= -1
        elif space not in ('right-anterior-superior', 'ras'):
            raise ValueError('Unsupported segmentation coordinate system.')
        ids = sorted(set(re.findall(r'Segment(\d+)_ID', ' '.join(header.keys()))), key=int)
        if not ids:
            raise ValueError('Slicer segmentation has no segment metadata.')
        for index in ids:
            prefix = 'Segment' + index + '_'
            layer = int(header.get(prefix + 'Layer', 0))
            values = data if data.ndim == 3 else np.take(data, layer, axis=int(np.where(~spatial)[0][0]))
            mask = (values == int(header[prefix + 'LabelValue'])).astype(np.uint8)
            yield header.get(prefix + 'Name', 'Segment ' + index), canonical(mask, affine)
    else:
        data, affine = volume(path)
        if np.any(data < 0) or not np.equal(data, np.rint(data)).all():
            raise ValueError('Masks must contain nonnegative integer labels, with 0 as background.')
        labels = np.unique(data[data > 0])
        if len(labels) > 128:
            raise ValueError('Mask has more than 128 labels; probability maps are unsupported.')
        stem = path.name.split('.')[0]
        for label in labels:
            yield (stem if len(labels) == 1 else f'{stem} label {int(label)}'), ((data == label).astype(np.uint8), affine)


def build_dataset(ct, mask_paths):
    image, affine = ct
    masks = {}
    for path in mask_paths:
        for name, (mask, mask_affine) in mask_segments(path):
            # Accept exact integer-grid cropped masks without interpolation.
            mapping = np.linalg.inv(affine) @ mask_affine
            translation = mapping[:3, 3]
            if not np.allclose(mapping[:3, :3], np.eye(3), atol=1e-4) or not np.allclose(translation, np.rint(translation), atol=.01):
                raise ValueError('Mask and CT are not aligned. Align/resample them in Slicer before uploading.')
            start = np.rint(translation).astype(int)
            stop = start + mask.shape
            if np.any(start < 0) or np.any(stop > image.shape):
                raise ValueError('Mask extends outside the CT grid.')
            if not mask.any():
                continue
            full = np.zeros(image.shape, dtype=bool)
            full[tuple(slice(a, b) for a, b in zip(start, stop))] = mask
            key = re.sub(r'[^a-zA-Z0-9_-]+', '_', name).strip('_')[:60] or 'segment'
            base, count = key, 2
            while key in masks:
                key = f'{base}_{count}'; count += 1
            masks[key] = full
            if len(masks) > 128 or len(masks) * image.size > 500_000_000:
                raise ValueError('Too many full-resolution mask voxels for this local server.')
    if not masks:
        raise ValueError('Upload at least one nonempty segmentation mask.')
    return ScanDataset(image.astype(np.float32), affine, 'uploaded', 'User-provided local CT', masks=masks)
