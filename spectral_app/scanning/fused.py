"""Bounded, single-pass source sampling and scan LUT execution.

Geometry needs source halos; flat correction is pointwise in source coordinates.
The CPU oracle and Metal consume the same frozen map without intermediate images.
"""
from contextlib import contextmanager
from pathlib import Path
import numpy as np
import tifffile
from ..imaging.geometry import Geometry,source_bounds
from ..imaging.blocks import Region
from ..imaging.sources import MappedSource
from .flat_assets import FlatCorrection


class FusedScanSource:
    decoder_bytes=0;channels=3;itemsize=4;resampling_passes=1
    def __init__(self,path,flat,cube,*,geometry=None,short_edge=None,backend=None,budget=64*1024**2,technical=True,stage='half',encoded_srgb=False,display_flat_coefficients=None):
        self.flat=FlatCorrection.of(flat)
        self.encoded_srgb=encoded_srgb
        if encoded_srgb and (cube is not None or self.flat.gain is not None or np.any(self.flat.coefficients)):
            raise ValueError('Encoded RT display input cannot use camera flat or scan LUT')
        self.display_flat=display_flat_coefficients is not None
        if self.display_flat:
            if not encoded_srgb:raise ValueError('Display flat requires encoded RT sRGB')
            self.flat=FlatCorrection(coefficients=display_flat_coefficients)
        a=tifffile.memmap(path,mode='r')
        try:
            if a.dtype!=(np.float32 if encoded_srgb else np.uint16) or a.ndim!=3 or a.shape[2]!=3:raise ValueError('Unexpected scan source encoding')
            if self.flat.native_shape is not None:
                expected=np.asarray(self.flat.native_shape[:2])*(2 if stage=='full' else 1)
                if np.max(np.abs(np.asarray(a.shape[:2])-expected))>(1 if stage=='full' else 0):raise ValueError('平场的原生可见区域与图像不匹配。')
            self.source=MappedSource.from_array(a)
        finally:a._mmap.close()
        self.geometry=Geometry(geometry,self.source.width,self.source.height);self.width,self.height=self.geometry.size(short_edge)
        self.cube=cube;self.backend=backend;self.technical=technical and not encoded_srgb;self.max_source_pixels=0
        self.prefix=np.r_[(self.flat.coefficients if self.flat.coefficients is not None else np.zeros((6,3))).ravel(),cube.domain_min if cube else np.zeros(3),cube.domain_max if cube else np.ones(3),
            cube.table.transpose(2,1,0,3).ravel() if cube else np.empty(0)].astype(np.float32)
        self.flat_offset=len(self.prefix)
        if self.flat.gain is not None:self.prefix=np.r_[self.prefix,np.dstack([self.flat.gain,self.flat.confidence]).astype(np.float32).ravel()]
        self.limit=min(262144,max(1,(budget-self.prefix.nbytes-8*1024**2)//48))
        if self.limit<4096:raise ValueError('Fused sampling working budget is too small')
        if backend:
            if not hasattr(backend,'scan_program'):
                from spectral_lut.shaders import shader_path
                backend.scan_program=backend.program(shader_path(backend,'scan').read_text(encoding='utf-8'))
            self.program=backend.scan_program
    def _cpu(self,raw,coordinates,bounds):
        x0,y0,w,h=bounds;points=np.asarray(coordinates,float);ix,iy=points[:,:2].T.astype(int);fx,fy,rx,ry=points[:,2:].T
        value=np.zeros((len(points),3));total=np.zeros(len(points));inside=(ix+fx>=-.5)&(iy+fy>=-.5)&(ix+fx<self.source.width-.5)&(iy+fy<self.source.height-.5)
        gain=self.flat.evaluate(self.source.height,self.source.width,y0,y0+h,x0,x0+w)
        values=np.asarray(raw,float)
        if self.display_flat:
            from colour.models import eotf_sRGB
            values=eotf_sRGB(values)
        corrected=values/(1 if self.encoded_srgb else 65535)*gain
        for dy in range(-int(np.ceil(ry.max()))-1,int(np.ceil(ry.max()))+2):
            y=iy+dy;wy=np.maximum(0,1-np.abs(dy-fy)/ry)
            for dx in range(-int(np.ceil(rx.max()))-1,int(np.ceil(rx.max()))+2):
                x=ix+dx;weight=wy*np.maximum(0,1-np.abs(dx-fx)/rx)
                keep=inside&(weight>0)&(x>=0)&(x<self.source.width)&(y>=0)&(y<self.source.height)
                if not np.any(keep):continue
                xx,yy=x[keep]-x0,y[keep]-y0
                if min(xx.min(),yy.min())<0 or xx.max()>=w or yy.max()>=h:raise ValueError('Missing source halo')
                value[keep]+=corrected[yy,xx]*weight[keep,None];total[keep]+=weight[keep]
        value/=np.maximum(total[:,None],1e-30)
        if self.cube:value=self.cube.apply(-np.log10(np.maximum(value,1e-12)))
        elif self.display_flat:
            from colour.models import eotf_inverse_sRGB
            value=eotf_inverse_sRGB(value)
        elif self.technical:value=np.clip(value,0,1)**(1/2.2)
        value[~inside]=0
        return value
    def _tile(self,region):
        coordinates=self.geometry.coordinates(region,(self.width,self.height));bounds=source_bounds(coordinates,self.source.width,self.source.height)
        if bounds[2]*bounds[3]>self.limit or region.width*region.height>65536:
            if region.width>=region.height and region.width>1:
                n=region.width//2;parts=[Region(region.x,region.y,n,region.height),Region(region.x+n,region.y,region.width-n,region.height)]
                return np.concatenate([self._tile(r) for r in parts],axis=1)
            if region.height>1:
                n=region.height//2;parts=[Region(region.x,region.y,region.width,n),Region(region.x,region.y+n,region.width,region.height-n)]
                return np.concatenate([self._tile(r) for r in parts],axis=0)
            raise ValueError('Single-pixel source support exceeds working budget')
        self.max_source_pixels=max(self.max_source_pixels,bounds[2]*bounds[3])
        with self.source.read(Region(*bounds)) as raw:
            if self.backend:
                data=np.concatenate([self.prefix,np.asarray(raw,np.float32).ravel()]);x0,y0,w,h=bounds
                fh,fw=self.flat.gain.shape[:2] if self.flat.gain is not None else (0,0)
                metadata=np.array([w,h,x0,y0,self.source.width,self.source.height,self.cube.table.shape[0] if self.cube else 0,len(self.prefix),3 if self.display_flat else 2 if self.encoded_srgb else int(self.technical),fw,fh,self.flat_offset],np.uint32)
                value,_=self.program.run(coordinates,data,metadata)
            else:value=self._cpu(raw,coordinates,bounds)
        return value.reshape(region.height,region.width,3)
    @contextmanager
    def read(self,region):yield self._tile(region)
    def close(self):self.source.close()
