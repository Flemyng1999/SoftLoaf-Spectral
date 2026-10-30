from pathlib import Path
import copy
import numpy as np
import pytest
from experiments.gui_recipe_server import template
from spectral_app.input_priors import LEGACY

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    root=Path.cwd()
    return SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('optimized'),core=NativeCore())


def test_current_recipe_uses_the_separately_selected_optimized_model(model):
    for route,family,name in [('slide','reversal','local_512_128'),('negative','negative','root3_source_balanced_1e-05'),('print','negative','root3_source_balanced_1e-05')]:
        recipe=model.validate(template(route))['normalized_recipe'];identity=recipe['input_model']
        assert identity['family']==family and identity['id']==name
        assert model.validate(recipe)['normalized_recipe']==recipe
        rgb=np.array([[.08,.12,.2],[.3,.12,.04]])
        expected=model.input_priors.models[family].reconstruct(rgb)
        actual=model.sample(rgb,**model.parameters(recipe))['reflectance']
        np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-14)


def test_mismatched_family_is_rejected_and_legacy_remains_explicit(model):
    from experiments.gui_recipe_server import RecipeError
    slide=model.validate(template())['normalized_recipe'];negative=model.validate(template('negative'))['normalized_recipe']
    slide['input_model']=negative['input_model']
    with pytest.raises(RecipeError):model.validate(slide)
    slide['input_model']=copy.deepcopy(LEGACY);r=model.validate(slide)['normalized_recipe']
    rgb=np.array([[.21,.08,.3]])
    np.testing.assert_array_equal(model.sample(rgb,**model.parameters(r))['reflectance'],np.maximum(rgb@model.basis,0))


def test_gpu_reconstructs_original_prior_at_every_wavelength_and_is_tiled(model):
    from spectral_app.metal_renderer import MetalRenderer,INDEX
    model.metal=MetalRenderer(model)
    points=np.vstack([np.random.default_rng(91).uniform(-.04,3,(101,3)),np.zeros(3),[.18]*3,[1e-9]*3,[-.01,.2,.05]])
    for route in ['slide','negative']:
        r=model.validate(template(route))['normalized_recipe'];expected=model.input_priors.models['reversal' if route=='slide' else 'negative'].reconstruct(points)
        data,meta=model.metal._plan(r,purpose='exposure');data=data.copy();data[meta[INDEX['FILMSCALE']]]=1
        for start in range(0,len(model.source_wavelengths),3):
            kernel=np.zeros((len(model.source_wavelengths),3));bands=list(range(start,min(start+3,len(kernel))))
            for channel,band in enumerate(bands):kernel[band,channel]=1
            offset=meta[INDEX['EXPOSURE']];data[offset:offset+kernel.size]=kernel.ravel()
            actual=model.metal._run(points,(data,meta),r['display']['view'],'sRGB',tile_pixels=37)
            np.testing.assert_allclose(actual[:,:len(bands)],expected[:,bands],rtol=3e-4,atol=3e-5)
        a=model.metal.render(points,r,tile_pixels=17,input_ev=.3);b=model.metal.render(points,r,tile_pixels=61,input_ev=.3)
        np.testing.assert_array_equal(a,b)
