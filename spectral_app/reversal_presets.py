"""Optional reversal materials from identified complete component sets."""
import hashlib
import json
from pathlib import Path


def load_reversal_presets(root):
    from .runtime_paths import science_root
    root=Path(root);manifest=root/'data/reversal-presets-manifest.json';directory=science_root(root)/'local/materials/reversal-presets-v1'
    if not manifest.is_file() or not directory.is_dir():return []
    catalog=json.loads(manifest.read_text());result=[]
    if catalog['schema']!='softloaf.reversal-presets/1':raise ValueError('Unknown reversal catalog')
    for entry in catalog['materials']:
        values=[]
        for role in ['file','plot_file']:
            name=entry[role]
            if Path(name).name!=name:raise ValueError('Invalid reversal filename')
            raw=(directory/name).read_bytes();expected=entry['sha256' if role=='file' else 'plot_sha256']
            if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Reversal source identity changed')
            values.append(json.loads(raw))
        material,plot=values;p=material.get('provenance',{})
        if entry['process']!='E-6' or p.get('process')!='E-6' or p.get('stock_id')!=entry['id'] or p.get('density_metric')!='Status A':raise ValueError('Reversal process identity mismatch')
        result.append({**entry,'material':material,'plot':plot})
    return result
