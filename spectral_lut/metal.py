"""Bounded float32 Metal ABI. A Metal failure is reported, never hidden by CPU."""
import ctypes as ct
from pathlib import Path
import hashlib
import threading

import numpy as np

F=ct.POINTER(ct.c_float)
U=ct.POINTER(ct.c_uint32)


class MetalBackend:
    name='metal'
    def __init__(self,path=None):
        self.path=Path(path or Path(__file__).resolve().parents[1]/'build/libsoftloaf_metal.dylib')
        if not self.path.is_file():raise RuntimeError('Build the Metal library before selecting GPU processing.')
        self.lib=ct.CDLL(str(self.path));self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        lib=self.lib;lib.sl_metal_error.restype=ct.c_char_p;lib.sl_metal_device_name.restype=ct.c_char_p
        lib.sl_metal_create.argtypes=[ct.c_char_p];lib.sl_metal_create.restype=ct.c_void_p
        lib.sl_metal_destroy.argtypes=[ct.c_void_p]
        lib.sl_metal_texture.argtypes=[ct.c_void_p,*([ct.c_uint32]*7),F]
        lib.sl_metal_run.argtypes=[ct.c_void_p,F,ct.c_uint64,ct.c_uint32,F,ct.c_uint64,U,ct.c_uint64,F,ct.POINTER(ct.c_double)]
        name=lib.sl_metal_device_name()
        if not name:raise RuntimeError('No Metal device is available; no CPU fallback selected.')
        self.device_name=name.decode();self.lock=threading.RLock()

    def check(self,code):
        if code:raise RuntimeError(self.lib.sl_metal_error().decode())

    def program(self,source,textures=()):return MetalProgram(self,source,textures)


class MetalProgram:
    def __init__(self,backend,source,textures):
        self.backend=backend;self.handle=backend.lib.sl_metal_create(source.encode())
        if not self.handle:raise RuntimeError(backend.lib.sl_metal_error().decode())
        self.source_sha256=hashlib.sha256(source.encode()).hexdigest()
        try:
            for texture in textures:
                values=np.ascontiguousarray(texture['values'],dtype=np.float32)
                backend.check(backend.lib.sl_metal_texture(self.handle,texture['binding'],texture['dimension'],texture['width'],texture['height'],texture['depth'],texture['channels'],texture['linear'],values.ctypes.data_as(F)))
        except Exception:self.close();raise

    def close(self):
        if getattr(self,'handle',None):self.backend.lib.sl_metal_destroy(self.handle);self.handle=None

    def __del__(self):self.close()

    def run(self,values,data,metadata):
        x=np.ascontiguousarray(values,dtype=np.float32);d=np.ascontiguousarray(data,dtype=np.float32);m=np.ascontiguousarray(metadata,dtype=np.uint32)
        if x.ndim!=2 or not 0<len(x)<=262144 or not np.isfinite(x).all():raise ValueError('GPU expects a finite, bounded pixel tile.')
        output=np.empty((len(x),3),dtype=np.float32);seconds=ct.c_double()
        with self.backend.lock:
            if hasattr(self.backend,'ensure_available'):self.backend.ensure_available()
            self.backend.check(self.backend.lib.sl_metal_run(self.handle,x.ctypes.data_as(F),len(x),x.shape[1],d.ctypes.data_as(F),len(d),m.ctypes.data_as(U),len(m),output.ctypes.data_as(F),ct.byref(seconds)))
        if not np.isfinite(output).all():raise ValueError('GPU generated invalid spectral density or output.')
        return output,seconds.value
