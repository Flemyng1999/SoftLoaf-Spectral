"""Build separate reversal/negative input databases, then tune on development data.

Negative APD output is explicitly unavailable. E100 is a local numerical
reference, not measured film truth. All data/model files remain local.
"""

import argparse
import copy
import hashlib
import json
import sqlite3
from pathlib import Path

from experiments.hsi_raw_lut import (
    AP1, apply_ocio, bake_cube, batched, build_reference, display_processor,
    load_scene, sha,
)
from experiments.sampling_database_study import farthest_points
from experiments.validate_it8_data import audit as audit_it8, read_chart
from spectral_lut.metrics import srgb_code_error, summarize_code_errors
from spectral_lut.reconstruction import LocalSpectralPrior, RootPolynomialPrior, global_spectral_basis
from spectral_lut.reference import acescct_encode, smooth_reconstruction_basis
from spectral_lut.sampling_db import SamplingDatabase, SpectrumRecord

import colour
import numpy as np
import scipy
from scipy.optimize import linprog
from scipy.spatial import cKDTree
from scipy.stats import qmc


GRID = np.arange(400, 721, 10, dtype=np.float64)
SPLITS = {'fit': (1, 5), 'dev': (6, 16), 'audit': (31, 38, 43, 50)}


def family_conditions(family, shared, reversal_reference):
    result = copy.deepcopy(shared)
    if family == 'reversal':
        result.update(stock='E100', output_status='E100_local_reference',
                      output_conditions=copy.deepcopy(reversal_reference))
    elif family == 'negative':
        result.update(stock='5207', output_status='APD_output_unimplemented',
                      output_conditions={'metric': 'APD', 'unit': 'D', 'status': 'unimplemented',
                                         'standard': 'SMPTE ST2065-2:2012',
                                         'standard_conversion_verified': False})
    else:
        raise ValueError('Unknown film family')
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def sources_and_samples(archive, it8):
    sources, samples = {}, []
    for split, scenes in SPLITS.items():
        for scene in scenes:
            name = f'hsi_{scene}'
            path = archive/'data'/f'{name}.zip'
            sources[name] = {'filename': path.name, 'sha256': sha(path),
                'reference': 'doi:10.48420/14877285.v3', 'rights': 'CC-BY-4.0; retain upstream attribution',
                'authors': 'David H. Foster; Kinjiro Amano; Sergio M. C. Nascimento',
                'quantity': 'spectral_reflectance_factor', 'unit': '1', 'native_grid_nm': [400, 720, 10],
                'group': name, 'split': split}
            image = load_scene(archive, scene)
            stride = 4 if split == 'fit' else 8
            for y in range(0, image.shape[0], stride):
                for x in range(0, image.shape[1], stride):
                    samples.append(SpectrumRecord(f'{name}/{y:04}_{x:04}', name, name, split,
                                                  'measured', GRID, image[y, x].copy()))
            del image
    for name in ('BabelColor Average', 'ColorChecker N Ohta'):
        identifier = name.lower().replace(' ', '_')
        patches = colour.SDS_COLOURCHECKERS[name]
        payload = b''.join(np.column_stack((s.wavelengths, s.values)).astype('<f8').tobytes() for s in patches.values())
        sources[identifier] = {'reference': 'Colour SDS_COLOURCHECKERS/' + name,
            'colour_version': colour.__version__, 'numeric_sha256': hashlib.sha256(payload).hexdigest(),
            'rights': 'exact source attribution and redistribution review pending',
            'quantity': 'spectral_reflectance_factor', 'unit': '1', 'group': 'colorchecker24', 'split': 'fit'}
        for patch, data in patches.items():
            samples.append(SpectrumRecord(identifier+'/'+patch, identifier, 'colorchecker24', 'fit',
                                           'measured', data.wavelengths.copy(), data.values.copy()))
    if it8 is not None:
        spectral_zip, reference_zip = it8
        audit = audit_it8(spectral_zip, reference_zip, 'Testscan14-5')
        _, rows, _, _ = read_chart(spectral_zip, 'Testscan14-5.cgt')
        values = rows[:, 1:].astype(np.float64)
        wavelengths, reflectance = values[0, 8::2], values[:, 9::2]/100
        sources['it8_set14_5'] = {**audit['source'], 'group': 'it8_set14_5', 'split': 'fit',
            'quantity': 'spectral_reflectance_factor', 'unit': '1',
            'note': 'All patches belong to one fit group, not independent film measurements.'}
        for identifier, row in zip(rows[:, 0], reflectance):
            samples.append(SpectrumRecord('it8/'+identifier, 'it8_set14_5', 'it8_set14_5',
                                           'fit', 'measured', wavelengths, row))
    return sources, samples


