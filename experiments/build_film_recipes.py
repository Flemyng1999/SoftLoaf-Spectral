"""Build explicitly provisional negative recipes from identified local sources.

Manufacturer PDFs and third-party profiles remain ignored local research data.
Only Status M negative materials are handled here. These pinned example files
retain legacy printing settings. The workbench independently selects positive
rendering and supplies identified modern optical defaults for new recipes.
"""
from pathlib import Path
import copy
import hashlib
import json
import uuid

import numpy as np
import pymupdf
from scipy.optimize import least_squares

from experiments.extract_5207_materials import runs, mapped
from experiments.gui_recipe_server import template, fingerprint, RecipeError
from spectral_app.model import SpectralModel, stage
from spectral_lut.native import NativeCore
from spectral_lut.negative import integrate_density
from spectral_lut.reference import decreasing_projection, quadrature_widths

ROOT=Path(__file__).resolve().parents[1]
SURVEY=ROOT/'local/reference-assets/film-stock-survey'
SPEKTRA=ROOT/'local/reference-assets/spektrafilm/profile-survey'
OUT=ROOT/'local/materials/film-presets-v1'

# PDF coordinates, zero-based drawing indices, and axis limits. Preserve
# original Bezier vertices and source hashes alongside the derived materials.
CHARTS={
 '5203': dict(pdf='kodak_5203_2015',char=[74,75,76],ca=(356.135,122.292,540.599,306.781),cl=(-8,8,0,3),anchor=0,stops=True,
     sens=[92,91,93],sa=(352.664,514.267,553.248,665.669),dye_page=4,dyes=[29,30,31],base=32,da=(81.351,172.864,265.763,357.217),dl=(400,800,-.2,1.8)),
 '5213': dict(pdf='kodak_5213_2015',char=[62,63,64],ca=(357.490,120.443,542.079,304.924),cl=(-8,8,0,3),anchor=0,stops=True,
     sens=[102,100,101],sa=(351.131,512.58,551.673,664.02),dye_page=4,dyes=[30,31,32],base=29,da=(77.899,171.907,262.194,356.343),dl=(400,800,-.2,1.8)),
 'portra400':dict(pdf='kodak_portra400_2016',char=[38,37,36],ca=(81.163,102.853,265.626,287.368),cl=(-4,1,0,4),anchor=-1.44,
     sens=[54,55,53],sa=(76.214,343.059,276.727,494.555),dye_page=3,base=69,da=(357.123,103.714,541.764,288.06),dl=(400,700,0,2.5)),
 'portra160':dict(pdf='kodak_portra160_2016',char=[35,34,33],ca=(81.450,102.119,266.008,286.599),cl=(-4,1,0,4),anchor=-1.051,
     sens=[52,51,50],sa=(73.750,347.981,274.230,499.568),dye_page=3,base=66,da=(355.131,101.161,539.495,285.512),dl=(400,700,0,2.5)),
 'portra800':dict(pdf='kodak_portra800_2016',char=[13,12,11],ca=(81.644,74.468,266.168,258.894),cl=(-4,1,0,4),anchor=-1.74,
     sens=[57,56,55],sa=(350.169,313.668,550.942,465.371),dye_page=4,base=35,da=(81.092,101.774,265.439,286.121),dl=(400,700,0,2.5)),
 'ektar100':dict(pdf='kodak_ektar100_2016',char=[35,34,33],ca=(81.193,107.924,265.698,292.408),cl=(-4,1,0,4),anchor=-.84,
     sens=[51,50,49],sa=(74.188,356.559,274.651,508.036),dye_page=3,base=68,da=(357.453,106.025,541.777,290.390),dl=(400,700,0,2.5)),
 'gold200':dict(pdf='kodak_gold200_2016',char=[37,36,35],ca=(81.676,101.301,266.184,285.809),cl=(-4,1,0,4),anchor=-1.14,
     profile='kodak_gold_200',dye_page=3,base=130,da=(357.087,102.901,541.437,287.249),dl=(400,700,0,2.5)),
}
STOCKS=[
 ('5203','Kodak VISION3 50D 5203','ECN-2','D55'),
 ('5213','Kodak VISION3 200T 5213','ECN-2','3200 K tungsten'),
 ('5219','Kodak VISION3 500T 5219','ECN-2','3200 K tungsten'),
 ('portra160','Kodak Portra 160','C-41','Daylight'),
 ('portra400','Kodak Portra 400','C-41','Daylight'),
 ('portra800','Kodak Portra 800','C-41','Daylight'),
 ('ektar100','Kodak Ektar 100','C-41','Daylight'),
 ('gold200','Kodak Gold 200','C-41','Daylight'),
 ('ultramax400','Kodak Ultramax 400','C-41','Daylight'),
 ('c200','Fujifilm C200','C-41','Daylight'),
 ('pro400h','Fujifilm Pro 400H','C-41','Daylight'),
 ('superia400','Fujifilm Superia X-TRA 400','C-41','Daylight'),
]
PROFILES={'5219':'kodak_vision3_500t','ultramax400':'kodak_ultramax_400',
          'c200':'fujifilm_c200','pro400h':'fujifilm_pro_400h','superia400':'fujifilm_xtra_400'}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_curves(config,source):
    pdf=SURVEY/(config['pdf']+'.pdf')
    if digest(pdf)!=source['sha256']:raise ValueError('PDF identity changed')
    doc=pymupdf.open(pdf);page=doc[3];traces={}
    if 'Status M' not in page.get_text():raise ValueError('Source page does not declare Status M')
    def trace(label,page,idx,axes,limits):
        result=mapped(runs(page,[idx])[0],axes,limits)
        traces[label]={'page':page.number+1,'drawing_index':idx,'axes_pdf_pt':axes,'limits':limits,'points':result.tolist()}
        return result
    chars=[trace('characteristic_'+c,page,idx,config['ca'],config['cl']) for c,idx in zip('RGB',config['char'])]
    for curve in chars:
        if config.get('stops'):curve[:,0]*=np.log10(2)
        curve[:,0]-=config['anchor']
    axis=np.linspace(max(c[0,0] for c in chars),min(c[-1,0] for c in chars),257)
    char={'log_exposure':axis.tolist(),'quantity':'status_m_density','unit':'D',
          'channels':{c:(-decreasing_projection(-np.interp(axis,t[:,0],t[:,1]))).tolist() for c,t in zip('RGB',chars)}}
    sensitivity=None
    if config.get('sens'):
        spectra=[trace('log_sensitivity_'+c,page,idx,config['sa'],(250,750,0,4)) for c,idx in zip('RGB',config['sens'])]
        x=np.arange(400,721,10)
        sensitivity={'wavelengths_nm':x.tolist(),'quantity':'relative_energy_sensitivity','unit':'relative',
            'channels':{c:np.where((x>=t[0,0])&(x<=t[-1,0]),10**np.interp(x,t[:,0],t[:,1]),0).tolist() for c,t in zip('RGB',spectra)}}
    page=doc[config['dye_page']]
    base=trace('base',page,config['base'],config['da'],config['dl'])
    dyes=None
    if config.get('dyes'):
        candidates=[trace('net_dye_'+str(idx),page,idx,config['da'],config['dl']) for idx in config['dyes']]
        # Curves are independently labelled by their peak wavelength, checked
        # against the original page overlay; do not infer RGB from path order.
        candidates.sort(key=lambda t:t[np.argmax(t[:,1]),0])
        assert all(.97<t[:,1].max()<1.04 for t in candidates)
        x=np.arange(360,731,2)
        dyes={'wavelengths_nm':x.tolist(),'quantity':'net_spectral_density','unit':'D',
            'channels':{c:np.interp(x,t[:,0],t[:,1]).tolist() for c,t in zip('YMC',candidates)}}
    return char,sensitivity,base,dyes,traces


