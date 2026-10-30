"""Small row-oriented libpng ABI, without full-frame Pillow decode on export."""
import ctypes as ct
import hashlib
import os
from pathlib import Path
import sys
import numpy as np


class PngLibrary:
    def __init__(self,path=None):
        suffix='.dylib' if sys.platform=='darwin' else '.dll' if sys.platform=='win32' else '.so'
        prefix='' if sys.platform=='win32' else 'lib'
        directory=Path(os.environ['SOFTLOAF_CORE']).parent if os.environ.get('SOFTLOAF_CORE') else Path(__file__).resolve().parents[2]/'build'/('Release' if sys.platform=='win32' else '')
        self.path=Path(path or directory/(prefix+'softloaf_imageio'+suffix))
        self.lib=ct.CDLL(str(self.path));self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest();lib=self.lib
        lib.sl_png_error.restype=ct.c_char_p
        lib.sl_png_writer_open.argtypes=[ct.c_char_p,ct.c_uint32,ct.c_uint32,ct.c_void_p,ct.c_uint32,ct.c_char_p,ct.c_int];lib.sl_png_writer_open.restype=ct.c_void_p
        lib.sl_png_reader_open.argtypes=[ct.c_char_p];lib.sl_png_reader_open.restype=ct.c_void_p
        for name in ['sl_png_width','sl_png_height']:
            getattr(lib,name).argtypes=[ct.c_void_p];getattr(lib,name).restype=ct.c_uint32
        lib.sl_png_icc.argtypes=[ct.c_void_p,ct.POINTER(ct.c_uint32)];lib.sl_png_icc.restype=ct.c_void_p
        lib.sl_png_fingerprint.argtypes=[ct.c_void_p];lib.sl_png_fingerprint.restype=ct.c_char_p
        for name in ['sl_png_write','sl_png_read']:getattr(lib,name).argtypes=[ct.c_void_p,ct.c_void_p,ct.c_uint32,ct.c_uint64]
        lib.sl_png_finish.argtypes=[ct.c_void_p];lib.sl_png_close.argtypes=[ct.c_void_p]

    def error(self):return OSError(self.lib.sl_png_error().decode(errors='replace') or 'PNG row operation failed')


class _Stream:
    def __enter__(self):return self
    def close(self):
        if self.handle:self.library.lib.sl_png_close(self.handle);self.handle=None
    def __exit__(self,kind,error,trace):
        try:
            if kind is None:self.finish()
        finally:self.close()
    def finish(self):
        if self.remaining:raise ValueError('PNG stream has incomplete rows')
        if self.library.lib.sl_png_finish(self.handle):raise self.library.error()


class PngWriter(_Stream):
    def __init__(self,path,size,icc,fingerprint='',compression=6,library=None):
        self.library=library or PngLibrary();self.size=tuple(size);self.remaining=self.size[1]
        self.handle=self.library.lib.sl_png_writer_open(os.fsencode(path),*self.size,icc,len(icc),fingerprint.encode('ascii'),compression)
        if not self.handle:raise self.library.error()
    def write(self,rows):
        rows=np.asarray(rows)
        if rows.dtype!=np.uint8 or rows.ndim!=3 or rows.shape[1:]!=(self.size[0],3) or not 0<len(rows)<=self.remaining:raise ValueError('Expected bounded RGB8 rows')
        rows=np.ascontiguousarray(rows)
        if self.library.lib.sl_png_write(self.handle,rows.ctypes.data,len(rows),rows.strides[0]):raise self.library.error()
        self.remaining-=len(rows)


class PngReader(_Stream):
    def __init__(self,path,library=None):
        self.library=library or PngLibrary();lib=self.library.lib
        self.handle=lib.sl_png_reader_open(os.fsencode(path))
        if not self.handle:raise self.library.error()
        self.size=(lib.sl_png_width(self.handle),lib.sl_png_height(self.handle));self.remaining=self.size[1]
        length=ct.c_uint32();pointer=lib.sl_png_icc(self.handle,ct.byref(length));self.icc=ct.string_at(pointer,length.value) if pointer else b''
        self.fingerprint=lib.sl_png_fingerprint(self.handle).decode('ascii')
    def read(self,count):
        if type(count)!=int or not 0<count<=self.remaining:raise ValueError('Invalid PNG row count')
        out=np.empty((count,self.size[0],3),dtype=np.uint8)
        if self.library.lib.sl_png_read(self.handle,out.ctypes.data,count,out.strides[0]):raise self.library.error()
        self.remaining-=count;return out
