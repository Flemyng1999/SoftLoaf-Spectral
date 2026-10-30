import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageCms
import pytest

from experiments.gui_recipe_server import E100Model, RecipeError, template


@pytest.fixture(scope='module')
def app(tmp_path_factory):
    from spectral_app.application import Application
    from spectral_lut.native import NativeCore
    archive = Path('local/film-color-slides/hyperspectral-demo')
    opendrt = Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists() or not opendrt.exists():
        pytest.skip('Optional local reference materials are not supplied.')
    return Application(E100Model(archive, opendrt, tmp_path_factory.mktemp('app'), core=NativeCore()))


def image_request(icc=None):
    pixels = np.array([[[128, 64, 32], [0, 255, 127]], [[1, 2, 3], [255, 255, 255]]], dtype=np.uint8)
    data = io.BytesIO()
    Image.fromarray(pixels).save(data, format='PNG', **({'icc_profile': icc} if icc else {}))
    return {'name': 'my photo.png', 'data_base64': base64.b64encode(data.getvalue()).decode()}, pixels


def test_import_and_export_keep_dimensions_recipe_and_declared_rgb_interpretation(app):
    request, pixels = image_request()
    imported = app.import_image(request)
    item = imported['input']
    assert (item['width'], item['height']) == (2, 2)
    assert item['interpretation']['assumed_srgb']
    assert item['interpretation']['scene_referred'] is False
    assert item['interpretation']['raw_development'] is False
    recipe = template()
    recipe['film']['exposure_ev'] = .5
    response = app.export_image({'recipe': recipe, 'input': {'id': item['id'], 'exposure_ev': .25}})
    assert response['ok'] and response['verification']['readback_exact']
    assert response['frozen']['revision'] == 1
    png = next(f for f in response['files'] if f['name'].endswith('.png'))
    path, _ = app.downloads[png['url']]
    with Image.open(path) as actual:
        assert actual.size == (2, 2) and actual.info['icc_profile']
        expected = app.model.sample(app.model.srgb_to_ap1(pixels/255)*np.exp2(.25), exposure_ev=.5)['sRGB']
        np.testing.assert_array_equal(np.array(actual), np.floor(expected*255+.5).astype(np.uint8))
    manifest_file = next(f for f in response['files'] if f['name'] == 'image.json')
    metadata = json.loads(app.downloads[manifest_file['url']][0].read_text())
    assert metadata['input']['interpretation']['scene_referred'] is False
    assert metadata['recipe']['film']['exposure_ev'] == .5
    assert metadata['conditions']['compute_backend'].startswith('C++')


def test_embedded_icc_is_converted_and_invalid_profile_not_ignored(app):
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    request, _ = image_request(profile)
    imported = app.import_image(request)
    assert not imported['input']['interpretation']['assumed_srgb']
    request, _ = image_request(b'invalid ICC bytes')
    with pytest.raises(RecipeError, match='ICC'):
        app.import_image(request)


def test_unknown_files_and_raw_do_not_acquire_an_srgb_assumption(app):
    with pytest.raises(RecipeError):
        app.import_image({'name': 'camera.dng', 'data_base64': base64.b64encode(b'not a PNG or JPEG').decode()})
    with pytest.raises(RecipeError):
        app.import_image({'name': 'image.png', 'data_base64': 'malformed'})
    with pytest.raises(RecipeError):
        app.export_image({'recipe': template(), 'input': {'id': '../../source'}})
    with pytest.raises(RecipeError):
        app.export_image({'recipe': template('negative'), 'input': {'id': 'chart'}})


def test_restart_restores_imported_inputs_without_leaking_paths(app):
    from spectral_app.application import Application
    request, _ = image_request()
    identifier = app.import_image(request)['input']['id']
    restarted = Application(app.model)
    bootstrap = restarted.bootstrap()
    assert identifier in restarted.model.inputs
    assert identifier in {item['id'] for item in bootstrap['inputs']}
    assert str(app.model.output) not in json.dumps(bootstrap)
    assert bootstrap['capabilities']['raw_supported'] is (restarted.raw_engine.cli is not None)


