"""Frozen 5207 scan comparison: camera assumptions and estimated effective light.

No RAW development. Numerical work, retained inputs, figures and results stay on
the configured data volume. Existing image/Metal/codec modules own pixel work.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from spectral_app.storage import DataStorage
from spectral_app.model import SpectralModel
from spectral_app.scanning.sensitivity import (load_response,light_weights,
    cross_validate_light,align_border,display_difference)
from spectral_app.scanning.inverse import MaterialInverse
from spectral_app.scanning.rendering import amounts_to_display
from spectral_app.scanning.export import export_scan_lut,material_density_domain
from spectral_app.metal_renderer import MetalRenderer
from spectral_app.imaging.sources import MappedSource
from spectral_app.imaging.pipeline import write_image
from spectral_lut.reference import Cube
from spectral_lut.native import NativeCore
from experiments.export_scan_lut import array_digest,retained_records


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('calibration-dir','response-dir','prediction','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--calibrate-only',action='store_true')
    args=parser.parse_args();storage=DataStorage.configured();storage.validate();storage.activate_temporary_directory()
    if not storage.volume or not args.output.resolve().is_relative_to(storage.volume.resolve()):
        raise ValueError('All sensitivity outputs require the external volume')
    out=args.output;out.mkdir(parents=True,exist_ok=True);directory=args.calibration_dir
    settings=json.loads((directory/'calibration.json').read_text());check=dict(settings);fingerprint=check.pop('fingerprint')
    if hashlib.sha256(json.dumps(check,sort_keys=True).encode()).hexdigest()!=fingerprint:
        raise ValueError('Frozen calibration identity differs')
    a=np.load(directory/'calibration.npz');wave=a['wave'];full_t=a['spectra'];rgb=a['camera']
    if array_digest(a['weights'])!=settings['effective_response_sha256']:
        raise ValueError('Frozen joint response differs')
    selected=(wave>=400)&(wave<=700);common=wave[selected];t=full_t[:,selected]
    sources={'v':load_response(args.prediction,common,kind='prediction',model='ILCE-7RM5')}
    for key,model_id in [('iv','ILCE-7RM4'),('iii','ILCE-7RM3'),('ii','ILCE-7RM2')]:
        sources[key]=load_response(args.response_dir/f'Sony_{model_id}_380_780_5.json',common,kind='measured',model=model_id)
    wide=load_response(args.response_dir/'Sony_ILCE-7RM4_380_780_5.json',wave,kind='measured',model='ILCE-7RM4')
    def extend(weights):
        result=np.zeros((len(wave),3));result[selected]=weights;return result
    cases={
        'joint_current':{'label':'Current joint fit','weights':a['weights'],'band_nm':[391,730],
            'outer_RMS_D':settings['nested_target_RMS_D'],'outer_max_D':settings['nested_target_max_D'],
            'arm':'current frozen baseline; nested same-target CV'},
        'joint_cropped':{'label':'Current fit / 400-700','weights':extend(a['weights'][selected]),'band_nm':[400,700],
            'arm':'coverage control; cropped original weights, no refit','outer_RMS_D':None}}
    fits={}
    for key,source in sources.items():
        print('Calibrate fixed camera:',source['model'],flush=True)
        fit=cross_validate_light(common,source['values'],t,rgb);fits[key]=fit
        cases[key+'_refit']={'label':'A7R '+key.upper()+' / light refit','weights':extend(fit['weights']),
            'band_nm':[400,700],'arm':'fixed camera / individually fitted effective light',
            'outer_RMS_D':fit['outer_RMS_D'],'outer_max_D':fit['outer_max_D'],
            'training_RMS_D':fit['training_RMS_D'],'camera_source':key}
    print('Calibrate IV / full finite band',flush=True)
    fit=cross_validate_light(wave,wide['values'],full_t,rgb);fits['iv_wide']=fit
    cases['iv_wide']={'label':'A7R IV / 391-730','weights':fit['weights'],'band_nm':[391,730],
        'arm':'A7R IV finite-band control / individually fitted effective light',
        'outer_RMS_D':fit['outer_RMS_D'],'outer_max_D':fit['outer_max_D'],
        'training_RMS_D':fit['training_RMS_D'],'camera_source':'iv_wide'}
    # A common-light arm isolates response changes after one fixed-border alignment.
    for key in ('iv','iii','ii'):
        weights=light_weights(common,sources[key]['values'],fits['v']['light'])
        scale=10**np.mean(np.log10(rgb/(t@weights)),axis=0)
        cases[key+'_fixed']={'label':'A7R '+key.upper()+' / common light','weights':extend(weights),
            'band_nm':[400,700],'arm':'effective light frozen from A7R V fit; one fixed border alignment',
            'outer_RMS_D':None,'training_RMS_D':float(np.sqrt(np.mean(np.log10((t@weights*scale)/rgb)**2))),
            'camera_source':key}
    source_metadata={key:{k:v for k,v in value.items() if k not in ('values','wavelengths')}
        for key,value in {**sources,'iv_wide':wide}.items()}
    baseline=storage.root/'scanning/retained-raw';retained_before=retained_records(baseline)
    root=Path(__file__).resolve().parents[1];core=NativeCore()
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',
        root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',directory/'reference-runtime',core=core)
    material=model.negative
    for name,values in [('dyes',material.dyes),('base',material.base),('apd_weights',model.apd_weights)]:
        if array_digest(values)!=settings['material_arrays_sha256'][name]:raise ValueError('Frozen material/APD differs')
    if settings['display_config']!=model.display_manager.config_metadata:raise ValueError('Display configuration differs')
    dyes=np.column_stack([np.interp(wave,model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
    base=np.interp(wave,model.negative_wavelengths,material.base)
    inverses={};domains=[]
    for key,case in cases.items():
        aligned,gain=align_border(case['weights'],10**-base,settings['measured_base_camera'])
        case['border_gain']=gain.tolist();case['aligned_weights_sha256']=array_digest(aligned)
        np.savez(out/(key+'-calibration.npz'),wave=wave,weights=case['weights'],gain=gain,aligned_weights=aligned,
            **({'light':fits[key.replace('_refit','')]['light']} if key.endswith('_refit') else {}))
        inverse=MaterialInverse(dyes,base,aligned,material.amounts.min(0),material.amounts.max(0))
        inverses[key]=inverse;domains.append(material_density_domain(inverse))
    low=np.min([d[0] for d in domains],axis=0);high=np.max([d[1] for d in domains],axis=0)
    case_metadata={key:{k:v for k,v in case.items() if k!='weights'} for key,case in cases.items()}
    metadata={'schema':'softloaf.camera-sensitivity/1','baseline_fingerprint':fingerprint,
        'sources':source_metadata,'cases':case_metadata,'common_LUT_density_domain':[low.tolist(),high.tolist()],
        'effective_light':'estimated energy SPD times unknown optical transmission, not measured lamp SPD',
        'light_fit':{'sigma_nm':10,'ridge':.1,'channel_scale':'fitted on training patches only'},
        'output':'APD / continuous ADX16 / ACES 2.0 SDR 100 nits / encoded sRGB D65',
        'material':'same frozen Status M fitted 5207','observer':'CIE 1931 2 degree for display XYZ bridge',
        'viewing_exposure_ev':2,'no_per_image_WB_or_auto_exposure':True,'source_rights':'local research only; source notices retained',
        'scope':'response-assumption sensitivity; no independent real-negative colour ground truth'}
    (out/'calibration-summary.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    np.savez(out/'response-and-light.npz',common_wave=common,
        **{key+'_response':value['values'] for key,value in sources.items()},
        **{key+'_light':value['light'] for key,value in fits.items()})
    print(json.dumps(case_metadata,indent=2),flush=True)
    if args.calibrate_only:return
    cubes={};exports={};metal=MetalRenderer(model);plans={}
    for key,inverse in inverses.items():
        destination=out/'luts'/key
        if not destination.exists():
            count=0
            def render(density):
                nonlocal count
                amounts=inverse.solve(10**-density)['amounts'];count+=len(density)
                if count%65536==0:print('Bake',key,count,'/274625',flush=True)
                return amounts_to_display(model,material,amounts,exposure_ev=2)
            exports[key]=export_scan_lut(destination,render,{'status':'estimated-joint-response',
                'camera':'Actual Sony ILCE-7RM5; assumed response '+case_metadata[key]['label'],
                'material':'Same frozen Kodak 5207 / Status M fitted',
                'calibration_sha256':hashlib.sha256((out/'calibration-summary.json').read_bytes()).hexdigest(),
                'view_exposure_ev':2,'case':case_metadata[key]},size=65,domain_min=low,domain_max=high)
        else:
            manifest=json.loads((destination/'manifest.json').read_text())
            if manifest['metadata']['calibration_sha256']!=hashlib.sha256((out/'calibration-summary.json').read_bytes()).hexdigest():
                raise ValueError('Existing sensitivity LUT belongs to another frozen analysis')
            for name,sha in manifest['files'].items():
                if hashlib.sha256((destination/name).read_bytes()).hexdigest()!=sha:raise ValueError('Existing sensitivity LUT changed')
        cubes[key]=Cube.read(destination/'scan-density-65.cube');plans[key]=metal.prepare_cube(cubes[key],False)
        print('Baked and verified',key,flush=True)
    paths=sorted(p for p in directory.glob('*-camera.npy') if not p.name.startswith('._'))
    if len(paths)!=37:raise ValueError('Expected the frozen 37-frame scan input set')
    records=[];samples={key:[] for key in cases};all_base=[];all_base0=[];all_baseline_valid=[]
    primary=set(cases)-{'iv_fixed','iii_fixed','ii_fixed'};selected_frames={1,8,17,24}
    for path in paths:
        started=time.monotonic();number=int(path.stem.split('-camera')[0].rsplit('_',1)[1]);pixels=np.load(path,mmap_mode='r');h,w=pixels.shape[:2]
        camera=np.array(pixels[int(.18*h):int(.84*h):max(1,int(.66*h)//16),
            int(.17*w):int(.82*w):max(1,int(.65*w)//24)]).reshape(-1,3).astype(float)
        density=-np.log10(np.maximum(camera,1e-12));inside=np.all((density>=low)&(density<=high),axis=1)
        solved={key:inverse.solve(camera) for key,inverse in inverses.items()}
        direct={key:amounts_to_display(model,material,result['amounts'],exposure_ev=2) for key,result in solved.items()}
        direct0={key:amounts_to_display(model,material,result['amounts'],exposure_ev=0) for key,result in solved.items()}
        all_base.append(direct['joint_current']);all_base0.append(direct0['joint_current']);all_baseline_valid.append(solved['joint_current']['valid'])
        frame={'number':number,'source':path.name,'sample_count':len(camera),'outside_common_domain_count':int((~inside).sum()),'cases':{}}
        for key in cases:
            result=solved[key];reference=core.apply_cube(cubes[key],density)
            gpu=metal.interpolate_cube(cubes[key],density,'Display Encoding','sRGB',False,plans[key])
            error=float(np.max(np.abs(gpu-reference)))
            if error>3e-5:raise ValueError('Metal and float64 lookup differ')
            valid=result['valid']&solved['joint_current']['valid']
            frame['cases'][key]={'valid_fraction':float(result['valid'].mean()),
                'at_bound_fraction':float(result['at_bound'].mean()),
                'residual_D_p50_p95_max':np.percentile(result['max_log10_residual'],[50,95,100]).tolist(),
                'jacobian_condition_p50_p95_max':np.percentile(result['jacobian_condition'],[50,95,100]).tolist(),
                'difference_plus2':display_difference(direct['joint_current'],direct[key],valid=valid),
                'difference_0':display_difference(direct0['joint_current'],direct0[key],valid=valid),
                'LUT_error_plus2':display_difference(direct[key],reference,valid=result['valid']&inside),
                'Metal_vs_float64_cube_max':error}
            samples[key].append({'rgb':direct[key],'rgb0':direct0[key],'valid':result['valid']})
            if key in primary or number in selected_frames:
                target=out/'images'/key/f'{number:02d}.png';target.parent.mkdir(parents=True,exist_ok=True)
                def image_render(block):
                    return metal.interpolate_cube(cubes[key],-np.log10(np.maximum(block,1e-12)),
                        'Display Encoding','sRGB',False,plans[key])
                frame['cases'][key]['image']=write_image(target,MappedSource.from_array(pixels),image_render,
                    model.display_profile('sRGB'),fingerprint=fingerprint+'-'+key+'-sensitivity-EV2',compression=3)
        pixels._mmap.close();frame['seconds']=time.monotonic()-started;records.append(frame)
        (out/'frames.json').write_text(json.dumps(records,indent=2)+'\n')
        print('Rendered frame',number,'/',37,'seconds',round(frame['seconds'],2),flush=True)
    reference=np.concatenate(all_base);reference0=np.concatenate(all_base0);baseline_valid=np.concatenate(all_baseline_valid)
    aggregate={}
    for key,values in samples.items():
        actual=np.concatenate([v['rgb'] for v in values]);actual0=np.concatenate([v['rgb0'] for v in values]);valid=np.concatenate([v['valid'] for v in values])
        aggregate[key]={'difference_plus2':display_difference(reference,actual,valid=valid&baseline_valid),
            'difference_0':display_difference(reference0,actual0,valid=valid&baseline_valid),
            'valid_fraction':float(valid.mean()),'CV_RMS_D':case_metadata[key].get('outer_RMS_D')}
    if retained_records(baseline)!=retained_before:raise ValueError('RAW retention records changed')
    (out/'summary.json').write_text(json.dumps({'cases':aggregate,'retained_RAW_records_unchanged':True,
        'retained_stage_count':len(retained_before),'new_RAW_developments':0,'full_image_count':sum('image' in c for f in records for c in f['cases'].values()),
        'scope':'conditional sensitivity, not colour accuracy or physical SSF selection'},indent=2)+'\n')
    print('Complete',out,flush=True)


if __name__=='__main__':main()