def make_synthetic(db, family, kernel, count):
    # TV minimization is a declared synthetic representative, not a measured
    # material or a probability sample of natural spectra.
    n = len(kernel)
    d1 = np.diff(np.eye(n), axis=0)
    d2 = np.diff(np.eye(n), n=2, axis=0)
    zeros = np.zeros((len(d2), len(d1)))
    inequality = np.vstack((np.column_stack((d1, -np.eye(len(d1)))),
                           np.column_stack((-d1, -np.eye(len(d1)))),
                           np.column_stack((d2, zeros)), np.column_stack((-d2, zeros))))
    limits = np.r_[np.zeros(2*len(d1)), np.full(2*len(d2), .025)]
    objective = np.r_[np.zeros(n), np.ones(len(d1))]
    equality = np.column_stack((kernel.T, np.zeros((3, len(d1)))))
    targets = qmc.Sobol(3, scramble=True, seed=20261026 if family == 'reversal' else 20261027).random_base2(int(np.log2(count)))
    successes = 0
    for index, target in enumerate(targets):
        solved = linprog(objective, A_eq=equality, b_eq=target, A_ub=inequality, b_ub=limits,
                         bounds=[(0, 1)]*n+[(0, None)]*len(d1), method='highs')
        status = 'infeasible_under_constraints'
        details = {'input': 'linear AP1 D60, unit exposure; D65 spectral reference',
                   'solver_status': int(solved.status), 'synthetic': True}
        if solved.success:
            spectrum = solved.x[:n]
            error = float(np.max(np.abs(spectrum @ kernel - target)))
            if error > 1e-7 or spectrum.min() < -1e-8 or spectrum.max() > 1+1e-8:
                raise ValueError('Invalid synthetic spectrum')
            # HiGHS may return tiny signed roundoff at an active bound. Store
            # it as returned; flags, not clipping, determine fitting eligibility.
            identifier = f'{family}/synthetic/{index:05}'
            db.add_spectrum(SpectrumRecord(identifier, 'synthetic_tv', identifier, 'probe',
                                            'synthetic', GRID, spectrum))
            details.update({'spectrum_id': identifier, 'RGB_residual': error})
            status, successes = 'feasible', successes+1
        elif solved.status != 2:
            raise RuntimeError('Unknown synthetic solver failure: ' + solved.message)
        db.add_probe(f'color_target/{index:05}', 'physical_color_target', target.tolist(), status, details)
    numeric = qmc.Sobol(3, scramble=True, seed=83 if family == 'reversal' else 84).random_base2(10)
    numeric = -.25 + numeric
    gray = np.repeat(np.linspace(-.25, .75, 257)[:, None], 3, axis=1)
    corners = np.array(list(np.ndindex(2, 2, 2)), dtype=float)-.25
    for index, target in enumerate(np.vstack((numeric, gray, corners))):
        db.add_probe(f'numeric/{index:05}', 'ACEScct_numeric_domain', target.tolist(),
                     'not_a_measured_spectrum', {'input': 'ACEScct AP1/D60', 'domain': [-.25, .75]})
    return {'targets': len(targets), 'feasible': successes, 'numeric_probes': len(numeric)+len(gray)+len(corners)}


