"""Identified optical transmittances and an independent partial-insertion model.

No upstream runtime code is imported. Raw third-party data remain local.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np


def dichroic_transmission(transmission, density_controls):
    """D is a logarithmic insertion control, not multiplied material thickness.

Each path mixes clear light q=10^-D and a filtered fraction 1-q.
The three sequential paths multiply. These are not calibrated enlarger units.
"""
    t=np.asarray(transmission,dtype=float);d=np.asarray(density_controls,dtype=float)
    if t.ndim!=2 or t.shape[1]!=3 or d.shape!=(3,) or not np.isfinite(t).all() or not np.isfinite(d).all() or np.any((t<0)|(t>1)) or np.any(d<0):
        raise ValueError('Invalid dichroic transmittance or control')
    return np.prod(t+(1-t)*10.**-d,axis=1)


def load_optics(root,grid):
    root=Path(root);manifest=root/'data/printing-optics-manifest.json'
    if not manifest.is_file():return None
    from .runtime_paths import science_root
    identity=json.loads(manifest.read_text());directory=science_root(root)/'local/reference-assets/spektrafilm/printing-optics'
    if not directory.is_dir():return None
    for name,record in identity['files'].items():
        path=directory/name
        if path.name!=name or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Optical source identity changed: '+name)
    profile=science_root(root)/'local/reference-assets/spektrafilm/profile-survey/kodak_ultra_endura.json'
    if hashlib.sha256(profile.read_bytes()).hexdigest()!=identity['paper_profile_sha256']:
        raise ValueError('Paper base source identity changed')
    source={**copy.deepcopy(identity),'resampling':'sort source wavelengths; average duplicate positions; linear interpolation; endpoint hold outside source coverage, explicitly assumed, not measured tails',
        'credits':['Andrea Volpato, spektrafilm; original filter data owners retain their rights',
                   'Paper profile base shape: CC BY-SA 4.0; modified by SoftLoaf Spectral; fixed Dmin alignment, resampling; not a measured paper-white record'],
        'rights':'Local reference; raw filter manufacturer and derived LUT redistribution pending review'}
    def read(name,scale):
        a=np.loadtxt(directory/name,delimiter=',');order=np.argsort(a[:,0],kind='stable');a=a[order]
        x,inverse=np.unique(a[:,0],return_inverse=True)
        y=np.bincount(inverse,weights=a[:,1])/np.bincount(inverse)/scale
        if not np.isfinite(a).all() or np.any((y<0)|(y>1)):raise ValueError('Invalid optical source fraction')
        return np.interp(grid,x,y),[float(x[0]),float(x[-1])]
    def record(name,values,coverage):
        return {'name':name,'source':'spektrafilm '+identity['commit']+'; original manufacturer links in source manifest',
            'quantity':'spectral_transmittance','unit':'fraction','wavelengths_nm':np.asarray(grid).tolist(),
            'values':values.tolist(),'native_coverage_nm':coverage,'provenance':copy.deepcopy(source)}
    heat,coverage=read('heat_absorbing__schott__KG3.csv',1)
    lens,lc=read('lens_transmission__canon__canon_24_f28_is.csv',100)
    filters={};cover={}
    for c in 'CMY':filters[c],cover[c]=read('dichroics__edmund_optics__filter_'+c.lower()+'.csv',100)
    p=json.loads(profile.read_text());base=np.asarray(p['data']['base_density'],dtype=float)
    if not np.isfinite(base).all() or np.any(base<0):raise ValueError('Missing paper base data')
    return {'heat':record('Schott KG3 · upstream digitized curve',heat,coverage),
        'lens':record('Canon 24mm f/2.8 IS · reference only, not an enlarger measurement',lens,lc),
        'filters':{'name':'Edmund CMY · upstream digitized curves','source':'Edmund Optics via spektrafilm '+identity['commit'],
            'quantity':'spectral_transmittance','unit':'fraction','wavelengths_nm':np.asarray(grid).tolist(),
            'channels':{c:y.tolist() for c,y in filters.items()},'native_coverage_nm':cover,'provenance':copy.deepcopy(source)},
        'paper_base':{'quantity':'spectral_density','unit':'D','wavelengths_nm':np.asarray(grid).tolist(),
            'values':np.interp(grid,p['data']['wavelengths'],base).tolist(),
            'name':'Ultra Endura · processed upstream base shape','source':'spektrafilm processed profile; not original measured paper white',
            'provenance':copy.deepcopy(source)},'source':source}


def modern_settings(assets):
    if not assets:raise ValueError('Missing identified optical sources')
    return {'pipeline':'spectral-v2','light':'Planck','temperature_k':3400,'exposure_ev':0,
        'filters':[0,.65,.55],'paper':'Ultra Endura','filter_model':'dichroic',
        'optics':{'heat':'KG3','lens':'none'},'preflash':{'exposure':0,'filters':[0,.65,.55]},
        'calibration_note':'Fixed relative printer balance and existing paper exposure denominators. Partial-insertion controls are not calibrated Kodak CP units; no per-image or per-roll fitting.'}
