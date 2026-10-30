"""Identify bundled MSYS2 DLLs by original package bytes, not by filename alone."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def parse_fields(text):
    result={};key=None
    for line in text.splitlines():
        if line.startswith('%') and line.endswith('%'):
            key=line[1:-1];result[key]=[]
        elif line and key:result[key].append(line)
    return result


def verify_member(binary,archive,member,tar_command=('tar',),env=None):
    expected=digest(binary);actual=hashlib.sha256()
    process=subprocess.Popen([*map(str,tar_command),'-xOf',str(archive),member],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    for block in iter(lambda:process.stdout.read(1024*1024),b''):actual.update(block)
    error=process.stderr.read();code=process.wait()
    if code:raise RuntimeError('Cannot read original binary package: '+error.decode(errors='replace'))
    if actual.hexdigest()!=expected:raise ValueError(Path(binary).name+' differs from its binary package')
    return expected


def verify_source_recipe(archive,base,expected,tar_command=('tar',),env=None):
    result=subprocess.run([*map(str,tar_command),'-xOf',str(archive),base+'/PKGBUILD'],capture_output=True,check=True,env=env)
    actual=hashlib.sha256(result.stdout).hexdigest()
    if actual!=expected:raise ValueError(base+' source recipe differs from the binary build')
    return actual


def source_notices(archive,destination,tar_command=('tar',),env=None):
    """Read license texts from a verified source package and its upstream tar."""
    def safe(name):
        p=PurePosixPath(name)
        return not p.is_absolute() and '..' not in p.parts and '\\' not in name and ':' not in name
    def notice(name):
        p=PurePosixPath(name)
        return (safe(name) and
                any(word in p.name.lower() for word in ('license','licence','copying','copyright','notice','authors'))
                and p.suffix.lower() not in ('.c','.h','.cc','.cpp','.py','.rs','.json','.toml','.cmake'))
    def save(name,data):
        if len(data)>2_000_000:return 0
        target=Path(destination)/Path(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);return 1
    names=subprocess.check_output([*map(str,tar_command),'-tf',str(archive)],env=env,text=True).splitlines();count=0
    for name in names:
        p=PurePosixPath(name)
        if not safe(name) or name.endswith('/'):continue
        if not notice(name) and not name.endswith(('.tar.gz','.tar.xz','.tar.bz2','.tgz')):continue
        data=subprocess.check_output([*map(str,tar_command),'-xOf',str(archive),name],env=env)
        if notice(name):count+=save(name,data)
        else:
            with tarfile.open(fileobj=io.BytesIO(data)) as nested:
                for member in nested:
                    if member.isfile() and member.size<=2_000_000 and notice(member.name):
                        count+=save(p.name+'/'+member.name,nested.extractfile(member).read())
    return count


def installed_owners(root):
    owners={}
    for folder in sorted((root/'var/lib/pacman/local').iterdir()):
        if not (folder/'desc').is_file() or not (folder/'files').is_file():continue
        fields=parse_fields((folder/'desc').read_text(encoding='utf-8'))
        for name in parse_fields((folder/'files').read_text(encoding='utf-8')).get('FILES',[]):
            if name.lower().endswith('.dll'):owners[name.casefold()]=(folder,fields,name)
    return owners


def audit(root,paths,destination):
    root=Path(root).resolve();destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    owners=installed_owners(root);packages={};binaries=[]
    tar=(root/'usr/bin/tar.exe')
    if not tar.is_file():raise FileNotFoundError(tar)
    env={**os.environ,'PATH':os.pathsep.join([str(root/'usr/bin'),str(root/'ucrt64/bin'),os.environ.get('PATH','')])}
    for path in sorted(set(map(Path,paths))):
        relative=path.resolve().relative_to(root).as_posix()
        if relative.casefold() not in owners:raise ValueError('DLL has no installed package owner: '+relative)
        folder,fields,member=owners[relative.casefold()]
        name=fields['NAME'][0];version=fields['VERSION'][0];base=fields['BASE'][0]
        candidates=[p for p in (root/'var/cache/pacman/pkg').glob(name+'-'+version+'-*.pkg.tar.*') if not p.name.endswith('.sig')]
        if len(candidates)!=1:raise ValueError('Expected one exact cached binary package: '+name+' '+version)
        archive=candidates[0];verified=verify_member(path,archive,member,(tar,'--force-local'),env)
        binaries.append({'file':path.name,'sha256':verified,'package':name,'version':version,'package_member':member})
        if name in packages:continue
        target=destination/name;target.mkdir(exist_ok=True)
        metadata={}
        for entry in ('.PKGINFO','.BUILDINFO'):
            result=subprocess.run([str(tar),'--force-local','-xOf',str(archive),entry],capture_output=True,check=True,env=env)
            (target/entry.lstrip('.')).write_bytes(result.stdout)
            metadata[entry.lstrip('.')+'_sha256']=hashlib.sha256(result.stdout).hexdigest()
            if entry=='.BUILDINFO':
                values=dict(line.split(' = ',1) for line in result.stdout.decode().splitlines() if ' = ' in line)
                recipe=values.get('pkgbuild_sha256sum','')
                if len(recipe)!=64:raise ValueError('Binary build has no PKGBUILD identity: '+name)
                metadata['build_recipe_sha256']=recipe
        # Preserve installed upstream notices owned by this exact package.
        count=0
        for item in parse_fields((folder/'files').read_text(encoding='utf-8')).get('FILES',[]):
            if '/share/licenses/' not in item or item.endswith('/'):continue
            source=root/item
            if source.is_file():
                out=target/'notices'/Path(item).relative_to(Path(item).parts[0]+'/share/licenses')
                out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,out);count+=1
        packages[name]={'name':name,'version':version,'provider':'MSYS2 UCRT64',
            'source_package_base':base,'source':'https://repo.msys2.org/mingw/sources/'+base+'-'+version+'.src.tar.zst',
            'source_checksums':[],'binary_package':archive.name,'binary_package_sha256':digest(archive),
            'upstream':fields.get('URL',[]),'licenses':fields.get('LICENSE',[]),'notice_files':count,**metadata}
    result={'schema':1,'platform':'windows-x64','components':list(packages.values()),'binaries':binaries}
    (destination/'native-components.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--role',type=Path,action='append',default=[]);p.add_argument('--destination',type=Path,required=True)
    p.add_argument('--sources-manifest',type=Path)
    a=p.parse_args();paths=set();prefix=(a.toolchain/'ucrt64/bin').resolve()
    for role in a.role:
        for item in json.loads((role/'native-inputs.json').read_text())['components']:
            if item['file'].lower()=='rawtherapee-cli.exe':continue
            source=prefix/item['file']
            if not source.is_file() or digest(source)!=item['input_sha256']:raise ValueError('RAW DLL does not match curated UCRT64 provider: '+item['file'])
            paths.add(source)
    entries=ast.literal_eval(a.analysis.read_text(encoding='utf-8'))
    for group in entries:
        if not isinstance(group,list):continue
        for item in group:
            if isinstance(item,tuple) and len(item)==3 and item[2] in ('BINARY','EXTENSION'):
                path=Path(item[1]).resolve()
                if path.is_relative_to(a.toolchain.resolve()) and path.suffix.lower()=='.dll':paths.add(path)
    result=audit(a.toolchain,paths,a.destination)
    if a.sources_manifest:
        records=json.loads(a.sources_manifest.read_text())['archives'];sources={(r['name'],r['version']):r for r in records}
        env={**os.environ,'PATH':os.pathsep.join([str(a.toolchain/'usr/bin'),str(a.toolchain/'ucrt64/bin'),os.environ.get('PATH','')])}
        for item in result['components']:
            record=sources[(item['name'],item['version'])];archive=a.sources_manifest.parent/record['file']
            if digest(archive)!=record['sha256']:raise ValueError('Source archive hash changed: '+item['name'])
            verify_source_recipe(archive,item['source_package_base'],item['build_recipe_sha256'],(a.toolchain/'usr/bin/tar.exe','--force-local'),env)
            item['source_archive_sha256']=record['sha256'];item['source_recipe_verified']=True
            if not item['notice_files']:
                item['source_notice_files']=source_notices(archive,a.destination/item['name']/'upstream-source-notices',(a.toolchain/'usr/bin/tar.exe','--force-local'),env)
                if not item['source_notice_files']:raise ValueError('No upstream notice found: '+item['name'])
        (a.destination/'native-components.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'packages':len(result['components']),'verified_native_binaries':len(result['binaries'])}))
