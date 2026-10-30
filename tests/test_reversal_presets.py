import copy
from pathlib import Path
import numpy as np
import pytest
from experiments.gui_recipe_server import template,RecipeError

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    if not (ROOT/'local/materials/reversal-presets-v1/velvia100.json').is_file():pytest.skip('Identified local manufacturer curves required')
    return SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('reversal-presets'),core=NativeCore())


def test_curated_bootstrap_hides_other_negatives_and_exposes_verified_reversal(model):
    from spectral_app.pipeline_routes import PipelineRoutes
    from experiments.gui_recipe_server import Workbench
    class App(PipelineRoutes,Workbench):pass
    b=App(model).bootstrap()
    assert {e['recipe']['film']['stock'] for e in b['recipe_presets']}=={'5203','5207','5213','5219'}
    assert [e['id'] for e in b['reversal_presets']]==['velvia100','velvia50','provia100f']
    r=b['reversal_presets'][0]['recipe']
    assert r['route']=='slide' and r['film']['stock']=='velvia100'
    assert r['film']['custom_material']['provenance']['process']=='E-6'
    assert 'portra400' in b['spectral_assets'] # historical/user documents retain their own data


@pytest.mark.parametrize('stock',['velvia100','velvia50','provia100f'])
def test_reversal_has_stock_specific_relative_calibration_and_native_reference_agreement(model,stock):
    from spectral_app.reversal_presets import load_reversal_presets
    entry=next(e for e in load_reversal_presets(ROOT) if e['id']==stock)
    r=template('slide');r.update(name='Velvia',scene={'illuminant':'CIE_D','temperature_k':5500})
    r['film'].update(stock=stock,custom_material=copy.deepcopy(entry['material']))
    r=model.validate(r)['normalized_recipe']
    x=np.full(len(model.source_wavelengths),.18)
    actual=model.sample_spectra(x,**model.parameters(r));np.testing.assert_allclose(actual['exposure'],[1,1,1],rtol=3e-14)
    native=model.core
    try:
        model.core=None;reference=model.sample_spectra(x,**model.parameters(r))
    finally:model.core=native
    for key in ['transmission','XYZ','display_rgb']:np.testing.assert_allclose(actual[key],reference[key],rtol=3e-13,atol=1e-14)
    _,meta=model.material(r['film']['custom_material'])
    assert meta['neutral_StatusA_max_error_D']<=meta['neutral_fit_limit_D'] and meta['provenance']['process']=='E-6'
    bad=copy.deepcopy(r);bad['film']['custom_material']['provenance']['process']='K-14'
    with pytest.raises(RecipeError):model.validate(bad)
    bad=copy.deepcopy(r);bad['route']='negative'
    with pytest.raises(RecipeError):model.validate(bad)


@pytest.mark.parametrize('stock,limit',[('velvia100',.003),('velvia50',.025),('provia100f',.015)])
def test_original_manufacturer_nodes_and_frozen_csv_exposure_reference(model,stock,limit):
    import json
    from spectral_app.reversal_presets import load_reversal_presets
    from spectral_lut.reference import density_transmittance
    material=next(e['material'] for e in load_reversal_presets(ROOT) if e['id']==stock)
    film,meta=model.material(material)
    traces=json.loads((ROOT/f'local/materials/reversal-presets-v1/{stock}-source-points.json').read_text())
    errors={}
    weights=model.status_a_weights/model.status_a_weights.sum(0)
    for i,c in enumerate('RGB'):
        raw=np.array(traces['characteristic'][c]);logs=raw[:,0]
        amounts=np.column_stack([np.interp(logs,film.log_h,film.amounts[:,j]) for j in range(3)])
        predicted=-np.log10(density_transmittance(amounts,film.dyes)@weights)
        errors[c]=float(np.max(np.abs(predicted[:,i]-raw[:,1])))
    assert max(errors.values())<limit,errors
    changed=copy.deepcopy(material)
    changed['sensitivity']['channels']['R']=(np.array(changed['sensitivity']['channels']['R'])*2).tolist()
    changed_film,_=model.material(changed)
    np.testing.assert_allclose(changed_film.exposure_kernel[:,0],2*film.exposure_kernel[:,0],rtol=1e-14)
    np.testing.assert_array_equal(changed_film.exposure_kernel[:,1:],film.exposure_kernel[:,1:])


