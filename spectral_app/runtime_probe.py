"""Pixel-free probe of the frozen service, native libraries and RAW reader roles."""
import ctypes
import importlib
import json
import subprocess
from .runtime_paths import packaged,resources,native_directory


def probe():
    import sys
    result={'ok':False,'packaged':packaged(),'python':sys.version.split()[0],'modules':{},'native':{},'raw':{}}
    for name in ('numpy','scipy','colour','PIL','PyOpenColorIO','tifffile'):
        module=importlib.import_module(name);result['modules'][name]=getattr(module,'__version__','loaded')
    from spectral_lut.native import NativeCore,sibling_library
    from .imaging.png_codec import PngLibrary
    core=NativeCore();result['native']['core']=core.lib.sl_abi_version()
    PngLibrary(sibling_library(core.path,'softloaf_imageio'));result['native']['png']=True
    if sys.platform=='darwin':
        from spectral_lut.metal import MetalBackend
        MetalBackend(sibling_library(core.path,'softloaf_metal'));result['native']['metal']=True
    from .raw_runtime import RawRuntime,find_lcms2
    runtime=RawRuntime(resources())
    if not (runtime.resources/'options').is_file():raise RuntimeError('RT platform options file is missing')
    library=find_lcms2()
    if not library:raise RuntimeError('Bundled LCMS2 library is unavailable')
    ctypes.CDLL(str(library));result['native']['lcms2']=True
    from .imaging.lens_profiles import LensCatalog
    lenses=LensCatalog()
    if not lenses.available:raise RuntimeError('Bundled Lensfun library/database is unavailable')
    result['native']['lensfun_profiles']=len(lenses.entries)
    for name,path in [('integrated',runtime.integrated),('reference',runtime.reference)]:
        if not path.is_file():raise RuntimeError('Bundled RAW reader is missing: '+name)
        process=subprocess.run([str(path)],capture_output=True,env=runtime.environment(path),timeout=30)
        if process.returncode or b'RawTherapee' not in process.stdout:raise RuntimeError('Bundled RAW reader cannot execute: '+name)
        result['raw'][name]=True
    for name in ('design/gui-v2/index.html','assets/branding/softloaf-spectral.png','core/metal/spectral.metal','spectral_app/model.py'):
        if not (resources()/name).is_file():raise RuntimeError('Bundled resource missing: '+name)
    result['ok']=True
    return result
