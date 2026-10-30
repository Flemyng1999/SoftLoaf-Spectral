"""Locations and subprocess dependencies for the two pinned RT reader roles."""
import ctypes.util
import json
import os
from pathlib import Path
import shutil
import sys


class RawRuntime:
    def __init__(self,root,cli=None,*,platform=None):
        from .runtime_paths import packaged,resources,state_root
        root=Path(root);platform=platform or sys.platform
        frozen=packaged() and root.resolve()==resources()
        config_path=(state_root() if frozen else root)/'local/raw-runtime.json';config={}
        if config_path.is_file():
            config=json.loads(config_path.read_text(encoding='utf-8'))
            if config.get('schema')!=1:raise ValueError('Unknown RAW runtime configuration')
            for name in ('integrated','reference','dll_directory'):
                if name in config and (not isinstance(config[name],str) or not config[name]):raise ValueError('Invalid RAW runtime path')
        def location(name,default):
            value=Path(config.get(name,default))
            return value if value.is_absolute() else root/value
        base=root/'local/runtime'
        executable='bin/rawtherapee-cli.exe' if platform=='win32' else 'MacOS/rawtherapee-cli'
        integrated=(root/'raw-engine'/executable) if frozen else base/('RawTherapeeEngine/rawtherapee-cli.exe' if platform=='win32' else 'RawTherapeeEngine.app/Contents/MacOS/rawtherapee-cli')
        reference=(root/'raw-reference'/executable) if frozen else base/('RawTherapee/rawtherapee-cli.exe' if platform=='win32' else 'RawTherapee.app/Contents/MacOS/rawtherapee-cli')
        self.integrated=location('integrated',integrated)
        self.reference=Path(os.environ.get('SOFTLOAF_RAWTHERAPEE_REFERENCE',location('reference',reference)))
        override=cli or os.environ.get('SOFTLOAF_RAWTHERAPEE')
        candidates=[override] if override else [self.integrated,self.reference]+([] if frozen else [shutil.which('rawtherapee-cli'),'/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli'])
        self.cli=next((Path(p) for p in candidates if p and Path(p).is_file()),None)
        self.preview=Path(os.environ.get('SOFTLOAF_RAWTHERAPEE_PREVIEW',str(self.integrated)))
        self.dll_directory=location('dll_directory',root/'local/runtime/dlls') if 'dll_directory' in config else None
        share=Path('/Applications/RawTherapee.app/Contents/Resources/share')
        if self.cli:
            bundled=self.cli.parent.parent/'Resources/share'
            share=bundled if bundled.is_dir() else self.cli.parent if platform=='win32' else share
        self.resources=Path(os.environ.get('SOFTLOAF_RAWTHERAPEE_DATA',str(root/'raw-engine'/('bin' if platform=='win32' else 'Resources/share') if frozen else share)))

    def environment(self,cli,base=None):
        env=dict(os.environ if base is None else base)
        directories=[str(Path(cli).parent)]
        if self.dll_directory:directories.append(str(self.dll_directory))
        env['PATH']=os.pathsep.join(directories+[env.get('PATH','')])
        return env


def find_lcms2():
    configured=os.environ.get('SOFTLOAF_LCMS2_LIBRARY')
    if configured:
        if not Path(configured).is_file():raise RuntimeError('Configured LCMS2 library is missing')
        return configured
    from .runtime_paths import packaged,native_directory
    if packaged():
        return next((str(native_directory()/name) for name in
            ('liblcms2.2.dylib','liblcms2-2.dll','lcms2.dll','liblcms2.so.2')
            if (native_directory()/name).is_file()),None)
    library=ctypes.util.find_library('lcms2')
    if library:return library
    runtime=RawRuntime(Path(__file__).resolve().parents[1])
    directories=[p for p in (runtime.dll_directory,runtime.reference.parent,runtime.cli.parent if runtime.cli else None) if p]
    candidates=[p/name for p in directories for name in ('liblcms2-2.dll','lcms2.dll')]
    candidates += [Path('/opt/homebrew/opt/little-cms2/lib/liblcms2.dylib'),Path('/usr/local/lib/liblcms2.dylib')]
    return next((str(p) for p in candidates if p.is_file()),None)
