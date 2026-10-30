"""Build the pinned RT compatibility reader without copying opaque old DLLs.

The caller supplies the official source archive and an installed MSYS2 UCRT64
toolchain. This script does not fetch or execute unidentified source packages.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

SOURCE_URL='https://github.com/RawTherapee/RawTherapee/releases/download/5.12/rawtherapee-5.12.tar.xz'
SOURCE_SHA256='d9a6c10537d64a285bc465675fe59aaa94ce3223823dfbecf0ae2c9599082d57'


def patch_sources(source):
    paths=['rtengine/hilite_recon.cc','rtengine/xtrans_demosaic.cc'];changes=[]
    for name in paths:
        path=source/name;before=path.read_bytes();text=before.decode()
        if name.endswith('hilite_recon.cc'):
            needle='    const ProcParams params;\n'
            if text.count(needle)!=1:raise ValueError('Unexpected reference initialization source')
            text=text.replace(needle,'')
        else:
            needle='''                if (height - top < ts + 4) {
                    mrow = height - top + 2;
                }

                if (width - left < ts + 4) {
                    mcol = width - left + 2;
                }
'''
            if text.count(needle)!=1:raise ValueError('Unexpected reference X-Trans bounds source')
            text=text.replace(needle,'''                // The 5x5 sum must stay within initialized homogeneity maps.
                // The remaining sensor boundary uses the existing RT raw
                // interpolation below, rather than stale tile-buffer bytes.
''')
            needle='xtransborder_interpolate(passes > 1 ? 8 : 11, red, green, blue);'
            if text.count(needle)!=1:raise ValueError('Unexpected reference X-Trans border source')
            text=text.replace(needle,'xtransborder_interpolate(11, red, green, blue);')
        after=text.encode();path.write_bytes(after)
        changes.append({'path':name,'before_sha256':hashlib.sha256(before).hexdigest(),
                        'after_sha256':hashlib.sha256(after).hexdigest()})
    return changes


def compile_reader(source,toolchain,output):
    prefix=toolchain/'ucrt64';cmake=prefix/'bin/cmake.exe';bash=toolchain/'usr/bin/bash.exe'
    for path in (cmake,bash,prefix/'bin/g++.exe',prefix/'bin/ninja.exe'):
        if not path.is_file():raise FileNotFoundError(path)
    env={**os.environ,'PATH':os.pathsep.join([str(prefix/'bin'),str(toolchain/'usr/bin'),os.environ.get('PATH','')]),
         'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig'),'SHELL':str(bash),
         'MSYSTEM':'UCRT64','CHERE_INVOKING':'1','MSYS2_PATH_TYPE':'inherit'}
    command=[str(cmake),'-S',str(source),'-B',str(output),'-G','Ninja',
        '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_POLICY_VERSION_MINIMUM=3.5',
        '-DOPTION_OMP=ON','-DPROC_TARGET_NUMBER=1','-DWITH_JXL=OFF','-DDATADIR=.',
        '-DCMAKE_C_COMPILER='+str(prefix/'bin/gcc.exe'),'-DCMAKE_CXX_COMPILER='+str(prefix/'bin/g++.exe'),
        '-DCMAKE_MAKE_PROGRAM='+str(prefix/'bin/ninja.exe'),'-DCMAKE_PREFIX_PATH='+str(prefix)]
    subprocess.run(command,check=True,env=env)
    subprocess.run([str(cmake),'--build',str(output),'--target','rth-cli','--parallel','4'],check=True,env=env)
    executable=output/'rtgui/rawtherapee-cli.exe'
    return {'processor_target':'generic x86-64','executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
        'build_command_template':[arg.replace(str(source),'<SOURCE>').replace(str(output),'<BUILD>').replace(str(toolchain),'<MSYS2>') for arg in command]}


def build(archive,toolchain,source,output):
    archive,toolchain,source,output=map(Path,(archive,toolchain,source,output))
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SOURCE_SHA256:
        raise ValueError('RT source archive does not match the pinned official release')
    if source.exists() or output.exists():raise FileExistsError('Use new explicit source/build directories')
    # Validate tools before creating output/source directories.
    for path in (toolchain/'ucrt64/bin/cmake.exe',toolchain/'usr/bin/bash.exe'):
        if not path.is_file():raise FileNotFoundError(path)
    source.mkdir(parents=True)
    with tarfile.open(archive) as tar:tar.extractall(source,filter='data')
    source=source/'rawtherapee-5.12';changes=patch_sources(source)
    compiler=compile_reader(source,toolchain,output)
    record={'schema':1,'upstream_source':SOURCE_URL,'upstream_source_sha256':SOURCE_SHA256,
        **compiler,'patches':changes,
        'patch_scope':'Remove unused global ProcParams initialization; keep X-Trans homogeneity sums within initialized maps and use RT interpolation for the outer 11 sensor pixels.',
        }
    (output/'reference-build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record


def build_integrated(source,toolchain,output):
    source,toolchain,output=map(Path,(source,toolchain,output))
    if output.exists():raise FileExistsError(output)
    manifest=json.loads((source/'softloaf-source.json').read_text())
    for name,expected in manifest['local_changes'].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Integrated RT source identity differs: '+name)
    record={'schema':1,'source_snapshot':manifest,**compile_reader(source,toolchain,output)}
    (output/'integrated-build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--archive',type=Path);mode.add_argument('--integrated-source',type=Path)
    p.add_argument('--source',type=Path)
    for name in ('toolchain','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.archive and not a.source:p.error('--archive requires a new --source directory')
    print(json.dumps(build_integrated(a.integrated_source,a.toolchain,a.output) if a.integrated_source else build(a.archive,a.toolchain,a.source,a.output),indent=2))
