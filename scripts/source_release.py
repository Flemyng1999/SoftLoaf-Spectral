"""Build an audited source archive from an immutable Git commit.

Does not create tags, upload files, collect ignored assets or certify binaries.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def source_channel(version):
    number=r'(?:0|[1-9][0-9]*)'
    if not isinstance(version,str) or not re.fullmatch(rf'{number}\.{number}\.{number}(?:-alpha\.[1-9][0-9]*)?',version):
        raise ValueError('Expected a canonical stable or alpha release version')
    return 'source-only prerelease' if '-alpha.' in version else 'source archive'


def validate_entry(name,data,policy):
    p=PurePosixPath(name)
    def reject(reason):raise ValueError(f'{name}: {reason}')
    if p.is_absolute() or '..' in p.parts or '\\' in name:reject('unsafe archive path')
    if not p.parts or any(part in policy['forbidden_components'] for part in p.parts):reject('private or generated path')
    if p.parts[0] not in policy['directories'] and name not in policy['files']:reject('outside source inventory')
    if p.suffix.lower() in policy['forbidden_suffixes']:reject('excluded data or binary')
    if p.suffix.lower()=='.csv':
        if hashlib.sha256(data).hexdigest()!=policy['approved_csv'].get(name):reject('unreviewed or modified numerical table')
    if any(prefix+home.encode()+b'/' in data for home in policy['private_home_names']
           for prefix in (b'/Users/',b'/home/')):reject('personal-path marker')
    if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{32,}',data):reject('private key payload')
    if re.search(rb'(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})',data):reject('credential-shaped value')
    if name=='data/vision3-materials-manifest.json':
        for item in json.loads(data)['materials']:
            if set(item['fit'])!=set(policy['public_fit_fields']):reject('material data embedded in identity summary')


def build(commit,output,root=ROOT):
    root=Path(root);output=Path(output)
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('A full immutable commit SHA is required')
    def git(*args):return subprocess.check_output(['git','-C',str(root),*args])
    if git('rev-parse',commit+'^{commit}').decode().strip()!=commit:raise ValueError('Commit identity mismatch')
    version=git('show',commit+':VERSION').decode().strip()
    policy=json.loads(git('show',commit+':release/source-policy.json'))
    channel=source_channel(version)
    if policy.get('version')!=version:raise ValueError('Source policy version differs from VERSION')
    output.mkdir(parents=True,exist_ok=True)
    stem='SoftLoaf-Spectral-'+version+'-source';archive=output/(stem+'.tar.gz')
    partial=archive.with_suffix(archive.suffix+'.partial');records=[]
    process=subprocess.Popen(['git','-C',str(root),'archive','--format=tar',commit],stdout=subprocess.PIPE)
    try:
        with partial.open('wb') as raw, gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as compressed:
            with tarfile.open(fileobj=process.stdout,mode='r|') as source,tarfile.open(fileobj=compressed,mode='w|') as target:
                for item in source:
                    if item.isdir():continue
                    if not item.isfile():raise ValueError(item.name+': only regular source files are allowed')
                    stream=source.extractfile(item);data=stream.read();validate_entry(item.name,data,policy)
                    records.append({'path':item.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
                    import io
                    item.name=stem+'/'+item.name;target.addfile(item,io.BytesIO(data))
        if process.wait()!=0:raise RuntimeError('Git source archive failed')
        partial.replace(archive)
    except BaseException:
        process.kill();process.wait();partial.unlink(missing_ok=True);raise
    manifest={'schema':1,'version':version,'commit':commit,'channel':channel,
              'scientific_runtime_included':False,'installer_included':False,
              'files':records,'archive':archive.name,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    record_path=output/(stem+'-manifest.json')
    record_path.write_text(json.dumps(manifest,indent=2)+'\n')
    sums=output/'SHA256SUMS'
    sums.write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in (archive,record_path)))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True);parser.add_argument('--output',type=Path,default=ROOT/'dist/source')
    args=parser.parse_args();manifest=build(args.commit,args.output)
    print(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2))
