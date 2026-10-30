"""Frozen spatial flat fields in native camera coordinates.

Flat fields preserve the central channel levels; they do not perform white
balance. Unsupported regions blend to identity. Legacy polynomial calibrations
remain explicit and retain their original normalization.
"""
import numpy as np
import hashlib
import json
from pathlib import Path
import tifffile
from scipy.ndimage import gaussian_filter
from .preparation import patch_design


class FlatCorrection:
    def __init__(self,*,gain=None,confidence=None,coefficients=None,native_shape=None):
        self.native_shape=None if native_shape is None else tuple(int(n) for n in native_shape)
        if self.native_shape is not None and (len(self.native_shape)!=3 or self.native_shape[2]!=3 or min(self.native_shape)<1):raise ValueError('Invalid flat source geometry')
        self.coefficients=None if coefficients is None else np.asarray(coefficients,float)
        if self.coefficients is not None:
            if self.coefficients.shape!=(6,3) or not np.isfinite(self.coefficients).all():raise ValueError('Invalid legacy flat')
            self.gain=self.confidence=None;return
        self.gain=np.asarray(gain,float);self.confidence=np.asarray(confidence,float)
        if (self.gain.ndim!=3 or self.gain.shape[2]!=3 or min(self.gain.shape[:2])<2
                or self.confidence.shape!=self.gain.shape[:2] or not np.isfinite(self.gain).all()
                or not np.isfinite(self.confidence).all() or np.min(self.gain)<.25 or np.max(self.gain)>4
                or np.min(self.confidence)<0 or np.max(self.confidence)>1):raise ValueError('Invalid spatial flat')
    @classmethod
    def of(cls,value):return value if isinstance(value,cls) else cls(coefficients=value)
    @classmethod
    def profile(cls,data):
        shape=data['flat_native_shape'] if 'flat_native_shape' in data else None
        return cls(gain=data['flat_gain'],confidence=data['flat_confidence'],native_shape=shape) if 'flat_gain' in data else cls(coefficients=data['flat'],native_shape=shape)
    def arrays(self):
        arrays={'flat':self.coefficients} if self.coefficients is not None else {'flat_gain':self.gain,'flat_confidence':self.confidence}
        if self.native_shape is not None:arrays['flat_native_shape']=np.asarray(self.native_shape,int)
        return arrays
    def evaluate(self,height,width,y0,y1,x0,x1):
        if self.coefficients is not None:return np.exp(-patch_design(height,width,y0,y1,x0,x1)@self.coefficients)
        h,w=self.gain.shape[:2]
        x=np.clip((np.arange(x0,x1)+.5)/width*w-.5,0,w-1);y=np.clip((np.arange(y0,y1)+.5)/height*h-.5,0,h-1)
        ix=np.minimum(x.astype(int),w-2);iy=np.minimum(y.astype(int),h-2);fx=x-ix;fy=y-iy
        # Interpolate the confidence-weighted correction, so an invalid cell
        # cannot contribute a plausible but unmeasured extrapolated gain.
        delta=(self.gain-1)*self.confidence[...,None]
        top=delta[iy[:,None],ix]*(1-fx[None,:,None])+delta[iy[:,None],ix+1]*fx[None,:,None]
        bottom=delta[iy[:,None]+1,ix]*(1-fx[None,:,None])+delta[iy[:,None]+1,ix+1]*fx[None,:,None]
        return 1+top*(1-fy[:,None,None])+bottom*fy[:,None,None]


