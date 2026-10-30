import json
import numpy as np
import pytest


def test_response_loader_preserves_source_band_and_rejects_extrapolation(tmp_path):
    from spectral_app.scanning.sensitivity import load_response
    wave=np.arange(400,701,10.)
    values=np.column_stack([np.exp(-.5*((wave-c)/35)**2) for c in [620,540,450]])
    path=tmp_path/'prediction.csv'
    np.savetxt(path,np.column_stack([wave,values]),delimiter=',',header='wavelength,red,green,blue',comments='')
    response=load_response(path,np.arange(400,701.),kind='prediction',model='ILCE-7RM5')
    assert response['kind']=='prediction' and response['source_band_nm']==[400.,700.]
    assert response['source_step_nm']==10 and response['values'].shape==(301,3)
    with pytest.raises(ValueError,match='coverage'):
        load_response(path,np.arange(391,731.),kind='prediction',model='ILCE-7RM5')
    data={'header':{'model':'ILCE-7RM4','measurement_equipment':'lightsaber','document_creator':'wetadigital','license':'Apache-2.0'},
        'spectral_data':{'units':'relative','index':{'main':['R','G','B']},'data':{'main':{str(w):v.tolist() for w,v in zip(wave,values)}}}}
    target=tmp_path/'measured.json';target.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='identity'):
        load_response(target,wave,kind='measured',model='ILCE-7RM5')
    result=load_response(target,wave,kind='measured',model='ILCE-7RM4')
    assert result['source_header']['measurement_equipment']=='lightsaber'


def test_common_light_fit_predicts_heldout_filters_and_is_channel_scale_invariant():
    from spectral_app.scanning.sensitivity import fit_effective_light,light_weights
    wave=np.arange(400,701,2.)
    response=np.column_stack([np.exp(-.5*((wave-c)/35)**2) for c in [620,540,450]])
    lamp=sum(a*np.exp(-.5*((wave-c)/10)**2) for a,c in [(1,440),(2,530),(1,640)])
    weights=light_weights(wave,response,lamp)*[.9,1.1,.8]
    rng=np.random.default_rng(412)
    absorbers=np.array([np.exp(-.5*((wave-c)/25)**2) for c in [410,460,520,580,640,690]])
    spectra=np.exp(-rng.uniform(0,2,(48,6))@absorbers)
    observed=spectra@weights
    fit=fit_effective_light(wave,response,spectra[:36],observed[:36],sigma=10,ridge=1e-8)
    assert np.min(fit['light'])>=0 and np.min(fit['weights'])>=0
    assert np.sqrt(np.mean(np.log10((spectra[36:]@fit['weights'])/observed[36:])**2))<.002
    scaled=fit_effective_light(wave,response*[3,.4,1.7],spectra[:36],observed[:36],sigma=10,ridge=1e-8)
    np.testing.assert_allclose(spectra[36:]@fit['weights'],spectra[36:]@scaled['weights'],atol=2e-5)


def test_border_alignment_freezes_same_observed_base_without_mutating_weights():
    from spectral_app.scanning.sensitivity import align_border
    weights=np.array([[.2,.3,.4],[.8,.7,.6]])
    original=weights.copy();base=np.array([.4,.6]);observed=np.array([.3,.2,.1])
    aligned,gain=align_border(weights,base,observed)
    np.testing.assert_allclose(base@aligned,observed,atol=1e-15)
    np.testing.assert_array_equal(weights,original)
    np.testing.assert_allclose(aligned,weights*gain)


def test_display_comparison_reports_invalid_and_domain_samples_without_dropping_them():
    from spectral_app.scanning.sensitivity import display_difference
    a=np.array([[.2,.3,.4],[.5,.5,.5],[.9,.8,.7]])
    b=a.copy();b[1,0]+=.1
    result=display_difference(a,b,valid=np.array([True,False,True]))
    assert result['count']==3 and result['valid_count']==2
    assert result['all']['max_channel_codes']['max']==pytest.approx(25.5)
    assert result['all']['deltaE00']['max']>0
    assert result['valid']['deltaE00']['max']==0


def test_border_alignment_accepts_only_roundoff_negative_response_and_does_not_mutate():
    from spectral_app.scanning.sensitivity import align_border
    weights=np.array([[-3.5909992250157564e-20,.01,.02],[.03,.02,.01]])
    before=weights.copy();base=np.array([.4,.6]);observed=np.array([.19,.27,.11])
    aligned,gain=align_border(weights,base,observed)
    assert np.min(aligned)>=0 and np.isfinite(aligned).all()
    np.testing.assert_allclose(base@aligned,observed,atol=1e-15)
    np.testing.assert_array_equal(weights,before)
    with pytest.raises(ValueError,match='负值'):
        align_border(np.array([[-1e-5,.01,.02],[.03,.02,.01]]),base,observed)


def test_response_fit_projects_solver_roundoff_to_nonnegative_coefficients(monkeypatch):
    from spectral_app.scanning import calibration
    from types import SimpleNamespace
    def solved(matrix,target,**kwargs):
        x=np.zeros(matrix.shape[1]);x[0]=1;x[-1]=-1e-18
        return SimpleNamespace(success=True,x=x)
    monkeypatch.setattr(calibration,'lsq_linear',solved)
    wave=np.arange(400,701.);transmission=np.full((4,len(wave)),.5)
    result=calibration.fit_response(wave,transmission,np.full((4,3),.5))
    assert np.min(result['weights'])>=0
    assert np.all(result['weights'].sum(0)>0)
