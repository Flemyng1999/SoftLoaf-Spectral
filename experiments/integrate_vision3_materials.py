"""Build four independent VISION3 materials; preserve legacy recipe snapshots.

5203 uses the complete, identified 2015 manufacturer source; the 2025 simplified
sheet remains a separate survey. Other stocks use the new collected own curves.
Status M fits materials; APD is never a fitting target or a printing input.
"""
from pathlib import Path
import copy
import hashlib
import json
import uuid

import numpy as np
from spectral_lut.provenance import public_fit_summary

from experiments.harvest_kodak_motion import SOURCES, ACTIVE_STOCKS
from experiments.build_film_recipes import CHARTS, extract_curves
from experiments.gui_recipe_server import template, fingerprint
from spectral_lut.reference import decreasing_projection

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_material(root,stock):
    root=Path(root)
    if stock not in ACTIVE_STOCKS:raise ValueError('Only the four selected VISION3 stocks are eligible')
    if stock=='5203':
        record=json.loads((root/'local/reference-assets/film-stock-survey/source-record.json').read_text())
        source=next(s for s in record['documents'] if s['id']=='kodak_5203_2015')
        _,_,_,_,raw=extract_curves(CHARTS['5203'],source)
        traces={}
        for c in 'RGB':
            t=np.array(raw['characteristic_'+c]['points']);t[:,0]*=np.log10(2)
            traces['characteristic_'+c]=t
            traces['sensitivity_'+c]=np.array(raw['log_sensitivity_'+c]['points'])
        dye_traces=sorted([np.array(t['points']) for key,t in raw.items() if key.startswith('net_dye_')],key=lambda a:a[np.argmax(a[:,1]),0])
        traces.update({'dye_'+c:t for c,t in zip('YMC',dye_traces)})
        traces['minimum_density']=np.array(raw['base']['points'])
        identity={'file':source['file'],'sha256':source['sha256'],'revision':'H-1-5203t, July 2015','url':source['url'],'pages':[4,5]}
        seconds=.1
    else:
        folder=root/'local/materials/kodak-motion-survey-v1'/stock
        entry=json.loads((folder/'source-curves.json').read_text())
        if entry['source']['sha256']!=SOURCES[stock]['sha256']:raise ValueError('Unexpected manufacturer source')
        original=root/'local/reference-assets/kodak-motion-user-2026'/SOURCES[stock]['file']
        if digest(original)!=entry['source']['sha256']:raise ValueError('Manufacturer PDF changed')
        traces={n:np.array(c['points'],dtype=float) for n,c in entry['curves'].items()}
        for n in list(traces):
            if n.startswith('characteristic_'):traces[n][:,0]*=np.log10(2)
        identity={**entry['source'],'pages':[3,4],'source_collection_sha256':digest(folder/'source-curves.json')}
        seconds=entry['sensitivity_exposure_seconds']
    char_grid=np.linspace(max(traces['characteristic_'+c][0,0] for c in 'RGB'),min(traces['characteristic_'+c][-1,0] for c in 'RGB'),321)
    char={'quantity':'status_m_density','unit':'D','log_exposure':char_grid.tolist(),'channels':{c:(-decreasing_projection(-np.interp(char_grid,*traces['characteristic_'+c].T))).tolist() for c in 'RGB'}}
    wavelengths=np.arange(400.,721.,10.)
    sensitivity={'quantity':'relative_energy_sensitivity','unit':'relative','wavelengths_nm':wavelengths.tolist(),'channels':{}}
    for c in 'RGB':
        t=traces['sensitivity_'+c];values=10**np.interp(wavelengths,*t.T)
        values[(wavelengths<t[0,0])|(wavelengths>t[-1,0])]=0
        sensitivity['channels'][c]=values.tolist()
    grid=np.arange(360.,731.,2.)
    dyes={'quantity':'net_spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'channels':{c:np.interp(grid,*traces['dye_'+c].T).tolist() for c in 'CMY'}}
    base={'quantity':'spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'values':np.interp(grid,*traces['minimum_density'].T).tolist()}
    k=3200 if stock in ('5213','5219') else 5500;illuminant='Planck' if k==3200 else 'CIE_D'
    uncertainty='Status M inferred from this document\'s MTF and sensitivity labels; characteristic panel misprints ECN-2 as the densitometry. User accepted this interpretation.'
    p={'stock_id':stock,'process':'ECN-2','density_metric':'Status M','experimental':True,'material_version':'vision3-source/2','sources':{'manufacturer':identity},'credits':['Eastman Kodak Company: manufacturer curves; local research data, redistribution pending.'],'substitutions':{},
       'source_conditions':{'characteristic_exposure_seconds':.02,'sensitivity_exposure_seconds':seconds,'characteristic_temperature_k':k,'density_criterion':'0.2 D above D-min for spectral sensitivity','sensitivity_original_unit':'reciprocal exposure in erg/cm^2'},
       'density_metric_evidence':{'status':'inferred_from_same_document' if stock=='5219' else 'explicit_chart_label','note':uncertainty if stock=='5219' else 'Original manufacturer characteristic and sensitivity charts explicitly declare Status M.'},
       'exposure_reference':{**copy.deepcopy(sensitivity),'temperature_k':k,'illuminant':illuminant,'reflectance':.18},
       'exposure_anchor':'Own frozen 18% flat-reflector reference at manufacturer camera stops 0; relative, not ISO speed measured. Frozen sensitivity is retained when CSV amplitude changes.',
       'tail_assumptions':['Sensitivity is zero outside each drawn trace; a model assumption, not a measured zero.','Own signed CMY and processed D-min use endpoint extension outside the drawn ranges on 360-730 nm; no other stock supplies tails.'],
       'characteristic_processing':'Common original source coverage; linear resampling and increasing isotonic projection of chart-reading reversals; source points retained for validation.',
       'base_model':'Published processed-film minimum density; own spectral shape aligned once to own lowest Status M plateau; not a bare-support measurement.',
       'summary':'原厂独立曲线；相对曝光参考，非实拍校准。'+(' Status M 按同文档交叉推定。' if stock=='5219' else '')}
    name=SOURCES[stock]['name'].split(' / ')[0]
    material={'schema':'softloaf.material/1','name':name,'source':name+' / '+identity['revision']+' / ECN-2 / Status M; '+p['density_metric_evidence']['note'],'sensitivity':sensitivity,'characteristic':char,'dyes':dyes,'base':base,'provenance':p}
    plot={'sensitivity':{'quantity':'relative_energy_sensitivity','unit':'relative','source':identity['revision']+'; original manufacturer curve detail','provenance_sha256':identity['sha256'],'calculation_step_nm':10,'channels':{c:{'wavelengths_nm':traces['sensitivity_'+c][:,0].tolist(),'values':(10**traces['sensitivity_'+c][:,1]).tolist()} for c in 'RGB'}}}
    return material,plot,traces


def build(root=ROOT):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    root=Path(root);out=root/'local/materials/film-presets-v1';out.mkdir(parents=True,exist_ok=True)
    runtime=root/'artifacts/vision3-integration/build-runtime'
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',runtime,core=NativeCore())
    old=json.loads((root/'data/film-presets-manifest.json').read_text());records=[];materials=[]
    for stock in ACTIVE_STOCKS:
        material,plot,traces=build_material(root,stock);model._validate_negative_material(material);fitted=model._negative_fit(material)
        folder=root/'local/materials/vision3-source-v2';folder.mkdir(parents=True,exist_ok=True)
        for suffix,data in [('material',material),('plot',plot),('original-traces',{k:v.tolist() for k,v in traces.items()})]:
            (folder/f'{stock}-{suffix}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        materials.append({'id':stock,'file':f'{stock}-material.json','sha256':digest(folder/f'{stock}-material.json'),'plot_file':f'{stock}-plot.json','plot_sha256':digest(folder/f'{stock}-plot.json'),'source':material['provenance']['sources']['manufacturer'],'fit':public_fit_summary(fitted.metadata)})
        for route in ['negative','print']:
            r=model.validate(template(route))['normalized_recipe'];r.update(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'softloaf.vision3-source/2/'+stock+'/'+route)),revision=1,name=material['name']+' · '+('APD' if route=='negative' else 'Ultra Endura'))
            r['film'].update(stock=stock,custom_material=copy.deepcopy(material));frozen=material['provenance']['exposure_reference'];r['scene']={k:frozen[k] for k in ('illuminant','temperature_k')}
            if route=='print':r['printing']=model.modern_printing(r)
            r=model.validate(r,compute=True)['normalized_recipe'];file=f'{stock}-{route}-vision3-v2.json';path=out/file;path.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
            records.append({'id':stock+'-'+route,'name':material['name'],'process':'ECN-2','route':route,'file':file,'sha256':digest(path),'summary':material['provenance']['summary']})
        print(stock,'own material fitted',fitted.metadata['neutral_max_error_D'],flush=True)
    old['recipes']=[r for r in old['recipes'] if r['id'] not in {e['id'] for e in records}]+records
    old.update(recorded_on='2026-10-28',vision3_material_version='vision3-source/2')
    (root/'data/film-presets-manifest.json').write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    manifest={'schema':'softloaf.vision3-materials/1','directory':'local/materials/vision3-source-v2','recorded_on':'2026-10-28','materials':materials,'excluded':['5206'],'rights':'Local manufacturer reference; derived LUT redistribution pending review.'}
    (root/'data/vision3-materials-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__=='__main__':build()
