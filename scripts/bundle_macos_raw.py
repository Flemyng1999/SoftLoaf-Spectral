"""Give each RAW reader its own relocated native dependency closure.

The official compatibility reader must not silently load the integrated
reader's newer libraries. Inputs are local public software distributions,
never scanner profiles or scientific curves.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def output(*args):
    return subprocess.check_output(args,text=True)


def dependencies(path):
    return [line.strip().split(' (compatibility',1)[0] for line in output('otool','-arch','arm64','-L',str(path)).splitlines()[1:]
            if line.startswith('\t')]


def rpaths(path):
    text=output('otool','-arch','arm64','-l',str(path))
    return re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset',text)


def relocate_resource_literals(path):
    """RT 5.12 macOS hardcodes /Applications unless OSX_DEV_BUILD is selected.

    Relocate only its complete NUL-terminated resource constants in the
    official compatibility reader. String offsets and all numeric code stay
    unchanged. This is equivalent to the documented relative-path build option;
    original input hashes, the changed constants and the adaptation travel with
    the package. Native load commands are independently relocated below.
    """
    path=Path(path);raw=path.read_bytes();changes=[]
    for old,new in [(b'/Applications/RawTherapee.app/Contents/Resources/share/lensfun',b'../Resources/share/lensfun'),
                    (b'/Applications/RawTherapee.app/Contents/Resources/share',b'../Resources/share'),
                    (b'/Applications/RawTherapee.app/Contents/Resources',b'../Resources')]:
        count=raw.count(old+b'\0')
        if count:
            raw=raw.replace(old+b'\0',new+b'\0'*(len(old)-len(new)+1))
            changes.append({'original':old.decode(),'relative':new.decode(),'occurrences':count})
    if b'/Applications/RawTherapee.app/Contents/Resources' in raw:
        raise ValueError('Unrecognized absolute RT resource constant; do not patch by guessing')
    path.write_bytes(raw)
    return changes


def bundle(executable,share,destination,dependency_prefix=None,dependency_directories=()):
    executable,share,destination=map(Path,(executable,share,destination))
    if destination.exists():raise FileExistsError('Use a new RAW reader island')
    destination.mkdir(parents=True);(destination/'MacOS').mkdir();(destination/'Frameworks').mkdir()
    if __package__:from .install_rt_resources import install
    else:from install_rt_resources import install
    install(share,destination/'Resources/share','macos')
    paths={};names={};queue=[executable.resolve()];sources=[]
    def resolve(name,owner):
        if dependency_prefix is not None:
            for directory in dependency_directories:
                selected=Path(directory)/Path(name).name
                if selected.is_file():return selected.resolve()
            selected=Path(dependency_prefix)/'lib'/Path(name).name
            if selected.is_file():return selected.resolve()
            keg_matches={p.resolve() for p in (Path(dependency_prefix)/'opt').glob('*/lib/'+Path(name).name) if p.is_file()}
            if len(keg_matches)==1:return keg_matches.pop()
            if len(keg_matches)>1:raise RuntimeError('Ambiguous dependency-provider match for '+Path(name).name)
            if str(owner).startswith('/Applications/RawTherapee.app/'):
                raise RuntimeError('No reviewed dependency-provider match for '+Path(name).name)
        candidate=name.replace('@loader_path',str(owner.parent)).replace('@executable_path',str(executable.parent))
        if candidate.startswith('@rpath/'):
            for base in rpaths(owner)+rpaths(executable):
                base=base.replace('@loader_path',str(owner.parent)).replace('@executable_path',str(executable.parent))
                p=Path(base)/candidate.removeprefix('@rpath/')
                if p.is_file():return p.resolve()
            raise RuntimeError('Unresolved RAW dependency: '+name)
        p=Path(candidate)
        if not p.is_file():raise FileNotFoundError('Unresolved RAW dependency: '+name)
        return p.resolve()
    while queue:
        source=queue.pop()
        if source in paths:continue
        if source!=executable.resolve() and source.name in names and names[source.name]!=source:
            raise ValueError('Ambiguous RAW library basename: '+source.name)
        names[source.name]=source
        target=destination/('MacOS/rawtherapee-cli' if source==executable.resolve() else 'Frameworks/'+source.name)
        arches=output('lipo','-archs',str(source)).strip().split()
        if 'arm64' not in arches:raise ValueError('RAW dependency has no Apple Silicon code: '+source.name)
        if len(arches)>1:subprocess.run(['lipo',str(source),'-thin','arm64','-output',str(target)],check=True)
        else:shutil.copy2(source,target)
        target.chmod(0o755)
        subprocess.run(['codesign','--remove-signature',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        paths[source]=target
        record={'file':source.name,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        if str(source).startswith('/opt/homebrew/Cellar/'):
            parts=source.parts;record['provider']={'kind':'homebrew','name':parts[4],'version':parts[5]}
        else:record['provider']={'kind':'RawTherapee','version':'5.12','role':'official-compatibility' if str(source).startswith('/Applications/') else 'source-integrated'}
        sources.append(record)
        for dep in dependencies(source):
            if dep.startswith(('/System/','/usr/lib/')) or Path(dep).name==source.name:continue
            dependency=resolve(dep,source)
            if dependency!=source:queue.append(dependency)
    relocated_resources=relocate_resource_literals(paths[executable.resolve()])
    for source,target in paths.items():
        if source!=executable.resolve():subprocess.run(['install_name_tool','-id','@rpath/'+target.name,str(target)],check=True)
        for dep in dependencies(source):
            if dep.startswith(('/System/','/usr/lib/')) or Path(dep).name==source.name:continue
            dependency=resolve(dep,source)
            if dependency==source:continue
            new=('@loader_path/../Frameworks/' if target.parent.name=='MacOS' else '@loader_path/')+paths[dependency].name
            subprocess.run(['install_name_tool','-change',dep,new,str(target)],check=True)
        for path in set(rpaths(target)):subprocess.run(['install_name_tool','-delete_rpath',path,str(target)],check=True)
        subprocess.run(['strip','-S',str(target)],check=True)
        subprocess.run(['codesign','--force','--sign','-',str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if any(d.startswith(('/opt/','/Applications/','/Users/')) for d in dependencies(target)):
            raise RuntimeError('External RAW library dependency survived relocation')
    result={'schema':1,'architecture':'arm64','role_isolated_dependencies':True,'relocated_resource_constants':relocated_resources,'components':sources}
    (destination/'native-inputs.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True);parser.add_argument('--share',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--dependency-prefix',type=Path)
    parser.add_argument('--dependency-directory',type=Path,action='append',default=[])
    args=parser.parse_args();result=bundle(args.executable,args.share,args.destination,args.dependency_prefix,args.dependency_directory)
    print(json.dumps({'copied_native_components':len(result['components']),'role_isolated_dependencies':True}))