def test_native_lut_export_checks_python_and_ocio_readback_separately(app):
    result = app.export({'recipe': template(), 'purpose': 'pipeline', 'grid': 17})
    assert result['ok'] and result['verification']['integrity_passed']
    assert result['verification']['native_vs_python_max_abs_output'] < 2e-12
    ctf = next(file for file in result['files'] if file['name'] == 'recipe.ctf')
    assert app.downloads[ctf['url']][0].is_file()


def test_session_recovers_applied_material_and_refuses_stale_overwrites(app):
    from spectral_app.application import Application
    recipe = template()
    recipe['film']['exposure_ev'] = .75
    baseline = template()
    state = {'documents': [{'recipe': recipe, 'baseline': baseline}], 'active_id': recipe['id']}
    saved = app.save_session({'expected_revision': 0, 'session': state})
    assert saved['revision'] == 1
    restored = Application(app.model).bootstrap()
    assert restored['session']['documents'][0]['recipe']['film']['exposure_ev'] == .75
    assert restored['session']['documents'][0]['baseline']['film']['exposure_ev'] == 0
    with pytest.raises(RecipeError, match='另一'):
        app.save_session({'expected_revision': 0, 'session': state})
    state['documents'][0]['recipe']['film']['exposure_ev'] = 20
    with pytest.raises(RecipeError):
        app.save_session({'expected_revision': 1, 'session': state})
    assert Application(app.model).bootstrap()['session_revision'] == 1


def test_deleted_recipe_and_empty_workspace_survive_restart_without_resetting_templates(app,tmp_path):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;app=Application(model)
    recipe=template();recipe['film']['exposure_ev']=.75
    deleted={'id':'deletion-1','index':0,'document':{'recipe':recipe,'baseline':None}}
    state={'documents':[],'active_id':None,'deleted_documents':[deleted]}
    saved=app.save_session({'expected_revision':0,'session':state})
    assert saved['ok']
    restored=Application(app.model).bootstrap()['session']
    assert restored['documents']==[] and restored['active_id'] is None
    assert restored['deleted_documents'][0]['document']['recipe']['film']['exposure_ev']==.75
    assert restored['deleted_documents'][0]['index']==0


def test_deleted_recipe_records_are_validated_before_overwriting_workspace(app,tmp_path):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;app=Application(model)
    state={'documents':[],'active_id':None,'deleted_documents':[{'id':'x','index':0,
        'document':{'recipe':template(),'baseline':None}}]}
    app.save_session({'expected_revision':0,'session':state})
    state['deleted_documents'][0]['document']['recipe']['film']['exposure_ev']=99
    with pytest.raises(RecipeError):app.save_session({'expected_revision':1,'session':state})
    assert json.loads((app.model.output/'workspace.json').read_text())['revision']==1


def test_batch_export_freezes_one_recipe_and_keeps_each_images_exposure_and_profile(app,tmp_path):
    from spectral_app.application import Application
    import zipfile
    model=copy.copy(app.model);model.output=tmp_path;batch=Application(model)
    source=[]
    for index,color in enumerate([(128,64,32),(30,170,90)]):
        data=io.BytesIO();Image.new('RGB',(3+index,2),color).save(data,format='PNG')
        item=batch.import_image({'name':'same-name.png','data_base64':base64.b64encode(data.getvalue()).decode()})['input']
        assert item.get('thumbnail','').startswith('data:image/png;base64,')
        source.append({'id':item['id'],'exposure_ev':index*.5})
    r=template();r['revision']=8;r['display']['target']='Display P3'
    result=batch.export_images({'recipe':r,'inputs':source})
    assert result['ok'] and result['succeeded']==2 and result['failed']==0
    archive=batch.downloads[result['files'][0]['url']][0]
    with zipfile.ZipFile(archive) as z:
        report=json.loads(z.read('manifest.json'));assert report['frozen']['revision']==8
        assert [i['input']['exposure_ev'] for i in report['images']]==[0,.5]
        names=[i['file'] for i in report['images']];assert len(set(names))==2
        for index,name in enumerate(names):
            assert not name.startswith('/') and '..' not in name
            with Image.open(io.BytesIO(z.read(name))) as image:
                assert image.size==(3+index,2)
                assert image.info['icc_profile']==model.display_profile('Display P3')
        assert json.loads(z.read('recipe.json'))['revision']==8


