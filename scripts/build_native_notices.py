"""Collect exact native provider recipes, source locations and installed notices.

Run on the build host. Output contains public package metadata, never developer
paths. It does not approve scientific-data redistribution.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import shutil


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def notice_files(provider,target):
    count=0
    for p in sorted(provider.rglob('*')):
        if not p.is_file() or p.is_symlink():continue
        name=p.name.lower()
        if not any(word in name for word in ('license','licence','copying','copyright','notice','lgpl','gpl')):continue
        if p.suffix.lower() in ('.h','.hpp','.c','.cc','.py','.pyc','.rb','.so','.dll','.dylib','.o','.a'):continue
        if p.stat().st_size>2_000_000:continue
        out=target/p.relative_to(provider);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out);count+=1
    return count


def macos(analysis,roles,destination):
    entries=ast.literal_eval(Path(analysis).read_text(encoding='utf-8'))
    paths={Path(x[1]).resolve() for group in entries if isinstance(group,list)
           for x in group if isinstance(x,tuple) and len(x)==3 and x[2] in ('BINARY','EXTENSION')}
    providers={Path(*p.parts[:6]) for p in paths if str(p).startswith('/opt/homebrew/Cellar/')}
    for role in roles:
        data=json.loads((Path(role)/'native-inputs.json').read_text())
        for component in data['components']:
            p=component.get('provider',{})
            if p.get('kind')=='homebrew':providers.add(Path('/opt/homebrew/Cellar')/p['name']/p['version'])
            elif component['file']!='rawtherapee-cli':
                raise ValueError('RAW dependency lacks a reviewed provider: '+component['file'])
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);records=[]
    for provider in sorted(providers):
        sbom=json.loads((provider/'sbom.spdx.json').read_text())
        package=sbom['packages'][0]
        name=provider.parent.name;version=provider.name;folder=destination/name;folder.mkdir(exist_ok=True)
        recipes=sorted((provider/'.brew').glob('*.rb'))
        if len(recipes)!=1:raise ValueError('Expected one exact installed Homebrew recipe: '+name)
        recipe=recipes[0];shutil.copyfile(recipe,folder/'build-recipe.rb')
        licence=re.search(r'^\s*license\s+(.+)',recipe.read_text(),re.M)
        record={'name':name,'version':version,'provider':'Homebrew','source':package.get('downloadLocation'),
                'source_checksums':package.get('checksums',[]),'license_recipe':licence.group(1) if licence else 'See exact build recipe',
                'recipe_sha256':digest(recipe),'notice_files':notice_files(provider,folder)}
        if not record['source'] or record['source'] in ('NOASSERTION','NONE'):raise ValueError('Source location missing: '+name)
        records.append(record)
    result={'schema':1,'platform':'macos-arm64','components':records}
    (destination/'native-components.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--role',type=Path,action='append',default=[]);p.add_argument('--destination',type=Path,required=True)
    a=p.parse_args();r=macos(a.analysis,a.role,a.destination);print(json.dumps({'components':len(r['components']),'without_installed_notice':[x['name'] for x in r['components'] if not x['notice_files']]}))
