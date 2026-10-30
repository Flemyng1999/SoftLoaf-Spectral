"""Validate user-supplied scientific inputs and atomically save runtime locations."""
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import sys

from .runtime_paths import SetupRequired, state_root


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def validate_science(directory):
    directory=Path(directory).resolve()
    try:manifest=json.loads((directory/'runtime-science.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as error:raise SetupRequired('Select a prepared scientific-data directory containing runtime-science.json.') from error
    if not isinstance(manifest,dict) or manifest.get('schema')!='softloaf.runtime-science/1' or not isinstance(manifest.get('files'),list) or not 1<=len(manifest['files'])<=10000:
        raise SetupRequired('Unsupported or empty scientific-data directory.')
    seen=set()
    for record in manifest['files']:
        if not isinstance(record,dict) or not isinstance(record.get('path'),str) or not isinstance(record.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',record['sha256']):
            raise SetupRequired('Invalid scientific-data inventory record.')
        name=record['path'];relative=PurePosixPath(name)
        if not name or name!=relative.as_posix() or ':' in name or relative.is_absolute() or '..' in relative.parts or '\\' in name or name in seen:
            raise SetupRequired('Invalid scientific-data inventory path.')
        seen.add(name);path=(directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or file_digest(path)!=record.get('sha256'):
            raise SetupRequired('Scientific-data file is missing or differs from its inventory: '+name)
    required={
        'local/film-color-slides/hyperspectral-demo/output/reversal-E100/data/'+name
        for name in ('E100_dye_density_CMY.csv','E100_characteristic_RGB.csv','E100_linear_sensitivity_RGB.csv')}
    required|={'local/film-color-slides/hyperspectral-demo/output/reversal-E100/intermediate/model.npz',
        'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',
        'artifacts/sampling-database/report.json','artifacts/sampling-database/reversal.sqlite',
        'artifacts/sampling-database/negative.sqlite','artifacts/sampling-database/models/reversal.npz',
        'artifacts/sampling-database/models/negative.npz'}
    required|={'local/film-color-slides/data/'+name for name in ('CIE_xyz_official.csv','CIE_std_illum_D50.csv','CIE_std_illum_D65.csv')}
    if not required<=seen:raise SetupRequired('Scientific-data inventory lacks required E100, CIE or frozen-model inputs.')
    return manifest


def configure(science,data,volume,*,state=None):
    science,data,volume=map(lambda p:Path(p).resolve(),(science,data,volume))
    if not volume.is_mount() or not data.is_relative_to(volume):
        raise SetupRequired('Select a mounted external data volume and a folder on it.')
    if sys.platform=='darwin' and volume.parent!=Path('/Volumes'):
        raise SetupRequired('RAW and hyperspectral data require an external data volume.')
    if sys.platform=='win32' and volume.drive.casefold()==Path(os.environ.get('SystemDrive','C:')+'\\').drive.casefold():
        raise SetupRequired('Select a separate data drive for RAW and hyperspectral data.')
    if not science.is_relative_to(volume):
        raise SetupRequired('The scientific-data directory must remain on the selected data volume.')
    validate_science(science)
    state=Path(state) if state is not None else state_root()
    state.mkdir(parents=True,exist_ok=True)
    record={'schema':1,'science_root':str(science),'data_root':str(data),'volume':str(volume)}
    temporary=state/'runtime.working.json';temporary.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temporary.replace(state/'runtime.json')
    return record
