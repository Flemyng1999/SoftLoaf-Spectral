"""Preserve the two MSVC PNG-codec providers, recipes and exact cached sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def digest(path,algorithm='sha256'):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,algorithm).hexdigest()


def audit(root,installed,service,notices,sources):
    root,installed,service,notices,sources=map(Path,(root,installed,service,notices,sources))
    records=[]
    for name,dll in [('libpng','libpng16.dll'),('zlib','z.dll')]:
        provider=installed/'share'/name;port=root/'ports'/name
        abi=dict(line.split(' ',1) for line in (provider/'vcpkg_abi_info.txt').read_text().splitlines() if ' ' in line)
        if abi.get('features')!='core':raise ValueError('Review additional vcpkg features before distribution: '+name)
        for path in port.rglob('*'):
            if path.is_file() and path.name in abi and digest(path)!=abi[path.name]:
                raise ValueError('vcpkg build recipe differs: '+path.name)
        if digest(root/'scripts/ports.cmake')!=abi.get('ports.cmake'):
            raise ValueError('vcpkg build driver differs: '+name)
        binary=installed/'bin'/dll;frozen=service/'_internal'/dll
        if digest(binary)!=digest(frozen):raise ValueError('Frozen DLL differs from installed vcpkg provider: '+dll)
        metadata=json.loads((provider/'vcpkg.spdx.json').read_text())
        primary=next(p for p in metadata['packages'] if p['name']==name)
        upstream=[p for p in metadata['packages'] if p.get('downloadLocation','').startswith('git+https://github.com/') and '@' in p['downloadLocation']]
        if len(upstream)!=1:raise ValueError('Expected one reviewed upstream source: '+name)
        upstream=upstream[0];repository,ref=upstream['downloadLocation'].removeprefix('git+https://github.com/').rsplit('@',1)
        archive_name=repository.replace('/','-')+'-'+ref+'.tar.gz';archive=root/'downloads'/archive_name
        expected=next(c['checksumValue'] for c in upstream['checksums'] if c['algorithm']=='SHA512')
        if digest(archive,'sha512')!=expected:raise ValueError('vcpkg upstream archive differs: '+name)
        notice=notices/name;notice.mkdir(parents=True,exist_ok=True)
        for filename in ('copyright','vcpkg.spdx.json','vcpkg_abi_info.txt'):shutil.copy2(provider/filename,notice/filename)
        target=sources/name;target.mkdir(parents=True,exist_ok=True)
        shutil.copytree(port,target/'port',dirs_exist_ok=True);shutil.copy2(archive,target/archive_name)
        records.append({'name':name,'version':primary['versionInfo'],'provider':'vcpkg x64-windows',
            'features':['core'],'binary':dll,'binary_sha256':digest(binary),
            'source':'https://github.com/'+repository+'/archive/'+ref+'.tar.gz',
            'source_sha512':expected,'source_sha256':digest(archive),'source_archive':name+'/'+archive_name,
            'recipe_sha256':digest(port/'portfile.cmake'),'installed_abi_sha256':digest(provider/'vcpkg_abi_info.txt')})
    # Build helpers are source code, kept in the source supplement rather than
    # inflating the installed notices. No other project instructions are copied.
    for relative in ('scripts','ports/vcpkg-cmake','ports/vcpkg-cmake-config'):
        shutil.copytree(root/relative,sources/'build-helpers'/relative,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('AGENTS.md','__pycache__','*.pyc'))
    for name in ('vcpkg-cmake','vcpkg-cmake-config'):
        shutil.copytree(installed/'share'/name,sources/'installed-build-helpers'/name,dirs_exist_ok=True)
    (sources/'triplets').mkdir(exist_ok=True);shutil.copy2(root/'triplets/x64-windows.cmake',sources/'triplets/x64-windows.cmake')
    shutil.copy2(root/'LICENSE.txt',sources/'vcpkg-LICENSE.txt')
    result={'schema':1,'platform':'windows-x64','scope':'MSVC PNG codec dependencies; MSYS2, Python and Microsoft SDK/runtime inventories are separate.','components':records}
    notices.mkdir(parents=True,exist_ok=True);(notices/'native-components.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','installed','service','notices','sources'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(audit(a.root,a.installed,a.service,a.notices,a.sources),indent=2))
