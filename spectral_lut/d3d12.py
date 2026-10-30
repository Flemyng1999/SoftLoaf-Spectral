"""Windows D3D12 bounded GPU transport; caller owns explicit CPU recovery."""
import ctypes as ct
import atexit
import hashlib
import os
import re
from pathlib import Path
import threading
import weakref
from .metal import F,U,MetalProgram


class D3D12Backend:
    name='d3d12'
    shader_extension='.hlsl'
    timing_kind='D3D12 timestamp queries around dispatch; separate wall time includes transfers'

    def __init__(self,path=None):
        directory=Path(os.environ['SOFTLOAF_CORE']).parent if os.environ.get('SOFTLOAF_CORE') else Path(__file__).resolve().parents[1]/'build/Release'
        self.path=Path(path or os.environ.get('SOFTLOAF_D3D12') or directory/'softloaf_d3d12.dll')
        if not self.path.is_file():raise RuntimeError('Build the D3D12 library before selecting GPU processing.')
        self.lib=ct.CDLL(str(self.path));self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        # Reuse the validated bounded program wrapper, not a second pixel path.
        for name in ('error','device_name','create','destroy','texture','run'):
            setattr(self.lib,'sl_metal_'+name,getattr(self.lib,'sl_d3d12_'+name))
        lib=self.lib;lib.sl_metal_error.restype=ct.c_char_p;lib.sl_metal_device_name.restype=ct.c_char_p
        lib.sl_metal_create.argtypes=[ct.c_char_p];lib.sl_metal_create.restype=ct.c_void_p
        lib.sl_metal_destroy.argtypes=[ct.c_void_p]
        lib.sl_metal_texture.argtypes=[ct.c_void_p,*([ct.c_uint32]*7),F]
        lib.sl_metal_run.argtypes=[ct.c_void_p,F,ct.c_uint64,ct.c_uint32,F,ct.c_uint64,U,ct.c_uint64,F,ct.POINTER(ct.c_double)]
        name=lib.sl_metal_device_name()
        if not name:raise RuntimeError(lib.sl_metal_error().decode(errors='replace'))
        self.device_name=name.decode();self.lock=threading.RLock()
        self.on_failure=None;self.disabled=False;self.programs=weakref.WeakSet();self.closed=False
        lib.sl_d3d12_shutdown.argtypes=[];lib.sl_d3d12_shutdown.restype=ct.c_int
        atexit.register(self.close)

    def close(self):
        with self.lock:
            if self.closed:return
            self.closed=True
            for program in list(self.programs):program.close()
            self.lib.sl_d3d12_shutdown()

    def ensure_available(self):
        if self.disabled or self.closed:
            from spectral_app.compute_policy import GPUUnavailable
            raise GPUUnavailable('D3D12 context has been disabled')

    def failure(self,error):
        from spectral_app.compute_policy import GPUUnavailable
        from spectral_app.diagnostics import event
        code=re.search(r'(?:error (X\d{4})|HRESULT=(\d+))',str(error));line=re.search(r'softloaf-compute\((\d+)',str(error))
        event('compute.fallback',requested_backend='d3d12',backend='cpu',reason='gpu_dispatch_failed',native_code=next((v for v in code.groups() if v),None) if code else None,source_line=int(line[1]) if line else None,error=error)
        if self.on_failure is None:raise error
        self.disabled=True
        self.on_failure(error)
        raise GPUUnavailable('D3D12 unavailable; retrying the frozen operation on CPU') from error

    def check(self,code):
        if code:self.failure(RuntimeError(self.lib.sl_metal_error().decode(errors='replace')))

    def program(self,source,textures=()):
        from spectral_app.compute_policy import GPUUnavailable
        with self.lock:
            self.ensure_available()
            try:
                program=MetalProgram(self,source,textures);self.programs.add(program);return program
            except GPUUnavailable:raise
            except RuntimeError as error:self.failure(error)
