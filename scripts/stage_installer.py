"""Stage program-only installers from explicit native/service/notice inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil

ROOT=Path(__file__).resolve().parents[1]


def inventory(root):
    records=[]
    for p in sorted(root.rglob('*')):
        relative=p.relative_to(root).as_posix()
        if p.is_symlink():
            try:p.resolve().relative_to(root.resolve())
            except ValueError:raise ValueError('Installation symlink escapes payload: '+relative)
            records.append({'path':relative,'symlink':p.readlink().as_posix()})
        elif p.is_file():
            with p.open('rb') as stream:value=hashlib.file_digest(stream,'sha256').hexdigest()
            records.append({'path':relative,'bytes':p.stat().st_size,'sha256':value})
    return {'schema':1,'version':(ROOT/'VERSION').read_text().strip(),
            'hash_stage':'Staging, before signing/notarization. Final distribution hashes are in release SHA256SUMS.',
            'scope':'Program/runtime only; user scientific data and pixels are excluded.','files':records}


def stage(platform,native,service,notices,destination):
    native,service,notices,destination=map(Path,(native,service,notices,destination))
    if destination.exists():raise FileExistsError(destination)
    if not (service/'_internal/spectral_app/model.py').is_file():raise ValueError('Frozen service sources missing')
    for role in ('raw-engine','raw-reference'):
        executable=service/'_internal'/role/('MacOS/rawtherapee-cli' if platform=='macos' else 'bin/rawtherapee-cli.exe')
        if not executable.is_file():raise ValueError('RAW executable missing: '+role)
        resource=service/'_internal'/role/('Resources/share' if platform=='macos' else 'bin')
        for name in ('camconst.json','cammatrices.json','dcraw.json','options'):
            if not (resource/name).is_file():raise ValueError('RAW resource missing: '+role+'/'+name)
    if platform=='macos':
        contents=destination/'SoftLoaf Spectral.app/Contents'
        info=plistlib.loads((native/'Contents/Info.plist').read_bytes())
        (contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
        shutil.copy2(native/'Contents/Info.plist',contents/'Info.plist')
        executable=info['CFBundleExecutable']
        shutil.copy2(native/'Contents/MacOS'/executable,contents/'MacOS'/executable)
        icon=info['CFBundleIconFile']
        shutil.copy2(native/'Contents/Resources'/icon,contents/'Resources'/icon)
        for language in ('en','zh-Hans'):
            shutil.copytree(native/'Contents/Resources'/(language+'.lproj'),contents/'Resources'/(language+'.lproj'))
        target=contents/'Resources'
    else:
        destination.mkdir(parents=True);target=destination
        shutil.copy2(native,target/'SoftLoaf Spectral.exe')
        shutil.copy2(ROOT/'assets/branding/SoftLoafSpectral.ico',target/'App.ico')
        for name in ('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll'):
            shutil.copy2(service/'_internal'/name,target/name)
    # Native build products must not bring a stale service along.
    if (target/'Service').exists():raise ValueError('Native shell input already contains a service')
    shutil.copytree(service,target/'Service',symlinks=True)
    shutil.copytree(notices,target/'Notices',symlinks=True)
    for name in ('LICENSE','NOTICE'):shutil.copy2(ROOT/name,target/name)
    shutil.copy2(ROOT/'docs/installer-README.txt',target/'README.txt')
    report=inventory(destination)
    (target/'payload-inventory.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',choices=('macos','windows'),required=True)
    for name in ('native','service','notices','destination'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=stage(a.platform,a.native,a.service,a.notices,a.destination)
    print(json.dumps({'files':len(r['files']),'version':r['version']}))