def profile_sensitivity(name):
    record=json.loads((SPEKTRA/'source-record.json').read_text())
    source=next(r for r in record['files'] if r['path'].endswith('/'+name+'.json'))
    path=SPEKTRA/(name+'.json')
    if digest(path)!=source['sha256']:raise ValueError('Profile identity changed')
    p=json.loads(path.read_text());info=p['info']
    if info['densitometer']!='status_M' or info['stage']!='filming' or info['type']!='negative':
        raise ValueError('Wrong profile process; requires Status M camera negative')
    values=np.asarray(p['data']['log_sensitivity'],dtype=float);x=np.asarray(p['data']['wavelengths'],dtype=float)
    if values.shape!=(len(x),3) or not np.isfinite(values).all():raise ValueError('Missing sensitivity samples')
    grid=np.arange(400,721,10)
    sensitivity={'wavelengths_nm':grid.tolist(),'quantity':'relative_energy_sensitivity','unit':'relative',
        'channels':{c:np.interp(grid,x,10**values[:,i]).tolist() for i,c in enumerate('RGB')}}
    return sensitivity,source


def fixed_print_start(model,recipe):
    """A frozen virtual gray test, not image-dependent grading or CP units."""
    params=model.parameters(recipe);material=params['material'];paper=model.route_paper(recipe)
    t=model._film_stage(np.full(len(model.source_wavelengths),.18),0,
        params['scene_temperature_k'],material,params['scene_illuminant'])[2]
    lamp=model.printer_light(recipe['printing']['temperature_k'])
    dyes=np.stack([model.printing_filter_curves['channels'][c] for c in 'CMY'],axis=-1)
    kernel=paper.sensitivity*quadrature_widths(model.negative_wavelengths)[:,None]/paper.normal
    def exposure(x):return (t*lamp*10**-(dyes@x[:3]))@kernel*np.exp2(x[3])
    fitted=least_squares(lambda x:np.log10(np.maximum(exposure(x),1e-30)),
        [.1,.1,.1,0],bounds=([0,0,0,-4],[2,2,2,4]),ftol=1e-12,xtol=1e-12,gtol=1e-12)
    error=float(np.max(np.abs(np.log10(exposure(fitted.x)))))
    if not fitted.success or error>1e-5:raise ValueError('Fixed paper gray balance could not be realized')
    recipe['printing'].update(filters=fitted.x[:3].tolist(),exposure_ev=float(fitted.x[3]),
        calibration_note='Frozen virtual 18% flat-reflector test under this recipe camera illuminant, matched to the existing paper reference layer exposure [1,1,1]. Ideal CMY density controls, not Kodak CP/dichroic units. No image or roll analysis; not measured stock calibration.',
        neutral_start={'reflectance':.18,'target_paper_layer_exposure':[1,1,1],
            'achieved_paper_layer_exposure':exposure(fitted.x).tolist(),'max_log10_layer_error':error,
            'scene':copy.deepcopy(recipe['scene']),'film_exposure_ev':0})


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    model=SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',ROOT/'artifacts/film-preset-build/runtime',core=NativeCore())
    sources={r['id']:r for r in json.loads((SURVEY/'source-record.json').read_text())['documents']}
    records=[];checks=[]
    for stock,name,process,illuminant in STOCKS:
        material=copy.deepcopy(model.negative_material);material['name']=name+' · 实验参考'
        provenance={'stock_id':stock,'process':process,'density_metric':'Status M','experimental':True,
            'manufacturer_reference_illuminant':illuminant,'sources':{},'substitutions':{},'credits':[],
            'exposure_anchor':'Borrowed frozen 5207 layer exposure denominators and relative 18% gray anchor; not ISO speed calibrated',
            'sensitivity_scale':'One common scalar aligns the maximum with 5207; RGB channel ratios retained; not an exposure-index measurement',
            'simulation_illuminant':'CIE D55, 5500 K; no automatic correction to manufacturer test illuminant'}
        if stock in ('c200','pro400h','superia400'):
            provenance['manufacturer_process_label']='CN-16; C-41-compatible negative family; exact manufacturer development differs'
        borrowed='Kodak 5207 / ECN-2 / Status M, model 5207-paper-reference/4; temporary approximation, not a measurement of this stock'
        for key in ['characteristic','dyes','base','exposure_anchor']:provenance['substitutions'][key]=borrowed
        config=CHARTS.get(stock);traces={}
        if config:
            source=sources[config['pdf']];char,sensitivity,base,dyes,traces=extract_curves(config,source)
            material['characteristic']=char;provenance['substitutions'].pop('characteristic')
            grid=model.negative_wavelengths
            values=np.interp(grid,base[:,0],base[:,1]);outside=(grid<base[0,0])|(grid>base[-1,0])
            values[outside]=np.asarray(model.negative_material['base']['values'])[outside]
            material['base']['values']=values.tolist()
            provenance['substitutions']['base']='5207 outside published base trace; this stock inside the recorded source extent'
            if dyes:
                material['dyes']=dyes;provenance['substitutions'].pop('dyes')
                provenance['substitutions']['dye_tails']='5207 below 400 nm; original stock net-dye curves at 400–730 nm'
                for c in 'CMY':
                    y=np.array(material['dyes']['channels'][c]);y[grid<400]=np.array(model.negative_material['dyes']['channels'][c])[grid<400];material['dyes']['channels'][c]=y.tolist()
            provenance['sources']['manufacturer']={k:source[k] for k in ['url','sha256','file']}
            provenance['characteristic_axis']={'source':'camera stops' if config.get('stops') else 'log10 lux-seconds',
                'subtracted_logH_reference':config['anchor'],'source_pages':[4,config['dye_page']+1]}
            (OUT/(stock+'-original-traces.json')).write_text(json.dumps(traces,ensure_ascii=False,indent=2)+'\n')
        else:sensitivity=None
        if sensitivity is None:
            profile=(config or {}).get('profile') or PROFILES[stock]
            sensitivity,source=profile_sensitivity(profile)
            provenance['sources']['processed_sensitivity']={**source,'quantity':'processed spektrafilm relative log sensitivity converted to linear; no density curves imported'}
            provenance['credits']=[
                'Copyright (c) 2026 Andrea Volpato. Licensed under CC BY-SA 4.0. (Processed sensitivity profile data)',
                'Andrea Volpato, spektrafilm; https://github.com/andreavolpato/spektrafilm; commit 3bb2c2d2801ff68b92019cf1dbcbb133d60832bc',
                'Sensitivity data and this derivative: CC BY-SA 4.0; https://creativecommons.org/licenses/by-sa/4.0/',
                'Modifications: linearized sensitivity, common amplitude scale, resampling; hybrid 5207 material, not the spektrafilm runtime or full model']
        peak=max(max(v) for v in sensitivity['channels'].values());target=max(max(v) for v in model.negative_material['sensitivity']['channels'].values())
        provenance['sensitivity_common_scale']=float(target/peak)
        provenance['characteristic_processing']='Source reference exposure offset, common channel coverage, piecewise resampling and monotone projection; original vector points retained separately where available'
        for c in 'RGB':sensitivity['channels'][c]=(np.asarray(sensitivity['channels'][c])*target/peak).tolist()
        material['sensitivity']=sensitivity
        failures=[]
        # If the new curves cannot be reproduced by a borrowed dye set, retain
        # the failed source separately and label the fallback, never silently
        # relax the 0.006 D fit threshold or clip signed dye increments.
        for fallback in [None,'dyes','base','characteristic']:
            if fallback:
                material[fallback]=copy.deepcopy(model.negative_material[fallback]);provenance['substitutions'][fallback]=borrowed+'; source combination failed the material fit/passivity check'
            try:
                model._validate_negative_material(material);fitted=model._negative_fit(material);break
            except RecipeError as error:failures.append(str(error))
        else:raise RuntimeError('No valid material for '+stock)
        borrowed_names={'characteristic':'特性曲线','dyes':'染料','base':'片基（来源中注明范围）','exposure_anchor':'曝光标定','dye_tails':'染料短波尾部'}
        provenance['summary']='实验模型；5207 暂代：'+'、'.join(borrowed_names[k] for k in provenance['substitutions'])+'。非原厂完整测量。'
        if process=='ECN-2' and illuminant.startswith('3200'):
            provenance['simulation_illuminant']='3200 K Planck blackbody energy SPD approximation, not CIE daylight'
            provenance['summary']+=' 3200 K 钨丝光采用黑体近似。'
        material['provenance']=provenance;material['source']=name+' / '+process+' / Status M；'+provenance['summary']
        # Refit with final metadata and compare the optimized stage against a
        # separate NumPy implementation, retaining all absolute-density bounds.
        fitted=model._negative_fit(material)
        original_curve_error=None
        if traces and 'characteristic' not in provenance['substitutions']:
            errors=[]
            for c in 'RGB':
                points=np.array(traces['characteristic_'+c]['points']);x=points[:,0].copy()
                if config.get('stops'):x*=np.log10(2)
                x-=config['anchor'];inside=(x>=fitted.axis[0])&(x<=fitted.axis[-1]);x=x[inside]
                amounts=np.stack([np.interp(x,fitted.axis,fitted.amounts[:,i]) for i in range(3)],axis=-1)
                status_m=integrate_density(10**-(fitted.base+amounts@fitted.dyes.T),model.status_m_weights)
                errors.extend(np.abs(status_m[:,list('RGB').index(c)]-points[inside,1]).tolist())
            original_curve_error=float(max(errors))
        provenance['original_status_m_curve_point_max_error_D']=original_curve_error
        kernel=fitted.sensitivity*model.scene_light(5500)[:,None]*quadrature_widths(model.source_wavelengths)[:,None]/model.negative_denominators
        reflectance=np.random.default_rng(20261027).random((128,len(model.source_wavelengths)))
        native=stage(reflectance,kernel,fitted.axis,fitted.amounts,fitted.dyes,fitted.base,core=model.core)[2]
        reference=stage(reflectance,kernel,fitted.axis,fitted.amounts,fitted.dyes,fitted.base,core=None)[2]
        difference=float(np.max(np.abs(native-reference)))
        if difference>2e-12:raise RuntimeError('Native/reference mismatch')
        per_stock={'stock':stock,'name':name,'process':process,'material_sha256':fingerprint(material),
            'original_manufacturer_vector_point_max_error_D':original_curve_error,
            'source_neutral_fit_max_D':fitted.metadata['neutral_max_error_D'],'minimum_absolute_density_bound_D':fitted.metadata['minimum_absolute_density_bound_D'],
            'native_numpy_max_transmittance_difference':difference,'failed_source_combinations':failures,
            'provenance':provenance,'recipes':[]}
        for route in (['negative','print'] if process=='ECN-2' else ['print']):
            recipe=model.validate(template(route))['normalized_recipe'];recipe['id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'softloaf.experimental/'+stock+'/'+route));recipe['revision']=1
            recipe['name']=name+' · '+('APD' if route=='negative' else 'Ultra Endura')+' · 实验'
            recipe['film'].update(stock=stock,custom_material=copy.deepcopy(material))
            if process=='ECN-2' and illuminant.startswith('3200'):
                recipe['scene']={'illuminant':'Planck','temperature_k':3200}
            if route=='print':
                fixed_print_start(model,recipe)
            recipe=model.validate(recipe,compute=True)['normalized_recipe']
            test=model.sample_spectra(reflectance,**model.parameters(recipe))
            if not np.isfinite(test['display_rgb']).all():raise RuntimeError('Nonfinite output')
            if route=='print':
                gray=model.sample_spectra(np.full(len(model.source_wavelengths),.18),**model.parameters(recipe))
                np.testing.assert_allclose(gray['paper_exposure'],np.ones(3),rtol=3e-5,atol=1e-10)
            path=OUT/(stock+'-'+route+'.json');path.write_text(json.dumps(recipe,ensure_ascii=False,indent=2)+'\n')
            entry={'id':stock+'-'+route,'name':name,'process':process,'route':route,'file':path.name,
                'sha256':digest(path),'summary':provenance['summary']}
            records.append(entry);per_stock['recipes'].append(entry['id'])
        checks.append(per_stock);print(stock,'validated; routes',per_stock['recipes'],'borrowed',list(provenance['substitutions']),flush=True)
    manifest={'schema':'softloaf.experimental-presets/1','recorded_on':'2026-10-27','status':'local research only; not measured full-stock color accuracy',
        'directory':'local/materials/film-presets-v1','recipes':records}
    (ROOT/'data/film-presets-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    report={'schema':'softloaf.film-preset-build/1','model':model.negative_refs,'materials':checks,
        'limits':'Component substitutions explicitly permitted by the user. Source-neutral fits and optimized/reference checks do not establish full-color film accuracy. No E-6, RA-4 or movie-positive curves are treated as Status M camera negatives.'}
    (OUT/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
