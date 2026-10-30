"""Analysis-only camera/light sensitivity; no RAW or application-state changes."""
import hashlib
import json
from pathlib import Path
import numpy as np
import colour
from scipy.optimize import least_squares
from .calibration import nonnegative_response
from spectral_lut.reference import quadrature_widths


def load_response(path,wavelengths,*,kind,model):
    path=Path(path);wave=np.asarray(wavelengths,float)
    if kind not in ('prediction','measured'):raise ValueError('Response provenance is required')
    header={}
    if path.suffix.lower()=='.json':
        source=json.loads(path.read_text());header=source['header'];spectral=source['spectral_data']
        if header.get('model')!=model:raise ValueError('Camera response identity differs')
        if kind=='measured' and not header.get('measurement_equipment'):raise ValueError('Measurement provenance missing')
        if spectral['units']!='relative' or spectral['index']['main']!=['R','G','B']:
            raise ValueError('Unsupported response units or channel order')
        items=sorted((float(w),v) for w,v in spectral['data']['main'].items())
        x=np.array([w for w,v in items]);values=np.array([v for w,v in items],float)
    else:
        if kind!='prediction':raise ValueError('CSV measurement needs a separately reviewed provenance record')
        data=np.loadtxt(path,delimiter=',',skiprows=1);x=data[:,0];values=data[:,1:]
    if (x.ndim!=1 or len(x)<4 or values.shape!=(len(x),3) or not np.isfinite(values).all()
            or not np.isfinite(x).all() or np.any(np.diff(x)<=0) or np.min(values)<0
            or np.any(values.max(0)<=0) or wave.ndim!=1 or len(wave)<2
            or not np.isfinite(wave).all() or np.any(np.diff(wave)<=0)):
        raise ValueError('Invalid camera response')
    if wave[0]<x[0] or wave[-1]>x[-1]:raise ValueError('Requested grid exceeds source coverage; no extrapolation')
    resampled=np.column_stack([np.interp(wave,x,values[:,c]) for c in range(3)])
    return {'model':model,'kind':kind,'source_band_nm':[float(x[0]),float(x[-1])],
        'source_step_nm':float(np.diff(x)[0]) if np.allclose(np.diff(x),np.diff(x)[0]) else None,
        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_header':header,
        'response_unit':'relative effective energy-response convention; not absolute QE',
        'interpolation':'linear in provided nonnegative response; no extrapolation',
        'wavelengths':wave,'values':resampled/resampled.max(0)}


def light_weights(wavelengths,response,light):
    wave=np.asarray(wavelengths,float);s=np.asarray(response,float);e=np.asarray(light,float)
    if (s.shape!=(len(wave),3) or e.shape!=(len(wave),) or not np.isfinite(s).all()
            or not np.isfinite(e).all() or np.min(s)<0 or np.min(e)<0):raise ValueError('Invalid response/light')
    weights=s*e[:,None]*quadrature_widths(wave)[:,None]
    if np.any(weights.sum(0)<=0):raise ValueError('Unilluminated camera channel')
    return weights/weights.sum(0)


def fit_effective_light(wavelengths,response,transmission,camera,*,sigma=10,ridge=.1):
    """One nonnegative effective energy SPD shared by all three fixed SSFs.

    The spectrum includes unknown optical transmission. Channel scale nuisance
    parameters are eliminated analytically in log10 space on training data only.
    A normalization constraint fixes the energy/scale gauge, not absolute power.
    """
    wave=np.asarray(wavelengths,float);s=np.asarray(response,float)
    t=np.asarray(transmission,float);rgb=np.asarray(camera,float);width=quadrature_widths(wave)
    if (s.shape!=(len(wave),3) or t.shape!=(len(rgb),len(wave)) or rgb.shape[1:]!=(3,)
            or len(rgb)<4 or not all(np.isfinite(a).all() for a in (s,t,rgb)) or np.min(s)<0
            or np.min(t)<0 or np.max(t)>1 or np.min(rgb)<=0 or np.any(s.sum(0)<=0)
            or not np.isfinite([sigma,ridge]).all() or sigma<=0 or ridge<0):
        raise ValueError('Invalid common-light calibration')
    centres=np.arange(wave[0],wave[-1]+1e-6,10.)
    basis=np.exp(-.5*((wave[:,None]-centres)/sigma)**2)
    basis/=np.sum(basis*width[:,None],axis=0)
    design=np.einsum('nl,lc,lk,l->nck',t,s,basis,width,optimize=True)
    k=len(centres);observed=np.log10(rgb)
    def residual(a):
        predicted=np.maximum(design@a,1e-300)
        error=np.log10(predicted)-observed;error-=error.mean(0)
        return np.r_[error.ravel(),np.sqrt(ridge)*a,10*(a.sum()-1)]
    def jacobian(a):
        predicted=np.maximum(design@a,1e-300)
        j=design/(predicted[...,None]*np.log(10));j-=j.mean(0)
        return np.vstack([j.reshape(-1,k),np.sqrt(ridge)*np.eye(k),10*np.ones((1,k))])
    fit=least_squares(residual,np.full(k,1/k),jac=jacobian,bounds=(1e-12,np.inf),
        ftol=1e-10,xtol=1e-10,gtol=1e-10,max_nfev=1000)
    if not fit.success:raise ValueError('Common-light fit did not converge')
    coefficients=fit.x/fit.x.sum();light=basis@coefficients
    raw_weights=s*light[:,None]*width[:,None];raw_prediction=t@raw_weights
    scale=10**np.mean(np.log10(rgb/raw_prediction),axis=0)
    weights=raw_weights*scale
    return {'light':light,'weights':weights,'prediction':t@weights,'coefficients':coefficients,
        'channel_scale':scale,'sigma_nm':sigma,'ridge':ridge,'basis_centres_nm':centres,
        'nfev':fit.nfev,'cost':float(fit.cost),'optimality':float(fit.optimality)}


