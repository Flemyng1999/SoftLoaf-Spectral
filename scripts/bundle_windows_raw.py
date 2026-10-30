"""Copy a PE RAW reader and its non-system DLL closure into an isolated role."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import pefile


def imports(path):
    with pefile.PE(str(path),fast_load=True) as pe:
        pe.parse_data_directories(directories=[1,13])
        entries=list(getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]))+list(getattr(pe,'DIRECTORY_ENTRY_DELAY_IMPORT',[]))
        return sorted({e.dll.decode('ascii').lower() for e in entries})


def bundle(executable,share,dependencies,destination,prefer_dependencies=False):
    executable,share,dependencies,destination=map(Path,(executable,share,dependencies,destination))
    if destination.exists():raise FileExistsError(destination)
    folder=destination/'bin';folder.mkdir(parents=True)
    if __package__:from .install_rt_resources import install
    else:from install_rt_resources import install
    install(share,folder,'windows')
    lookup={p.name.lower():p for p in dependencies.glob('*.dll')}
    if not prefer_dependencies:lookup.update({p.name.lower():p for p in executable.parent.glob('*.dll')})
    system=Path(__import__('os').environ['SystemRoot'])/'System32'
    queue=[executable];seen={};records=[]
    while queue:
        source=queue.pop();name=source.name.lower()
        if name in seen:continue
        seen[name]=source
        target=folder/('rawtherapee-cli.exe' if source==executable else source.name)
        shutil.copy2(source,target)
        records.append({'file':target.name,'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                        'provider':'explicit-dependency-directory' if source.parent==dependencies else 'RAW-distribution'})
        for dep in imports(source):
            if dep in lookup:queue.append(lookup[dep])
            elif dep.startswith(('api-ms-','ext-ms-')) or (system/dep).is_file():continue
            else:raise RuntimeError('Unresolved RAW dependency: '+dep)
    record={'schema':1,'architecture':'x64','role_isolated_dependencies':True,'components':records}
    (destination/'native-inputs.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('executable','share','dependencies','destination'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--prefer-dependencies',action='store_true')
    a=p.parse_args();r=bundle(a.executable,a.share,a.dependencies,a.destination,a.prefer_dependencies)
    print(json.dumps({'copied_native_components':len(r['components'])}))
