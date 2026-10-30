import copy
from pathlib import Path
import numpy as np
import pytest
from experiments.gui_recipe_server import template
from spectral_app.printing_optics import dichroic_transmission, load_optics

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    if not (ROOT/'local/materials/5207-v1/provenance.json').is_file() or not (ROOT/'local/reference-assets/spektrafilm/printing-optics').is_dir():pytest.skip('Optional identified local material and optical assets required.')
    return SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('optics'),core=NativeCore())


def test_dichroic_control_mixes_clear_and_filtered_paths_instead_of_paper_dye_density():
    t=np.array([[0,.2,.9],[.8,.7,.1]],float)
    np.testing.assert_array_equal(dichroic_transmission(t,[0,0,0]),np.ones(2))
    d=[.5,.25,.8]
    expected=np.prod(t+(1-t)*10**-np.array(d),axis=1)
    np.testing.assert_allclose(dichroic_transmission(t,d),expected,rtol=1e-15)
    assert np.all(expected>=0) and np.all(expected<=1)


def test_optical_sources_are_pinned_and_shapes_are_not_paper_dyes(model):
    assets=load_optics(ROOT,model.negative_wavelengths)
    assert assets['source']['commit']=='3bb2c2d2801ff68b92019cf1dbcbb133d60832bc'
    assert np.min(assets['heat']['values'])>=0 and np.max(assets['heat']['values'])<=1
    assert len(assets['filters']['channels']['C'])==len(model.negative_wavelengths)
    assert assets['filters']['quantity']=='spectral_transmittance'
    assert 'endpoint' in assets['source']['resampling']


def modern(model):
    r=model.validate(template('print'))['normalized_recipe']
    r['printing']=model.modern_printing()
    return model.validate(r)['normalized_recipe']


def test_legacy_recipe_does_not_silently_add_heat_filters_or_new_paper(model):
    r=model.validate(template('print'))['normalized_recipe']
    assert r['printing']['pipeline']=='legacy-v1'
    assert model.route_paper(r) is model.paper
    r['route']='negative'
    assert model.route_material(r) is model.negative


def test_new_pipeline_matches_independent_optical_integration_and_float64_reference(model):
    r=modern(model);r['printing']['filters']=[.2,.3,.1]
    x=np.linspace(.03,.9,len(model.source_wavelengths))
    p=model.parameters(r);actual=model.sample_spectra(x,**p)
    assets=model.printing_assets;lamp=model.printer_light(r['printing']['temperature_k'])
    f=np.column_stack([assets['filters']['channels'][c] for c in 'CMY'])
    optical=lamp*np.array(assets['heat']['values'])
    filtered=np.prod(f+(1-f)*10**-np.array(r['printing']['filters']),axis=1)
    incident=actual['transmission']*optical*filtered
    from spectral_lut.reference import quadrature_widths
    paper=model.route_paper(r)
    expected=(incident*2**r['printing']['exposure_ev'])@(paper.sensitivity*quadrature_widths(model.negative_wavelengths)[:,None]/paper.normal)
    np.testing.assert_allclose(actual['paper_exposure'],expected,rtol=3e-14,atol=1e-15)
    native=model.core
    try:
        model.core=None
        reference=model.sample_spectra(x,**p)
    finally:model.core=native
    for key in ['paper_exposure','paper_amounts','paper_reflectance','XYZ','display_rgb']:
        np.testing.assert_allclose(actual[key],reference[key],rtol=3e-13,atol=1e-14)


def test_preflash_is_an_additive_fixed_spectrum_and_never_reexposes_negative(model):
    r=modern(model);x=np.full(len(model.source_wavelengths),.18)
    a=model.sample_spectra(x,**model.parameters(r))
    r['printing']['preflash']['exposure']=.04
    b=model.sample_spectra(x,**model.parameters(r))
    np.testing.assert_array_equal(a['transmission'],b['transmission'])
    np.testing.assert_allclose(b['paper_exposure']-a['paper_exposure'],b['preflash_exposure'],rtol=2e-13)
    assert np.all(b['paper_exposure']>a['paper_exposure'])
    assert np.all(b['paper_reflectance']<=a['paper_reflectance']+1e-13)


