"""Manufacturer-source integration and frozen per-stock exposure regression."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    if not (ROOT/'local/materials/5207-v1/provenance.json').exists():pytest.skip('Local sources required')
    return SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('vision3'),core=NativeCore())


def test_stock_exposure_is_frozen_to_its_own_reference_not_5207(model):
    m=copy.deepcopy(model.negative_material)
    for c in 'RGB':m['sensitivity']['channels'][c]=(np.array(m['sensitivity']['channels'][c])*3).tolist()
    m['provenance']={'stock_id':'5219','process':'ECN-2','density_metric':'Status M',
        'exposure_reference':{**copy.deepcopy(m['sensitivity']),'temperature_k':3200,'illuminant':'Planck','reflectance':.18}}
    fit=model._negative_fit(m);gray=np.full(len(model.source_wavelengths),.18)
    np.testing.assert_allclose(model._film_stage(gray,0,3200,fit,'Planck')[0],1,rtol=1e-13)
    for c in 'RGB':m['sensitivity']['channels'][c]=(np.array(m['sensitivity']['channels'][c])*2).tolist()
    adjusted=model._negative_fit(m)
    np.testing.assert_allclose(model._film_stage(gray,0,3200,adjusted,'Planck')[0],2,rtol=1e-13)
    np.testing.assert_array_equal(adjusted.denominators,fit.denominators)


def test_invalid_frozen_reference_is_rejected(model):
    from experiments.gui_recipe_server import RecipeError
    m=copy.deepcopy(model.negative_material);m['provenance']={'exposure_reference':{'reflectance':.5}}
    with pytest.raises(RecipeError,match='曝光参考'):model._negative_fit(m)


def test_builder_retains_own_sources_and_density_definition(model):
    from experiments.integrate_vision3_materials import build_material
    for stock in ['5203','5207','5213','5219']:
        material,plot,traces=build_material(ROOT,stock)
        p=material['provenance']
        assert p['stock_id']==stock and p['process']=='ECN-2' and p['density_metric']=='Status M'
        assert material['characteristic']['quantity']=='status_m_density'
        assert material['dyes']['quantity']=='net_spectral_density'
        assert not p['substitutions']
        assert p['source_conditions']['characteristic_exposure_seconds']==.02
        assert p['source_conditions']['sensitivity_exposure_seconds']==(.1 if stock=='5203' else .02 if stock=='5207' else .04)
        assert p['density_metric_evidence']['status']==('inferred_from_same_document' if stock=='5219' else 'explicit_chart_label')
        assert p['exposure_reference']['temperature_k']==(3200 if stock in ('5213','5219') else 5500)
        assert len(plot['sensitivity']['channels']['B']['values'])>30
        model._validate_negative_material(material)
        fitted=model._negative_fit(material)
        assert fitted.metadata['neutral_max_error_D']<=.006
        assert fitted.metadata['minimum_absolute_density_bound_D']>=0
        for c in 'RGB':assert 'characteristic_'+c in traces


def test_bootstrap_exposes_new_materials_without_rewriting_legacy(model):
    from spectral_app.application import Application
    before=copy.deepcopy(model.negative_material);boot=Application(model).bootstrap()
    assert set(e['recipe']['film']['stock'] for e in boot['recipe_presets'])=={'5203','5207','5213','5219'}
    assert '5206' not in boot['spectral_assets']
    for stock in ['5203','5207','5213','5219']:
        m=boot['spectral_assets'][stock];assert m['provenance']['material_version']=='vision3-source/2'
        p=boot['spectral_assets']['material_plot_sources'][stock]['sensitivity']
        assert p['reference_curve']==m['sensitivity']
        assert len(p['channels']['B']['values'])>30
    for entry in boot['templates']:
        if entry['id'] in ('negative','print'):assert entry['recipe']['film']['custom_material']['provenance']['stock_id']=='5207'
    assert model.negative_material==before and boot['spectral_assets']['legacy_5207']==before
