"""Entry point for the directory-based, independently installed service."""
import os
from pathlib import Path
import sys

from spectral_app.runtime_paths import resources,state_root,native_directory

state=state_root()
os.environ['MPLBACKEND']='Agg'
os.environ.setdefault('MPLCONFIGDIR',str(state/'font-cache'))
os.environ.setdefault('XDG_CACHE_HOME',str(state/'library-cache'))
name='libsoftloaf_core.dylib' if sys.platform=='darwin' else 'softloaf_core.dll' if sys.platform=='win32' else 'libsoftloaf_core.so'
os.environ['SOFTLOAF_CORE']=str(native_directory()/name)
for name in ('liblcms2.2.dylib','liblcms2-2.dll','lcms2.dll','liblcms2.so.2'):
    path=native_directory()/name
    if path.is_file():os.environ['SOFTLOAF_LCMS2_LIBRARY']=str(path);break

from spectral_app.__main__ import main
raise SystemExit(main())