def test_composite_custom_spd_can_bypass_optical_filter_to_avoid_double_counting(model):
    r=modern(model);r['printing'].update(light='custom',custom_spd=copy.deepcopy(model.printing_original_light))
    r['printing']['optics']['heat']='none';r['printing']['optics']['lens']='none'
    a=model.sample_spectra(np.full(len(model.source_wavelengths),.18),**model.parameters(r))
    np.testing.assert_allclose(a['printer_light'],model.printer_light(3200),rtol=1e-14)


def test_spectral_paper_base_is_explicit_and_still_fits_status_a(model):
    r=modern(model);paper=model.route_paper(r)
    assert np.ptp(paper.base)>0.01
    assert paper.metadata['neutral_max_error_D']<.02
    assert 'processed' in paper.metadata['base_model']['source_scope']
    assert np.min(paper.base)>=0


def test_wrong_optical_quantities_and_out_of_bounds_transmission_are_rejected(model):
    from experiments.gui_recipe_server import RecipeError
    r=modern(model);r['printing']['optics']['custom_heat']=copy.deepcopy(model.printing_assets['heat'])
    r['printing']['optics']['heat']='custom'
    r['printing']['optics']['custom_heat']['values'][0]=1.2
    with pytest.raises(RecipeError):model.validate(r)
    r=modern(model);r['printing']['custom_filters']=copy.deepcopy(model.printing_filter_curves)
    with pytest.raises(RecipeError):model.validate(r)


def test_optical_source_identity_and_apd_material_are_separate(model):
    from experiments.gui_recipe_server import RecipeError
    r=modern(model);r['printing']['optical_sources_sha256']='wrong'
    with pytest.raises(RecipeError,match='哈希'):model.validate(r)
    a=model.validate(template('negative'))['normalized_recipe'];b=copy.deepcopy(a)
    b['printing']=model.modern_printing();b=model.validate(b)['normalized_recipe']
    x=np.linspace(.05,.8,len(model.source_wavelengths))
    va=model.sample_spectra(x,**model.parameters(a));vb=model.sample_spectra(x,**model.parameters(b))
    for key in ['transmission','apd','ACES','display_rgb']:np.testing.assert_array_equal(va[key],vb[key])


def test_modern_print_export_records_optics_and_is_independently_executable(model):
    import json,zipfile
    from spectral_app.pipeline_routes import PipelineRoutes
    from experiments.gui_recipe_server import Workbench
    class App(PipelineRoutes,Workbench):pass
    r=modern(model);r['printing']['preflash']['exposure']=.02
    result=App(model).export({'recipe':r,'purpose':'display','grid':65})
    assert result['verification']['integrity_passed']
    assert result['verification']['ocio_vs_float64_max_abs_output']<2e-5
    d=model.output/'exports'/result['export_id'];header=(d/'recipe.cube').read_text().split('LUT_3D_SIZE')[0]
    assert 'Printing pipeline: spectral-v2' in header
    assert 'Andrea Volpato' in header and 'Yangming Feng' in header and 'Schott' in header
    assert 'Preflash:' in header and 'not calibrated CP' in header
    manifest=json.loads((d/'manifest.json').read_text())
    assert manifest['conditions']['printing']['optics']['heat']=='KG3'
    assert manifest['conditions']['paper']['base_model']['curve']['provenance']['commit']==model.printing_assets['source']['commit']
    with zipfile.ZipFile(d/'recipe.zip') as bundle:
        assert {'CHANGELOG.txt','SPEKTRAFILM_LICENSE.txt'}.issubset(bundle.namelist())


def test_white_paper_zero_base_is_valid_but_a_zero_energy_lamp_is_not(model):
    from experiments.gui_recipe_server import RecipeError
    r=modern(model);r['printing']['custom_material']=copy.deepcopy(model.modern_paper_material)
    base=r['printing']['custom_material']['base'];base['values']=[0]*len(base['values'])
    checked=model.validate(r)['normalized_recipe']
    assert np.all(model.route_paper(checked).base==0)
    r=modern(model);r['printing'].update(light='custom',custom_spd=copy.deepcopy(model.printing_original_light))
    r['printing']['custom_spd']['values']=[0]*len(r['printing']['custom_spd']['values'])
    with pytest.raises(RecipeError):model.validate(r)
