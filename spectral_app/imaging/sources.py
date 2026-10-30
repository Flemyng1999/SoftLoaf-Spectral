"""Borrowed region sources. Pixel arrays may only be used inside read()."""
from contextlib import contextmanager
from pathlib import Path
import numpy as np


class ArraySource:
    decoder_bytes=0
    def __init__(self,array):
        self.array=np.asarray(array)
        if self.array.ndim!=3:raise ValueError('Image source must have height, width and channels')
        self.height,self.width,self.channels=self.array.shape;self.itemsize=self.array.dtype.itemsize
    @contextmanager
    def read(self,region):
        yield self.array[region.y:region.y+region.height,region.x:region.x+region.width]
    def close(self):pass


class MappedSource:
    """Map each export region independently, so visited file pages unmap promptly."""
    decoder_bytes=0
    def __init__(self,path,shape,dtype,offset=0):
        self.path=Path(path);self.height,self.width,self.channels=shape
        self.dtype=np.dtype(dtype);self.itemsize=self.dtype.itemsize;self.offset=offset
    @classmethod
    def from_array(cls,array):
        if not isinstance(array,np.memmap) or not array.flags.c_contiguous:raise ValueError('Expected contiguous mapped source')
        base=array
        while isinstance(base.base,np.memmap):base=base.base
        offset=base.offset+array.ctypes.data-base.ctypes.data
        return cls(array.filename,array.shape,array.dtype,offset)
    @contextmanager
    def read(self,region):
        offset=self.offset+region.y*self.width*self.channels*self.itemsize
        mapping=np.memmap(self.path,mode='r',dtype=self.dtype,offset=offset,shape=(region.height,self.width,self.channels))
        try:yield mapping[:,region.x:region.x+region.width]
        finally:mapping._mmap.close()
    def close(self):pass


class RasterSource:
    """Existing bounded RGB8 decoder, with float/color conversion only per region."""
    channels=3
    itemsize=8
    def __init__(self,image,to_ap1):
        self.image=image;self.width,self.height=image.size;self.to_ap1=to_ap1
        self.decoder_bytes=self.width*self.height*3
    @contextmanager
    def read(self,region):
        crop=self.image.crop((region.x,region.y,region.x+region.width,region.y+region.height))
        try:yield self.to_ap1(np.asarray(crop,dtype=np.float64)/255)
        finally:crop.close()
    def close(self):self.image.close()