def test_batch_export_reports_bad_source_and_still_exports_other_images(app,tmp_path):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;batch=Application(model)
    req,_=image_request();a=batch.import_image(req)['input']
    data=io.BytesIO();Image.new('RGB',(1,1),(42,51,60)).save(data,format='PNG')
    b=batch.import_image({'name':'good.png','data_base64':base64.b64encode(data.getvalue()).decode()})['input']
    (batch.import_directory/(a['id']+'.source')).write_bytes(b'changed')
    result=batch.export_images({'recipe':template(),'inputs':[{'id':a['id']},{'id':b['id']}]})
    assert result['ok'] and result['succeeded']==1 and result['failed']==1
    assert result['errors'][0]['id']==a['id']


def test_photo_queue_exposures_and_order_survive_workspace_restart(app,tmp_path):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;photo=Application(model)
    req,_=image_request();item=photo.import_image(req)['input'];r=template()
    state={'documents':[{'recipe':r,'baseline':None}],'active_id':r['id'],
        'photo_workspace':{'order':[item['id']],'active_input_id':item['id'],'exposures':{item['id']:.6}}}
    photo.save_session({'session':state,'expected_revision':0})
    restored=Application(model).bootstrap()['session']
    assert restored['photo_workspace']==state['photo_workspace']
    state['photo_workspace']['exposures'][item['id']]=99
    with pytest.raises(RecipeError):photo.save_session({'session':state,'expected_revision':1})


def test_startup_check_lists_incomplete_materials_without_starting_a_service(tmp_path):
    material = tmp_path/'archive/output/reversal-E100/data'
    material.mkdir(parents=True)
    (material/'E100_dye_density_CMY.csv').write_text('incomplete fixture')
    ready = tmp_path/'ready.json'
    process = subprocess.run([sys.executable, '-m', 'spectral_app', '--check',
        '--archive', str(tmp_path/'archive'), '--opendrt', str(tmp_path/'missing.zip'),
        '--ready-file', str(ready)], capture_output=True, text=True)
    report = json.loads(process.stdout)
    assert process.returncode == 2 and not ready.exists()
    assert any('characteristic' in item for item in report['missing'])
    assert any('OpenDRT' in item for item in report['missing'])


def test_separate_application_instances_cannot_overwrite_a_newer_workspace(app, tmp_path):
    from spectral_app.application import Application
    model = copy.copy(app.model)
    model.output = tmp_path
    first, stale = Application(model), Application(model)
    state = {'documents': [{'recipe': template(), 'baseline': None}], 'active_id': 'slide-default'}
    first.save_session({'expected_revision': 0, 'session': state})
    with pytest.raises(RecipeError, match='另一'):
        stale.save_session({'expected_revision': 0, 'session': state})


def test_reference_a_is_original_spectral_scene_and_ignores_film_and_display(app):
    if 'scene43_rgb' not in app.model.inputs:
        pytest.skip('Optional hyperspectral scene is not supplied.')
    request = {'recipe': template(), 'input': {'id': 'scene43_rgb', 'exposure_ev': 0},
               'selection': {'x': .37, 'y': .61}}
    original = app.evaluate(request)
    changed = copy.deepcopy(request)
    changed['recipe']['film']['exposure_ev'] = 2
    changed['recipe']['viewing'] = {'illuminant': 'D65', 'gain': 4}
    changed['recipe']['display']['view'] = 'Umbra'
    changed['baseline'] = changed['recipe']
    result = app.evaluate(changed)
    assert result['baseline'] is None
    assert result['reference']['method'] == 'spectral_XYZ_to_sRGB'
    assert result['reference']['preview']['data_url'] == original['reference']['preview']['data_url']
    assert result['reference']['includes_film'] is False
    assert result['reference']['includes_opendrt'] is False
    assert result['current']['preview']['data_url'] != original['current']['preview']['data_url']


