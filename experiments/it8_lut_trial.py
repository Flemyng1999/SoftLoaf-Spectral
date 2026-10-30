"""Try reflective IT8 spectra as the prior used to generate film LUTs.

One fixed, exposure-homogeneous linear reconstruction is learned from the IT8
second moment. This is a baseline, not a final reconstruction algorithm.
All LUTs/results are local; numerical error does not block experimental export.
"""

import argparse
import json
from pathlib import Path

from experiments.hsi_raw_lut import (
    SCENES, LOW, HIGH, apply_ocio, bake_cube, batched, build_reference,
    display_processor, load_scene, sha,
)
from experiments.validate_it8_data import read_chart
from spectral_lut.metrics import srgb_code_error, summarize_code_errors
from spectral_lut.reference import acescct_encode, smooth_reconstruction_basis

import colour
import numpy as np


def prior_from_it8(spectra, kernel, relative_ridge=1e-6):
    covariance = spectra.T @ spectra / len(spectra)
    ridge = relative_ridge * np.trace(covariance) / len(covariance)
    covariance += ridge * np.eye(len(covariance))
    gram = kernel.T @ covariance @ kernel
    basis = np.linalg.solve(gram, kernel.T @ covariance)
    identity_error = float(np.max(np.abs(basis @ kernel - np.eye(3))))
    if identity_error > 1e-10:
        raise ValueError('IT8 reconstruction does not preserve unconstrained RGB')
    return basis, {'relative_ridge': relative_ridge, 'absolute_ridge': float(ridge),
                   'RGB_gram_condition_number': float(np.linalg.cond(gram)),
                   'unclipped_RGB_identity_max_abs': identity_error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spectral-zip', type=Path, required=True)
    parser.add_argument('--reference-zip', type=Path, required=True)
    parser.add_argument('--stem', default='Testscan14-5')
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/it8-lut-trial'))
    parser.add_argument('--grids', type=int, nargs='+', default=[33, 65])
    parser.add_argument('--scenes', type=int, nargs='*', default=list(SCENES))
    parser.add_argument('--scene-stride', type=int, default=16)
    args = parser.parse_args()
    if args.scene_stride < 1 or any(n < 2 or n > 129 for n in args.grids):
        parser.error('This trial supports positive scene strides and LUT edge sizes 2–129')
    # Require the full data audit before fitting. It also checks metadata,
    # units, sample identities, bounds and independent color integration.
    from experiments.validate_it8_data import audit
    audited = audit(args.spectral_zip, args.reference_zip, args.stem)
    args.output.mkdir(parents=True, exist_ok=True)
    fields, rows, _, _ = read_chart(args.spectral_zip, args.stem + '.cgt')
    numbers = rows[:, 1:].astype(np.float64)
    wavelengths, spectra = numbers[0, 8::2], numbers[:, 9::2] / 100
    target_wavelengths = np.arange(400, 721, 10)
    spectra = np.stack([np.interp(target_wavelengths, wavelengths, r) for r in spectra])
    film, kernel, _, _, settings = build_reference(args.archive)
    it8_basis, prior_settings = prior_from_it8(spectra, kernel)
    bases = {'it8_second_moment': it8_basis,
             'smooth_control': smooth_reconstruction_basis(kernel)}
    display, _ = display_processor(args.opendrt, args.output / 'opendrt')
    transforms, cubes = {}, {}
    for name, basis in bases.items():
        transforms[name] = lambda rgb, b=basis: film.evaluate(np.maximum(rgb @ b, 0))
        cubes[name] = {}
        for size in args.grids:
            print(f'Building {name}, {size}^3', flush=True)
            path = args.output / f'{name}_{size}.cube'
            cube, processor = bake_cube(transforms[name], size, path)
            cubes[name][size] = (cube, processor, path)
    report = {
        'source_audit': audited, 'reference_settings': settings,
        'prior': {'model': 'uncentered spectral second moment; constrained RGB projection; negative spectra projected to zero',
                  'training': f'{len(spectra)} reflective IT8 spectra only; no held-out scene or chart fitting',
                  'grid_nm': [400, 720, 10], **prior_settings},
        'interface': {'input': 'ACEScct AP1/D60', 'domain_min': LOW.tolist(), 'domain_max': HIGH.tolist(),
                      'output': 'relative viewing XYZ D65, gain 1.8', 'display': 'OpenDRT v1.0.0 Default, standard sRGB',
                      'interpolation': 'tetrahedral', 'EVs': [-2, 0, 2],
                      'exposure': 'uniform scale of incident spectrum; not reflectance above one',
                      'camera': 'ideal colorimetric RGB; no RAW decoder, camera responses or DCP in this trial'},
        'LUTs': [], 'frames': [], 'pooled': {},
        'limits': ['Exploratory baseline; its failure would not prove all IT8-driven methods fail.',
                   'Chart reference consistency does not validate real film accuracy.',
                   'Old development HSI scenes are held out from this IT8 fit, not a new independent final test suite.',
                   'Regular spatial scene subsampling is diagnostic, not a full-image or spectral-diversity guarantee.',
                   'Error is reported for user choice; experimental LUT files are written even if a reference line is missed.'],
    }
    for name, sizes in cubes.items():
        for size, (_, _, path) in sizes.items():
            report['LUTs'].append({'prior': name, 'edge': size, 'file': path.name,
                                   'bytes': path.stat().st_size, 'sha256': sha(path)})
    groups = [('it8_training', spectra)]
    for chart in ('BabelColor Average', 'ColorChecker N Ohta'):
        samples = np.stack([np.interp(target_wavelengths, sd.wavelengths, sd.values)
                            for sd in colour.SDS_COLOURCHECKERS[chart].values()])
        groups.append((chart, samples))
    # Read scenes one at a time. A strided view is copied so the full cube can
    # be released immediately; no HSI pixels enter fitting.
    def inputs():
        yield from groups
        for scene in args.scenes:
            hsi = load_scene(args.archive, scene)
            sample = hsi[::args.scene_stride, ::args.scene_stride].reshape(-1, len(target_wavelengths)).copy()
            del hsi
            yield f'hsi_{scene}', sample
    pooled = {}
    for group, samples in inputs():
        print(f'Checking {group}, {len(samples)} samples', flush=True)
        for ev in (-2, 0, 2):
            signal = samples * 2.0**ev
            rgb = signal @ kernel
            encoded = acescct_encode(rgb)
            outside = np.any((encoded < LOW) | (encoded > HIGH), axis=-1)
            reference = batched(lambda x: apply_ocio(display, film.evaluate(x)), signal)
            for name, transform in transforms.items():
                continuous_xyz = batched(transform, rgb)
                continuous = apply_ocio(display, continuous_xyz)
                approximate, _, _ = srgb_code_error(continuous, reference)
                reconstructed = np.maximum(rgb @ bases[name], 0)
                color_error = np.max(np.abs(reconstructed @ kernel - rgb), axis=-1)
                for size, (cube, processor, _) in cubes[name].items():
                    lut_xyz = apply_ocio(processor, encoded)
                    internal_error = float(np.max(np.abs(lut_xyz - cube.apply(encoded))))
                    if internal_error > 1e-4:
                        raise ValueError('Independent tetrahedral and OCIO LUT readback differ')
                    output = apply_ocio(display, lut_xyz)
                    interpolation, _, _ = srgb_code_error(output, continuous)
                    total, floats, codes = srgb_code_error(output, reference)
                    report['frames'].append({
                        'group': group, 'EV': ev, 'prior': name, 'edge': size,
                        'out_of_LUT_domain_fraction': float(np.mean(outside)),
                        'reconstructed_RGB_max_abs': float(color_error.max()),
                        'negative_before_projection_fraction': float(np.mean(rgb @ bases[name] < 0)),
                        'independent_vs_OCIO_XYZ_max_abs': internal_error,
                        'RGB_approximation': approximate, 'LUT_interpolation': interpolation, 'total': total,
                    })
                    category = 'hsi_diagnostic' if group.startswith('hsi_') else group
                    key = f'{category}/{name}/{size}'
                    pooled.setdefault(key, [[], []])
                    pooled[key][0].append(floats)
                    pooled[key][1].append(codes)
    report['pooled'] = {key: summarize_code_errors(np.concatenate(a), np.concatenate(b))
                        for key, (a, b) in pooled.items()}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    for key, result in report['pooled'].items():
        print(key, result['fraction_within_2_codes_float'], result['fraction_within_2_codes_u8'], flush=True)


if __name__ == '__main__':
    main()
