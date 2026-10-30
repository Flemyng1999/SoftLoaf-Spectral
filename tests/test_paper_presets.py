"""Paper identity, original conditions and fixed calibration are independent of film."""
import copy
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    return SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo', ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip', tmp_path_factory.mktemp('papers'), core=NativeCore())


def test_catalog_keeps_optical_papers_and_original_conditions_separate(model):
    from spectral_app.paper_presets import load_paper_presets
    entries = load_paper_presets(ROOT)
    assert {p['id'] for p in entries} == {'endura-premier', 'ektacolor-edge', 'royal-digital', 'endura-premier-metallic'}
    for entry in entries:
        material = entry['material']; p = material['provenance']
        assert p['process']=='RA-4' and p['density_metric']=='Status A'
        assert p['source_conditions']['optical_exposure_supported'] is True
        assert not p['substitutions'] and 'paper_white' in p['missing_measurements']
        assert p['source_conditions']['developer_temperature_c'] == (38 if entry['id'] in ('ektacolor-edge','royal-digital') else 35)
        assert p['source_conditions']['curve_exposure_seconds'] == (None if entry['id'] in ('ektacolor-edge','royal-digital') else .5)
        assert model._paper_fit(material).metadata['neutral_max_error_D'] <= .02


def test_paper_selection_is_a_saved_snapshot_with_frozen_exposure(model):
    from spectral_app.paper_presets import load_paper_presets
    from experiments.gui_recipe_server import template
    material = load_paper_presets(ROOT)[0]['material']
    recipe = model.validate(template('print'))['normalized_recipe']
    film = copy.deepcopy(recipe['film'])
    recipe['printing'].update(paper=material['provenance']['stock_id'], custom_material=copy.deepcopy(material))
    saved = model.validate(recipe)['normalized_recipe']
    assert saved['film']==film and saved['printing']['custom_material']==material
    fit = model.route_paper(saved)
    changed = copy.deepcopy(material)
    for c in 'RGB': changed['sensitivity']['channels'][c] = (np.array(changed['sensitivity']['channels'][c])*2).tolist()
    adjusted = model._paper_fit(changed)
    np.testing.assert_array_equal(fit.normal, adjusted.normal)
    assert fit.anchor == adjusted.anchor
    assert fit.metadata['published_reference_conditions']['reference'] != 'Kodak E-4020, July 2003, pp2–4,7; conditions of the builtin reference curves, not verified for user CSV'
    broken=copy.deepcopy(material);del broken['provenance']['exposure_reference']
    with pytest.raises(Exception,match='冻结曝光参考'):model._paper_fit(broken)


def test_bootstrap_exposes_papers_without_changing_old_default(model):
    from spectral_app.application import Application
    boot = Application(model).bootstrap()
    assert len(boot['paper_presets'])==4
    assert boot['spectral_assets']['paper']['name']=='Kodak Ultra Endura · RA-4'
    assert all(t['recipe']['printing']['paper']=='Ultra Endura' for t in boot['templates'] if t['id']=='print')
