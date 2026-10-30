from pathlib import Path
import json
import copy
import threading
import zipfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pytest

from experiments.gui_recipe_server import E100Model, RecipeError, Workbench, make_server, template, validate_recipe
from spectral_lut.reference import Cube, acescct_decode


@pytest.fixture(scope='module')
def model(tmp_path_factory):
    archive = Path('local/film-color-slides/hyperspectral-demo')
    opendrt = Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists() or not opendrt.exists():
        pytest.skip('Optional local spectral inputs are not supplied.')
    return E100Model(archive, opendrt, tmp_path_factory.mktemp('gui-recipe-model'))


def test_viewing_light_changes_viewed_spectrum_but_not_developed_film(model):
    d50 = model.sample([0.18, 0.12, 0.08], viewing_light='D50')
    d65 = model.sample([0.18, 0.12, 0.08], viewing_light='D65')
    np.testing.assert_array_equal(d50['transmission'], d65['transmission'])
    np.testing.assert_array_equal(d50['dye_amounts'], d65['dye_amounts'])
    assert not np.allclose(d50['viewed_spectrum'], d65['viewed_spectrum'])
    assert not np.allclose(d50['XYZ'], d65['XYZ'])


def test_positive_recipe_exposure_increases_reversal_transmission(model):
    base = model.sample([0.18]*3)
    changed = model.sample([0.18]*3, exposure_ev=0.5)
    assert np.all(changed['transmission'] >= base['transmission']-1e-13)
    assert np.any(changed['transmission'] > base['transmission']+1e-5)
    assert changed['XYZ'][1] > base['XYZ'][1]


def test_view_gain_is_a_declared_viewing_scale_and_does_not_change_film(model):
    base = model.sample([0.18]*3, viewing_gain=1)
    doubled = model.sample([0.18]*3, viewing_gain=2)
    np.testing.assert_array_equal(base['transmission'], doubled['transmission'])
    np.testing.assert_allclose(doubled['XYZ'], 2*base['XYZ'], rtol=1e-13)


def test_actual_opendrt_presets_change_display_without_changing_XYZ(model):
    default = model.sample([0.32, 0.14, 0.06], display='Default')
    umbra = model.sample([0.32, 0.14, 0.06], display='Umbra')
    np.testing.assert_array_equal(default['XYZ'], umbra['XYZ'])
    assert not np.allclose(default['sRGB'], umbra['sRGB'], atol=1e-4)


def test_validation_rejects_conflicting_or_incomplete_custom_spd():
    recipe = template()
    recipe['viewing']['custom_spd'] = {'name': 'test', 'source': 'measurement',
        'quantity': 'relative_energy_spd', 'unit': 'relative',
        'wavelengths_nm': [400, 550, 700], 'values': [1, 2, 1]}
    assert not validate_recipe(recipe)['ok']
    recipe['viewing']['illuminant'] = 'custom'
    assert validate_recipe(recipe)['ok']
    recipe['viewing']['custom_spd']['wavelengths_nm'] = [410, 550, 700]
    assert not validate_recipe(recipe)['ok']


def test_known_5207_is_savable_draft_but_not_computable():
    result = validate_recipe(template('negative'))
    assert result['ok'] and not result['computable']
    assert result['normalized_recipe']['film']['stock'] == '5207'


def test_negative_template_is_apd_draft_without_capture_dependencies(model):
    recipe = template('negative')
    output = recipe['negative_output']
    assert recipe['name'] == '5207 · APD 草案'
    assert output['metric'] == 'APD' and output['value_type'] == 'float_density'
    assert output['base_density'] is None and output['spectral_weights'] is None
    assert output['standard_conversion']['version'] is None
    assert output['standard_conversion']['status'] == 'unimplemented'
    bootstrap = Workbench(model).bootstrap()
    capability = next(r for r in bootstrap['capabilities']['routes'] if r['id'] == 'negative')
    assert not capability['computable'] and capability['density_metric'] == 'APD'
    with pytest.raises(RecipeError, match='APD'):
        Workbench(model).evaluate({'recipe': recipe})
    with pytest.raises(RecipeError, match='APD'):
        Workbench(model).export({'recipe': recipe, 'purpose': 'pipeline'})


