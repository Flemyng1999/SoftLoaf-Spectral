"""Extract original Kodak paper vectors; no processed upstream paper profiles.

PDFs and derived tables stay local. Axes and path IDs refer to hash-pinned PDFs.
Two-nm resampling does not add measurement resolution. Preserve original paths.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pymupdf

from experiments.extract_5207_materials import runs, mapped
from spectral_lut.reference import decreasing_projection

ROOT=Path(__file__).resolve().parents[1]
SPECS={
 'endura-premier':dict(source='endura-premier-2017',name='Kodak Endura Premier',revision='E-4070, December 2017',char=(3,[8,9,10],(364.676,72.550,549.205,257.170),(-3,0,0,3)),sensitivity=(3,[19,18,17],(350.586,315.738,551.084,467.333)),dyes=(4,[15,16,17],(88.833,50.570,273.263,234.914)),temperature=35,seconds=.5),
 'ektacolor-edge':dict(source='kodak-edge-e7020',name='Kodak Ektacolor EDGE',revision='E-7020, April 2019',char=(2,[list(range(3,18)),list(range(43,55)),list(range(30,43))],(368.404,86.963,555.632,269.324),(-4,1,0,4)),sensitivity=(3,[28,27,26],(73.602,101.065,274.130,252.538)),dyes=(2,[70,71,72],(367.344,330.641,551.774,514.985)),temperature=38,seconds=None),
 'royal-digital':dict(source='kodak-royal-e7021',name='Kodak ROYAL Digital',revision='E-7021, April 2019',char=(2,[list(range(50,66)),list(range(32,50)),[14]+list(range(17,32))],(362.326,79.566,537.525,255.215),(-4,1,0,4)),sensitivity=(3,[27,26,25],(73.566,104.279,274.094,255.752)),dyes=(2,[83,84,85],(365.916,331.355,550.346,515.699)),temperature=38,seconds=None),
 'endura-premier-metallic':dict(source='kodak-metallic-e4071',name='Kodak Endura Premier Metallic',revision='E-4071, March 2013',char=(3,[11,12,13],(350.739,72.678,535.020,257.264),(-3,0,0,3)),sensitivity=(3,[19,18,17],(349.961,314.236,550.459,465.831)),dyes=(4,[26,27,28],(76.832,106.217,261.262,290.561)),temperature=35,seconds=.5),
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(root,stock):
    spec=SPECS[stock];directory=Path(root)/'local/reference-assets/paper-survey-20261028'
    record=next(r for r in json.loads((directory/'source-record.json').read_text())['files'] if r['id']==spec['source'])
    path=directory/(spec['source']+'.pdf')
    if sha(path)!=record['sha256']:raise ValueError('Paper PDF identity changed')
    pdf=pymupdf.open(path);traces={};geometry={}
    for role,labels in [('char','RGB'),('sensitivity','RGB'),('dyes','CMY')]:
        page,paths,axes,*limits=spec[role]
        for label,indices in zip(labels,paths):
            indices=[indices] if isinstance(indices,int) else indices
            parts=sorted(runs(pdf[page],indices),key=lambda p:p[0,0]);points=[]
            for part in parts:
                if points and np.linalg.norm(np.asarray(points[-1])-part[0])>.03:raise ValueError('Disconnected paper curve')
                points.extend(part.tolist() if not points else part[1:].tolist())
            geometry[role+'_'+label]={'page':page+1,'paths':indices,'axes_points':axes,'pdf_points':points}
            traces[role+'_'+label]=mapped(points,axes,limits[0] if limits else (250,750,-2,2) if role=='sensitivity' else (400,700,0,2.5))
    # Identify CMY by peak wavelength, independently of a PDF's drawing order.
    ordered=sorted([(traces['dyes_'+c],geometry['dyes_'+c]) for c in 'CMY'],key=lambda pair:pair[0][np.argmax(pair[0][:,1]),0])
    for c,(trace,g) in zip('YMC',ordered):traces['dyes_'+c]=trace;geometry['dyes_'+c]=g
    x=np.linspace(max(traces['char_'+c][0,0] for c in 'RGB'),min(traces['char_'+c][-1,0] for c in 'RGB'),321)
    char={'quantity':'status_a_density','unit':'D','log_exposure':x.tolist(),'channels':{c:(-decreasing_projection(-np.interp(x,*traces['char_'+c].T))).tolist() for c in 'RGB'}}
    grid=np.arange(360.,751.,2.)
    sens={'quantity':'relative_energy_sensitivity','unit':'relative','wavelengths_nm':grid.tolist(),'channels':{}}
    for c in 'RGB':
        t=traces['sensitivity_'+c];v=10**np.interp(grid,*t.T);v[(grid<t[0,0])|(grid>t[-1,0])]=0;sens['channels'][c]=v.tolist()
    dye={'quantity':'spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'channels':{c:np.maximum(0,np.interp(grid,*traces['dyes_'+c].T)).tolist() for c in 'CMY'}}
    base={'name':spec['name']+' modeled minimum density','source':'Constant density at the lowest own published Status A target; assumed paper white, not measured reflectance','quantity':'spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'values':np.full(len(grid),min(v[0] for v in char['channels'].values())).tolist()}
    conditions={'reference':spec['revision'],'process':'RA-4','density_metric':'Status A','curve_exposure_seconds':spec['seconds'],'developer_temperature_c':spec['temperature'],'developer_time_seconds':45,'optical_exposure_supported':True,'sensitivity_original_unit':'reciprocal energy exposure in erg/cm^2, plotted log10','specified_enlarger_spd':False,'specified_enlarger_temperature_k':None,'evaluation_cct_k':5000,'evaluation_cct_tolerance_k':1000,'evaluation_cri_range':[85,100]}
    special=stock=='endura-premier-metallic'
    p={'stock_id':stock,'process':'RA-4','density_metric':'Status A','material_version':'kodak-paper-source/1','sources':{'manufacturer':{'url':record['url'],'sha256':record['sha256'],'revision':spec['revision'],'pages':sorted({spec[k][0]+1 for k in ('char','sensitivity','dyes')})}},'source_conditions':conditions,'credits':['Kodak manufacturer curves; independent vector extraction by SoftLoaf Spectral; redistribution pending.'],'substitutions':{},'missing_measurements':['paper_white','fluorescence','angular_scattering','paired_exposure_print_spectra'],'appearance_limit':'Metallic directional/gloss appearance is not modeled' if special else None,'summary':'原厂三类曲线；纸白为模型假设。'+('不模拟金属反光。' if special else '曝光时长未注明。' if spec['seconds'] is None else ''),'tail_assumptions':['Sensitivity outside each own drawn trace is set to zero; not a measured zero.','Own CMY spectra use endpoint extension beyond 400-700 nm; no other paper supplies curve tails.'],'characteristic_processing':'Original vectors retained; common domain, linear interpolation and increasing isotonic projection of small chart reversals.','exposure_anchor':'Frozen virtual 5207 D65 18% gray / 3200 K printer reference, own original sensitivity, D50 Y=0.1 paper anchor; relative calibration, not absolute lux-seconds.','exposure_reference':{'sensitivity':copy.deepcopy(sens)}}
    material={'schema':'softloaf.material/1','name':spec['name'],'source':spec['revision']+'; independently extracted original vectors; no spektrafilm paper profile substitution','sensitivity':sens,'characteristic':char,'dyes':dye,'base':base,'provenance':p}
    plot={}
    for role,key,labels in [('sensitivity','sensitivity','RGB'),('char','characteristic','RGB'),('dyes','dyes','CMY')]:
        axis='log_exposure' if role=='char' else 'wavelengths_nm'
        plot[key]={'quantity':material[key]['quantity'],'unit':material[key]['unit'],'source':spec['revision'],'sampling_kind':'manufacturer_vector','calculation_step_nm':None if role=='char' else 2,'reference_curve':copy.deepcopy(material[key]),'channels':{c:{axis:traces[role+'_'+c][:,0].tolist(),'values':(10**traces[role+'_'+c][:,1] if role=='sensitivity' else traces[role+'_'+c][:,1]).tolist()} for c in labels}}
    return material,plot,{'curves':{k:v.tolist() for k,v in traces.items()},'geometry':geometry,'source':p['sources']['manufacturer']}


def build(root=ROOT):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    root=Path(root);directory=root/'local/materials/paper-presets-v1';directory.mkdir(parents=True,exist_ok=True)
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',root/'artifacts/paper-presets/build-runtime',core=NativeCore())
    entries=[]
    for stock in SPECS:
        material,plot,source=extract(root,stock);fit=model._paper_fit(material)
        material['provenance']['exposure_reference']['anchor_logH']=fit.anchor
        for suffix,obj in [('material',material),('plot',plot),('source',source)]:
            (directory/(stock+'-'+suffix+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
        entries.append({'id':stock,'name':material['name'],'process':'RA-4','density_metric':'Status A','file':stock+'-material.json','sha256':sha(directory/(stock+'-material.json')),'plot_file':stock+'-plot.json','plot_sha256':sha(directory/(stock+'-plot.json')),'source_file':stock+'-source.json','source_sha256':sha(directory/(stock+'-source.json')),'source':source['source'],'fit_max_error_D':fit.metadata['neutral_max_error_D'],'summary':material['provenance']['summary']})
        print(stock,fit.metadata['neutral_max_error_D'],flush=True)
    manifest={'schema':'softloaf.paper-presets/1','recorded_on':'2026-10-28','directory':'local/materials/paper-presets-v1','materials':entries,'reference_only':[{'id':'fuji-dpii-af3212e','reason':'Laser exposure / CP-48S / relative H; not validated for optical enlargement'}],'rights':'Local manufacturer reference; redistribution of curves and derived LUTs pending review.'}
    (root/'data/paper-presets-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__=='__main__':build()
