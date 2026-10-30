import copy
from pathlib import Path
import numpy as np
import pytest
from experiments.gui_recipe_server import E100Model, template, validate_recipe


@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_lut.native import NativeCore
    archive=Path('local/film-color-slides/hyperspectral-demo')
    drt=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists() or not drt.exists(): pytest.skip('Local materials not supplied.')
    return E100Model(archive,drt,tmp_path_factory.mktemp('daylight'),core=NativeCore())


def test_daylight_keeps_default_and_recomputes_layer_exposure_in_both_engines(model):
    base=model.sample([.18,.12,.08])
    np.testing.assert_array_equal(base['XYZ'],model.sample([.18,.12,.08],scene_temperature_k=6500)['XYZ'])
    warm=model.sample([.18,.12,.08],scene_temperature_k=4000)
    cool=model.sample([.18,.12,.08],scene_temperature_k=10000)
    assert not np.allclose(warm['exposure'],cool['exposure'])
    assert not np.allclose(warm['XYZ'],cool['XYZ'])
    original=model.core
    try:
        model.core=None
        python=model.sample([.18,.12,.08],scene_temperature_k=4000)
    finally: model.core=original
    for key in warm: np.testing.assert_allclose(warm[key],python[key],atol=2e-12,rtol=2e-12)


def test_daylight_same_photometric_scale_and_no_new_gray_fit(model):
    from spectral_lut.reference import quadrature_widths
    from experiments.hsi_raw_lut import csv,interpolate
    cmf=interpolate(csv(model.archive.parent/'data/CIE_xyz_official.csv'),model.source_wavelengths)
    weights=cmf[:,1]*quadrature_widths(model.source_wavelengths)
    for k in [4000,5500,6500,10000]:
        np.testing.assert_allclose(model.scene_light(k)@weights,model.source_light@weights,rtol=1e-13)
    assert model.material()[0].gray_log_h==model.film.gray_log_h


@pytest.mark.parametrize('k',[True,3999,10001,float('nan'),'5500'])
def test_daylight_rejects_invalid_temperatures(k):
    recipe=template();recipe['scene']={'illuminant':'CIE_D','temperature_k':k}
    assert not validate_recipe(recipe)['ok']


def test_scene_temperature_does_not_change_original_a(model):
    from spectral_app.application import Application
    app=Application(model)
    recipe=template();first=app.evaluate({'recipe':recipe})
    recipe=copy.deepcopy(recipe);recipe['scene']={'illuminant':'CIE_D','temperature_k':4000}
    result=app.evaluate({'recipe':recipe})
    assert first['reference']['preview']==result['reference']['preview']
    assert first['current']['preview']!=result['current']['preview']
    assert result['conditions']['scene_temperature_k']==4000
