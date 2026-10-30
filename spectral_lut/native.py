"""Validated NumPy / C ABI boundary. Loading failure never selects a fallback."""
import ctypes as ct
import hashlib
import os
from pathlib import Path
import sys

import numpy as np

P = ct.POINTER(ct.c_double)


def sibling_library(core_path,name):
    path=Path(core_path)
    return path.with_name(('lib' if path.name.startswith('lib') else '')+name+path.suffix)


class _Reversal(ct.Structure):
    _fields_ = [(key, ct.c_uint64) for key in ('source_count', 'view_count', 'curve_count')] + [
        (key, P) for key in ('basis', 'exposure', 'log_h', 'amounts', 'dyes',
                            'view_kernel', 'viewed_light', 'adaptation')] + [
        (key, ct.c_double) for key in ('gray_log_h', 'exposure_ev', 'view_gain')]


def _array(value, shape=None):
    array = np.ascontiguousarray(value, dtype=np.float64)
    if shape is not None and array.shape != shape:
        raise ValueError(f'Expected array shape {shape}, received {array.shape}.')
    if not np.isfinite(array).all():
        raise ValueError('Expected finite float64 values.')
    return array


def _rgb(value):
    array = _array(value)
    if array.ndim < 1 or array.shape[-1] != 3:
        raise ValueError('Expected a final RGB dimension of 3.')
    return array


def _ptr(array):
    return array.ctypes.data_as(P)


class NativeCore:
    def __init__(self, path=None):
        extension = '.dylib' if sys.platform == 'darwin' else '.dll' if sys.platform == 'win32' else '.so'
        prefix = '' if sys.platform == 'win32' else 'lib'
        self.path = Path(path or os.environ.get('SOFTLOAF_CORE') or
            Path(__file__).resolve().parents[1]/'build'/('Release' if sys.platform=='win32' else '')/f'{prefix}softloaf_core{extension}').resolve()
        if not self.path.is_file():
            raise RuntimeError('C++ core is not built. Configure and build the CMake project first.')
        self.lib = ct.CDLL(str(self.path))
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.lib.sl_abi_version.restype = ct.c_uint32
        self.lib.sl_last_error.restype = ct.c_char_p
        self.lib.sl_acescct_decode.argtypes = [P, ct.c_uint64, P]
        self.lib.sl_cube_apply.argtypes = [P, ct.c_uint64, P, P, P, ct.c_uint64, P]
        if hasattr(self.lib,'sl_cube_apply_f32'):self.lib.sl_cube_apply_f32.argtypes=[ct.POINTER(ct.c_float),ct.c_uint64,P,P,P,ct.c_uint64,P]
        self.lib.sl_reversal.argtypes = [ct.POINTER(_Reversal), P, ct.c_uint64, P]
        if not hasattr(self.lib, 'sl_spectral_stage'):
            raise RuntimeError('C++ core lacks the spectral material stage; rebuild the application.')
        if self.lib.sl_abi_version() != 1:
            raise RuntimeError('Unsupported C++ core ABI; rebuild this application.')

    def _check(self, code):
        if code:
            raise ValueError(self.lib.sl_last_error().decode('utf-8'))

    def decode(self, values):
        array = _rgb(values)
        output = np.empty_like(array)
        self._check(self.lib.sl_acescct_decode(_ptr(array), array.size, _ptr(output)))
        return output

    def apply_cube(self, cube, values):
        array = _rgb(values)
        n = cube.table.shape[0]
        low, high = _array(cube.domain_min, (3,)), _array(cube.domain_max, (3,))
        output = np.empty_like(array)
        if cube.table.dtype==np.float32:
            if not hasattr(self.lib,'sl_cube_apply_f32'):raise RuntimeError('Rebuild the C++ core for mapped float32 CUBE verification')
            table=np.ascontiguousarray(cube.table.transpose(2,1,0,3),dtype=np.float32)
            if table.shape!=(n,n,n,3):raise ValueError('Invalid float32 CUBE shape')
            self._check(self.lib.sl_cube_apply_f32(table.ctypes.data_as(ct.POINTER(ct.c_float)),n,_ptr(low),_ptr(high),_ptr(array),array.size//3,_ptr(output)))
        else:
            table = _array(cube.table, (n, n, n, 3))
            self._check(self.lib.sl_cube_apply(_ptr(table), n, _ptr(low), _ptr(high),
                                             _ptr(array), array.size//3, _ptr(output)))
        return output

    def reversal(self, values, film, basis, view_kernel, viewed_light, adaptation,
                 exposure_ev=0, view_gain=1.8, exposure_kernel=None):
        array = _rgb(values)
        source_count, view_count, curve_count = len(film.exposure_kernel), len(film.dyes), len(film.log_h)
        arrays = [_array(basis, (3, source_count)),
                  _array(film.exposure_kernel if exposure_kernel is None else exposure_kernel, (source_count, 3)),
                  _array(film.log_h, (curve_count,)), _array(film.amounts, (curve_count, 3)),
                  _array(film.dyes, (view_count, 3)), _array(view_kernel, (view_count, 3)),
                  _array(viewed_light, (view_count,)), _array(adaptation, (3, 3))]
        model = _Reversal(source_count, view_count, curve_count,
            *[_ptr(a) for a in arrays], film.gray_log_h, exposure_ev, view_gain)
        widths = [source_count, 3, 3, view_count, view_count, 3, 3]
        output = np.empty((*array.shape[:-1], sum(widths)), dtype=np.float64)
        self._check(self.lib.sl_reversal(ct.byref(model), _ptr(array), array.size//3, _ptr(output)))
        keys = ['reflectance', 'exposure', 'dye_amounts', 'transmission', 'viewed_spectrum', 'XYZ_view', 'XYZ']
        return dict(zip(keys, np.split(output, np.cumsum(widths)[:-1], axis=-1)))

    def spectral_stage(self, spectra, kernel, axis, amounts, dyes, base, anchor=0, ev=0):
        source = _array(spectra)
        ns, nv, nc = source.shape[-1], len(dyes), len(axis)
        arrays = [source, _array(kernel,(ns,3)), _array(axis,(nc,)),
                  _array(amounts,(nc,3)), _array(dyes,(nv,3)), _array(base,(nv,))]
        function = self.lib.sl_spectral_stage
        function.argtypes = [P,ct.c_uint64,ct.c_uint64,P,ct.c_uint64,P,P,
                             ct.c_uint64,P,P,ct.c_double,ct.c_double,P]
        output = np.empty((*source.shape[:-1],6+nv),dtype=np.float64)
        self._check(function(_ptr(arrays[0]),source.size//ns,ns,_ptr(arrays[1]),nc,
            _ptr(arrays[2]),_ptr(arrays[3]),nv,_ptr(arrays[4]),_ptr(arrays[5]),anchor,ev,_ptr(output)))
        return tuple(np.split(output,[3,6],axis=-1))
