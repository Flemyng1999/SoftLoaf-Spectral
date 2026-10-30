"""Optional, hash-pinned source detail, separate from computation materials."""
import hashlib
import json
from pathlib import Path


def load_e100_plot(root, sources, calculation_step_nm):
    manifest_path=root/'data/e100-plot-reference-manifest.json'
    path=root/'local/materials/e100-plot-v1/sensitivity.json'
    if not path.exists() or not manifest_path.exists():return {}
    manifest=json.loads(manifest_path.read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['plot_sha256']:
        raise ValueError('E100 source plot identity mismatch; re-extract the reviewed PDF.')
    # Extra detail must describe this archived computation material, not another
    # E100 calibration supplied through a different archive.
    if sources.get('E100_linear_sensitivity_RGB.csv')!=manifest['calculation_sensitivity_sha256']:return {}
    data=json.loads(path.read_text())
    data['calculation_step_nm']=float(calculation_step_nm)
    data['provenance_sha256']=manifest['plot_sha256']
    return {'E100':{'sensitivity':data}}


def load_vision3_plots(root):
    """Only reviewed material/plot pairs may supply optional display detail."""
    manifest=root/'data/vision3-materials-manifest.json'
    if not manifest.exists():return {}
    data=json.loads(manifest.read_text());directory=root/'local/materials/vision3-source-v2';out={}
    if data.get('schema')!='softloaf.vision3-materials/1':raise ValueError('Unknown VISION3 material catalog')
    for entry in data['materials']:
        if entry['id'] not in ('5203','5207','5213','5219'):raise ValueError('Unselected motion-picture stock')
        for key,hash_key in [('file','sha256'),('plot_file','plot_sha256')]:
            if Path(entry[key]).name!=entry[key]:raise ValueError('Invalid VISION3 file name')
            if hashlib.sha256((directory/entry[key]).read_bytes()).hexdigest()!=entry[hash_key]:raise ValueError('VISION3 source plot identity mismatch')
        material=json.loads((directory/entry['file']).read_text());plot=json.loads((directory/entry['plot_file']).read_text())
        plot['sensitivity']['reference_curve']=material['sensitivity']
        plot['sensitivity']['sampling_kind']='manufacturer_chart_digitization' if entry['id']!='5203' else 'manufacturer_vector'
        out[entry['id']]=plot
    return out
