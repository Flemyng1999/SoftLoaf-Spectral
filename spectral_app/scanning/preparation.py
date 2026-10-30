"""Coordinate-dependent flat correction after existing bounded resampling.

Resampling needs neighbouring source rows; the imaging resampler owns that
support. Division by a frozen smooth flat is pointwise with known coordinates.
"""
from pathlib import Path
import numpy as np
import tifffile
from spectral_app.imaging.resample import resize_npy


def patch_design(height,width,y0,y1,x0,x1,degree=2):
    y,x=np.mgrid[y0:y1,x0:x1]
    y=y/max(height-1,1)*2-1;x=x/max(width-1,1)*2-1
    return np.stack([x**i*y**j for n in range(degree+1) for i in range(n+1) for j in [n-i]],-1)


def prepare_camera(source,destination,flat_coefficients,*,short_edge=2048,rows=16):
    destination=Path(destination);coeff=np.asarray(flat_coefficients,float)
    if coeff.shape!=(6,3) or not np.isfinite(coeff).all() or short_edge<1 or rows<1:raise ValueError('Invalid frozen scan preparation')
    native=tifffile.memmap(source,mode='r');h,w=native.shape[:2]
    factor=min(1.,short_edge/min(h,w));width,height=max(1,round(w*factor)),max(1,round(h*factor))
    resize_npy(native,(width,height),destination)
    native._mmap.close()
    target=np.load(destination,mmap_mode='r+')
    try:
        for y in range(0,height,rows):
            end=min(y+rows,height)
            field=np.exp(patch_design(height,width,y,end,0,width)@coeff)
            target[y:end]=target[y:end]/65535/field
        target.flush()
    finally:target._mmap.close()
    return destination
