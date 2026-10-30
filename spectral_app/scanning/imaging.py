"""Scan image operations. Flat division/log/LUT are pointwise at global coords.

Resampling support and codecs are owned by the existing imaging modules.
"""
from pathlib import Path
import numpy as np
import tifffile
from contextlib import contextmanager
from .preparation import prepare_camera,patch_design
from ..imaging.sources import MappedSource
from ..imaging.pipeline import write_image
from ..imaging.resample import ResampledSource
from .fused import FusedScanSource


class FlatCameraSource:
    decoder_bytes=0
    def __init__(self,path,coefficients,*,short_edge=None,budget=64*1024**2):
        self.coefficients=np.asarray(coefficients,float)
        if self.coefficients.shape!=(6,3) or not np.isfinite(self.coefficients).all():raise ValueError('Invalid frozen flat')
        a=tifffile.memmap(path,mode='r')
        if a.dtype!=np.uint16 or a.ndim!=3 or a.shape[2]!=3:raise ValueError('Expected native camera uint16')
        self.source=MappedSource.from_array(a);a._mmap.close()
        self.preview=short_edge is not None
        if self.preview:
            h,w=self.source.height,self.source.width;factor=min(1.,short_edge/min(h,w))
            self.source=ResampledSource(self.source,(max(1,round(w*factor)),max(1,round(h*factor))),budget=budget)
        self.width=self.source.width;self.height=self.source.height;self.channels=3;self.itemsize=4
    @contextmanager
    def read(self,region):
        with self.source.read(region) as values:
            field=np.exp(patch_design(self.height,self.width,region.y,region.y+region.height,
                region.x,region.x+region.width)@self.coefficients)
            corrected=np.asarray(values,np.float32)/65535/field
            yield corrected.astype(np.float32) if self.preview else corrected
    def close(self):self.source.close()


class ScanRenderer:
    max_tile_pixels=65536
    def __init__(self,model,cube):
        self.model=model;self.cube=cube;self.metal=getattr(model,'metal',None)
        self.plan=self.metal.prepare_cube(cube,False) if self.metal else None
    def __call__(self,values):
        density=-np.log10(np.maximum(values,1e-12))
        if self.metal:return self.metal.interpolate_cube(self.cube,density,'Display Encoding','sRGB',False,self.plan)
        return self.model.core.apply_cube(self.cube,density) if self.model.core else self.cube.apply(density)


def preview_image(native,destination,coefficients,profile,*,renderer=None,fingerprint='',short_edge=2048,budget=64*1024**2,geometry=None,backend=None):
    fused=renderer is None or isinstance(renderer,ScanRenderer)
    backend=backend or (getattr(renderer.metal,'backend',None) if isinstance(renderer,ScanRenderer) else None)
    source=FusedScanSource(native,coefficients,renderer.cube if isinstance(renderer,ScanRenderer) else None,
        geometry=geometry,short_edge=short_edge,backend=backend,budget=budget) if fused else FlatCameraSource(native,coefficients,short_edge=short_edge,budget=budget)
    try:
        # Only a selection visualization. Native camera channels have no sRGB colourimetry.
        render=(lambda x:x) if fused else renderer
        return write_image(destination,source,render,profile,
            fingerprint=fingerprint,budget=budget,compression=3)
    finally:source.close()


def preview_srgb(source_path,destination,profile,*,geometry=None,backend=None,short_edge=2048,budget=64*1024**2,display_flat_coefficients=None,progress=None):
    source=FusedScanSource(source_path,np.zeros((6,3)),None,geometry=geometry,short_edge=short_edge,
        backend=backend,budget=budget,encoded_srgb=True,display_flat_coefficients=display_flat_coefficients)
    try:return write_image(destination,source,lambda x:x,profile,budget=budget,compression=3,progress=progress)
    finally:source.close()


def export_image(native,destination,coefficients,renderer,profile,*,fingerprint='',budget=64*1024**2,progress=None,geometry=None):
    fused=isinstance(renderer,ScanRenderer)
    source=FusedScanSource(native,coefficients,renderer.cube,geometry=geometry,backend=getattr(renderer.metal,'backend',None),budget=budget,stage='full') if fused else FlatCameraSource(native,coefficients)
    try:return write_image(destination,source,(lambda x:x) if fused else renderer,profile,fingerprint=fingerprint,
        budget=budget,progress=progress,compression=3)
    finally:source.close()
