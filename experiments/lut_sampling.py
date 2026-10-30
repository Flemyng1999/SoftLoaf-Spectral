"""Issue #2: bounded 33-edge sampling/interpolation comparison, not a release.

Run from the repository root: python -m experiments.lut_sampling.
Only the analytic spectral recipe supplies coefficient-fit samples. Development
photographs are evaluation inputs; they do not determine nodes or domains.
"""
import argparse
import json
from pathlib import Path
import platform
import time

from .hsi_raw_lut import (CAMERAS, SCENES, LOW, HIGH, acescct_decode, acescct_encode,
    apply_ocio, batched, build_reference, camera_kernel, dcp_to_ap1,
    display_processor, load_scene, read_dcp, sha, smooth_reconstruction_basis,
    write_synthetic_dng)
import numpy as np
import PyOpenColorIO as ocio

from spectral_lut.metrics import srgb_code_error, summarize_code_errors
from spectral_lut.reference import Cube
from spectral_lut.resampling import fit_trilinear_nodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/lut-sampling'))
    args = parser.parse_args()
    started = time.time()
    root, out = args.archive, args.output
    out.mkdir(parents=True, exist_ok=True)
    film, kernel, _, light, settings = build_reference(root)
    basis = smooth_reconstruction_basis(kernel)

    def reference(encoded):
        return batched(lambda rgb: film.evaluate(np.maximum(rgb@basis, 0)), acescct_decode(encoded))

    def grid(size, low, high):
        axis = np.linspace(low, high, size)
        return np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1)

    print('Calculating uniform 65-edge spectral reference for coefficient fitting', flush=True)
    fine = reference(grid(65, LOW[0], HIGH[0]))
    raw_fitted = fit_trilinear_nodes(fine)
    baseline = Cube(fine[::2, ::2, ::2], LOW, HIGH)
    # A bounded coefficient projection, not a constrained least-squares solve.
    # Its effects on all evaluation and guard samples are measured below.
    fitted = Cube(np.maximum(raw_fitted, 0), LOW, HIGH)
    variants = [('uniform33_tetra', baseline, 'tetrahedral'),
                ('uniform33_linear', baseline, 'trilinear'),
                ('fitted33_linear', fitted, 'trilinear'),
                ('fitted33_tetra_control', fitted, 'tetrahedral'),
                ('domain33_tetra', Cube(reference(grid(33, 0, .7)), np.zeros(3), np.full(3, .7)), 'tetrahedral'),
                ('uniform65_tetra_control', Cube(fine, LOW, HIGH), 'tetrahedral')]
    display, _ = display_processor(args.opendrt, out/'opendrt')
    processors = {}
    report = {'issue': 2, 'recipe': settings,
              'input': 'ACEScct AP1/D60', 'output': 'relative viewed XYZ D65 before OpenDRT',
              'fit': {'samples': 'uniform 65^3 analytic spectral evaluations, including nodes and edge midpoints',
                      'objective': 'unweighted squared XYZ error at analytic grid samples; separable trilinear basis',
                      'constraint': 'project fitted XYZ coefficients to >=0 after fitting; not an NNLS optimum',
                      'negative_components_before_projection': int(np.count_nonzero(raw_fitted < 0)),
                      'minimum_before_projection': float(raw_fitted.min()),
                      'photo_fitting': False},
              'acceptance': {'limit': 'at least 99% of pixels within 2/255 in all three final sRGB channels',
                             'checks': 'both continuous and rounded codes; frame and pooled verdicts distinct'},
              'limitations': ['Development scenes reused; no independent final benchmark',
                              'Candidate selection was informed by development results',
                              'LUT interpolation only; spectral-prior/profile error remains separate',
                              'Random-domain and gray guards do not certify every possible input',
                              'Local research assets only; rights pending'],
              'sources': [], 'variants': [], 'frames': [], 'pooled': []}
    sources = list((root/'output/reversal-E100/data').glob('*.csv'))
    sources += [root/'output/reversal-E100/intermediate/model.npz', args.opendrt]
    sources += [root.parent/'data'/n for n in ['CIE_xyz_official.csv', 'CIE_std_illum_D50.csv', 'CIE_std_illum_D65.csv']]
    for sensor, profile, _, _ in CAMERAS.values():
        sources += [root/'data'/sensor, root/'profiles'/profile]
    sources += [root/'data'/f'hsi_{n}.zip' for n in SCENES]
    report['sources'] = [{'name': p.name, 'sha256': sha(p)} for p in sources]
    for name, cube, mode in variants:
        path = out/(name+'.cube')
        cube.write(path)
        reloaded = Cube.read(path)
        np.testing.assert_array_equal(cube.table, reloaded.table)
        processors[name] = ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(
            src=str(path.resolve()), interpolation=ocio.INTERP_LINEAR if mode == 'trilinear'
            else ocio.INTERP_TETRAHEDRAL)).getDefaultCPUProcessor()
        report['variants'].append({'name': name, 'edge': len(cube.table),
                                   'domain_min': cube.domain_min.tolist(), 'domain_max': cube.domain_max.tolist(),
                                   'interpolation': mode, 'file': path.name, 'sha256': sha(path)})
    pooled = {(name, camera, kind): [[], []] for name, _, _ in variants
              for camera in CAMERAS for kind in ['interpolation', 'total']}
    cameras = {}
    for camera, (sensor, profile, make, model) in CAMERAS.items():
        response, _ = camera_kernel(root/'data'/sensor, light, np.arange(400, 721, 10))
        cameras[camera] = response, read_dcp(root/'profiles'/profile), make, model
    for scene in SCENES:
        print('Scene', scene, flush=True)
        stimulus = load_scene(root, scene)
        for ev in [-1, 0, 1]:
            hsi = stimulus*2**ev
            truth = apply_ocio(display, batched(film.evaluate, hsi))
            for camera, (response, profile, make, model) in cameras.items():
                raw, neutral, clipping = write_synthetic_dng(out/'scratch_SYNTHETIC.dng', hsi@response,
                    response.sum(axis=0), profile, make, model)
                rgb, _ = dcp_to_ap1(raw, neutral, profile)
                encoded = acescct_encode(rgb)
                continuous = apply_ocio(display, reference(encoded))
                for name, cube, mode in variants:
                    xyz = cube.apply(encoded, interpolation=mode)
                    independent = apply_ocio(processors[name], encoded)
                    own_display = apply_ocio(display, xyz)
                    ocio_display = apply_ocio(display, independent)
                    item = dict(variant=name, camera=camera, scene=scene, ev=ev,
                                ocio_vs_float64_max_XYZ=float(np.max(np.abs(xyz-independent))),
                                outside_fraction=float(np.mean(np.any((encoded<cube.domain_min)|(encoded>cube.domain_max),axis=-1))),
                                RAW_clipped_channel_fraction=clipping)
                    item['ocio_interpolation'], _, _ = srgb_code_error(ocio_display, continuous)
                    for kind, target in [('interpolation', continuous), ('total', truth)]:
                        summary, floats, codes = srgb_code_error(own_display, target)
                        item[kind] = summary
                        pooled[name, camera, kind][0].append(floats.ravel())
                        pooled[name, camera, kind][1].append(codes.ravel())
                    report['frames'].append(item)
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    for name, _, _ in variants:
        for camera in CAMERAS:
            row = dict(variant=name, camera=camera)
            for kind in ['interpolation', 'total']:
                floats, codes = pooled[name, camera, kind]
                row[kind] = summarize_code_errors(np.concatenate(floats), np.concatenate(codes))
            frames = [f for f in report['frames'] if f['variant']==name and f['camera']==camera]
            row['frames_accepted'] = sum(f['interpolation']['accepted'] for f in frames)
            row['worst_frame_float_fraction'] = min(f['interpolation']['fraction_within_2_codes_float'] for f in frames)
            report['pooled'].append(row)
            print(name, camera, 'float:', row['interpolation']['fraction_within_2_codes_float'],
                  '8-bit:', row['interpolation']['fraction_within_2_codes_u8'],
                  'frame passes:', row['frames_accepted'], '/24', flush=True)
    # No photo participates in these fixed independent validation points.
    rng = np.random.default_rng(20261026)
    random = rng.uniform(LOW, HIGH, size=(100000, 3))
    ramp = np.repeat(np.linspace(LOW[0], HIGH[0], 4097)[:, None], 3, axis=1)
    coarse = grid(9, LOW[0], HIGH[0]).reshape(-1, 3)
    boundaries = coarse[np.any((coarse == LOW)|(coarse == HIGH), axis=1)]
    report['guards'] = []
    for label, points in [('uniform_domain_random', random), ('neutral_ramp', ramp), ('boundary_grid', boundaries)]:
        target_xyz = reference(points)
        target = apply_ocio(display, target_xyz)
        for name, cube, mode in variants:
            xyz = cube.apply(points, interpolation=mode)
            metric, _, _ = srgb_code_error(apply_ocio(display, xyz), target)
            guard = dict(variant=name, samples=label, metric=metric,
                         max_abs_XYZ=float(np.max(np.abs(xyz-target_xyz))),
                         nonfinite_values=int(np.count_nonzero(~np.isfinite(xyz))),
                         negative_values=int(np.count_nonzero(xyz<0)),
                         outside_fraction=float(np.mean(np.any((points<cube.domain_min)|(points>cube.domain_max),axis=-1))))
            if label == 'neutral_ramp':
                guard['decreasing_Y_steps'] = int(np.count_nonzero(np.diff(xyz[:, 1]) < -1e-12))
                guard['largest_Y_drop'] = float(max(0, -np.min(np.diff(xyz[:, 1]))))
            report['guards'].append(guard)
    report['versions'] = {'python': platform.python_version(), 'numpy': np.__version__, 'ocio': ocio.__version__}
    report['implementation_sources'] = [{'name': str(p), 'sha256': sha(p)} for p in [
        Path('experiments/lut_sampling.py'), Path('experiments/hsi_raw_lut.py'),
        Path('spectral_lut/reference.py'), Path('spectral_lut/film.py'),
        Path('spectral_lut/camera.py'), Path('spectral_lut/resampling.py'), Path('spectral_lut/metrics.py'),
        Path('requirements-experiment.txt')]]
    report['elapsed_seconds'] = time.time()-started
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('Complete:',len(report['frames']),'comparisons;',round(report['elapsed_seconds'],1),'seconds',flush=True)


if __name__ == '__main__':
    main()