def arrays(db, split):
    rows = db.connection.execute('SELECT id,group_id,eligible FROM spectra WHERE split=? AND kind=? ORDER BY id',
                                  (split, 'measured')).fetchall()
    return ([r[0] for r in rows], [r[1] for r in rows], np.array([r[2] for r in rows], dtype=bool),
            np.stack([db.spectrum(r[0]).on_grid(GRID) for r in rows]))


def add_metamer_groups(db, family, kernel, film):
    n = len(kernel)
    d1, d2 = np.diff(np.eye(n), axis=0), np.diff(np.eye(n), n=2, axis=0)
    constraints = np.vstack((d1, -d1, d2, -d2))
    limits = np.r_[np.full(2*len(d1), .08), np.full(2*len(d2), .025)]
    generic = np.stack([np.sin(np.linspace(0, np.pi*(i+1), n)) for i in range(3)], axis=1)
    objectives = film.exposure_kernel if family == 'reversal' else generic
    db.add_source('metamer_lp', {'kind': 'synthetic_metamer_stress', 'unit': '1',
        'method': 'min/max linear objective with exact input RGB equality, bounded smooth spectra',
        'objective': 'E100 effective exposure' if family == 'reversal' else 'generic sinusoidal spectral projections; no negative output model',
        'bounds': [0, 1], 'max_adjacent_difference': .08, 'max_second_difference': .025})
    for gray in (.02, .18, .5):
        color = np.full(n, gray) @ kernel
        for axis in range(3):
            group = f'{family}/metamer/{gray}/{axis}'
            identifiers = []
            for side, sign in enumerate((1, -1)):
                solved = linprog(sign*objectives[:, axis], A_eq=kernel.T, b_eq=color,
                                 A_ub=constraints, b_ub=limits, bounds=(0, 1), method='highs')
                if not solved.success:
                    raise ValueError('Metamer constraints could not be satisfied')
                residual = float(np.max(np.abs(solved.x @ kernel-color)))
                if residual > 1e-7 or np.max(constraints @ solved.x-limits) > 1e-7:
                    raise ValueError('Metamer constraint residual exceeds tolerance')
                identifier = group+'/'+str(side)
                db.add_spectrum(SpectrumRecord(identifier, 'metamer_lp', group, 'probe', 'synthetic', GRID, solved.x))
                identifiers.append(identifier)
            db.add_probe(group, 'metamer_group', color.tolist(), 'synthetic_input_match',
                         {'spectrum_ids': identifiers, 'input': 'linear AP1/D60; D65; unit exposure',
                          'negative_output_tested': False})
    return {'groups': 9, 'spectra': 18}


def spectral_evaluate(reconstruct, spectra, kernel):
    predicted = reconstruct(spectra @ kernel)
    rms = np.sqrt(np.mean((predicted-spectra)**2, axis=1))
    return {'spectra': len(spectra), 'mean_spectral_RMSE': float(np.mean(rms)),
            'p95_spectral_RMSE': float(np.percentile(rms, 95)), 'max_spectral_RMSE': float(rms.max()),
            'RGB_roundtrip_max_abs': float(np.max(np.abs(predicted @ kernel-spectra @ kernel))),
            'scope': 'input reconstruction only; not negative APD or display error'}


