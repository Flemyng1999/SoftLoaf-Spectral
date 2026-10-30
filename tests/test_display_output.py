import base64
import io
from pathlib import Path

import colour
import numpy as np
from PIL import Image, ImageCms
import PyOpenColorIO as ocio
import pytest

from experiments.gui_recipe_server import E100Model, template, validate_recipe, apply_ocio


@pytest.mark.parametrize('route,view', [('slide','Display Encoding'),
    ('print','Display Encoding'),('negative','ACES 2.0 - SDR 100 nits')])
def test_new_recipe_display_default_matches_physical_endpoint(route,view):
    assert template(route)['display']['view']==view


@pytest.mark.parametrize('target,matrix,gamma', [
    ('sRGB', [[3.2409699419,-1.5373831776,-.4986107603],
              [-.9692436363,1.8759675015,.0415550574],
              [.0556300797,-.2039769589,1.0569715142]],None),
    ('Display P3', [[2.4934969119,-.9313836179,-.4027107845],
                    [-.8294889696,1.7626640603,.0236246858],
                    [.0358458302,-.0761723893,.956884524]],None),
    ('Rec.1886', [[3.2409699419,-1.5373831776,-.4986107603],
                  [-.9692436363,1.8759675015,.0415550574],
                  [.0556300797,-.2039769589,1.0569715142]],2.4)])
def test_colorimetric_output_against_independent_matrix_and_transfer(model,target,matrix,gamma):
    # Independent numeric colorimetry, including the transfer-function toe.
    # A detour through packaged display LUTs fails this tolerance.
    linear=np.random.default_rng(71).uniform(0,1,(500,3))
    linear=np.concatenate([linear,np.repeat(np.array([0,.0001,.0031308,.18,1])[:,None],3,1)])
    xyz=linear@np.linalg.inv(np.asarray(matrix)).T
    expected=(np.maximum(linear,0)**(1/gamma) if gamma else
        np.where(linear<=.0031308,12.92*linear,1.055*np.maximum(linear,0)**(1/2.4)-.055))
    np.testing.assert_allclose(model.render(xyz,'Display Encoding',target),expected,atol=3e-5,rtol=0)
    graph=model.display_group('Display Encoding',target)
    assert not any(isinstance(t,(ocio.Lut1DTransform,ocio.Lut3DTransform,ocio.FixedFunctionTransform)) for t in graph)
    assert model.display_manager.metadata('Display Encoding',target)['rendering']=='colorimetric'


@pytest.fixture(scope='module')
def model(tmp_path_factory):
    archive = Path('local/film-color-slides/hyperspectral-demo')
    package = Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists() or not package.exists():
        pytest.skip('Optional local spectral data absent.')
    return E100Model(archive, package, tmp_path_factory.mktemp('display-output'))


@pytest.mark.parametrize('view', ['Colorful', 'Display Encoding', 'Bypass', 'ACES 2.0 - SDR 100 nits'])
def test_recipe_accepts_available_sdr_views(view):
    recipe = template(); recipe['display'].update(view=view, target='Display P3')
    assert validate_recipe(recipe)['ok']


def test_unknown_display_target_is_rejected():
    recipe = template(); recipe['display']['target'] = 'invented monitor'
    assert not validate_recipe(recipe)['ok']


def test_colorful_changes_only_the_display(model):
    rgb = [[.32,.14,.06], [.04,.2,.7]]
    default = model.sample(rgb)
    colorful = model.sample(rgb, display='Colorful')
    np.testing.assert_array_equal(default['XYZ'], colorful['XYZ'])
    assert np.max(abs(default['display_rgb']-colorful['display_rgb'])) > .001


def test_p3_is_encoded_as_p3_without_repeating_the_look(model):
    rgb = [[.32,.14,.06], [.04,.2,.7], [.18]*3]
    srgb = model.sample(rgb, display='Default')
    p3 = model.sample(rgb, display='Default', display_target='Display P3')
    np.testing.assert_array_equal(srgb['XYZ'], p3['XYZ'])
    expected = colour.RGB_to_RGB(srgb['display_rgb'], 'sRGB', 'Display P3',
                                apply_cctf_decoding=True, apply_cctf_encoding=True)
    np.testing.assert_allclose(p3['display_rgb'], expected, atol=7e-5, rtol=0)
    assert 'sRGB' not in p3  # P3 numbers must not be mislabeled as sRGB.


