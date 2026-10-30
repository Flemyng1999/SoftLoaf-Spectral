"""Float image resampling in row bands, including external mapped destinations."""
import math
from pathlib import Path
import uuid
from contextlib import contextmanager
import numpy as np
from PIL import Image
from .blocks import Region
from .sources import ArraySource,MappedSource


def _sample_band(source,size,y,count,method):
    """Resampling operation: source halo, original global phase, one output band."""
    width,height=size;h,w=source.height,source.width
    if (w,h)==size:
        with source.read(Region(0,y,w,count)) as values:return np.array(values,dtype=np.float32,copy=True)
    if method not in (Image.Resampling.BILINEAR,Image.Resampling.BOX):raise ValueError('Unsupported row filter')
    scale=h/height;support=max(1.,scale)*(1 if method==Image.Resampling.BILINEAR else .5)
    spans=[]
    for row in range(y,y+count):
        center=(row+.5)*scale
        lo=max(0,int(center-support+.5));hi=min(h,int(center+support+.5))
        positions=(np.arange(lo,hi)-center+.5)/max(1.,scale)
        weights=np.maximum(0,1-np.abs(positions)) if method==Image.Resampling.BILINEAR else ((positions>=-.5)&(positions<.5)).astype(float)
        weights/=weights.sum();spans.append((lo,hi,weights))
    top=min(s[0] for s in spans);bottom=max(s[1] for s in spans)
    out=np.empty((count,width,3),dtype=np.float32)
    with source.read(Region(0,top,w,bottom-top)) as values:
        for channel in range(3):
            image=Image.fromarray(np.asarray(values[...,channel],dtype=np.float32))
            try:
                tile=image.resize((width,bottom-top),method)
                try:
                    horizontal=np.asarray(tile,dtype=np.float32)
                    for i,(lo,hi,weights) in enumerate(spans):
                        out[i,:,channel]=np.einsum('i,ij->j',weights,horizontal[lo-top:hi-top],dtype=np.float64,optimize=False)
                finally:tile.close()
            finally:image.close()
    return out


def resize_rows(array,size,write,method=Image.Resampling.BILINEAR,rows=32):
    source=MappedSource.from_array(array) if isinstance(array,np.memmap) and array.flags.c_contiguous else ArraySource(array)
    try:
        for y in range(0,size[1],rows):write(y,_sample_band(source,size,y,min(rows,size[1]-y),method))
    finally:source.close()


class ResampledSource:
    """Pull-based row resampling. Halo memory is bounded separately from output."""
    channels=3;itemsize=4
    def __init__(self,source,size,*,budget=64*1024**2,method=Image.Resampling.BILINEAR):
        if len(size)!=2 or any(type(v)!=int or v<1 for v in size) or source.channels!=3:raise ValueError('Invalid resampling geometry')
        self.source=source;self.width,self.height=size;self.method=method;self.decoder_bytes=source.decoder_bytes
        scale=max(1.,source.height/self.height)
        # Native mapping plus one channel's float/Pillow/filter scratch. Preserve
        # half the caller budget for output, flat, renderer and codec buffers.
        source_rows=(budget//2)//(source.width*(source.itemsize*3+12))
        if source_rows<min(source.height,int(np.ceil(2*scale))+2):raise ValueError('Resampling halo exceeds working budget')
        self.rows=max(1,min(64,int(source_rows/scale)-3))
    @contextmanager
    def read(self,region):
        if min(region.x,region.y)<0 or min(region.width,region.height)<1 or region.x+region.width>self.width or region.y+region.height>self.height:raise ValueError('Resampling region exceeds image')
        out=np.empty((region.height,region.width,3),np.float32)
        for y in range(region.y,region.y+region.height,self.rows):
            count=min(self.rows,region.y+region.height-y)
            band=_sample_band(self.source,(self.width,self.height),y,count,self.method)
            out[y-region.y:y-region.y+count]=band[:,region.x:region.x+region.width]
        yield out
    def close(self):self.source.close()


def resize_npy(array,size,path):
    path=Path(path);temporary=path.with_name(uuid.uuid4().hex+'.tmp')
    width,height=size
    output=np.lib.format.open_memmap(temporary,mode='w+',dtype=np.float32,shape=(height,width,3))
    try:
        def write(y,values):
            # Release each destination band instead of retaining every dirty page.
            target=np.memmap(temporary,mode='r+',dtype=np.float32,offset=output.offset+y*width*12,shape=values.shape)
            try:target[:]=values;target.flush()
            finally:target._mmap.close()
        resize_rows(array,size,write);output._mmap.close();temporary.replace(path)
    except BaseException:
        output._mmap.close();temporary.unlink(missing_ok=True);raise
