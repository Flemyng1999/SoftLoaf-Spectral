"""Freeze only program code/resources and native libraries; never scientific inputs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def build(root,build_directory,output,native_dependencies=None):
    root=Path(root).resolve();build_directory=Path(build_directory).resolve();output=Path(output).resolve()
    work=root/'build/frozen-service';work.mkdir(parents=True,exist_ok=True)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--name','spectral-service',
        '--distpath',str(output),'--workpath',str(work/'work'),'--specpath',str(work),
        '--paths',str(root),'--copy-metadata','opencolorio','--copy-metadata','colour-science',
        '--exclude-module','pytest','--exclude-module','tkinter','--exclude-module','IPython',
        '--exclude-module','pandas','--exclude-module','pymupdf','--exclude-module','cv2',
        '--exclude-module','matplotlib']
    def data(path,relative):args.extend(['--add-data',str(path)+':'+str(relative)])
    # Hash-based producer identities read these exact source files at runtime.
    for folder in ('spectral_app','spectral_lut','experiments'):
        for path in sorted((root/folder).rglob('*.py')):
            if path.is_symlink():raise ValueError('Program source must not follow external symlinks')
            data(path,path.relative_to(root).parent)
    for folder in ('design/gui-v2','assets/branding','assets/science/cie','assets/lensfun','data'):
        for path in sorted((root/folder).rglob('*')):
            if path.is_file():data(path,path.relative_to(root).parent)
    for path in sorted((root/'core').glob('*/*')):
        if path.suffix in ('.metal','.hlsl'):data(path,path.relative_to(root).parent)
    for name in ('VERSION','LICENSE','NOTICE','third_party/aces-v1.2/LICENSE.md'):
        path=root/name;data(path,path.relative_to(root).parent)
    prefix='' if sys.platform=='win32' else 'lib';extension='.dll' if sys.platform=='win32' else '.dylib' if sys.platform=='darwin' else '.so'
    for name in ('softloaf_core','softloaf_imageio','softloaf_d3d12' if sys.platform=='win32' else 'softloaf_metal'):
        path=build_directory/(prefix+name+extension)
        if not path.is_file():raise FileNotFoundError(path)
        args.extend(['--add-binary',str(path)+':native'])
    if sys.platform=='darwin':
        for path in ('/opt/homebrew/opt/little-cms2/lib/liblcms2.2.dylib','/opt/homebrew/opt/lensfun/lib/liblensfun.1.dylib'):
            args.extend(['--add-binary',path+':native'])
    elif sys.platform=='win32':
        if not native_dependencies:raise ValueError('Windows requires an explicit native dependency directory')
        for name in ('liblcms2-2.dll','liblensfun.dll'):
            path=Path(native_dependencies)/name
            if not path.is_file():raise FileNotFoundError(path)
            args.extend(['--add-binary',str(path)+':native'])
    args.append(str(root/'scripts/frozen_service.py'))
    subprocess.run(args,cwd=root,check=True)
    return output/'spectral-service'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--native',type=Path,default=ROOT/'build')
    parser.add_argument('--output',type=Path,default=ROOT/'dist/runtime')
    parser.add_argument('--native-dependencies',type=Path)
    args=parser.parse_args();print(build(args.root,args.native,args.output,args.native_dependencies))
