"""Disposable scan views; source stages and calibration measurements stay intact.

Raw chart/sampling views retain source coordinates. Browsing views combine frozen
geometry and a separate display flat fitted in linear sRGB/D65. This display-space
gain does not invert RT's DCP; positive rendering uses the native camera flat.
"""
import numpy as np
import tifffile
from colour.models import eotf_sRGB
from .flatfield import fit_flatfield
from .imaging import preview_srgb
from ..imaging.sources import MappedSource
from ..imaging.resample import ResampledSource
from ..imaging.pipeline import write_image


def fit_display_flat(paths):
    coefficients=[];errors=[];clipping=[]
    for path in paths:
        a=tifffile.memmap(path,mode='r')
        try:
            stride=max(1,int(np.ceil(np.sqrt(a.shape[0]*a.shape[1]/300_000))))
            linear=eotf_sRGB(np.asarray(a[::stride,::stride],float))
        finally:a._mmap.close()
        report=fit_flatfield(np.maximum(linear,0))
        beta=report['coefficients'].copy();beta[0]=0
        coefficients.append(beta);errors.append(report['heldout_log_RMS']);clipping.append(report['clipped_fraction'])
    if not coefficients:raise ValueError('缺少平场照片。')
    return {'coefficients':np.mean(coefficients,axis=0).tolist(),'encoding':'linear sRGB / D65',
        'normalization':'central gain 1; preserve exposure and white balance',
        'purpose':'display-only; positive rendering uses native-camera flat',
        'heldout_log_RMS':errors,'clipped_fraction':clipping}


def raw_preview(path,destination,profile,*,budget=64*1024**2,progress=None):
    a=tifffile.memmap(path,mode='r')
    try:h,w=a.shape[:2];source=MappedSource.from_array(a)
    finally:a._mmap.close()
    factor=min(1,2048/min(h,w));source=ResampledSource(source,(round(w*factor),round(h*factor)),budget=budget)
    try:return write_image(destination,source,lambda x:x,profile,budget=budget,compression=3,progress=progress)
    finally:source.close()


def corrected_preview(path,destination,profile,*,geometry,display_flat=None,backend=None,budget=64*1024**2,progress=None):
    return preview_srgb(path,destination,profile,geometry=geometry,backend=backend,budget=budget,
        display_flat_coefficients=display_flat,progress=progress)
