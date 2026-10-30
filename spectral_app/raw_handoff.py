"""One-decode technical handoffs for an unmodified RT compatibility executable."""
import ctypes as ct
import ctypes.util
from pathlib import Path
import numpy as np
import tifffile
from PIL import Image


def half_compatibility_output(path,profile):
    from .imaging.resample import resize_rows
    source=tifffile.memmap(path,mode='r');h,w=source.shape[:2];size=((w+1)//2,(h+1)//2)
    tmp=path.with_name('half-'+path.name)
    target=tifffile.memmap(tmp,shape=(size[1],size[0],3),dtype=np.float32,photometric='rgb',extratags=[(34675,'B',len(profile),profile,False)])
    offset=target.offset;target._mmap.close()
    def write(y,values):
        block=np.memmap(tmp,mode='r+',dtype=np.float32,offset=offset+y*size[0]*12,shape=values.shape)
        try:block[:]=values;block.flush()
        finally:block._mmap.close()
    try:
        resize_rows(source,size,write,method=Image.Resampling.BOX)
        source._mmap.close();tmp.replace(path)
    except BaseException:
        source._mmap.close();tmp.unlink(missing_ok=True);raise
    return [w,h]



def srgb_from_ap1(source,destination,profiles):
    """Relative-colorimetric float ICC bridge, without another RAW development."""
    from .raw_runtime import find_lcms2
    library=find_lcms2()
    if not library:raise RuntimeError('LCMS2 is required for the official RAW compatibility handoff')
    lib=ct.CDLL(library)
    lib.cmsOpenProfileFromMem.argtypes=[ct.c_void_p,ct.c_uint32];lib.cmsOpenProfileFromMem.restype=ct.c_void_p
    lib.cmsCreateTransform.argtypes=[ct.c_void_p,ct.c_uint32,ct.c_void_p,ct.c_uint32,ct.c_uint32,ct.c_uint32];lib.cmsCreateTransform.restype=ct.c_void_p
    lib.cmsDoTransform.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_void_p,ct.c_uint32]
    lib.cmsDeleteTransform.argtypes=[ct.c_void_p];lib.cmsCloseProfile.argtypes=[ct.c_void_p]
    buffers=[ct.create_string_buffer(profiles[k]) for k in ['ap1','srgb']]
    handles=[lib.cmsOpenProfileFromMem(b,len(profiles[k])) for b,k in zip(buffers,['ap1','srgb'])]
    transform=None
    try:
        if not all(handles):raise RuntimeError('RAW ICC profiles could not be opened')
        # lcms2.h: FLOAT_SH(1)|COLORSPACE_SH(PT_RGB)|CHANNELS_SH(3)|BYTES_SH(4).
        transform=lib.cmsCreateTransform(handles[0],0x44001c,handles[1],0x44001c,1,0x0100|0x0040)
        if not transform:raise RuntimeError('RAW ICC bridge could not be created')
        values=tifffile.memmap(source,mode='r');profile=profiles['srgb']
        target=tifffile.memmap(destination,shape=values.shape,dtype=np.float32,photometric='rgb',extratags=[(34675,'B',len(profile),profile,False)])
        from .imaging.sources import MappedSource
        from .imaging.blocks import Region
        source_regions=MappedSource.from_array(values);offset=target.offset;shape=target.shape
        values._mmap.close();target._mmap.close()
        for row in range(0,shape[0],32):
            count=min(32,shape[0]-row)
            with source_regions.read(Region(0,row,shape[1],count)) as block:
                out=np.memmap(destination,mode='r+',dtype=np.float32,offset=offset+row*shape[1]*12,shape=(count,shape[1],3))
                try:lib.cmsDoTransform(transform,block.ctypes.data,out.ctypes.data,block.size//3);out.flush()
                finally:out._mmap.close()

    finally:
        if transform:lib.cmsDeleteTransform(transform)
        for handle in handles:
            if handle:lib.cmsCloseProfile(handle)