def cross_validate_light(wavelengths,response,transmission,camera,*,sigma=10,ridge=.1):
    t=np.asarray(transmission,float);rgb=np.asarray(camera,float)
    if len(t)!=24:raise ValueError('Expected four-by-six measured transmission card')
    groups=np.arange(24)%6;outer=np.zeros_like(rgb)
    for fold in range(6):
        keep=groups!=fold
        fit=fit_effective_light(wavelengths,response,t[keep],rgb[keep],sigma=sigma,ridge=ridge)
        outer[~keep]=t[~keep]@fit['weights']
    fitted=fit_effective_light(wavelengths,response,t,rgb,sigma=sigma,ridge=ridge)
    error=np.log10(outer/rgb)
    return {**fitted,'outer_prediction':outer,'outer_RMS_D':float(np.sqrt(np.mean(error**2))),
        'outer_max_D':float(np.max(np.abs(error))),
        'training_RMS_D':float(np.sqrt(np.mean(np.log10(fitted['prediction']/rgb)**2))),
        'validation':'six physical-column holdouts; fixed predeclared hyperparameters; one target only'}


def align_border(weights,base_transmission,observed):
    w=np.asarray(weights,float);base=np.asarray(base_transmission,float);rgb=np.asarray(observed,float)
    if base.ndim!=1 or not base.size or w.shape!=(len(base),3) or rgb.shape!=(3,):
        raise ValueError('扫描标定与片基的波长或通道数量不匹配，请重新建立标定。')
    w=nonnegative_response(w)
    if not np.isfinite(base).all() or np.any(base<0) or np.any(base>1):
        raise ValueError('胶片片基模型的透射率无效，请检查材料资料。')
    if not np.isfinite(rgb).all() or np.any(rgb<=0):
        raise ValueError('片基取样信号无效或过暗，请重新选择未曝光片边。')
    predicted=base@w
    if np.any(predicted<=0):raise ValueError('扫描标定无法预测片基信号，请重新建立标定。')
    with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
        gain=rgb/predicted;aligned=w*gain
    if not np.isfinite(gain).all() or not np.isfinite(aligned).all():
        raise ValueError('片基对齐增益无效，请检查标定和片基取样。')
    return aligned,gain


def display_difference(reference,actual,*,valid=None):
    a,b=np.asarray(reference,float),np.asarray(actual,float)
    if a.ndim!=2 or a.shape[1]!=3 or b.shape!=a.shape or not np.isfinite([a,b]).all():
        raise ValueError('Expected finite display RGB samples')
    valid=np.ones(len(a),bool) if valid is None else np.asarray(valid,bool)
    if valid.shape!=(len(a),):raise ValueError('Invalid display-comparison mask')
    lab_a=colour.XYZ_to_Lab(colour.sRGB_to_XYZ(a));lab_b=colour.XYZ_to_Lab(colour.sRGB_to_XYZ(b))
    de=colour.delta_E(lab_a,lab_b,method='CIE 2000');codes=np.max(np.abs(b-a),axis=1)*255
    def distribution(value):
        return dict(zip(('median','P95','max'),map(float,np.percentile(value,[50,95,100])))) if len(value) else None
    def select(mask):return {'deltaE00':distribution(de[mask]),'max_channel_codes':distribution(codes[mask])}
    return {'count':len(a),'valid_count':int(valid.sum()),'all':select(np.ones(len(a),bool)),
        'valid':select(valid),'meaning':'differences between supplied rendered RGB values, not ground-truth colour error'}
