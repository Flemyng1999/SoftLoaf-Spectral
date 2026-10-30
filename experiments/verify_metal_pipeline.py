"""Real Metal validation/benchmarks, with float64 and independent color checks.

No real-film accuracy claim. Timings exclude RAW development unless identified.
"""
import argparse
import base64
import copy
import io
import json
from pathlib import Path
import time

import colour
import numpy as np
from PIL import Image

from experiments.gui_recipe_server import template
from experiments.validate_pipeline_defaults import colorimetric,independent_kernel
from spectral_app.application import Application
from spectral_app.model import SpectralModel
from spectral_app.metal_renderer import MetalRenderer
from spectral_lut.native import NativeCore

ROOT=Path(__file__).resolve().parents[1]


def main(raw=None):
    out=ROOT/'artifacts/metal-preview';out.mkdir(parents=True,exist_ok=True)
    m=SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'verification-runtime',core=NativeCore());m.metal=MetalRenderer(m);gpu=m.metal;app=Application(m);boot=app.bootstrap()
    recipes=[e['recipe'] for e in boot['templates'] if e['available']]+[e['recipe'] for e in boot['reversal_presets']]
    negatives={e['recipe']['film']['stock']:e['recipe'] for e in boot['recipe_presets'] if e['recipe']['route']=='negative'}
    recipes.extend(negatives.values())
    for stock,original in negatives.items():
        for paper in boot['paper_presets']:
            r=copy.deepcopy(original);r['route']='print';r['printing']=m.modern_printing(r);r['printing'].update(paper=paper['id'],custom_material=copy.deepcopy(paper['material']));r['display']['view']='Display Encoding';recipes.append(m.validate(r)['normalized_recipe'])
    rng=np.random.default_rng(20261028);rgb=np.vstack([rng.uniform(-.04,2,(256,3)),np.repeat(np.geomspace(1e-7,16,129)[:,None],3,axis=1)])
    spectra=np.maximum(rgb@m.basis,0);records=[]
    for r in recipes:
        check=[]
        for ev in [-4,0,4]:
            test=copy.deepcopy(r);test['film']['exposure_ev']=ev
            for direct,values in [(False,rgb),(True,spectra)]:
                reference=(m.sample_spectra if direct else m.sample)(values,**m.parameters(test))
                xyz=gpu.render(values,test,spectral=direct,purpose='XYZ');encoded=gpu.render(values,test,spectral=direct)
                rgb_error=float(abs(encoded-reference['display_rgb']).max());xyz_scaled=float(np.max(abs(xyz-reference['XYZ'])/np.maximum(abs(reference['XYZ']),.01)))
                assert rgb_error<=3e-4,(r['film']['stock'],r['route'],ev,rgb_error)
                assert xyz_scaled<=5e-4,(r['film']['stock'],r['route'],ev,xyz_scaled)
                record={'film_ev':ev,'measured_spectral_input':direct,'RGB_max_abs':rgb_error,'XYZ_max_scaled_abs':xyz_scaled}
                if r['route']=='negative':
                    apd=gpu.render(values,test,spectral=direct,purpose='apd');record['APD_max_abs_D']=float(abs(apd-reference['apd']).max());assert record['APD_max_abs_D']<3e-5
                elif r['route']=='print':
                    independent=reference['paper_reflectance']@independent_kernel(m,m.negative_wavelengths)*r['viewing']['gain'];record['independent_CMF_XYZ_max_abs']=float(abs(independent-reference['XYZ_view']).max());assert record['independent_CMF_XYZ_max_abs']<2e-12
                    record['independent_sRGB_max_abs']=float(abs(colorimetric(xyz)-encoded).max());assert record['independent_sRGB_max_abs']<3e-4
                check.append(record)
        records.append({'stock':r['film']['stock'],'route':r['route'],'paper':r.get('printing',{}).get('paper'),'checks':check})
        print('checked',r['film']['stock'],r['route'],r.get('printing',{}).get('paper'),flush=True)
    # Short edge is below 2048: retain the 2560x1707 source and export dimensions.
    y,x=np.mgrid[:1707,:2560];picture=np.stack([x/2559,y/1706,(np.sin(x/11)+1)/2],-1)
    stream=io.BytesIO();Image.fromarray(np.rint(picture*255).astype('uint8')).save(stream,format='PNG')
    item=app.import_image({'name':'2048-detail-check.png','data_base64':base64.b64encode(stream.getvalue()).decode()})['input'];assert m.inputs[item['id']].shape==(1707,2560,3)
    r=boot['templates'][1]['recipe'];bench=[]
    for route in ['slide','negative','print']:
        r=copy.deepcopy(next(e['recipe'] for e in boot['templates'] if e['id']==route));values=m.inputs[item['id']]
        gpu.render(values[:2],r)
        start=time.perf_counter();result=gpu.render(values,r);elapsed=time.perf_counter()-start
        benchmark={'route':route,'width':values.shape[1],'height':values.shape[0],'wall_seconds':elapsed,**copy.deepcopy(gpu.last_stats)};bench.append(benchmark)
        Image.fromarray(np.rint(result*255).astype('uint8')).save(out/f'2048-{route}.png',icc_profile=m.display_profile('sRGB'))
        print('native short-edge preview',route,elapsed,'seconds',flush=True)
    preview=app.evaluate({'recipe':r,'input':{'id':item['id'],'exposure_ev':.5},'selection':{'x':.5,'y':.5}})
    assert preview['current']['preview']['width']==2560 and preview['reference']['preview']['width']==2560
    assert preview['conditions']['pixel_compute']['backend']=='Metal'
    exported=app.export_image({'recipe':r,'input':{'id':item['id'],'exposure_ev':.5}});assert exported['verification']['readback_exact'];assert exported['verification']['width']==2560
    lut=app.export({'recipe':r,'purpose':'display','grid':65});assert lut['verification']['integrity_passed']
    raw_report=None
    if raw is not None:
        raw=Path(raw);start=time.perf_counter();photo=app.import_image({'name':raw.name,'data_base64':base64.b64encode(raw.read_bytes()).decode()})['input'];development=time.perf_counter()-start
        raw_preview=app.evaluate({'recipe':r,'input':{'id':photo['id'],'exposure_ev':0},'selection':{'x':.5,'y':.5}})
        from spectral_app.preview_policy import preview_size
        assert (raw_preview['current']['preview']['width'],raw_preview['current']['preview']['height'])==preview_size(*photo['interpretation']['decoded_size'])
        raw_export=app.export_image({'recipe':r,'input':{'id':photo['id'],'exposure_ev':0}})
        assert raw_export['verification']['width']==photo['width'] and raw_export['verification']['height']==photo['height']
        raw_report={'source_file':raw.name,'source_sha256':photo['sha256'],'original_size':[photo['width'],photo['height']],'preview_size':[raw_preview['current']['preview']['width'],raw_preview['current']['preview']['height']],'development_and_registration_seconds':development,'pixel_compute':raw_preview['conditions']['pixel_compute'],'export':raw_export}
    report={'schema':'softloaf.metal-verification/1','compute':gpu.metadata(),'cases':records,'benchmarks':bench,'image_export':exported,'LUT_export':lut,'real_RAW':raw_report,'limits':['Float32 implementation accuracy is separate from real-film material accuracy.','Current built-in HSI source is 329x249; it is not upscaled to pretend to contain 2048px detail.','RawTherapee development, fitting, reference diagnostics and file encoding are CPU boundary work.','GPU working tiles contain at most 65536 pixels; no image-sized intermediate spectral arrays.']}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--raw',type=Path);args=parser.parse_args();main(args.raw)
