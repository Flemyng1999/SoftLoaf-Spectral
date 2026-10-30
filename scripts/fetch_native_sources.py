"""Fetch hash-identified native source archives and preserve their notices.

Sources come only from the exact installed provider's source inventory. The
archives are not extracted as programs and no downloaded code is executed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path,PurePosixPath
import tarfile
import subprocess
import urllib.parse
import urllib.request


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def fetch(record,destination,notices):
    url=record['source']
    if not url.startswith('https://'):raise ValueError('Expected HTTPS source URL')
    suffix=next((s for s in ('.tar.xz','.tar.gz','.tar.bz2','.tgz','.tar.zst','.zip') if urllib.parse.urlsplit(url).path.endswith(s)),None)
    if not suffix:raise ValueError('Unknown source archive extension: '+record['name'])
    name=record['name'].replace('@','-').replace('+','p')+'-'+record['version']+suffix
    target=destination/name
    expected=next((x['checksumValue'].lower() for x in record.get('source_checksums',[]) if x['algorithm']=='SHA256'),None)
    if not target.is_file() or (expected and digest(target)!=expected):
        temporary=target.with_suffix(target.suffix+'.partial')
        subprocess.run(['curl','--fail','--location','--retry','3','--connect-timeout','15','--max-time','180',
                        '--silent','--show-error','--output',str(temporary),url],check=True)
        actual=digest(temporary)
        if expected and actual!=expected:raise ValueError('Source hash mismatch: '+name)
        temporary.replace(target)
    actual=digest(target)
    if suffix!='.zip' and suffix!='.tar.zst':
        folder=notices/record['name']/'upstream-source-notices'
        with tarfile.open(target) as archive:
            for member in archive:
                p=PurePosixPath(member.name);lower=p.name.lower()
                if not member.isfile() or member.size>2_000_000 or '..' in p.parts:continue
                if not any(word in lower for word in ('license','licence','copying','copyright','notice')):continue
                if p.suffix.lower() in ('.c','.h','.cc','.py','.rs','.toml','.json','.cmake'):continue
                out=folder/Path(*p.parts[1:]);out.parent.mkdir(parents=True,exist_ok=True)
                stream=archive.extractfile(member)
                if stream is not None:out.write_bytes(stream.read())
    print(name,actual,flush=True)
    return {'name':record['name'],'version':record['version'],'file':name,'sha256':actual,'source':url}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--destination',type=Path,required=True);p.add_argument('--notices',type=Path,required=True)
    a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=True)
    records=json.loads(a.inventory.read_text())['components']
    # The permissively licensed OpenMP source is a very large complete LLVM tree;
    # its exact URL, SHA and build recipe remain in the dependency inventory.
    selected=[r for r in records if r['name']!='libomp']
    with ThreadPoolExecutor(max_workers=4) as pool:
        result=list(pool.map(lambda r:fetch(r,a.destination,a.notices),selected))
    (a.destination/'source-inventory.json').write_text(json.dumps({'schema':1,'archives':result},indent=2)+'\n')

if __name__=='__main__':main()
