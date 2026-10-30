import copy
from pathlib import Path
import numpy as np
import pytest
from experiments.gui_recipe_server import template

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    if not Path('local/materials/5207-v1/provenance.json').exists():pytest.skip('Local manufacturer materials required.')
    return SpectralModel(Path('local/film-color-slides/hyperspectral-demo'),Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'),tmp_path_factory.mktemp('5207'),core=NativeCore())


def test_application_updates_saved_daylight_and_tungsten_stocks_to_their_own_reference(model):
    from spectral_app.application import Application
    app=Application(model);data=app.bootstrap();seen=set()
    for group in ('templates','recipe_presets','reversal_presets'):
        for entry in data.get(group,[]):
            old=copy.deepcopy(entry['recipe']);stock=old['film']['stock']
            old['scene']={'illuminant':'CIE_D','temperature_k':6500};old['revision']=10
            result=app.validate_recipe(old,compute=True)['normalized_recipe']
            expected={'illuminant':'Planck','temperature_k':3200} if stock in ('5213','5219') else {'illuminant':'CIE_D','temperature_k':5500}
            assert result['scene']==expected
            assert result['revision']==11
            for field in old.keys()-{'scene','revision'}:assert result[field]==old[field]
            assert app.validate_recipe(result,compute=True)['normalized_recipe']==result
            seen.add(stock)
    assert seen=={'5203','5207','5213','5219','E100','velvia50','velvia100','provia100f'}


def test_5207_preserves_published_dmin_subtracted_dye_basis(model):
    dyes=model.negative_material['dyes']
    assert dyes['quantity']=='net_spectral_density'
    for c in 'CMY':
        trace=np.array(model.calibration['traces']['5207_dye_'+c])
        np.testing.assert_allclose(dyes['channels'][c],np.interp(dyes['wavelengths_nm'],trace[:,0],trace[:,1]),rtol=1e-13,atol=1e-14)
    assert min(dyes['channels']['M'])<-.01
    # Signed increments are permitted, absolute density is not negative.
    n=model.negative;lo=n.amounts.min(0);hi=n.amounts.max(0)
    bound=n.base+np.where(n.dyes>=0,n.dyes*lo,n.dyes*hi).sum(1)
    assert np.min(bound)>0
    assert n.metadata['minimum_absolute_density_bound_D']==pytest.approx(bound.min())


def test_5207_d55_gray_exposure_uses_the_runtime_light_normalization(model):
    h=model._film_stage(np.full(len(model.source_wavelengths),.18),0,5500,model.negative)[0]
    np.testing.assert_allclose(h,np.ones(3),rtol=2e-14,atol=2e-14)


def test_c41_material_can_use_either_positive_method_without_refitting(model):
    material=copy.deepcopy(model.negative_material)
    material['name']='C-41 test / 5207 temporary dyes'
    material['provenance']={'stock_id':'C41-test','process':'C-41','density_metric':'Status M',
        'substitutions':{'dyes':'Kodak 5207 / ECN-2'},'summary':'Experimental; 5207 dyes borrowed'}
    recipe=model.validate(template('print'))['normalized_recipe']
    recipe['film'].update(stock='C41-test',custom_material=material)
    checked=model.validate(recipe)['normalized_recipe']
    assert checked['film']['stock']=='C41-test'
    assert 'negative_output' not in checked
    assert model.route_material(checked).metadata['provenance']==material['provenance']
    before=model.sample_spectra(np.full(len(model.source_wavelengths),.18),**model.parameters(checked))
    checked['route']='negative'
    apd=model.validate(checked)['normalized_recipe']
    assert apd['negative_output']['metric']=='APD'
    assert apd['film']==checked['film']
    assert apd['printing']==checked['printing']
    after=model.sample_spectra(np.full(len(model.source_wavelengths),.18),**model.parameters(apd))
    np.testing.assert_array_equal(before['transmission'],after['transmission'])
    np.testing.assert_array_equal(before['dye_amounts'],after['dye_amounts'])
    assert 'apd' in after and 'paper_reflectance' not in after
    assert 'paper_reflectance' in before and 'apd' not in before
    assert np.isfinite(after['display_rgb']).all()


def test_other_stock_requires_matching_process_and_explicit_status_m_material(model):
    from experiments.gui_recipe_server import RecipeError
    recipe=model.validate(template('negative'))['normalized_recipe']
    recipe['film']['stock']='other'
    with pytest.raises(RecipeError):model.validate(recipe)
    material=copy.deepcopy(model.negative_material)
    material['provenance']={'stock_id':'other','process':'E-6','density_metric':'Status M'}
    recipe['film']['custom_material']=material
    with pytest.raises(RecipeError):model.validate(recipe)


def test_tungsten_camera_light_is_planck_not_extrapolated_cie_daylight(model):
    import colour
    recipe=model.validate(template('negative'))['normalized_recipe']
    recipe['scene']={'illuminant':'Planck','temperature_k':3200}
    recipe=model.validate(recipe)['normalized_recipe']
    light=model.scene_light(3200,'Planck')
    independent=colour.sd_blackbody(3200,colour.SpectralShape(400,720,10)).values
    np.testing.assert_allclose(light/light.max(),independent/independent.max(),rtol=3e-4)
    from experiments.hsi_raw_lut import csv, interpolate
    from spectral_lut.reference import quadrature_widths
    cmf=interpolate(csv(model.archive.parent/'data/CIE_xyz_official.csv'),model.source_wavelengths)
    weights=cmf[:,1]*quadrature_widths(model.source_wavelengths)
    assert light@weights==pytest.approx(model.source_light@weights,rel=1e-13)
    output=model.sample_spectra(np.full(len(light),.18),**model.parameters(recipe))
    assert np.isfinite(output['display_rgb']).all()


@pytest.mark.parametrize('route',['negative','print'])
def test_5207_defaults_follow_the_manufacturer_d55_exposure_conditions(model,route):
    recipe=model.validate(template(route))['normalized_recipe']
    assert recipe['scene']=={'illuminant':'CIE_D','temperature_k':5500}
    assert model.parameters(recipe)['scene_temperature_k']==5500
    assert recipe['film']['exposure_ev']==0
    gray=np.full(len(model.source_wavelengths),.18)
    result=model.sample_spectra(gray,**model.parameters(recipe))
    np.testing.assert_allclose(result['exposure'],[1,1,1],rtol=2e-14,atol=2e-14)


def test_paper_conditions_come_from_its_own_status_a_ra4_document(model):
    conditions=model.paper.metadata['published_reference_conditions']
    assert conditions['density_metric']=='Status A'
    assert conditions['process']=='RA-4'
    assert conditions['developer_temperature_c']==35 and conditions['developer_time_seconds']==45
    assert conditions['curve_exposure_seconds']==.5
    assert conditions['evaluation_cct_k']==5000 and conditions['evaluation_cct_tolerance_k']==1000
    assert conditions['evaluation_minimum_lux']==538
    assert conditions['specified_enlarger_temperature_k'] is None
    assert model.paper.metadata['reference_scene_temperature_k']==6500
    assert 'software' in model.paper.metadata['calibration']


@pytest.mark.parametrize('route',['negative','print'])
def test_old_inherited_d65_default_migrates_but_explicit_color_temperature_is_retained(model,route):
    recipe=model.validate(template(route))['normalized_recipe']
    recipe['asset_refs']=copy.deepcopy(model.legacy_negative_refs[-1]);recipe['scene']={'illuminant':'D65'};recipe['revision']=9
    recipe['film']['exposure_ev']=.7
    migrated=model.validate(recipe)['normalized_recipe']
    assert migrated['scene']=={'illuminant':'CIE_D','temperature_k':5500}
    assert migrated['revision']==10 and migrated['film']==recipe['film']
    assert model.validate(migrated)['normalized_recipe']==migrated
    for k in [4500,5500,6500,8000]:
        recipe['scene']={'illuminant':'CIE_D','temperature_k':k}
        result=model.validate(recipe)['normalized_recipe']
        assert result['scene']==recipe['scene']
        assert model.parameters(result)['scene_temperature_k']==k


def test_negative_fit_matches_original_status_m_without_apd_targets(model):
    from spectral_lut.negative import integrate_density
    n=model.negative;targets=np.array([model.negative_material['characteristic']['channels'][c] for c in 'RGB']).T
    transmission=10**-(n.base+n.amounts@n.dyes.T)
    measured=integrate_density(transmission,model.status_m_weights)
    assert n.metadata['fit_metric']=='Status M'
    assert np.max(abs(measured-targets))<.006
    assert 'dmin_apd' not in n.metadata and 'status_m_to_apd' not in n.metadata
    assert n.metadata['neutral_max_error_D']==pytest.approx(np.max(abs(measured-targets)))


def test_apd_output_weights_cannot_change_film_fit_or_optical_print(model):
    r=model.validate(template('print'))['normalized_recipe'];spectra=np.random.default_rng(71).uniform(.01,1,(7,len(model.source_wavelengths)))
    before=model.sample_spectra(spectra,**model.parameters(r));fit=model._negative_fit(model.negative_material)
    original=model.apd_weights
    compatibility=copy.deepcopy(model.calibration['status_m_to_apd'])
    try:
        model.apd_weights=np.roll(original,23,axis=0)
        model.calibration['status_m_to_apd']={'matrix':None,'offset':None}
        changed=model._negative_fit(model.negative_material)
        after=model.sample_spectra(spectra,**model.parameters(r))
        for key in ['base','amounts','dyes','sensitivity']:np.testing.assert_array_equal(getattr(changed,key),getattr(fit,key))
        assert changed.metadata==fit.metadata
        for key in ['transmission','paper_exposure','paper_reflectance','XYZ','display_rgb']:np.testing.assert_array_equal(before[key],after[key])
    finally:
        model.apd_weights=original
        model.calibration['status_m_to_apd']=compatibility


@pytest.mark.parametrize('route',['negative','print'])
@pytest.mark.parametrize('version',[1,2,3])
def test_5207_known_model_revision_migrates_without_resetting_recipe(model,route,version):
    r=model.validate(template(route))['normalized_recipe']
    assert r['asset_refs']['model']=='5207-paper-reference/4'
    old=copy.deepcopy(r);old['asset_refs']=copy.deepcopy(model.legacy_negative_refs[version-1]);old['revision']=7
    old['film']['exposure_ev']=.8;old['printing']['filters']=[.1,.2,.3]
    result=model.validate(old)['normalized_recipe']
    assert result['revision']==8
    assert result['film']==old['film'] and result['printing']==old['printing']
    assert old['asset_refs']['model']==f'5207-paper-reference/{version}'
    assert model.validate(result)['normalized_recipe']==result
    old['asset_refs']['sha256']['5207_dyes.csv']='0'*64
    with pytest.raises(ValueError):model.validate(old)


def test_signed_dye_csv_requires_explicit_net_density_and_passive_combination(model):
    from experiments.gui_recipe_server import RecipeError
    r=model.validate(template('negative'))['normalized_recipe']
    custom=copy.deepcopy(model.negative_material)
    custom['dyes']['quantity']='net_spectral_density'
    r['film']['custom_material']=custom
    model.validate(r,compute=True)
    custom['dyes']['quantity']='spectral_density'
    with pytest.raises(RecipeError):model.validate(r,compute=True)
    custom['dyes']['quantity']='net_spectral_density'
    # A neutral fit alone must not accept a basis that amplifies light for
    # independent colored layer amounts. Check the whole coefficient box.
    custom['dyes']['channels']['M'][20]=-10
    with pytest.raises(RecipeError):model.validate(r,compute=True)


@pytest.mark.parametrize('route,view',[('slide','Display Encoding'),('print','Display Encoding'),
    ('negative','ACES 2.0 - SDR 100 nits')])
def test_old_default_migrates_once_in_session_without_resetting_material_or_viewing(model,route,view):
    from spectral_app.application import Application
    r=model.validate(template(route))['normalized_recipe']
    r['display']={'view':'Default','target':'Display P3'};r['revision']=11
    r['viewing']['gain']=2.5;r['film']['exposure_ev']=.7
    original=copy.deepcopy(r)
    app=Application(model)
    state={'documents':[{'recipe':r,'baseline':copy.deepcopy(r)}],'active_id':r['id']}
    restored=app._validated_session(state)
    assert r==original
    for entry in ['recipe','baseline']:
        migrated=restored['documents'][0][entry]
        assert migrated['display']['view']==view
        assert migrated['display']['target']=='Display P3'
        assert migrated['revision']==12
        assert migrated['viewing']==original['viewing']
        assert migrated['film']==original['film']
        assert model.validate(migrated)['normalized_recipe']==migrated
        # A subsequent explicit OpenDRT selection must remain available.
        migrated['display']['view']='Default'
        assert model.validate(migrated)['normalized_recipe']['display']['view']=='Default'


def test_both_routes_compute_and_keep_polarity_without_image_calibration(model):
    gray=model.srgb_to_ap1(np.repeat(np.linspace(.01,.95,33)[:,None],3,1))
    for route in ['negative','print']:
        recipe=model.validate(template(route),compute=True)['normalized_recipe']
        out=model.sample(gray,**model.parameters(recipe))
        assert np.isfinite(out['XYZ']).all()
        assert np.all(np.diff(out['XYZ'][:,1])>=-1e-9)
        assert np.all((out['transmission']>0)&(out['transmission']<=1))
        if route=='print':assert np.all((out['paper_reflectance']>0)&(out['paper_reflectance']<=1))
    assert model.negative.metadata['neutral_max_error_D']<.006


def test_native_matches_float64_at_every_material_stage(model):
    rgb=np.random.default_rng(2).uniform(0,2,(83,3));core=model.core
    for route in ['negative','print']:
        p=model.parameters(model.validate(template(route))['normalized_recipe'])
        native=model.sample(rgb,**p)
        try:
            model.core=None;reference=model.sample(rgb,**p)
        finally:model.core=core
        for key in ['exposure','dye_amounts','transmission','XYZ']+(['paper_exposure','paper_reflectance'] if route=='print' else ['apd']):
            np.testing.assert_allclose(native[key],reference[key],rtol=1e-10,atol=2e-12)


def test_apd_ignores_viewing_and_printing_settings_and_is_not_double_converted(model):
    r=model.validate(template('negative'))['normalized_recipe'];p=model.parameters(r);rgb=np.array([.1,.2,.3])
    a=model.sample(rgb,**p)
    r['viewing']={'illuminant':'D65','gain':7};r['printing']['exposure_ev']=2
    b=model.sample(rgb,**model.parameters(r))
    np.testing.assert_array_equal(a['XYZ'],b['XYZ'])
    from spectral_lut.negative import integrate_density
    np.testing.assert_allclose(a['apd'],integrate_density(a['transmission'],model.apd_weights))


def test_printing_exposure_and_filters_have_independent_physical_effects(model):
    r=model.validate(template('print'))['normalized_recipe'];rgb=np.array([.18]*3)
    a=model.sample(rgb,**model.parameters(r));r['printing']['exposure_ev']=1
    b=model.sample(rgb,**model.parameters(r))
    np.testing.assert_allclose(b['paper_exposure'],a['paper_exposure']*2,rtol=1e-14)
    assert b['XYZ'][1]<a['XYZ'][1]
    r['printing']['filters']=[.2,0,0]
    c=model.sample(rgb,**model.parameters(r));assert not np.allclose(c['paper_exposure'],b['paper_exposure'])
    np.testing.assert_array_equal(a['transmission'],c['transmission'])


def test_print_branch_uses_transmission_without_apd_or_adx_intermediates(model):
    r=model.validate(template('print'))['normalized_recipe']
    result=model.sample_spectra(np.full((1,33),.18),**model.parameters(r))
    assert all(k in result for k in ['transmission','paper_exposure','paper_reflectance','XYZ_view'])
    assert 'apd' not in result and 'adx16_float' not in result and 'ACES' not in result


def test_application_connects_route_nodes_and_exports_same_pipeline(model):
    from spectral_app.application import Application
    app=Application(model)
    boot=app.bootstrap()
    assert all(t['available'] for t in boot['templates'])
    for route in ['negative','print']:
        recipe=next(t['recipe'] for t in boot['templates'] if t['id']==route)
        result=app.evaluate({'recipe':recipe,'input':{'id':'chart'},'selection':{'sample_id':'cc01'}})
        nodes=result['current']['nodes']
        assert 'apd' in nodes if route=='negative' else all(k in nodes for k in ['enlarger','filter','paper','view'])
        assert result['reference']['includes_film'] is False
        assert result['conditions']['material']['neutral_max_error_D']<.006
        assert nodes['film']['name'].startswith('5207')
        exported=app.export({'recipe':recipe,'purpose':'internal','grid':9})
        assert exported['ok']


def test_manufacturer_plot_detail_is_separate_from_calculation_material(model):
    from spectral_app.application import Application
    before=copy.deepcopy(model.negative_material)
    boot=Application(model).bootstrap()
    plot=boot['spectral_assets']['material_plot_sources']['legacy_5207']['sensitivity']
    assert plot['unit']=='relative'
    assert plot['source']=='Kodak H-1-5207t, July 2015, p4'
    assert plot['calculation_step_nm']==10
    for channel in 'RGB':
        native=np.array(model.calibration['traces']['5207_sensitivity_'+channel])
        series=plot['channels'][channel]
        np.testing.assert_array_equal(series['wavelengths_nm'],native[:,0])
        np.testing.assert_allclose(series['values'],10**native[:,1],rtol=1e-14)
        assert len(series['values'])>150
    assert model.negative_material==before
    assert len(boot['spectral_assets']['5207']['sensitivity']['wavelengths_nm'])==33
    assert [t['name'] for t in boot['templates']]==['反转片 · 透射观看','负片 · APD 输出','负片 · 光学放大']


@pytest.mark.parametrize('route',['slide','negative','print'])
def test_chart_patch_diagnostics_use_that_patches_measured_reflectance(model,route):
    from spectral_app.application import Application
    app=Application(model)
    recipe=model.validate(template(route))['normalized_recipe']
    before=copy.deepcopy(recipe)
    values=[]
    for index in [12,14]:
        patch=f'cc{index+1:02d}'
        result=app.evaluate({'recipe':recipe,'input':{'id':'chart','exposure_ev':0},'selection':{'sample_id':patch}})
        assert result['selection']=={'sample_id':patch}
        rho=model.measured_inputs['chart'][(index//6)*64+32,(index%6)*64+32]
        incident=np.array(result['current']['nodes']['light']['output']['series'][0]['values'])
        np.testing.assert_allclose(incident,rho*model.scene_light(recipe['scene'].get('temperature_k',6500))*np.exp2(recipe['film']['exposure_ev']),rtol=1e-13)
        values.append(incident)
    assert not np.allclose(*values)
    assert recipe==before


def test_apd_interface_trace_matches_actual_sample_and_final_xyz(model):
    from spectral_app.application import Application
    app=Application(model);recipe=model.validate(template('negative'))['normalized_recipe']
    for patch in ['cc13','cc15','cc22']:
        result=app.evaluate({'recipe':recipe,'input':{'id':'chart'},'selection':{'sample_id':patch}})
        nodes=result['current']['nodes'];trace=nodes['interface']['details']['process']
        np.testing.assert_array_equal(trace['input'],nodes['apd']['output']['values'])
        np.testing.assert_allclose(trace['output'],nodes['interface']['output']['values'],rtol=2e-14,atol=1e-14)
        np.testing.assert_allclose(trace['steps'][1]['output'],nodes['interface']['details']['adx16_float_code_values'],rtol=1e-14)
        np.testing.assert_allclose(trace['steps'][6]['output'],nodes['interface']['details']['aces2065_1_AP0_D60'],rtol=1e-14)


@pytest.mark.parametrize('scene',[16,38,43])
def test_saved_manuscript_adx_replays_with_shared_aces2_display(model,scene):
    # Historical output arrays are evidence, not application code or profiles.
    reference=Path('video/assets/experiments/apd-standard-reference-v1/intermediate')/f'scene{scene}.npz'
    if not reference.exists():pytest.skip('Optional manuscript comparison arrays required')
    from spectral_lut.negative import adx_to_aces
    from experiments.hsi_raw_lut import D60,D65,cat
    import colour
    with np.load(reference) as saved:
        aces=adx_to_aces(saved['ADX16'].astype(np.float64))
        xyz=aces@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ.T@cat(D60,D65).T
        current=model.render(xyz,'ACES 2.0 - SDR 100 nits','sRGB')
        expected_xyz=saved['ACES2065_1']@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ.T@cat(D60,D65).T
        expected=model.render(expected_xyz,'ACES 2.0 - SDR 100 nits','sRGB')
        codes=np.abs(current-expected)*255
        assert codes.max()<.01


@pytest.mark.parametrize('route',['slide','negative','print'])
def test_session_migrates_old_aces_in_recipes_and_baselines(model,route):
    from spectral_app.application import Application
    app=Application(model);r=model.validate(template(route))['normalized_recipe']
    baseline=copy.deepcopy(r);r['display']['view']='ACES 1.0 - SDR Video';baseline['display']['view']='ACES 1.1 - SDR Video'
    original=copy.deepcopy(r)
    state=app._validated_session({'active_id':r['id'],'documents':[{'recipe':r,'baseline':baseline}]})
    assert r==original
    for entry in ['recipe','baseline']:
        migrated=state['documents'][0][entry]
        assert migrated['display']['view']=='ACES 2.0 - SDR 100 nits'
        assert migrated['revision']==r['revision']+1


def test_measured_inputs_bypass_rgb_prior_and_ordinary_rgb_does_not(model):
    from spectral_app.application import Application
    app=Application(model);r=model.validate(template('negative'))['normalized_recipe']
    result=app.evaluate({'recipe':r,'input':{'id':'chart'},'selection':{'sample_id':'cc03'}})
    assert result['conditions']['preview_input_method']=='measured_spectral'
    reflectance=model.measured_inputs['chart'][32,160]
    expected=model.sample_spectra(reflectance,**model.parameters(r))
    np.testing.assert_allclose(result['current']['sample']['xyz_d65'],expected['XYZ'],atol=1e-14)
    assert not np.allclose(expected['XYZ'],model.sample(model.inputs['chart'][32,160],**model.parameters(r))['XYZ'])


def test_csv_negative_and_paper_materials_are_used_not_just_displayed(model):
    r=model.validate(template('print'))['normalized_recipe'];rgb=np.array([.3,.15,.1])
    a=model.sample(rgb,**model.parameters(r))
    custom=copy.deepcopy(model.negative_material)
    custom['sensitivity']['channels']['R']=[v*1.05 for v in custom['sensitivity']['channels']['R']]
    r['film']['custom_material']=custom
    b=model.sample(rgb,**model.parameters(model.validate(r)['normalized_recipe']))
    assert not np.allclose(a['transmission'],b['transmission'])
    custom=copy.deepcopy(model.paper_material)
    custom['sensitivity']['channels']['B']=[v*1.05 for v in custom['sensitivity']['channels']['B']]
    r['printing']['custom_material']=custom
    c=model.sample(rgb,**model.parameters(model.validate(r)['normalized_recipe']))
    assert not np.allclose(b['paper_reflectance'],c['paper_reflectance'])
    np.testing.assert_array_equal(b['transmission'],c['transmission'])


def test_paper_software_gray_anchor_has_its_declared_luminance_scale(model):
    r=model.validate(template('print'))['normalized_recipe']
    r['scene']={'illuminant':'CIE_D','temperature_k':6500}
    o=model.sample_spectra(np.full(len(model.source_wavelengths),.18),**model.parameters(r))
    assert o['XYZ_view'][1]==pytest.approx(.18,abs=1e-8)


def test_invalid_negative_structure_and_mislabeled_base_are_rejected(model):
    from experiments.gui_recipe_server import RecipeError
    r=template('negative');r['film']=[]
    with pytest.raises(RecipeError):model.validate(r)
    r=template('negative');r['film']['custom_material']=copy.deepcopy(model.negative_material)
    r['film']['custom_material']['base']['quantity']='spectral_transmittance'
    with pytest.raises(RecipeError):model.validate(r)


def test_print_node_spectra_include_exposure_at_the_node_that_controls_it(model):
    from spectral_app.application import Application
    app=Application(model);r=model.validate(template('print'))['normalized_recipe']
    image=np.array([[.18,.12,.08]])
    a=app.evaluate_one(r,image,image[0])['nodes'];r['printing']['exposure_ev']=1
    b=app.evaluate_one(r,image,image[0])['nodes']
    def values(nodes,key):return np.array(nodes[key]['output']['series'][0]['values'])
    np.testing.assert_allclose(values(b,'enlarger'),values(a,'enlarger')*2,atol=1e-15)
    np.testing.assert_allclose(values(b,'filter'),values(b,'enlarger'),atol=1e-15)


def test_lut_export_distinguishes_spectral_approximation_and_interpolation(model):
    from spectral_app.application import Application
    app=Application(model);r=model.validate(template('negative'))['normalized_recipe']
    result=app.export({'recipe':r,'purpose':'internal','grid':9})
    check=result['verification']['spectral_reference']
    assert check['measured_input_count']==5376
    assert check['input_model']['family']=='negative'
    assert check['rgb_approximation']['pixel_count']>1000
    assert 'total_lut_vs_spectral' in check
    assert 'not real-film' in check['scope']


def test_printing_light_and_filter_csv_are_independent_replaceable_inputs(model):
    r=model.validate(template('print'))['normalized_recipe'];rgb=np.array([.18,.12,.05])
    a=model.sample(rgb,**model.parameters(r))
    grid=model.negative_wavelengths
    r['printing']['light']='custom'
    r['printing']['custom_spd']={'name':'test lamp','source':'synthetic test only','quantity':'relative_energy_spd','unit':'relative','wavelengths_nm':grid.tolist(),'values':np.ones(len(grid)).tolist()}
    b=model.sample(rgb,**model.parameters(model.validate(r)['normalized_recipe']))
    assert not np.allclose(a['paper_exposure'],b['paper_exposure'])
    r['printing']['custom_filters']={'name':'test filter','source':'synthetic test only','quantity':'spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'channels':{c:np.full(len(grid),i+1.).tolist() for i,c in enumerate('CMY')}}
    r['printing']['filters']=[.1,0,0]
    c=model.sample(rgb,**model.parameters(model.validate(r)['normalized_recipe']))
    np.testing.assert_allclose(c['filter_transmission'],10**-.1)
    np.testing.assert_array_equal(c['transmission'],a['transmission'])


def test_builtin_standard_weights_cannot_change_silently(tmp_path):
    import shutil
    from spectral_app.model import SpectralModel
    from experiments.gui_recipe_server import RecipeError
    directory=tmp_path/'materials';shutil.copytree('local/materials/5207-v1',directory)
    p=directory/'apd_weights.csv';s=p.read_text();p.write_text(s.replace('0.0001','0.0009',1))
    with pytest.raises(RecipeError,match='校验'):
        SpectralModel(Path('local/film-color-slides/hyperspectral-demo'),Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'),tmp_path/'output',materials=directory)


def test_every_node_uses_the_declared_plot_wire_format(model):
    from spectral_app.application import Application
    app=Application(model)
    for route in ['negative','print']:
        r=model.validate(template(route))['normalized_recipe'];nodes=app.evaluate_one(r,np.array([[.18]*3]),np.array([.18]*3))['nodes']
        for node in nodes.values():
            for key in ['input','output']:
                q=node[key]
                if q['kind']=='channels':
                    assert isinstance(q['labels'],list)
                    assert len(q['labels'])==len(q['values'])==3


def test_all_local_negative_materials_share_transmittance_between_positive_methods(model):
    import colour
    from spectral_app.presets import load_recipe_presets
    from spectral_app.pipeline_routes import PipelineRoutes
    entries=load_recipe_presets(Path('.'))
    if not entries:pytest.skip('Optional local material catalog required.')
    stocks={entry['recipe']['film']['stock']:entry['recipe'] for entry in entries}
    spectra=np.array([np.interp(model.source_wavelengths,sd.wavelengths,sd.values)
        for sd in colour.SDS_COLOURCHECKERS['BabelColor Average'].values()])
    routes=PipelineRoutes();routes.model=model
    for stock,source in stocks.items():
        results=[];materials=[]
        for route in ('negative','print'):
            recipe=copy.deepcopy(source);recipe['route']=route
            recipe=model.validate(recipe)['normalized_recipe']
            result=model.sample_spectra(spectra,**model.parameters(recipe))
            assert np.isfinite(result['display_rgb']).all(),(stock,route)
            results.append(result);materials.append(model.route_material(recipe).metadata['fingerprint'])
            assert ('apd' in result)==(route=='negative')
            assert ('paper_reflectance' in result)==(route=='print')
            conditions=routes.conditions(recipe)
            if route=='negative' and recipe['film']['custom_material']['provenance']['process']=='C-41':
                assert 'Experimental' in conditions['positive_method_scope']
        assert materials[0]==materials[1],stock
        np.testing.assert_array_equal(results[0]['transmission'],results[1]['transmission'])
        np.testing.assert_array_equal(results[0]['dye_amounts'],results[1]['dye_amounts'])


def test_c41_apd_display_cube_has_correct_scope_and_independent_file_execution(model):
    import json
    from spectral_app.presets import load_recipe_presets
    from spectral_app.pipeline_routes import PipelineRoutes
    from experiments.gui_recipe_server import Workbench
    class CombinationWorkbench(PipelineRoutes,Workbench):
        pass
    entries=load_recipe_presets(Path('.'))
    source=next((e['recipe'] for e in entries if e['recipe']['film']['stock']=='portra400'),None)
    if source is None:pytest.skip('Optional Portra material required.')
    recipe=copy.deepcopy(source);recipe['route']='negative'
    recipe['display']['view']='ACES 2.0 - SDR 100 nits'
    result=CombinationWorkbench(model).export({'recipe':recipe,'purpose':'display','grid':33})
    assert result['verification']['readback_exact']
    assert result['verification']['integrity_passed']
    assert result['verification']['ocio_vs_float64_max_abs_output']<2e-5
    directory=model.output/'exports'/result['export_id']
    header=(directory/'recipe.cube').read_text().split('LUT_3D_SIZE')[0]
    assert 'C-41' in header and 'Experimental application' in header
    assert 'Yangming Feng' in header and 'Output: sRGB encoded RGB / D65' in header
    frozen=json.loads((directory/'recipe.json').read_text())
    assert frozen['film']['stock']=='portra400'
    assert frozen['film']['custom_material']['provenance']['process']=='C-41'