def test_unconfigured_legacy_negative_can_remain_apd_draft():
    recipe = template('negative')
    recipe.pop('negative_output')
    result = validate_recipe(recipe)
    assert result['ok'] and not result['computable']
    assert result['normalized_recipe']['negative_output']['metric'] == 'APD'


def test_configured_capture_recipe_is_not_silently_reinterpreted_as_apd(model):
    recipe = template('negative')
    recipe['digitization']['light'] = 'old capture light'
    recipe['digitization']['calibration'] = {'matrix': [1, 0, 0]}
    with pytest.raises(RecipeError) as error:
        model.validate(recipe)
    assert error.value.code == 'legacy_digitization'
    assert error.value.issues[0]['field'] == 'digitization'


def test_modified_density_weights_cannot_keep_standard_apd_name():
    recipe = template('negative')
    recipe['negative_output']['spectral_weights'] = {'R': [1, 2, 3]}
    result = validate_recipe(recipe)
    assert not result['ok']
    assert any(issue['field'] == 'negative_output' for issue in result['issues'])


def test_preview_and_baseline_use_identical_current_input(model):
    app = Workbench(model)
    recipe = template()
    baseline = template()
    baseline['film']['exposure_ev'] = -.5
    response = app.evaluate({'recipe': recipe, 'baseline': baseline,
        'input': {'id': 'chart', 'exposure_ev': .5}, 'selection': {'sample_id': 'gray18'}})
    assert response['ok']
    np.testing.assert_array_equal(response['current']['sample']['input_ap1'], response['baseline']['sample']['input_ap1'])
    assert response['current']['preview']['data_url'].startswith('data:image/png;base64,')
    assert set(response['current']['nodes']) == {'estimate', 'light', 'film', 'view', 'interface', 'display'}
    assert response['version']['fingerprint'] != response['baseline_version']['fingerprint']
    second = app.evaluate({'recipe': recipe, 'input': {'id': 'chart', 'exposure_ev': 0},
                           'selection': {'sample_id': 'gray18'}})
    assert response['version'] == second['version']


def test_input_exposure_is_not_part_of_export_recipe(model):
    app = Workbench(model)
    with pytest.raises(RecipeError, match='输入曝光'):
        app.export({'recipe': template(), 'purpose': 'display', 'input': {'exposure_ev': 1}})


def test_source_mismatch_does_not_fall_back_to_local_material(model):
    recipe = template()
    recipe['asset_refs'] = {'model': 'wrong'}
    result = validate_recipe(recipe, model.source_refs)
    assert not result['ok'] and not result['computable']