def build_flat(references,*,shape=(48,64)):
    if not 1<=len(references)<=8:raise ValueError('请选择1–8张同条件平场 RAW。')
    maps=[];supports=[];clipping=[]
    for native in references:
        a=np.asarray(native,float)
        if a.ndim!=3 or a.shape[2]!=3 or not np.isfinite(a).all():raise ValueError('Invalid native flat pixels')
        h,w=a.shape[:2];valid=(a>1e-6)&(a<.98);clipping.append(np.mean(a>=.98,axis=(0,1)))
        centre=a[int(h*.4):int(h*.6),int(w*.4):int(w*.6)];ok=(centre>1e-6)&(centre<.98)
        levels=[]
        for c in range(3):
            if np.mean(ok[...,c])<.9:raise ValueError('平场中心的 '+ 'RGB'[c] +' 通道饱和或过暗，请更换曝光正确的平场 RAW。')
            levels.append(np.median(centre[...,c][ok[...,c]]))
        surface=np.zeros((*shape,3));support=np.zeros(shape)
        for y in range(shape[0]):
            for x in range(shape[1]):
                block=a[y*h//shape[0]:(y+1)*h//shape[0],x*w//shape[1]:(x+1)*w//shape[1]]
                good=valid[y*h//shape[0]:(y+1)*h//shape[0],x*w//shape[1]:(x+1)*w//shape[1]]
                if not good.size:continue
                support[y,x]=float(np.min(np.mean(good,axis=(0,1))))
                for c in range(3):surface[y,x,c]=np.median(block[...,c][good[...,c]]) if np.any(good[...,c]) else 0
        support=np.where(support>=.9,1.,0.)
        mass=gaussian_filter(support,1.25,mode='nearest')
        smooth=gaussian_filter(surface*support[...,None],(1.25,1.25,0),mode='nearest')/np.maximum(mass[...,None],1e-12)
        gain=np.clip(np.asarray(levels)/np.maximum(smooth,1e-12),.25,4)
        maps.append(np.log(gain)*support[...,None]);supports.append(support)
    mass=np.sum(supports,axis=0);gain=np.exp(np.sum(maps,axis=0)/np.maximum(mass[...,None],1))
    confidence=np.minimum(mass,1)
    return FlatCorrection(gain=gain,confidence=confidence),{'clipped_fraction':np.max(clipping,axis=0).tolist(),
        'supported_fraction':float(np.mean(confidence)),'gain_range':[float(gain.min()),float(gain.max())],
        'grid':[shape[1],shape[0]],'normalization':'per-channel central 20%; spatial only; no white balance'}


def from_raw_stages(paths):
    references=[];geometry=None
    for path in paths:
        a=tifffile.memmap(path,mode='r')
        try:
            if geometry is not None and geometry!=list(a.shape):raise ValueError('平场的原生可见区域尺寸不一致。')
            geometry=list(a.shape)
            stride=max(1,int(np.ceil(np.sqrt(a.shape[0]*a.shape[1]/1_000_000))))
            references.append(np.asarray(a[::stride,::stride],float)/65535)
        finally:a._mmap.close()
    field,report=build_flat(references);field.native_shape=tuple(geometry);report['native_shape']=geometry
    return field,report


def verify_compatibility(record,capture,shape=None):
    if record['capture'].get('Model')!=capture.get('Model'):raise ValueError('平场机身不匹配。')
    if shape is not None and list(shape)!=record['native_shape']:raise ValueError('平场原生可见区域尺寸不匹配。')
    return [key for key in ('LensModel','FNumber','ISO','ExposureTime') if record['capture'].get(key)!=capture.get(key)]


def save_flat(root,key,field,report,sources,capture):
    folder=Path(root)/key;folder.mkdir(parents=True,exist_ok=True)
    path=folder/'flat.npz';temporary=folder/'flat.working.npz'
    np.savez(temporary,**field.arrays());temporary.replace(path)
    record={'id':key,'name':'平场 · '+str(capture.get('Model','RAW')),'capture':capture,'sources':sources,
        **report,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (folder/'flat.json').write_text(json.dumps(record,ensure_ascii=False))
    return record


def load_flat(root,record):
    path=Path(root)/record['id']/'flat.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('平场数据发生变化。')
    with np.load(path) as a:return FlatCorrection.profile(a)
