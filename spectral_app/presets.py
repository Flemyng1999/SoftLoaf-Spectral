"""Optional, hash-pinned local recipes; never infer a process from its name."""
import hashlib
import json
from pathlib import Path

VISIBLE_NEGATIVE_STOCKS=frozenset({'5203','5207','5213','5219'})


def visible_negative_presets(entries):
    """Curate choices without deleting historical recipes or source evidence."""
    return [entry for entry in entries
            if entry['recipe']['film']['stock'] in VISIBLE_NEGATIVE_STOCKS
            and entry['recipe']['film']['custom_material']['provenance']['process']=='ECN-2']


def load_recipe_presets(root):
    root=Path(root)
    manifest=root/'data/film-presets-manifest.json'
    directory=root/'local/materials/film-presets-v1'
    if not manifest.is_file() or not directory.is_dir():return []
    catalog=json.loads(manifest.read_text())
    if catalog.get('schema')!='softloaf.experimental-presets/1':raise ValueError('Unknown preset catalog')
    result=[]
    for entry in catalog['recipes']:
        name=entry['file']
        if Path(name).name!=name or not name.endswith('.json'):raise ValueError('Invalid preset filename')
        data=(directory/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Preset file identity changed')
        recipe=json.loads(data);identity=recipe['film']['custom_material']['provenance']
        process=identity['process'];route=recipe['route']
        if (process not in ('C-41','ECN-2') or route not in ('negative','print')
                or process!=entry['process'] or route!=entry['route']
                or identity['stock_id']!=recipe['film']['stock'] or identity['density_metric']!='Status M'):
            raise ValueError('Preset process or density metric mismatch')
        result.append({**entry,'recipe':recipe})
    return result
