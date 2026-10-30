from pathlib import Path
import json
import numpy as np
import pytest
from experiments.gui_recipe_server import template
from spectral_app.exporting.lut_files import grid_blocks,write_cube,read_cube


def test_streamed_cube_uses_red_fast_order_and_exact_float32_readback(tmp_path):
    low=np.full(3,-.25);high=np.full(3,.75);path=tmp_path/'small.cube'
    nodes=write_cube(path,9,low,high,lambda p:p*np.array([.8,.9,1.1])+np.array([.1,.2,.3]),'test',['Author: Yangming Feng'],block=37)
    cube=read_cube(path,tmp_path/'read.nodes',nodes,block=29)
    values=np.random.default_rng(53).uniform(low,high,(100,3))
    np.testing.assert_allclose(cube.apply(values),values*[.8,.9,1.1]+[.1,.2,.3],rtol=0,atol=8e-8)
    assert 'Yangming Feng' in path.open().read(200)

@pytest.fixture(scope='module')
def app(tmp_path_factory):
    from spectral_app.application import Application
    from spectral_app.model import SpectralModel
    from spectral_app.metal_renderer import MetalRenderer
    from spectral_lut.native import NativeCore
    root=Path.cwd();model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('gpu-lut-app'),core=NativeCore());model.metal=MetalRenderer(model)
    return Application(model)


@pytest.mark.parametrize('route',['slide','negative','print'])
def test_real_app_export_is_gpu_optimized_and_verifies_current_family_audit(app,route):
    r=app.model.validate(template(route))['normalized_recipe']
    if route=='print':r['printing']=app.model.modern_printing(r)
    result=app.export({'recipe':r,'purpose':'display','grid':17})
    assert result['ok'],result.get('verification')
    check=result['verification'];assert check['integrity_passed'] and check['production_backend'].startswith('Metal')
    assert check['spectral_reference']['measured_input_count']==5376
    assert check['spectral_reference']['input_model']['family']==('reversal' if route=='slide' else 'negative')
    assert check['gpu_vs_float64_reference_max_abs_display']<3e-4
    directory=app.model.output/'exports'/result['export_id'];manifest=json.loads((directory/'manifest.json').read_text())
    assert manifest['input_model']==r['input_model'] and not list(directory.glob('*.nodes'))
    assert r['input_model']['model_sha256'] in (directory/'recipe.cube').open().read(16000)


def test_material_ctf_package_uses_same_optimized_prior_and_independent_execution(app):
    result=app.export({'recipe':template('negative'),'purpose':'pipeline','grid':17})
    assert result['ok'],result.get('verification')
    assert result['verification']['pipeline_vs_material_display_max_abs']<2e-5
    path=app.model.output/'exports'/result['export_id']
    manifest=json.loads((path/'manifest.json').read_text())
    assert manifest['output']['includes_display'] and manifest['output']['format'].startswith('CTF')
    assert (path/'recipe.ctf').exists() and (path/'ACES-LICENSE.md').exists()


def test_cube_domain_corruption_is_rejected_even_when_nodes_match(tmp_path):
    low=np.zeros(3);high=np.ones(3);path=tmp_path/'corrupt.cube'
    source=write_cube(path,3,low,high,lambda x:x,'test',[],block=5)
    path.write_text(path.read_text().replace('DOMAIN_MAX 1 1 1','DOMAIN_MAX 2 1 1'))
    with pytest.raises(ValueError):read_cube(path,tmp_path/'read.nodes',source,expected_low=low,expected_high=high)


def test_bootstrap_and_new_templates_already_carry_frozen_prior_identity(app):
    boot=app.bootstrap()
    for group in ['templates','recipe_presets','reversal_presets']:
        for entry in boot[group]:
            recipe=entry['recipe'];assert recipe['input_model']['family']==('reversal' if recipe['route']=='slide' else 'negative')
            assert app.model.validate(recipe)['normalized_recipe']==recipe
    assert boot['default_recipe']['input_model']==boot['templates'][0]['recipe']['input_model']
