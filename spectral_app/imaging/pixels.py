"""Explicit display quantization. Scientific float values are never modified."""
import numpy as np


def rgb8(values,rounding='export'):
    values=np.asarray(values)
    if values.ndim!=3 or values.shape[-1]!=3 or not np.isfinite(values).all():raise ValueError('Invalid rendered RGB block')
    work=np.array(values,copy=True)
    np.clip(work,0,1,out=work);np.multiply(work,255,out=work)
    if rounding=='preview':np.rint(work,out=work)
    elif rounding=='export':np.add(work,.5,out=work);np.floor(work,out=work)
    else:raise ValueError('Unknown quantization rule')
    return work.astype(np.uint8)