def candidate_priors(spectra, selection, groups, kernel, budgets):
    baseline = smooth_reconstruction_basis(kernel)
    candidates, models = {'smooth_baseline': lambda x: np.maximum(x @ baseline, 0)}, {}
    for budget in budgets:
        chosen = spectra[selection[:budget]]
        basis = global_spectral_basis(chosen, kernel)
        candidates[f'global_{budget}'] = lambda x, b=basis: np.maximum(x @ b, 0)
        for degree in (2, 3):
            for ridge in (1e-5, 1e-3):
                name = f'root{degree}_{budget}_{ridge}'
                model = RootPolynomialPrior(chosen, kernel, degree=degree, ridge=ridge)
                candidates[name], models[name] = model.reconstruct, model
        for neighbors in (32, 128):
            name = f'local_{budget}_{neighbors}'
            model = LocalSpectralPrior(chosen, kernel, AP1.matrix_RGB_to_XYZ[1], neighbors=neighbors, ridge=.01)
            candidates[name], models[name] = model.reconstruct, model
    unique, counts = np.unique(groups, return_counts=True)
    group_counts = dict(zip(unique, counts))
    weights = np.array([1/group_counts[g] for g in groups])
    for ridge in (1e-5, 1e-3):
        name = f'root3_source_balanced_{ridge}'
        model = RootPolynomialPrior(spectra, kernel, degree=3, ridge=ridge, weights=weights)
        candidates[name], models[name] = model.reconstruct, model
    return candidates, models


