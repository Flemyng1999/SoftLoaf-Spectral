"""Exploratory sampling-design study, not a released database or new default.

Compare color-space coverage with reflectance feasibility, test several small
measured-spectra coresets, and construct bounded smooth metamer stress pairs.
The numerical and material limits of the existing E100 reference still apply.
"""

import argparse
import json
from pathlib import Path

from experiments.hsi_raw_lut import (
    AP1, D60, HIGH, LOW, apply_ocio, build_reference, display_processor,
    load_scene, sha,
)
from experiments.it8_lut_trial import prior_from_it8
from spectral_lut.metrics import srgb_code_error, summarize_code_errors
from spectral_lut.reference import acescct_decode, acescct_encode

import colour
import matplotlib.pyplot as plt
import numpy as np
import scipy
from scipy.optimize import linprog
from scipy.spatial import cKDTree
from scipy.stats import qmc


def farthest_points(features, count, start):
    distance = np.full(len(features), np.inf)
    selected, next_index = [], start
    for _ in range(count):
        selected.append(next_index)
        delta = features - features[next_index]
        distance = np.minimum(distance, np.einsum('ij,ij->i', delta, delta))
        distance[selected] = -np.inf
        next_index = int(np.argmax(distance))
    return np.asarray(selected)


def quantiles(values):
    return dict(zip(('median', 'p95', 'max'), map(float, np.percentile(values, (50, 95, 100)))))


def feasibility(kernel, size_log2):
    unit = qmc.Sobol(3, scramble=True, seed=20261026).random_base2(size_log2)
    srgb = colour.cctf_decoding(unit, function='sRGB')
    xyz = srgb @ colour.RGB_COLOURSPACES['sRGB'].matrix_RGB_to_XYZ.T
    adaptation = colour.adaptation.matrix_chromatic_adaptation_VonKries(
        colour.xy_to_XYZ([0.3127, 0.3290]), D60, 'Bradford')
    rgb_srgb = xyz @ adaptation.T @ AP1.matrix_XYZ_to_RGB.T
    domains = {'encoded_sRGB_cube_0_1': rgb_srgb,
               'linear_AP1_cube_0_1': unit,
               'ACEScct_cube_minus0.25_0.75': acescct_decode(LOW + unit * (HIGH - LOW))}
    rows = []
    for name, colors in domains.items():
        print('Feasibility:', name, flush=True)
        for upper in (1.0, 16.0):
            feasible, errors, uncertain = 0, [], 0
            for color in colors:
                solved = linprog(np.zeros(len(kernel)), A_eq=kernel.T, b_eq=color,
                                 bounds=(0, upper), method='highs')
                if solved.success:
                    residual = float(np.max(np.abs(solved.x @ kernel - color)))
                    if residual > 1e-7 or np.min(solved.x) < -1e-8 or np.max(solved.x) > upper + 1e-8:
                        raise ValueError('LP returned an invalid spectrum')
                    errors.append(residual)
                    feasible += 1
                elif solved.status != 2:
                    uncertain += 1
            rows.append({'domain': name, 'count': len(colors), 'spectrum_upper_bound': upper,
                         'feasible_count': feasible, 'feasible_fraction': feasible / len(colors),
                         'infeasible_count': len(colors) - feasible - uncertain,
                         'solver_other_status_count': uncertain,
                         'max_equality_residual': max(errors, default=None)})
    return rows