def test_reference_rgb_fallback_does_not_claim_measured_spectrum(app):
    request,pixels=image_request()
    identifier=app.import_image(request)['input']['id']
    response = app.evaluate({'recipe': template(), 'input': {'id': identifier, 'exposure_ev': 0}, 'selection':{'x':0,'y':0}})
    reference = response['reference']
    assert reference['method'] == 'characterized_RGB_XYZ_to_sRGB'
    assert not reference['has_measured_spectrum']
    expected = pixels[0,0]/255
    # The existing RGB import bridge uses Colour's rounded sRGB matrix.
    np.testing.assert_allclose(reference['sample']['srgb'], expected, atol=1e-4)


def test_reference_display_uses_standard_srgb_toe_and_matrix(app):
    import colour
    from experiments.hsi_raw_lut import apply_ocio
    linear = np.array([[0, .001, .0031308], [.18, .5, 1]])
    matrix = colour.normalised_primary_matrix([[.64,.33],[.3,.6],[.15,.06]], [.3127,.329])
    expected = np.where(linear <= .0031308, linear*12.92, 1.055*linear**(1/2.4)-.055)
    actual = apply_ocio(app.reference_processor, linear @ matrix.T)
    # OCIO's built-in CPU transform uses its fitted sRGB toe and float32 fast
    # powers. 1e-5 is <0.003 of one 8-bit code, well below image comparisons.
    np.testing.assert_allclose(actual, expected, atol=1e-5, rtol=0)


def test_reference_preview_stays_identical_across_icc_creation_times(app):
    request = {'recipe': template(), 'input': {'id': 'chart', 'exposure_ev': 0}}
    first = app.evaluate(request)['reference']['preview']['data_url']
    # LittleCMS stamps generated ICC profiles with wall-clock creation seconds.
    # A must not be replaced just because a B edit occurs in a different second.
    time.sleep(1.1)
    request['recipe']['film']['exposure_ev'] = .5
    second = app.evaluate(request)['reference']['preview']['data_url']
    assert first == second


def test_colour_24_chart_is_spectral_and_is_the_only_chart_in_ui(app):
    bootstrap=app.bootstrap()
    assert len(bootstrap['samples'])==24
    assert bootstrap['chart_layout']=={'rows':4,'columns':6}
    assert 'softloaf-first-image.png' not in {i['name'] for i in bootstrap['inputs']}
    assert bootstrap['capabilities']['image_import']
    result=app.evaluate({'recipe':template(),'input':{'id':'chart'},'selection':{'sample_id':'cc24'}})
    assert result['reference']['has_measured_spectrum']
    assert result['current']['preview']['width']==384


def test_xyz_observer_reference_is_the_same_cie_functions_used_for_viewing(app):
    observer=app.bootstrap()['spectral_assets']['xyz_observer']
    assert observer['quantity']=='cie1931_xyz_matching_functions'
    assert [s['name'] for s in observer['series']]==['X','Y','Z']
    np.testing.assert_array_equal(observer['wavelengths_nm'],app.model.view_wavelengths)
    np.testing.assert_array_equal(np.array([s['values'] for s in observer['series']]).T,app.model.cmfs)


