"""GPU numerical checks use the unchanged float64 calculation as their oracle."""
import copy
from pathlib import Path

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def renderer(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_app.metal_renderer import MetalRenderer
    from spectral_lut.native import NativeCore
    model=SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('metal'),core=NativeCore())
    return MetalRenderer(model)


def test_metal_device_is_real_and_failure_is_not_cpu_fallback(renderer):
    assert renderer.backend.device_name
    assert renderer.metadata()['backend']=='Metal'
    assert renderer.metadata()['precision']=='float32'


@pytest.mark.parametrize('route',['slide','negative','print'])
def test_gpu_complete_routes_match_float64_for_rgb_and_measured_spectra(renderer,route):
    from experiments.gui_recipe_server import template
    m=renderer.model;r=m.validate(template(route))['normalized_recipe']
    if route=='print':r['printing']=m.modern_printing(r)
    rng=np.random.default_rng(20261028);rgb=np.vstack([rng.uniform(-.05,2,(100,3)),np.zeros((1,3)),np.ones((1,3))*.18])
    for ev in [-2,0,2]:
        r['film']['exposure_ev']=ev
        for spectra in [False,True]:
            values=np.maximum(rgb@m.basis,0) if spectra else rgb
            cpu=(m.sample_spectra if spectra else m.sample)(values,**m.parameters(r))
            actual=renderer.render(values,r,spectral=spectra)
            np.testing.assert_allclose(actual,cpu['display_rgb'],rtol=0,atol=3e-4)
            xyz=renderer.render(values,r,spectral=spectra,purpose='XYZ')
            np.testing.assert_allclose(xyz,cpu['XYZ'],rtol=3e-4,atol=3e-6)


@pytest.mark.parametrize('view',['Display Encoding','ACES 2.0 - SDR 100 nits','Default','Colorful','Umbra','Bypass'])
@pytest.mark.parametrize('target',['sRGB','Display P3','Rec.1886'])
def test_native_ocio_msl_and_original_textures_match_cpu(renderer,view,target):
    m=renderer.model;rng=np.random.default_rng(428);xyz=rng.uniform(-.01,2,(512,3))
    gpu=renderer.display(xyz,view,target)
    np.testing.assert_allclose(gpu,m.render(xyz,view,target),rtol=0,atol=3e-4)


def test_tile_boundaries_and_input_exposure_are_pointwise(renderer):
    from experiments.gui_recipe_server import template
    m=renderer.model;r=m.validate(template('negative'))['normalized_recipe'];rng=np.random.default_rng(1);x=rng.random((263,3))
    a=renderer.render(x,r,tile_pixels=31,input_ev=.5)
    b=renderer.render(x*2**.5,r,tile_pixels=257)
    # Root features amplify the two float32 input-scaling roundoff orders.
    # Identical input/exposure across tile sizes is checked bitwise separately.
    np.testing.assert_allclose(a,b,rtol=0,atol=1e-5)
    with pytest.raises(ValueError):renderer.render(np.array([[np.nan,0,0]]),r)


def test_cct_baking_and_original_reference_do_not_cross_input_encodings(renderer):
    from experiments.gui_recipe_server import template
    from spectral_lut.reference import acescct_encode
    import colour
    m=renderer.model;r=m.validate(template('negative'))['normalized_recipe'];x=np.random.default_rng(2).uniform(-.03,4,(300,3))
    np.testing.assert_allclose(renderer.render(acescct_encode(x),r,acescct=True),m.sample(x,**m.parameters(r))['display_rgb'],rtol=0,atol=3e-4)
    encoded=np.random.default_rng(3).random((300,3))
    np.testing.assert_array_equal(renderer.reference(encoded,kind='raw_srgb'),encoded.astype(np.float32))
    for ev in [-1,.5,2]:
        reference=np.clip(colour.models.eotf_inverse_sRGB(colour.models.eotf_sRGB(encoded)*2**ev),0,1)
        np.testing.assert_allclose(renderer.reference(encoded,kind='raw_srgb',input_ev=ev),reference,rtol=0,atol=2e-6)
    with pytest.raises(ValueError):renderer.render(x,r,spectral=True,acescct=True)
    with pytest.raises(ValueError):renderer.reference(x,kind='APD')


def test_concurrent_tiles_survive_display_program_eviction(renderer):
    from concurrent.futures import ThreadPoolExecutor
    m=renderer.model;x=np.random.default_rng(4).uniform(-.01,2,(1031,3))
    tasks=[(view,target) for view in ('Display Encoding','ACES 2.0 - SDR 100 nits','Default','Colorful','Umbra','Bypass') for target in ('sRGB','Display P3','Rec.1886')]
    def run(pair):
        view,target=pair;out=renderer._run(x,renderer._reference_plan('xyz'),view,target,tile_pixels=127)
        np.testing.assert_allclose(out,m.render(x,view,target),rtol=0,atol=3e-4)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(run,tasks))
    assert len(renderer.programs)<=12