def evaluate(reconstruct, spectra, film, kernel, display):
    floats, rounded, closure, negatives = [], [], [], []
    for ev in (-2, 0, 2):
        signal = spectra * 2.**ev
        rgb = signal @ kernel
        prediction = reconstruct(rgb)
        truth = apply_ocio(display, film.evaluate(signal))
        rendered = apply_ocio(display, film.evaluate(prediction))
        _, f, u = srgb_code_error(rendered, truth)
        floats.append(f); rounded.append(u)
        closure.append(np.max(np.abs(prediction @ kernel-rgb), axis=1))
        negatives.append(int(np.count_nonzero(prediction < 0)))
    return {**summarize_code_errors(np.concatenate(floats), np.concatenate(rounded)),
            'RGB_roundtrip_max_abs': float(max(v.max() for v in closure)),
            'negative_output_values': sum(negatives)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--it8-spectral-zip', type=Path)
    parser.add_argument('--it8-reference-zip', type=Path)
    parser.add_argument('--output', type=Path, default=Path('artifacts/sampling-database'))
    parser.add_argument('--budgets', type=int, nargs='+', default=[512, 1024])
    parser.add_argument('--grids', type=int, nargs='+', default=[33, 65])
    parser.add_argument('--synthetic-targets', type=int, default=512)
    args = parser.parse_args()
    if any(b < 128 for b in args.budgets) or args.synthetic_targets < 1 or args.synthetic_targets & (args.synthetic_targets-1):
        parser.error('Use budgets >=128 and a power-of-two synthetic target count')
    if any(size < 2 or size > 129 for size in args.grids):
        parser.error('LUT edge sizes must be integers from 2 to 129')
    if bool(args.it8_spectral_zip) != bool(args.it8_reference_zip):
        parser.error('Supply both IT8 files or neither')
    if any((args.output/(family+'.sqlite')).exists() for family in ('reversal', 'negative')):
        parser.error('Output databases already exist; use a new output directory')
    args.output.mkdir(parents=True, exist_ok=True)
    film, kernel, _, _, reference_settings = build_reference(args.archive)
    reference_settings = {**reference_settings,
        'material_source_hashes': {name: sha(args.archive/'output/reversal-E100/data'/name) for name in
            ('E100_characteristic_RGB.csv', 'E100_linear_sensitivity_RGB.csv', 'E100_dye_density_CMY.csv')},
        'density_weight_source_sha256': sha(args.archive/'output/reversal-E100/intermediate/model.npz'),
        'OpenDRT_package_sha256': sha(args.opendrt)}
    display, _ = display_processor(args.opendrt, args.output/'opendrt')
    sources, records = sources_and_samples(args.archive, (args.it8_spectral_zip, args.it8_reference_zip)
                                           if args.it8_spectral_zip else None)
    conditions = {'native_grid_preserved': True, 'processing_grid_nm': [400, 720, 10],
        'input': 'linear AP1/D60 after finite-band D65 Bradford adaptation',
        'observer': 'CIE1931 2 degree', 'input_kernel': kernel.tolist(),
        'exposure_EVs': [-2, 0, 2],
        'input_colorimetry_sources': {name: sha(args.archive.parent/'data'/name) for name in
                                     ('CIE_xyz_official.csv', 'CIE_std_illum_D65.csv')},
        'source_splits': SPLITS, 'quality': 'values outside [0,1] retained and excluded from bounded fit',
        'validation_scope': 'Earlier development scenes; no claim of a fresh final blind test or real-film accuracy'}
    result = {'schema': 'softloaf.sampling-build/1',
        'versions': {'numpy': np.__version__, 'scipy': scipy.__version__, 'colour': colour.__version__},
        'code_hashes': {p.name: sha(p) for p in (Path(__file__), Path('spectral_lut/sampling_db.py'),
            Path('spectral_lut/reconstruction.py'), Path('spectral_lut/film.py'), Path('spectral_lut/reference.py'),
            Path('spectral_lut/metrics.py'), Path('experiments/hsi_raw_lut.py'),
            Path('experiments/sampling_database_study.py'), Path('experiments/validate_it8_data.py'))},
        'conditions': conditions, 'reversal_reference_settings': reference_settings, 'families': {}, 'trials': []}
    model_data = {}
    for family in ('reversal', 'negative'):
        print('Building database:', family, flush=True)
        status = 'E100_local_reference' if family == 'reversal' else 'APD_output_unimplemented'
        path = args.output/(family+'.sqlite')
        with SamplingDatabase.create(path, family, family_conditions(family, conditions, reference_settings)) as db:
            for identifier, source in sources.items():
                db.add_source(identifier, source)
            db.add_source('synthetic_tv', {'quantity': 'synthetic_reflectance', 'unit': '1',
                'method': 'minimize total variation; RGB equality, [0,1] bounds, second difference <=.025',
                'rights': 'locally generated; upstream dependency review remains applicable'})
            for record in records:
                db.add_spectrum(SpectrumRecord(family+'/'+record.identifier, record.source_id, record.group,
                                                record.split, record.kind, record.wavelengths, record.values))
            identifiers, groups, eligible, spectra = arrays(db, 'fit')
            identifiers = np.asarray(identifiers)[eligible]
            groups = np.asarray(groups)[eligible]
            spectra = spectra[eligible]
            rgb = spectra @ kernel
            lab = colour.XYZ_to_Lab(rgb @ AP1.matrix_RGB_to_XYZ.T, AP1.whitepoint)
            features = lab / np.maximum(np.ptp(lab, axis=0), 1e-8)
            if family == 'negative':
                # A separate, explicitly input-only selection until a real
                # negative output exists. Do not optimize against E100 labels.
                _, _, axes = np.linalg.svd(spectra-spectra.mean(axis=0), full_matrices=False)
                scores = spectra @ axes[:4].T
                scales = np.maximum(np.std(scores, axis=0), .02)
                features = np.column_stack((features/np.sqrt(3), scores/scales/np.sqrt(4)))
            start = int(np.argmin(np.linalg.norm(rgb-.18, axis=1)))
            selected = farthest_points(features, max(args.budgets), start)
            for budget in args.budgets:
                db.set_selection(f'coverage_{budget}', identifiers[selected[:budget]].tolist(),
                    {'method': 'Lab maximin' if family == 'reversal' else 'Lab + four spectral PCs; scale floor .02',
                     'budget': budget, 'output_tuned': False})
            unique_groups, group_sizes = np.unique(groups, return_counts=True)
            lookup = dict(zip(unique_groups, group_sizes))
            db.set_selection('all_source_balanced', identifiers.tolist(), {'method': 'inverse source-group count; not natural frequency'}, [1/lookup[g] for g in groups])
            synthetic = make_synthetic(db, family, kernel, args.synthetic_targets)
            synthetic['metamers'] = add_metamer_groups(db, family, kernel, film)
            _, _, _, dev = arrays(db, 'dev')
            _, _, audit_eligible, audit_spectra = arrays(db, 'audit')
            model_data[family] = (identifiers, groups, spectra, selected, dev, audit_spectra, audit_eligible)
            if family == 'reversal':
                for identifier, in db.connection.execute('SELECT id FROM spectra').fetchall():
                    value = db.spectrum(identifier).on_grid(GRID)
                    db.add_output(identifier, family, 'relative_viewed_XYZ_D65', film.evaluate(value).tolist(),
                                  {'exposure_ev': 0, 'reference': 'E100 D50/1931-2deg, gain1.8; finite-band model'})
            db.set_metadata('synthetic_summary', synthetic)
            db.set_metadata('readiness', 'input_database_built; ' + status)
            counts = db.audit()
            result['families'][family] = {'database': path.name, 'counts': counts, 'output_status': status,
                                          'synthetic': synthetic, 'eligible_fit_samples': len(spectra)}
        with SamplingDatabase.open(path, family) as reopened:
            assert reopened.audit() == counts
    identifiers, groups, spectra, selection, dev, audit_spectra, audit_eligible = model_data['reversal']
    candidates, models = candidate_priors(spectra, selection, groups, kernel, args.budgets)
    for name, reconstruct in candidates.items():
        check = evaluate(reconstruct, dev, film, kernel, display)
        result['trials'].append({'name': name, 'dev': check})
        print('Dev:', name, check['fraction_within_2_codes_float'], check['mean_pixel_max_code_float'], flush=True)
    winner = min(result['trials'], key=lambda t: (t['dev']['mean_pixel_max_code_float'], t['dev']['p95_pixel_max_code_float']))['name']
    result['selection_rule'] = 'minimum development mean pixel-maximum absolute display code error, then P95; no audit selection'
    result['selected_model'] = winner
    for name in ('smooth_baseline', winner):
        result.setdefault('audit', {})[name] = {'all': evaluate(candidates[name], audit_spectra, film, kernel, display),
                                               'bounded_subset': evaluate(candidates[name], audit_spectra[audit_eligible], film, kernel, display)}
    model_dir = args.output/'models'; model_dir.mkdir()
    def save_model(name, family, candidates, models, training, selected):
        path = model_dir/(family+'.npz')
        probe = model_data[family][4][:16] @ kernel
        if name in models:
            models[name].save(path, family=family)
            restored = (RootPolynomialPrior if name.startswith('root') else LocalSpectralPrior).load(path, family=family)
            np.testing.assert_array_equal(restored.reconstruct(probe), candidates[name](probe))
        else:
            basis = smooth_reconstruction_basis(kernel) if name == 'smooth_baseline' else global_spectral_basis(training[selected[:int(name.split('_')[1])]], kernel)
            np.savez_compressed(path, basis=basis, family=family, schema='softloaf.linear-spectral-prior/1')
            with np.load(path, allow_pickle=False) as saved:
                assert str(saved['family']) == family
                np.testing.assert_allclose(np.maximum(probe @ saved['basis'], 0), candidates[name](probe), atol=1e-14)
        return {'file': str(path.relative_to(args.output)), 'sha256': sha(path), 'name': name}
    result['families']['reversal']['model'] = save_model(winner, 'reversal', candidates, models, spectra, selection)
    n_ids, n_groups, n_spectra, n_selection, n_dev, n_audit, n_eligible = model_data['negative']
    n_candidates, n_models = candidate_priors(n_spectra, n_selection, n_groups, kernel, args.budgets)
    n_trials = []
    for name, reconstruct in n_candidates.items():
        check = spectral_evaluate(reconstruct, n_dev, kernel)
        n_trials.append({'name': name, 'dev': check})
        print('Negative input dev:', name, check['mean_spectral_RMSE'], flush=True)
    n_winner = min(n_trials, key=lambda t: (t['dev']['mean_spectral_RMSE'], t['dev']['p95_spectral_RMSE']))['name']
    result['negative_input_trials'] = n_trials
    result['families']['negative']['model'] = save_model(n_winner, 'negative', n_candidates, n_models, n_spectra, n_selection)
    result['negative_input_audit'] = {name: spectral_evaluate(n_candidates[name], n_audit, kernel) for name in ('smooth_baseline', n_winner)}
    result['negative_selection_rule'] = 'minimum development input-spectral RMSE; never use E100 or APD/display labels'
    for family, chosen in (('reversal', winner), ('negative', n_winner)):
        with SamplingDatabase(args.output/(family+'.sqlite'), sqlite3.connect(args.output/(family+'.sqlite'))) as db:
            assert db.metadata('family') == family
            db.set_metadata('selected_input_model', result['families'][family]['model'])
            db.set_metadata('selection_objective', result['selection_rule'] if family == 'reversal' else result['negative_selection_rule'])
            db.set_metadata('optimization_scope', 'E100 local-reference development' if family == 'reversal' else 'input-spectrum reconstruction; no APD output')
            db.audit()
    result['LUTs'] = []
    for model_name in dict.fromkeys(('smooth_baseline', winner)):
        for size in args.grids:
            transform = lambda rgb: film.evaluate(candidates[model_name](rgb))
            path = args.output/(f'reversal_{size}.cube' if model_name == winner else f'reversal_baseline_{size}.cube')
            cube, processor = bake_cube(transform, size, path)
            floats, rounded, totals_f, totals_u = [], [], [], []
            readback_max = 0.
            outside_domain = 0
            for ev in (-2, 0, 2):
                signal = audit_spectra * 2.**ev
                rgb = signal @ kernel
                points = acescct_encode(rgb)
                outside_domain += int(np.count_nonzero(np.any((points < -.25) | (points > .75), axis=1)))
                continuous = apply_ocio(display, transform(rgb))
                xyz = apply_ocio(processor, points)
                readback_max = max(readback_max, float(np.max(np.abs(xyz-cube.apply(points)))))
                output = apply_ocio(display, xyz)
                reference = apply_ocio(display, film.evaluate(signal))
                _, f, u = srgb_code_error(output, continuous); floats.append(f); rounded.append(u)
                _, f, u = srgb_code_error(output, reference); totals_f.append(f); totals_u.append(u)
            result['LUTs'].append({'family': 'reversal', 'model': model_name, 'edge': size, 'file': path.name, 'sha256': sha(path),
                'bytes': path.stat().st_size, 'independent_readback_XYZ_max_abs': readback_max,
                'outside_domain_samples': outside_domain, 'interpolation_method': 'tetrahedral',
                'interpolation': summarize_code_errors(np.concatenate(floats), np.concatenate(rounded)),
                'total': summarize_code_errors(np.concatenate(totals_f), np.concatenate(totals_u)),
                'input': 'ACEScct AP1/D60 [-.25,.75]', 'output': 'relative viewed XYZ D65; OpenDRT separate'})
            print('LUT:', size, result['LUTs'][-1]['interpolation']['fraction_within_2_codes_float'], flush=True)
    for family in ('reversal', 'negative'):
        result['families'][family]['sha256'] = sha(args.output/(family+'.sqlite'))
    result['limits'] = ['Negative input database only: no APD/ADX-to-ACES or negative image-error claims.',
                         'No real-film validation; finite 400-720nm processing coverage.',
                         'Audit scenes were previously used for development; not a fresh final blind test.',
                         'Data and model distribution remain subject to source-specific review.']
    write_json(args.output/'report.json', result)
    print('Selected:', winner, flush=True)


if __name__ == '__main__':
    main()
