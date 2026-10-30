"""Nonnegative effective scan responses, not separately measured lamp/SSF."""
import numpy as np
from scipy.optimize import lsq_linear
from spectral_lut.reference import quadrature_widths


# Relative to each channel's response scale, not to an absolute exposure level.
# This only projects float64 roundoff onto a model's declared nonnegative cone.
RESPONSE_ROUNDOFF_FACTOR=64

def nonnegative_response(values):
    a=np.asarray(values,dtype=np.float64)
    if a.ndim not in (1,2) or not a.size or not np.isfinite(a).all():
        raise ValueError('扫描标定响应含无效数值，请重新建立标定。')
    tolerance=RESPONSE_ROUNDOFF_FACTOR*np.finfo(np.float64).eps*np.max(np.abs(a),axis=0)
    if np.any(a < -tolerance):raise ValueError('扫描标定响应含明显负值，请重新建立标定。')
    return np.maximum(a,0)


def fit_response(wavelengths,transmission,camera,*,sigma=10,ridge=1e-4,normalise=True):
    wave=np.asarray(wavelengths,dtype=float);t=np.asarray(transmission,dtype=float);rgb=np.asarray(camera,dtype=float)
    if (wave.ndim!=1 or len(wave)<4 or not np.isfinite(wave).all() or np.any(np.diff(wave)<=0) or t.shape!=(len(rgb),len(wave)) or rgb.shape[1:]!=(3,)
            or not np.isfinite(t).all() or not np.isfinite(rgb).all() or np.min(t)<0 or np.max(t)>1 or np.min(rgb)<0):raise ValueError('Invalid scan calibration samples')
    if not np.isfinite([sigma,ridge]).all() or sigma<=0 or ridge<0:raise ValueError('Invalid response regularization')
    # Each basis column is a discrete integration mass, including actual bin
    # widths. Coefficients describe response mass, not an energy SPD.
    widths=quadrature_widths(wave)
    centres=np.arange(wave[0],wave[-1]+1e-6,10.)
    basis=np.exp(-.5*((wave[:,None]-centres)/sigma)**2)*widths[:,None]
    basis/=basis.sum(0)
    design=t@basis
    coefficients=[]
    for c in range(3):
        # Relative weights stop bright patches alone controlling density. A
        # fixed floor limits amplification of noisy dark patches.
        scale=1/np.maximum(rgb[:,c],.01)
        matrix=np.vstack([design*scale[:,None],np.sqrt(ridge)*np.eye(len(centres))])
        target=np.r_[rgb[:,c]*scale,np.zeros(len(centres))]
        if normalise:
            matrix=np.vstack([matrix,50*np.ones((1,len(centres)))]);target=np.r_[target,50]
        result=lsq_linear(matrix,target,bounds=(0,np.inf),method='bvls',tol=1e-11,max_iter=1000)
        if not result.success:raise ValueError('Scan response fit did not converge')
        coefficients.append(nonnegative_response(result.x))
    weights=basis@np.array(coefficients).T
    return {'weights':weights,'prediction':t@weights,'sigma_nm':sigma,'ridge':ridge,'basis_centres_nm':centres}


def select_response(wavelengths,transmission,camera,*,normalise=True):
    """Nested six-column CV separates parameter selection from outer testing.

    All patches of a held-out physical column are excluded together, including
    its neutral. This is still one target, not an independent film experiment.
    """
    t=np.asarray(transmission);rgb=np.asarray(camera)
    if len(t)!=24:raise ValueError('Expected the 4 by 6 measured transmission card')
    groups=np.arange(24)%6
    options=[(s,r) for s in (5,10,20,35) for r in (1e-6,.1)]
    def choose(keep):
        results=[]
        for sigma,ridge in options:
            prediction=np.zeros_like(rgb)
            for fold in np.unique(groups[keep]):
                test=keep&(groups==fold);train=keep&~test
                fit=fit_response(wavelengths,t[train],rgb[train],sigma=sigma,ridge=ridge,normalise=normalise)
                prediction[test]=t[test]@fit['weights']
            errors=np.log10(np.maximum(prediction[keep],1e-12)/np.maximum(rgb[keep],1e-12))
            results.append({'sigma_nm':sigma,'ridge':ridge,'selection_cv_RMS_log10':float(np.sqrt(np.mean(errors**2)))})
        return sorted(results,key=lambda r:r['selection_cv_RMS_log10'])
    outer=np.zeros_like(rgb);outer_choices=[]
    for fold in range(6):
        test=groups==fold;choice=choose(~test)[0]
        fit=fit_response(wavelengths,t[~test],rgb[~test],sigma=choice['sigma_nm'],ridge=choice['ridge'],normalise=normalise)
        outer[test]=t[test]@fit['weights'];outer_choices.append(choice)
    candidates=choose(np.ones(24,bool));fits=[]
    for option in candidates:
        fit=fit_response(wavelengths,t,rgb,sigma=option['sigma_nm'],ridge=option['ridge'],normalise=normalise)
        fits.append(fit['weights'])
        option['training_RMS_log10']=float(np.sqrt(np.mean(np.log10(fit['prediction']/rgb)**2)))
    error=np.log10(np.maximum(outer,1e-12)/np.maximum(rgb,1e-12))
    return {'weights':fits[0],'family':np.array(fits),'candidates':candidates,'outer_prediction':outer,
        'outer_choices':outer_choices,'outer_RMS_log10':float(np.sqrt(np.mean(error**2))),
        'outer_max_log10':float(np.max(np.abs(error)))}