def test_raw_application_uses_independent_rt_reference_and_linear_ap1_for_film(app,tmp_path):
    from spectral_app.application import Application
    source=Path('artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng')
    if not app.raw_engine.cli or not source.exists():pytest.skip('Optional local RT and synthetic DNG not supplied.')
    model=copy.copy(app.model);model.output=tmp_path;isolated=Application(model)
    item=isolated.import_image({'name':source.name,'data_base64':base64.b64encode(source.read_bytes()).decode()})['input']
    assert item['kind']=='imported_raw_photo' and item['interpretation']['scene_referred']
    original=isolated.raw_engine.develop(isolated.import_directory/(item['id']+'.source'),source_name=source.name,preview=True)
    np.testing.assert_array_equal(model.inputs[item['id']],isolated._resize_float(original['ap1']))
    request={'recipe':template(),'input':{'id':item['id'],'exposure_ev':0},'selection':{'x':.5,'y':.5}}
    result=isolated.evaluate(request)
    assert result['reference']['method']=='RawTherapee_RAW_to_sRGB'
    image=Image.open(io.BytesIO(base64.b64decode(result['reference']['preview']['data_url'].split(',')[1])))
    expected=np.rint(np.clip(isolated._resize_float(original['srgb']),0,1)*255).astype('uint8')
    np.testing.assert_array_equal(np.asarray(image),expected)
    assert 'AP1 D60' in item['interpretation']['film_input']
    assert str(tmp_path) not in json.dumps(item)


def test_restart_uses_verified_preview_cache_without_full_image_decode(app,tmp_path,monkeypatch):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;isolated=Application(model)
    item=isolated.import_image(image_request()[0])['input']
    def forbidden(*args):raise AssertionError('Restart unnecessarily decoded a full image')
    monkeypatch.setattr(Application,'_decode',forbidden)
    restarted=Application(model)
    assert item['id'] in restarted.model.inputs
    assert not restarted.model.inputs.memory
    np.testing.assert_array_equal(restarted.model.inputs[item['id']],isolated.model.inputs[item['id']])


def test_photo_panel_visibility_is_persisted_and_rejects_non_boolean_settings(app,tmp_path):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;isolated=Application(model)
    state={'documents':[{'recipe':template(),'baseline':None}],'active_id':template()['id'],
        'photo_workspace':{'order':['chart'],'active_input_id':'chart','exposures':{},
            'panels':{'recipes_collapsed':True,'filmstrip_collapsed':True}}}
    isolated.save_session({'expected_revision':0,'session':state})
    restarted=Application(model)
    assert restarted.bootstrap()['session']['photo_workspace']['panels']==state['photo_workspace']['panels']
    state['photo_workspace']['panels']['filmstrip_collapsed']='false'
    with pytest.raises(RecipeError):restarted.save_session({'expected_revision':1,'session':state})


def test_binary_renditions_reuse_exact_pixels_after_restart_and_without_render(app,tmp_path,monkeypatch):
    from spectral_app.application import Application
    model=copy.copy(app.model);model.output=tmp_path;photo=Application(model)
    request,_=image_request();item=photo.import_image(request)['input']
    spec={'recipe':template(),'input':{'id':item['id'],'exposure_ev':0}}
    first=photo.evaluate(spec);original=base64.b64decode(first['current']['preview']['data_url'].split(',',1)[1])
    restarted=Application(model)
    monkeypatch.setattr(restarted,'_evaluate_uncached',lambda *a:pytest.fail('Cached switch rerendered'))
    binary=restarted.evaluate({**spec,'preview_transport':'url'})
    url=binary['current']['preview']['data_url'];assert url.startswith('/previews/')
    assert restarted.renditions.asset(url)==original
    with Image.open(io.BytesIO(original)) as image:assert image.info.get('icc_profile')
    monkeypatch.setattr(restarted.storage,'mounted',lambda:False)
    with pytest.raises(RecipeError) as error:restarted.evaluate(spec)
    assert error.value.code=='external_storage'


def test_restart_restores_raw_library_index_without_reading_original_raw_bytes(app,tmp_path,monkeypatch):
    import spectral_app.application as module
    from spectral_app.application import Application
    source=Path('artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng')
    if not source.exists():pytest.skip('Local DNG not supplied')
    model=copy.copy(app.model);model.output=tmp_path;photo=Application(model)
    item=photo.import_image({'name':'original.dng','data_base64':base64.b64encode(source.read_bytes()).decode()})['input']
    original=module.sha
    def digest(path):
        assert Path(path).suffix!='.source','Restoring the library must not read every original RAW'
        return original(path)
    monkeypatch.setattr(module,'sha',digest)
    restored=Application(model)
    assert item['id'] in restored.photo_sources