@pytest.mark.parametrize('stock',['velvia100','velvia50','provia100f'])
def test_reversal_rgb_and_real_cube_export_keep_stock_and_source_identity(model,stock):
    import json
    from experiments.gui_recipe_server import Workbench
    from spectral_app.pipeline_routes import PipelineRoutes
    class App(PipelineRoutes,Workbench):pass
    app=App(model);r=next(e['recipe'] for e in app.bootstrap()['reversal_presets'] if e['id']==stock)
    point=np.array([[.18,.18,.18],[.35,.07,.015],[.03,.16,.24]])
    actual=model.sample(point,**model.parameters(r));core=model.core
    try:
        model.core=None;reference=model.sample(point,**model.parameters(r))
    finally:model.core=core
    for key in ['transmission','XYZ','display_rgb']:np.testing.assert_allclose(actual[key],reference[key],atol=2e-13,rtol=3e-13)
    original=model.sample(point,**model.parameters(template('slide')))
    assert np.max(np.abs(actual['display_rgb']-original['display_rgb']))>.01
    result=app.export({'recipe':r,'purpose':'display','grid':65})
    assert result['verification']['integrity_passed']
    assert result['verification']['ocio_vs_float64_max_abs_output']<2e-5
    directory=model.output/'exports'/result['export_id']
    saved=json.loads((directory/'recipe.json').read_text())
    assert saved['film']['stock']==stock
    header=(directory/'recipe.cube').read_text().split('LUT_3D_SIZE')[0]
    assert 'Yangming Feng' in header and r['film']['custom_material']['name'] in header and 'Status A' in header and 'E-6' in header
    assert saved['film']['custom_material']['provenance']['source_pdf_sha256'] in header
    assert 'Neutral Status A model fit max residual:' in header


@pytest.mark.parametrize('broken',[[],None,{'provenance':[]}])
def test_non_e100_slide_rejects_malformed_material(model,broken):
    r=template('slide');r['film'].update(stock='velvia100',custom_material=broken)
    with pytest.raises(RecipeError):model.validate(r)


@pytest.mark.parametrize('stock,limit',[('velvia50',.012),('provia100f',.006)])
def test_raster_source_fit_policy_is_stock_specific_and_csv_remains_strict(model,stock,limit):
    from spectral_app.reversal_presets import load_reversal_presets
    material=next(e['material'] for e in load_reversal_presets(ROOT) if e['id']==stock)
    assert model.material_fit_tolerance(material)==limit
    film,meta=model.material(material)
    assert meta['neutral_StatusA_max_error_D']<=limit
    assert meta['neutral_fit_limit_D']==limit
    changed=copy.deepcopy(material);changed['characteristic']['import_file']={'name':'user.csv'}
    assert model.material_fit_tolerance(changed)==limit # lossless own-CSV round trip
    changed['characteristic']['channels']['R'][0]+=.001
    assert model.material_fit_tolerance(changed)==.001
    assert model.material_fit_tolerance({})==.001


@pytest.mark.parametrize('stock',['velvia50','provia100f'])
def test_manufacturer_channel_identity_and_independent_viewing_integral(model,stock):
    import json,colour
    from spectral_app.reversal_presets import load_reversal_presets
    from spectral_app.pipeline_routes import PipelineRoutes
    from experiments.gui_recipe_server import Workbench
    class App(PipelineRoutes,Workbench):pass
    e=next(e for e in load_reversal_presets(ROOT) if e['id']==stock)
    raw=json.loads((ROOT/f'local/materials/reversal-presets-v1/{stock}-source-points.json').read_text())
    if stock=='provia100f':assert 1.05<max(p[1] for p in raw['sensitivity']['B'])<1.15 # original peak exceeds the 1.0 gridline
    for role,ranges in [('sensitivity',{'B':(430,465),'G':(530,560),'R':(625,665)}),('dyes',{'Y':(430,465),'M':(525,560),'C':(635,685)})]:
        for c,(low,high) in ranges.items():
            a=np.array(raw[role][c]);assert low<a[np.argmax(a[:,1]),0]<high
    r=next(e['recipe'] for e in App(model).bootstrap()['reversal_presets'] if e['id']==stock)
    rho=np.array([[.18]*len(model.source_wavelengths),np.linspace(.02,.65,len(model.source_wavelengths))])
    sample=model.sample_spectra(rho,**model.parameters(r));wl=model.view_wavelengths
    observer=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(colour.SpectralShape(400,700,2))
    light=model.light('D50');cmf=observer.values
    xyz=np.trapezoid(sample['transmission'][:,:,None]*light[None,:,None]*cmf[None,:,:],wl,axis=1)/np.trapezoid(light*cmf[:,1],wl)*r['viewing']['gain']
    np.testing.assert_allclose(xyz,sample['XYZ_view'],atol=2e-5,rtol=2e-4)
