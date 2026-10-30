"""Collect installed Python distribution notices actually used by a frozen build."""
import argparse
import ast
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys


def build(analysis,destination):
    entries=ast.literal_eval(Path(analysis).read_text(encoding='utf-8'))
    modules={entry[0].split('.')[0] for group in entries if isinstance(group,list)
        for entry in group if isinstance(entry,tuple) and len(entry)==3 and entry[2] in ('PYMODULE','EXTENSION')}
    mapping=metadata.packages_distributions()
    distributions={name for module in modules for name in mapping.get(module,[])}|{'pyinstaller'}
    target=Path(destination);target.mkdir(parents=True,exist_ok=True);records=[]
    for name in sorted(distributions):
        dist=metadata.distribution(name);folder=target/dist.metadata['Name'];folder.mkdir(exist_ok=True)
        records.append({'name':dist.metadata['Name'],'version':dist.version,'license_expression':dist.metadata.get('License-Expression'),
            'license':dist.metadata.get('License'),'source_links':dist.metadata.get_all('Project-URL',[])})
        (folder/'METADATA.txt').write_text(dist.read_text('METADATA') or str(dist.metadata),encoding='utf-8')
        count=0
        for item in dist.files or []:
            if not any(word in str(item).lower() for word in ('license','copying','copyright','notice')):continue
            source=Path(dist.locate_file(item))
            if not source.is_file() or source.suffix in ('.pyc','.so','.dll','.dylib'):continue
            relative=Path(*[part for part in item.parts if part not in ('..','.')])
            out=folder/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,out);count+=1
        records[-1]['notice_files']=count
    candidates=[Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'lib'/('python'+'.'.join(sys.version.split()[0].split('.')[:2]))/'LICENSE.txt']
    python_license=next((p for p in candidates if p.is_file()),None)
    if python_license is None:raise FileNotFoundError('Python runtime licence was not found')
    shutil.copyfile(python_license,target/'Python-LICENSE.txt')
    record={'schema':1,'python':sys.version.split()[0],'python_source':'https://www.python.org/downloads/source/',
        'distributions':records,'scope':'Python runtime components only; native RAW and OS dependency inventories are separate.'}
    (target/'python-components.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return record

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--analysis',type=Path,required=True);parser.add_argument('--destination',type=Path,required=True)
    a=parser.parse_args();r=build(a.analysis,a.destination);print(json.dumps({'distributions':[(x['name'],x['notice_files']) for x in r['distributions']]}))