@pytest.mark.parametrize('target', ['sRGB', 'Display P3', 'Rec.1886'])
def test_all_selected_display_graphs_match_portable_ocio(model, target):
    xyz = np.array([[.01,.02,.03],[.18,.18,.18],[.6,.3,.1],[1,1,1]])
    for view in model.displays:
        graph = model.display_group(view, target)
        cpu = ocio.Config.CreateRaw().getProcessor(graph).getDefaultCPUProcessor()
        expected = np.clip(apply_ocio(cpu, xyz), 0, 1)
        np.testing.assert_allclose(model.render(xyz, view, target), expected, atol=2e-6)


def test_p3_preview_and_photo_export_embed_matching_icc(model):
    from spectral_app.application import Application
    app = Application(model)
    data = io.BytesIO(); Image.new('RGB',(2,2),(128,64,32)).save(data,format='PNG')
    item = app.import_image({'name':'test.png','data_base64':base64.b64encode(data.getvalue()).decode()})['input']
    recipe = template(); recipe['display'].update(view='Colorful',target='Display P3')
    request = {'recipe':recipe,'input':{'id':item['id']}}
    evaluated = app.evaluate(request)
    encoded = base64.b64decode(evaluated['current']['preview']['data_url'].split(',')[1])
    with Image.open(io.BytesIO(encoded)) as preview:
        assert preview.info['icc_profile'] == model.display_profile('Display P3')
    exported = app.export_image(request)
    png = next(f for f in exported['files'] if f['name']=='image.png')
    with Image.open(app.downloads[png['url']][0]) as image:
        assert image.info['icc_profile'] == model.display_profile('Display P3')
        pixels = model.sample(model.srgb_to_ap1(np.full((2,2,3),[128,64,32])/255),
                              display='Colorful', display_target='Display P3')['display_rgb']
        np.testing.assert_array_equal(np.asarray(image),np.floor(pixels*255+.5).astype(np.uint8))
    assert 'Display P3' in exported['verification']['encoding']


def test_p3_profile_matches_independent_colorimetry(model):
    pixels = np.array([[[128,64,32],[64,180,120],[90,90,90]]],dtype=np.uint8)
    profile = ImageCms.ImageCmsProfile(io.BytesIO(model.display_profile('Display P3')))
    actual = np.asarray(ImageCms.profileToProfile(Image.fromarray(pixels),profile,
        ImageCms.createProfile('sRGB'),outputMode='RGB',renderingIntent=1))
    expected = colour.RGB_to_RGB(pixels/255,'Display P3','sRGB',
                                apply_cctf_decoding=True,apply_cctf_encoding=True)
    np.testing.assert_allclose(actual,np.rint(np.clip(expected,0,1)*255),atol=2)


