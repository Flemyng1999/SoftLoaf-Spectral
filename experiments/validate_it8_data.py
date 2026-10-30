"""Audit Colour's chart inventory and a locally supplied reflective IT8 dataset.

This reads the public Wolf Faust spectral/reference ZIPs without extracting
members or bundling measured data. It checks data structure and numerical
consistency, not measurement traceability, film accuracy or licensing.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import zipfile

os.environ.setdefault('MPLCONFIGDIR', str(Path('artifacts/.matplotlib').resolve()))
os.environ.setdefault('XDG_CACHE_HOME', str(Path('artifacts/.cache').resolve()))

import colour
import numpy as np


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_chart(archive, member):
    with zipfile.ZipFile(archive) as source:
        raw = source.read(member)
    text = raw.decode('latin1')
    fields = text.split('BEGIN_DATA_FORMAT', 1)[1].split('END_DATA_FORMAT', 1)[0].split()
    tokens = shlex.split(re.split(r'\bBEGIN_DATA\b', text, maxsplit=1)[1].split('END_DATA', 1)[0])
    declared_fields = int(re.search(r'^NUMBER_OF_FIELDS\s+(\d+)', text, re.M)[1])
    declared_sets = int(re.search(r'^NUMBER_OF_SETS\s+(\d+)', text, re.M)[1])
    if len(fields) != declared_fields or len(tokens) != declared_sets * declared_fields:
        raise ValueError('CGATS declared dimensions do not match its contents')
    rows = np.asarray(tokens).reshape(declared_sets, declared_fields)
    if fields[0] != 'SAMPLE_ID' or len(set(rows[:, 0])) != declared_sets:
        raise ValueError('Missing or duplicate sample IDs')
    if not np.isfinite(rows[:, 1:].astype(np.float64)).all():
        raise ValueError('Nonfinite measurement')
    metadata = {}
    for key in ('ORIGINATOR', 'DESCRIPTOR', 'CREATED', 'PROD_DATE', 'SAMPLE_BACKING', 'SERIAL', 'MATERIAL'):
        match = re.search(rf'^{key}\s+"([^"]*)"', text, re.M)
        metadata[key] = match[1] if match else None
    return fields, rows, metadata, sha256(raw)


def summary(values):
    return {key: float(value) for key, value in zip(
        ('mean', 'median', 'p95', 'max'),
        (np.mean(values), *np.percentile(values, (50, 95, 100))))}


def library_inventory():
    datasets = []
    for name, patches in colour.SDS_COLOURCHECKERS.items():
        first = next(iter(patches.values()))
        values = np.stack([patch.values for patch in patches.values()])
        grid = first.wavelengths
        datasets.append({
            'name': name, 'patches': len(patches),
            'coverage_nm': [float(grid[0]), float(grid[-1])],
            'step_nm': float(grid[1] - grid[0]),
            'finite': bool(np.isfinite(values).all()),
            'reflectance_range': [float(values.min()), float(values.max())],
        })
    package = Path(colour.__file__).parent
    matches = []
    for path in package.rglob('*.py'):
        if re.search(r'it8', path.read_text(errors='replace'), re.I):
            matches.append(str(path.relative_to(package)))
    return {
        'version': colour.__version__, 'spectral_chart_entries': datasets,
        'IT8_python_source_matches': matches,
        'IT8_named_spectral_entries': [d['name'] for d in datasets if 'it8' in d['name'].lower()],
        'coordinate_chart_entries': list(colour.CCS_COLOURCHECKERS),
        'ISO_17321_1_equals_Ohta': all(
            np.array_equal(a.wavelengths, b.wavelengths) and np.array_equal(a.values, b.values)
            for a, b in zip(colour.SDS_COLOURCHECKERS['ISO 17321-1'].values(),
                            colour.SDS_COLOURCHECKERS['ColorChecker N Ohta'].values())),
    }


def audit(spectral_zip, reference_zip, stem):
    fields, rows, metadata, member_hash = read_chart(spectral_zip, stem + '.cgt')
    ref_fields, reference, ref_metadata, ref_hash = read_chart(reference_zip, stem + '.txt')
    expected = ['SAMPLE_ID', 'XYZ_X', 'XYZ_Y', 'XYZ_Z', 'LAB_L', 'LAB_A', 'LAB_B', 'LAB_C', 'LAB_H']
    if fields[:9] != expected or ref_fields != expected:
        raise ValueError('Unsupported colorimetric fields')
    if fields[9:] != ['SPECTRAL_NM', 'SPECTRAL_PCT'] * 41:
        raise ValueError('Expected 41 wavelength/reflectance-percent pairs')
    if metadata != ref_metadata or not np.array_equal(rows[:, :9], reference):
        raise ValueError('Spectral/reference sample identities or colorimetric values differ')
    if metadata['MATERIAL'] != 'Kodak Professional Ultra Endura' or metadata['SAMPLE_BACKING'] != 'black':
        raise ValueError('This audit expects the reflective black-backed Ultra Endura set')
    if 'D50' not in metadata['DESCRIPTOR'] or 'angle 2' not in metadata['DESCRIPTOR']:
        raise ValueError('This audit requires declared D50 / 2 degree reference values')

    numbers = rows[:, 1:].astype(np.float64)
    wavelength_rows = numbers[:, 8::2]
    wavelength = wavelength_rows[0]
    if not np.array_equal(wavelength, np.arange(380, 781, 10)) or not np.all(wavelength_rows == wavelength):
        raise ValueError('Unexpected, nonuniform or mismatched wavelength grids')
    reflectance = numbers[:, 9::2] / 100.0
    if np.any((reflectance < 0) | (reflectance > 1)):
        raise ValueError('Reflectance outside [0, 1]; inspect without silently clipping')
    reference_xyz, reference_lab = numbers[:, :3], numbers[:, 3:6]
    cmfs = colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer']
    light = colour.SDS_ILLUMINANTS['D50']
    white_xy = colour.CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D50']
    calculations = {}
    for step in (10, 5, 1):
        shape = colour.SpectralShape(380, 780, step)
        matching = cmfs.copy().align(shape)
        illuminant = light.copy().align(shape)
        spectra = np.stack([colour.SpectralDistribution(r, wavelength).align(shape).values
                            for r in reflectance])
        # Independent float64 rectangular integration matching Colour's method;
        # use only the measured wavelength range, with no missing-band extension.
        kernel = matching.values * illuminant.values[:, None]
        xyz = 100.0 * (spectra @ kernel) / kernel[:, 1].sum()
        library_xyz = colour.sd_to_XYZ(spectra, matching, illuminant, method='Integration', shape=shape)
        numerical_error = float(np.max(np.abs(xyz - library_xyz)))
        if numerical_error > 1e-10:
            raise ValueError('Independent integration and Colour disagree')
        lab = colour.XYZ_to_Lab(xyz / 100.0, white_xy)
        delta_e = colour.delta_E(lab, reference_lab, method='CIE 2000')
        worst = int(np.argmax(delta_e))
        calculations[str(step) + 'nm'] = {
            'quadrature': 'rectangular sum, normalized perfect diffuser Y=100 within 380-780nm',
            'reflectance_interpolation': 'none (native samples)' if step == 10 else
                colour.SpectralDistribution(reflectance[0], wavelength).interpolator.__name__,
            'no_extrapolation': True,
            'resampled_reflectance_range': [float(spectra.min()), float(spectra.max())],
            'resampled_out_of_range_values': int(np.count_nonzero((spectra < 0) | (spectra > 1))),
            'independent_vs_colour_max_abs_XYZ_100': numerical_error,
            'source_XYZ_max_abs_difference_100': float(np.max(np.abs(xyz - reference_xyz))),
            'source_Lab_delta_E00': summary(delta_e), 'worst_patch': str(rows[worst, 0]),
        }

    # Rounded source XYZ and Lab are not interchangeable at low luminance.
    rounded_xyz_de = colour.delta_E(colour.XYZ_to_Lab(reference_xyz / 100, white_xy),
                                   reference_lab, method='CIE 2000')
    return {
        'library': library_inventory(),
        'source': {
            'spectral_url': 'https://www.colorreference.de/testdata/' + spectral_zip.name,
            'reference_url': 'https://www.colorreference.de/testdata/' + reference_zip.name,
            'spectral_archive_sha256': sha256(spectral_zip.read_bytes()),
            'reference_archive_sha256': sha256(reference_zip.read_bytes()),
            'spectral_member': stem + '.cgt', 'spectral_member_sha256': member_hash,
            'reference_member': stem + '.txt', 'reference_member_sha256': ref_hash,
            'metadata': metadata,
            'measurement_geometry': 'not established by the inspected metadata',
            'rights': 'public source downloaded for local review; redistribution review pending',
        },
        'structure': {
            'valid': True, 'patches': len(rows), 'bands': len(wavelength),
            'unique_spectra': len(np.unique(reflectance, axis=0)),
            'reflectance_range': [float(reflectance.min()), float(reflectance.max())],
            'original_quantity': 'SPECTRAL_PCT; divided by 100 without clipping',
            'coverage_nm': [380, 780, 10], 'reference_files_match': True,
        },
        'colorimetry': {
            'illuminant': 'D50', 'observer': 'CIE 1931 2 degree',
            'XYZ_scale': 'Y=100 for perfect reflecting diffuser',
            'Lab_white_xy': white_xy.tolist(), 'calculations': calculations,
            'source_rounded_XYZ_to_source_Lab_delta_E00': summary(rounded_xyz_de),
        },
        'limits': [
            'Reference XYZ/Lab derive from the same spectra: this is a consistency check, not independent measurement validation.',
            'One reflective photographic material/set does not represent all natural spectra or the full RGB LUT domain.',
            'Reference spectra are not paired negative Status M/APD measurements.',
            '380-780nm does not cover 360-380nm; do not invent data for a full-band conformance claim.',
            'Set14 spectra were used in earlier paper-model work; do not label reused patches as independent material validation.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spectral-zip', type=Path, required=True)
    parser.add_argument('--reference-zip', type=Path, required=True)
    parser.add_argument('--stem', default='Testscan14-5')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.spectral_zip, args.reference_zip, args.stem)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    result = report['colorimetry']['calculations']['1nm']
    print(json.dumps({'patches': report['structure']['patches'], 'bands': report['structure']['bands'],
                      'delta_E00_1nm': result['source_Lab_delta_E00'],
                      'integration_error_XYZ_100': result['independent_vs_colour_max_abs_XYZ_100']}, indent=2))


if __name__ == '__main__':
    main()