def metamer_pairs(film, kernel, display):
    # These derivative limits are declared exploratory stress constraints, not
    # a claim about the distribution or smoothness of measured materials.
    n = len(kernel)
    d1, d2 = np.diff(np.eye(n), axis=0), np.diff(np.eye(n), n=2, axis=0)
    constraints = np.vstack((d1, -d1, d2, -d2))
    limits = np.r_[np.full(2 * len(d1), .08), np.full(2 * len(d2), .025)]
    color = np.full(n, .18) @ kernel
    pairs, spectra = [], []
    for channel in range(3):
        endpoints = []
        for sign in (1, -1):
            solved = linprog(sign * film.exposure_kernel[:, channel], A_eq=kernel.T, b_eq=color,
                             A_ub=constraints, b_ub=limits, bounds=(0, 1), method='highs')
            if not solved.success:
                raise RuntimeError('Metamer LP failed: ' + solved.message)
            endpoints.append(solved.x)
        endpoints = np.stack(endpoints)
        equality_error = float(np.max(np.abs(endpoints @ kernel - color)))
        if equality_error > 1e-7 or np.max(constraints @ endpoints.T - limits[:, None]) > 1e-7:
            raise ValueError('Metamer pair violates constraints')
        output = np.clip(apply_ocio(display, film.evaluate(endpoints)), 0, 1)
        code_distance = float(np.max(np.abs(output[0] - output[1])) * 255)
        pairs.append({'maximized_exposure_channel': channel, 'same_AP1': color.tolist(),
                      'AP1_equality_max_abs': equality_error,
                      'reflectance_min': float(endpoints.min()), 'reflectance_max': float(endpoints.max()),
                      'output_sRGB': output.tolist(), 'output_diameter_codes': code_distance,
                      'pair_minimax_lower_bound_codes': code_distance / 2,
                      'both_can_be_within_2_codes': code_distance <= 4})
        spectra.append(endpoints)
    return pairs, np.stack(spectra)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/sampling-database-study'))
    parser.add_argument('--budgets', type=int, nargs='+', default=[256, 512])
    parser.add_argument('--lp-log2', type=int, default=9)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    film, kernel, _, _, settings = build_reference(args.archive)
    display, _ = display_processor(args.opendrt, args.output / 'opendrt')
    train_scenes, test_scenes = (1, 5, 6, 16), (31, 38, 43, 50)
    training, testing, source_hashes = [], [], {}
    ranges = {}
    for scene in train_scenes + test_scenes:
        full = load_scene(args.archive, scene)
        stride = 4 if scene in train_scenes else 8
        samples = full[::stride, ::stride].reshape(-1, len(kernel)).copy()
        ranges[str(scene)] = [float(samples.min()), float(samples.max())]
        (training if scene in train_scenes else testing).append(samples)
        source_hashes[f'hsi_{scene}.zip'] = sha(args.archive / 'data' / f'hsi_{scene}.zip')
        del full
    train, test = np.concatenate(training), np.concatenate(testing)
    if not np.isfinite(train).all() or not np.isfinite(test).all():
        raise ValueError('Nonfinite measured spectra')
    # Retain measurements as supplied, including any factors outside [0,1].
    # Bound-constrained LP spectra are a separate synthetic data class.
    train_rgb, test_rgb = train @ kernel, test @ kernel
    train_lab = colour.XYZ_to_Lab(train_rgb @ AP1.matrix_RGB_to_XYZ.T, AP1.whitepoint)
    test_lab = colour.XYZ_to_Lab(test_rgb @ AP1.matrix_RGB_to_XYZ.T, AP1.whitepoint)
    train_log = acescct_encode(train_rgb)
    # Robust scales determine an explicit distance measure; maximin is not a
    # claim of uniform probability density in RGB, Lab or spectral space.
    lab_scale = np.maximum(np.percentile(train_lab, 95, axis=0) - np.percentile(train_lab, 5, axis=0), 1e-8)
    spectrum_mean = train.mean(axis=0)
    _, _, axes = np.linalg.svd(train - spectrum_mean, full_matrices=False)
    scores = (train - spectrum_mean) @ axes[:8].T
    score_scales = np.maximum(np.std(scores, axis=0), 1e-8)
    log_features = train_log / np.maximum(np.ptp(train_log, axis=0), 1e-8)
    lab_features = train_lab / lab_scale
    hybrid_features = np.column_stack((lab_features / np.sqrt(3),
                                       scores / score_scales / np.sqrt(8)))
    start = int(np.argmin(np.linalg.norm(train_rgb - .18, axis=1)))
    selections = {'ACEScct_maximin': farthest_points(log_features, max(args.budgets), start),
                  'Lab_maximin': farthest_points(lab_features, max(args.budgets), start),
                  'Lab_spectral_maximin': farthest_points(hybrid_features, max(args.budgets), start)}
    for seed in range(3):
        selections[f'random_{seed}'] = np.random.default_rng(20261026 + seed).choice(len(train), max(args.budgets), replace=False)
    report = {
        'versions': {'numpy': np.__version__, 'scipy': scipy.__version__, 'colour': colour.__version__},
        'reference_settings': settings, 'source_hashes': source_hashes,
        'split': {'train_scenes': train_scenes, 'train_stride': 4, 'train_candidates': len(train),
                  'test_scenes': test_scenes, 'test_stride': 8, 'test_spectra': len(test),
                  'EVs': [-2, 0, 2], 'source_ranges': ranges,
                  'train_spectra_with_factor_above_one': int(np.count_nonzero(np.any(train > 1, axis=1))),
                  'test_spectra_with_factor_above_one': int(np.count_nonzero(np.any(test > 1, axis=1))),
                  'note': 'Whole scenes separated for this comparison; all eight were earlier development data, not a final blind set.'},
        'feasibility': feasibility(kernel, args.lp_log2), 'coresets': [],
        'feature_metric': {'Lab_white': 'D60 after the finite-band D65 to D60 adaptation',
                           'Lab_scales': lab_scale.tolist(), 'spectral_PCA_components': 8,
                           'spectral_PCA_scales': score_scales.tolist(),
                           'hybrid': 'equal total squared scale for 3 color axes and 8 standardized spectral PCA axes'},
        'limitations': ['No new measurements; measured selections and synthetic spectra are different classes.',
                        'Bounded finite-band reflectance feasibility is not full-band standard conformance.',
                        'A sampling comparison with one linear prior does not rank all reconstruction algorithms.',
                        'Perceptual maximin coverage and spectral constraints do not establish natural-material probability.',
                        'No LUT interpolation is used in the coreset comparison: this isolates the RGB approximation.',
                        'The synthetic metamer pairs are stress examples, not estimates of real-scene frequency.'],
    }
    truths = [apply_ocio(display, film.evaluate(test * 2.0**ev)) for ev in (-2, 0, 2)]
    for method, selection in selections.items():
        for budget in args.budgets:
            indices = selection[:budget]
            chosen = train[indices]
            basis, fit_settings = prior_from_it8(chosen, kernel)
            lab_distance = cKDTree(train_lab[indices]).query(test_lab)[0]
            spectral_distance = cKDTree(chosen / np.sqrt(len(kernel))).query(test / np.sqrt(len(kernel)))[0]
            floats, rounded = [], []
            for ev, truth in zip((-2, 0, 2), truths):
                predicted = apply_ocio(display, film.evaluate(np.maximum((test_rgb * 2.0**ev) @ basis, 0)))
                _, f, r = srgb_code_error(predicted, truth)
                floats.append(f)
                rounded.append(r)
            result = {'method': method, 'budget': budget,
                      'selected_spectra_with_factor_above_one': int(np.count_nonzero(np.any(chosen > 1, axis=1))),
                      'nearest_color_CIE76': quantiles(lab_distance),
                      'nearest_spectrum_RMSE': quantiles(spectral_distance),
                      'RGB_approximation': summarize_code_errors(np.concatenate(floats), np.concatenate(rounded)),
                      'prior_fit': fit_settings}
            report['coresets'].append(result)
            print(method, budget, 'LabP95', result['nearest_color_CIE76']['p95'],
                  'code fraction', result['RGB_approximation']['fraction_within_2_codes_float'], flush=True)
    report['metamer_pairs'], pair_spectra = metamer_pairs(film, kernel, display)
    report['metamer_constraints'] = {'bounds': [0, 1], 'max_adjacent_difference_per_10nm': .08,
                                    'max_second_difference': .025, 'grid_nm': [400, 720, 10]}
    np.savez_compressed(args.output / 'study.npz', train_lab=train_lab, test_lab=test_lab,
                        pair_spectra=pair_spectra, selections=np.stack(list(selections.values())),
                        selection_names=np.asarray(list(selections)), wavelengths_nm=np.arange(400, 721, 10))
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    figure, panels = plt.subplots(2, 2, figsize=(12, 9), layout='constrained')
    domain_names = list(dict.fromkeys(r['domain'] for r in report['feasibility']))
    x = np.arange(3)
    for offset, upper, title in [(-.18, 1., 'Reflectance [0,1]'), (.18, 16., 'Exposure-scaled [0,16]')]:
        values = [next(r['feasible_fraction'] for r in report['feasibility'] if r['domain'] == name and r['spectrum_upper_bound'] == upper) * 100 for name in domain_names]
        panels[0, 0].bar(x + offset, values, width=.36, label=title)
    panels[0, 0].set(xticks=x, xticklabels=['sRGB code cube', 'Linear AP1 cube', 'ACEScct domain'], ylabel='Feasible targets (%)', title='Finite-band spectral feasibility')
    panels[0, 0].legend(fontsize=8)
    chosen = selections['Lab_maximin'][:max(args.budgets)]
    panels[0, 1].scatter(test_lab[:, 1], test_lab[:, 2], s=3, alpha=.2, label='Held-out scene spectra')
    panels[0, 1].scatter(train_lab[chosen, 1], train_lab[chosen, 2], s=9, label='Lab maximin coreset')
    panels[0, 1].set(xlabel='a*', ylabel='b*', title='Color projection: lightness is omitted')
    panels[0, 1].legend(fontsize=8)
    for method in selections:
        rows = [r for r in report['coresets'] if r['method'] == method]
        panels[1, 0].plot([r['budget'] for r in rows], [r['RGB_approximation']['fraction_within_2_codes_float'] * 100 for r in rows], marker='o', label=method)
    panels[1, 0].set(xlabel='Selected measured spectra', ylabel='Within 2/255 (%)', title='Continuous RGB approximation on held-out scenes')
    panels[1, 0].legend(fontsize=7)
    for i, spectrum in enumerate(pair_spectra[0]):
        panels[1, 1].plot(np.arange(400, 721, 10), spectrum, label=f'Metamer {i+1}')
    gap = report['metamer_pairs'][0]['output_diameter_codes']
    panels[1, 1].set(xlabel='Wavelength (nm)', ylabel='Reflectance', title=f'Synthetic stress pair; model output gap {gap:.2f}/255')
    panels[1, 1].legend(fontsize=8)
    figure.savefig(args.output / 'sampling-study.png', dpi=160)
    plt.close(figure)
    print('Metamer pair code gaps:', [r['output_diameter_codes'] for r in report['metamer_pairs']], flush=True)


if __name__ == '__main__':
    main()