def test_p3_connects_all_physical_routes_and_portable_export(tmp_path):
    from spectral_app.model import SpectralModel
    from spectral_app.application import Application
    model = SpectralModel(Path('local/film-color-slides/hyperspectral-demo'),
        Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'),tmp_path)
    app = Application(model)
    for route in ['slide','negative','print']:
        recipe = template(route); recipe['display'].update(target='Display P3',view='Colorful')
        recipe = model.validate(recipe,compute=True)['normalized_recipe']
        result = app.evaluate({'recipe':recipe,'input':{'id':'chart'}})
        assert result['current']['sample']['display_target']=='Display P3'
        np.testing.assert_allclose(result['current']['nodes']['display']['details']['process']['output'],
            result['current']['sample']['display_rgb'],atol=2e-5)
        assert result['reference']['conditions']['encoding'].endswith('no OpenDRT')
        assert result['conditions']['display']['target']=='Display P3'
    for route, view in [('negative','Colorful'),('slide','ACES 2.0 - SDR 100 nits')]:
        recipe = template(route); recipe['display'].update(target='Display P3',view=view)
        result = app.export({'recipe':recipe,'purpose':'pipeline','grid':5})
        assert result['ok'] and result['verification']['integrity_passed']
        assert result['verification']['pipeline_vs_material_display_max_abs']<2e-5


def test_colorimetric_pipeline_export_does_not_claim_an_opendrt_look(model):
    import json,zipfile
    from spectral_app.application import Application
    app=Application(model)
    exported=app.export({'recipe':template(),'purpose':'pipeline','grid':5})
    manifest_path=next(app.downloads[f['url']][0] for f in exported['files'] if f['name']=='manifest.json')
    manifest=json.loads(manifest_path.read_text())
    assert manifest['conditions']['display']['rendering']=='colorimetric'
    assert 'opendrt' not in manifest
    assert 'OpenDRT' not in manifest['output']['format_reason']
    with zipfile.ZipFile(manifest_path.parent/'recipe.zip') as z:
        assert 'OpenDRT-LICENSE.md' not in z.namelist()


@pytest.mark.parametrize('target,view', [('sRGB','Default'),('Display P3','Colorful'),
    ('Display P3','ACES 2.0 - SDR 100 nits'),('Rec.1886','Display Encoding')])
def test_display_process_is_the_executed_graph_with_live_intermediate_values(model,target,view):
    assert hasattr(model.display_manager,'trace')
    xyz=np.array([.3,.18,.06])
    trace=model.display_manager.trace(xyz,view,target)
    np.testing.assert_array_equal(trace['input_xyz_d65'],xyz)
    assert trace['target']==target and trace['steps']
    previous=xyz
    for step in trace['steps']:
        np.testing.assert_allclose(step['input'],previous,atol=2e-6)
        if step['kind']=='matrix':
            expected=np.asarray(step['matrix'])@np.append(previous,1)+step['offset']
            np.testing.assert_allclose(step['output'],expected[:3],atol=2e-6)
        previous=step['output']
    np.testing.assert_allclose(previous,model.render(xyz,view,target),atol=2e-5)
    if view in ('Default','Colorful'):
        assert any(s['kind']=='lut3d' and s['grid']==48 for s in trace['steps'])
        graph=model.config.getProcessor(model.display_group(view,target)).getOptimizedProcessor(
            ocio.OPTIMIZATION_DEFAULT).createGroupTransform()
        expected_lengths=[t.getLength() for t in graph if isinstance(t,ocio.Lut1DTransform)]
        assert [s['length'] for s in trace['steps'] if s['kind']=='lut1d']==expected_lengths
        assert all(len(s['curve']['input'])==65 for s in trace['steps'] if s['kind'].startswith('lut'))


def test_primary_config_is_pinned_aces2_and_retired_views_have_no_processors(model):
    assert getattr(model.display_manager,'config_id',None)=='cg-config-v4.0.0_aces-v2.0_ocio-v2.5'
    assert (model.config.getMajorVersion(),model.config.getMinorVersion())==(2,5)
    assert 'ACES 2.0 - SDR 100 nits' in model.displays
    assert not any(v.startswith('ACES 1.') for v in model.displays)
    for view in ['ACES 1.0 - SDR Video','ACES 1.1 - SDR Video']:
        assert all(v!=view for _,v in model.display_manager.processors)
        assert all(v!=view for _,v in model.display_manager.groups)


@pytest.mark.parametrize('view',['ACES 1.0 - SDR Video','ACES 1.1 - SDR Video'])
def test_old_aces_recipe_migrates_once_and_preserves_other_settings(view):
    import copy
    r=template();r['revision']=7;r['display']={'view':view,'target':'Display P3'};r['film']['exposure_ev']=.5
    original=copy.deepcopy(r);result=validate_recipe(r)['normalized_recipe']
    assert r==original
    assert result['display']=={'view':'ACES 2.0 - SDR 100 nits','target':'Display P3','defaults_version':1}
    assert result['revision']==8
    expected=copy.deepcopy(original);expected['display'].update(view='ACES 2.0 - SDR 100 nits',defaults_version=1);expected['revision']=8
    assert result==expected
    assert validate_recipe(result)['normalized_recipe']==result


@pytest.mark.parametrize('target,display,view',[
    ('sRGB','sRGB - Display','ACES 2.0 - SDR 100 nits (Rec.709)'),
    ('Display P3','Display P3 - Display','ACES 2.0 - SDR 100 nits (P3 D65)'),
    ('Rec.1886','Rec.1886 Rec.709 - Display','ACES 2.0 - SDR 100 nits (Rec.709)')])
def test_aces2_matches_official_config_through_independent_ap1_bridge(model,target,display,view):
    from experiments.hsi_raw_lut import AP1,D65,D60,cat
    xyz=np.array([[0,0,0],[.18,.18,.18],[.6,.3,.1],[.04,.1,.7],[2,2,2]])
    ap1=xyz@cat(D65,D60).T@AP1.matrix_XYZ_to_RGB.T
    config=ocio.Config.CreateFromBuiltinConfig('cg-config-v4.0.0_aces-v2.0_ocio-v2.5')
    cpu=config.getProcessor(ocio.DisplayViewTransform(src='ACEScg',display=display,view=view)).getDefaultCPUProcessor()
    expected=np.clip(apply_ocio(cpu,ap1),0,1)
    actual=model.render(xyz,'ACES 2.0 - SDR 100 nits',target)
    np.testing.assert_allclose(actual,expected,atol=3e-5,rtol=0)
    metadata=model.display_manager.metadata('ACES 2.0 - SDR 100 nits',target)
    assert metadata['ocio_config']['aces_version']=='2.0'
    assert metadata['ocio_config']['config_version']=='4.0.0'
    assert len(metadata['ocio_config']['sha256'])==64
    assert metadata['display']==display and metadata['display_view']==view
