"""Optional original-source paper snapshots, separate from film stock presets."""
import hashlib
import json
from pathlib import Path


def load_paper_presets(root):
    from .runtime_paths import science_root
    root=Path(root);path=root/'data/paper-presets-manifest.json';directory=science_root(root)/'local/materials/paper-presets-v1'
    if not path.exists() or not directory.is_dir():return []
    catalog=json.loads(path.read_text())
    if catalog.get('schema')!='softloaf.paper-presets/1':raise ValueError('Unknown paper catalog')
    entries=[]
    for entry in catalog['materials']:
        values=[]
        for role,key in [('file','sha256'),('plot_file','plot_sha256')]:
            name=entry[role]
            if Path(name).name!=name:raise ValueError('Invalid paper filename')
            raw=(directory/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry[key]:raise ValueError('Paper source identity changed')
            values.append(json.loads(raw))
        material,plot=values;p=material.get('provenance',{})
        if p.get('stock_id')!=entry['id'] or p.get('process')!='RA-4' or p.get('density_metric')!='Status A' or not p.get('source_conditions',{}).get('optical_exposure_supported'):raise ValueError('Paper process mismatch')
        entries.append({**entry,'material':material,'plot':plot})
    return entries
