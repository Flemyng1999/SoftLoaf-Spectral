"""Analysis pass: smooth illumination model with explicit clipping extrapolation."""
import numpy as np


def terms(shape,degree=2):
    y,x=np.mgrid[-1:1:complex(shape[0]),-1:1:complex(shape[1])]
    return np.stack([x**i*y**j for n in range(degree+1) for i in range(n+1) for j in [n-i]],-1)


def fit_flatfield(pixels,*,degree=2):
    a=np.asarray(pixels,float)
    if a.ndim!=3 or a.shape[-1]!=3 or not np.isfinite(a).all() or np.min(a)<0:raise ValueError('Invalid linear flat field')
    design=terms(a.shape[:2],degree)
    coefficients=[];residual=[];fractions=[];masks=[]
    y,x=np.indices(a.shape[:2]);training=(x+2*y)%5!=0
    for c in range(3):
        good=(a[...,c]>.02)&(a[...,c]<.97)
        if good.sum()<max(100,10*design.shape[-1]):raise ValueError('Not enough unsaturated flat-field samples')
        fit=good&training
        log=np.log(np.maximum(a[...,c],1e-30))
        beta=np.linalg.lstsq(design[fit],log[fit],rcond=None)[0]
        for _ in range(3):
            error=log-np.einsum('...k,k->...',design,beta)
            robust=fit&(np.abs(error)<max(.005,4*np.median(np.abs(error[fit]))))
            beta=np.linalg.lstsq(design[robust],log[robust],rcond=None)[0]
        hold=good&~training
        residual.append(float(np.sqrt(np.mean((design[hold]@beta-log[hold])**2))))
        coefficients.append(beta);fractions.append(float(np.mean(a[...,c]>=1-1/65535)));masks.append(~good)
    field=np.exp(design@np.array(coefficients).T)
    return {'field':field,'coefficients':np.array(coefficients).T,'degree':degree,
        'heldout_log_RMS':residual,'clipped_fraction':fractions,'extrapolated_mask':np.stack(masks,-1)}