def test_http_whitelist_and_mutation_origin(model, tmp_path):
    ui = tmp_path/'index.html'
    ui.write_text('<title>workbench</title>')
    (tmp_path/'spectral-editor.js').write_text('window.spectralEditor = true;')
    server = make_server(Workbench(model), ui, None, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        assert urlopen(base+'/').read() == b'<title>workbench</title>'
        assert urlopen(base+'/assets/spectral-editor.js').read() == b'window.spectralEditor = true;'
        with pytest.raises(HTTPError) as error:
            urlopen(base+'/README.md')
        assert error.value.code == 404
        payload = json.dumps({'recipe': template()}).encode()
        request = Request(base+'/api/validate', data=payload, headers={'Content-Type': 'application/json', 'Origin': 'https://example.com'})
        with pytest.raises(HTTPError) as error:
            urlopen(request)
        assert error.value.code == 403
        request = Request(base+'/api/validate', data=payload, headers={'Content-Type': 'application/json', 'Origin': base})
        response = json.load(urlopen(request))
        assert response['ok'] and response['computable']
        assert response['normalized_recipe']['asset_refs'] == model.source_refs
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_default_d50_matches_existing_float64_reference(model):
    rgb = np.array([[.18, .12, .08], [.02, .04, .2]])
    reflectance = np.maximum(rgb@model.basis, 0)
    np.testing.assert_allclose(model.sample(rgb)['XYZ'], model.film.evaluate(reflectance), rtol=2e-14, atol=1e-15)


def test_custom_samples_remain_complete_and_scale_cancels_y_normalization(model):
    recipe = template()
    source = {'name': 'constant light', 'source': 'test measurement',
        'quantity': 'relative_energy_spd', 'unit': 'a.u.',
        'wavelengths_nm': [380, 400, 512, 600, 700, 780], 'values': [1, 1, 1, 1, 1, 1]}
    recipe['viewing'] = {'illuminant': 'custom', 'gain': 1.8, 'custom_spd': source}
    normalized = model.validate(recipe)['normalized_recipe']
    assert normalized['viewing']['custom_spd'] == source
    original = model.sample([.18]*3, viewing_light=source)
    scaled = dict(source, values=[2]*6)
    doubled = model.sample([.18]*3, viewing_light=scaled)
    np.testing.assert_array_equal(original['transmission'], doubled['transmission'])
    np.testing.assert_allclose(original['XYZ'], doubled['XYZ'], atol=1e-14)


def test_custom_spd_values_must_be_numbers_not_coerced_strings():
    recipe = template()
    recipe['viewing'] = {'illuminant': 'custom', 'gain': 1.8, 'custom_spd': {
        'name': 'bad', 'source': 'test', 'quantity': 'relative_energy_spd', 'unit': 'relative',
        'wavelengths_nm': [400, 700], 'values': ['1', '1']}}
    assert not validate_recipe(recipe)['ok']


@pytest.mark.parametrize('purpose', ['internal', 'display', 'pipeline'])
def test_real_65_export_freezes_recipe_and_reports_quality_without_blocking_download(model, purpose):
    app = Workbench(model)
    recipe = template()
    recipe['display']['view']='Default'  # This test exercises the packaged OpenDRT CTF.
    result = app.export({'recipe': recipe, 'purpose': purpose, 'request_id': 'test'})
    export_path = model.output/'exports'/result['export_id']
    frozen_recipe = json.loads((export_path/'recipe.json').read_text())
    manifest = json.loads((export_path/'manifest.json').read_text())
    header = (export_path/'recipe.cube').read_text().split('LUT_3D_SIZE', 1)[0]
    assert 'SoftLoaf Spectral' in header and 'Yangming Feng' in header
    assert 'TITLE ' in header and recipe['name'] in header
    assert 'ACEScct' in header and 'AP1' in header and 'D60' in header
    assert result['frozen']['fingerprint'] in header
    assert ('Includes display: yes' in header) == (purpose == 'display')
    assert ('relative XYZ D65' in header) == (purpose != 'display')
    assert manifest['application']['author'] == 'Yangming Feng and contributors'
    if purpose == 'pipeline':
        ctf = (export_path/'recipe.ctf').read_text()
        assert 'SoftLoaf Spectral' in ctf and 'Yangming Feng' in ctf
        assert 'Output: sRGB encoded RGB / D65' in ctf
        assert 'Includes display: yes' in ctf
    assert frozen_recipe['film']['exposure_ev'] == 0
    assert 'input_exposure_ev' not in frozen_recipe
    assert manifest['purpose'] == purpose
    assert manifest['frozen'] == result['frozen']
    assert result['verification']['readback_exact']
    assert result['verification']['ocio_vs_float64_max_abs_output'] < 2e-5
    assert result['ok'] and result['verification']['integrity_passed']
    if result['ok']:
        count = 6 if purpose == 'pipeline' else 4
        assert len(app.downloads) == count
        assert len(result['files']) == count
        if purpose == 'pipeline':
            assert (export_path/'recipe.ctf').is_file()
            assert 'MIT License' in (export_path/'OpenDRT-LICENSE.md').read_text()
            assert result['verification']['pipeline_vs_material_display_max_abs'] < 2e-5
            assert manifest['output']['includes_display']
            with zipfile.ZipFile(export_path/'recipe.zip') as bundle:
                assert set(bundle.namelist()) == {'recipe.cube', 'recipe.json', 'manifest.json', 'recipe.ctf', 'OpenDRT-LICENSE.md'}
                for name in bundle.namelist():
                    data = bundle.read(name)
                    assert data == (export_path/name).read_bytes()
                    assert b'/Users/' not in data and b'/Volumes/' not in data


def test_selected_grid_is_written_and_quality_failure_remains_downloadable(model):
    app = Workbench(model)
    result = app.export({'recipe': template(), 'purpose': 'display', 'grid': 17})
    directory = model.output/'exports'/result['export_id']
    cube = Cube.read(directory/'recipe.cube')
    assert cube.table.shape == (17, 17, 17, 3)
    assert result['ok'] and result['verification']['integrity_passed']
    assert result['verification']['grid'] == 17
    assert not result['verification']['accepted']
    assert result['warnings'][0]['code'] == 'quality_reference_missed'
    assert any(f['name'] == 'recipe.zip' for f in result['files'])


@pytest.mark.parametrize('grid', [1, 130, 33.5, True, '33'])
def test_export_rejects_invalid_grid_before_building(model, grid):
    with pytest.raises(RecipeError) as error:
        Workbench(model).export({'recipe': template(), 'purpose': 'internal', 'grid': grid})
    assert error.value.code == 'invalid_grid'


def custom_recipe(model):
    recipe = template()
    recipe['film']['custom_material'] = copy.deepcopy(Workbench(model).bootstrap()['spectral_assets']['E100'])
    recipe['film']['custom_material']['name'] = '自定义（基于 E100）'
    recipe['film']['custom_material']['source'] = 'Local user adjustment of archived E100 data'
    return recipe


def test_bootstrap_provides_complete_local_spectral_sources(model):
    assets = Workbench(model).bootstrap()['spectral_assets']
    assert assets['E100']['schema'] == 'softloaf.material/1'
    assert set(assets['E100']['sensitivity']['channels']) == {'R', 'G', 'B'}
    assert len(assets['E100']['characteristic']['log_exposure']) == 241
    assert set(assets['E100']['dyes']['channels']) == {'C', 'M', 'Y'}
    for light in assets['viewing_lights'].values():
        assert light['wavelengths_nm'][0] <= 400 and light['wavelengths_nm'][-1] >= 700
        assert len(light['values']) == len(light['wavelengths_nm'])


def test_custom_sensitivity_amplitude_is_not_normalized_away(model):
    recipe = custom_recipe(model)
    base = model.sample([.18, .12, .08])
    sensitivity = recipe['film']['custom_material']['sensitivity']['channels']
    sensitivity['R'] = (np.array(sensitivity['R'])*2).tolist()
    normalized = model.validate(recipe, compute=True)['normalized_recipe']
    changed = model.sample([.18, .12, .08], **model.parameters(normalized))
    np.testing.assert_allclose(changed['exposure'], base['exposure']*[2, 1, 1], rtol=2e-13)
    assert not np.allclose(changed['transmission'], base['transmission'])
    np.testing.assert_array_equal(changed['reflectance'], base['reflectance'])


def test_custom_density_model_recalculates_fit_and_anchor_and_preserves_samples(model):
    recipe = custom_recipe(model)
    material = recipe['film']['custom_material']
    material['characteristic']['channels']['R'] = (np.array(material['characteristic']['channels']['R'])+.05).tolist()
    result = model.validate(recipe, compute=True)
    assert result['normalized_recipe']['film']['custom_material'] == material
    changed = model.sample([.32, .14, .06], **model.parameters(result['normalized_recipe']))
    original = model.sample([.32, .14, .06])
    assert not np.allclose(changed['XYZ'], original['XYZ'])
    diagnostics = Workbench(model).evaluate({'recipe': recipe, 'input': {'id': 'chart'}})
    assert diagnostics['conditions']['material']['custom']
    assert diagnostics['conditions']['material']['neutral_StatusA_max_error_D'] <= .001
    assert diagnostics['current']['nodes']['film']['details']['material']['name'] == material['name']


@pytest.mark.parametrize('mutation', ['missing_channel', 'bad_units', 'increasing_density', 'incomplete_band', 'zero_sensitivity'])
def test_invalid_material_is_rejected_before_preview(model, mutation):
    recipe = custom_recipe(model)
    material = recipe['film']['custom_material']
    if mutation == 'missing_channel':
        del material['dyes']['channels']['C']
    elif mutation == 'bad_units':
        material['characteristic']['unit'] = 'nm'
    elif mutation == 'increasing_density':
        material['characteristic']['channels']['R'][1] = material['characteristic']['channels']['R'][0]+.1
    elif mutation == 'incomplete_band':
        material['sensitivity']['wavelengths_nm'][0] = 401
    else:
        material['sensitivity']['channels']['R'] = [0]*len(material['sensitivity']['wavelengths_nm'])
    with pytest.raises(RecipeError):
        model.validate(recipe, compute=True)


def test_incompatible_dyes_fail_refit_instead_of_using_original_amounts(model):
    recipe = custom_recipe(model)
    material = recipe['film']['custom_material']
    material['dyes']['channels'] = {key: [0]*len(material['dyes']['wavelengths_nm']) for key in ('C', 'M', 'Y')}
    with pytest.raises(RecipeError, match='拟合|密度|染料'):
        model.validate(recipe, compute=True)


def test_dye_spectral_shape_changes_real_output_after_compatible_refit(model):
    recipe = custom_recipe(model)
    dye = recipe['film']['custom_material']['dyes']
    wavelength = np.array(dye['wavelengths_nm'])
    dye['channels']['C'] = (np.array(dye['channels']['C'])*(1+.05*np.sin(wavelength/50))).tolist()
    normalized = model.validate(recipe, compute=True)['normalized_recipe']
    d50 = model.sample([.32, .14, .06], **model.parameters(normalized))
    default = model.sample([.32, .14, .06])
    assert not np.allclose(d50['XYZ'], default['XYZ'], atol=1e-7)
    params = model.parameters(normalized)
    params['viewing_light'] = 'D65'
    d65 = model.sample([.32, .14, .06], **params)
    np.testing.assert_array_equal(d50['transmission'], d65['transmission'])


def test_custom_material_cannot_invent_missing_gray_anchor(model):
    recipe = custom_recipe(model)
    characteristic = recipe['film']['custom_material']['characteristic']
    characteristic['channels'] = {key: [3.0]*len(characteristic['log_exposure']) for key in 'RGB'}
    with pytest.raises(RecipeError, match='锚点'):
        model.validate(recipe, compute=True)


def test_material_fit_cache_is_shared_by_concurrent_requests(model):
    from concurrent.futures import ThreadPoolExecutor
    material = custom_recipe(model)['film']['custom_material']
    material['name'] = 'concurrency cache check'
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: model.material(material), range(8)))
    assert all(result[0] is results[0][0] for result in results)
    assert len(model.material_cache) <= 16


def test_custom_material_is_frozen_and_baked_in_real_65_export(model):
    app = Workbench(model)
    recipe = custom_recipe(model)
    material = recipe['film']['custom_material']
    material['sensitivity']['channels']['R'] = (np.array(material['sensitivity']['channels']['R'])*1.02).tolist()
    result = app.export({'recipe': recipe, 'purpose': 'pipeline'})
    directory = model.output/'exports'/result['export_id']
    saved = json.loads((directory/'recipe.json').read_text())
    manifest = json.loads((directory/'manifest.json').read_text())
    assert saved['film']['custom_material'] == material
    assert manifest['conditions']['material']['custom']
    assert manifest['conditions']['material']['sensitivity_denominators'] == model.exposure_normalization.tolist()
    assert result['verification']['independent_ocio']['pixel_count'] > 0
    point = -.25+np.array([36, 40, 42])/64
    cube = Cube.read(directory/'recipe.cube')
    truth = model.sample(acescct_decode(point), **model.parameters(saved))['XYZ']
    np.testing.assert_allclose(cube.apply(point), truth, atol=1e-13)
    assert not np.allclose(truth, model.sample(acescct_decode(point))['XYZ'], atol=1e-7)
