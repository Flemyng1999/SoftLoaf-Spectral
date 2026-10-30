"""Read-only real-camera RAW review using an explicit, locally supplied selection.

Run with --source /path/to/RAW/root --selection selection.json. Selection records
contain relative_path, plus optional EXIF metadata. No source images are bundled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import colour
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from spectral_app.rawtherapee import RawTherapee,RAW_EXTENSIONS,lut_input
from spectral_app.application import Application
from experiments.gui_recipe_server import RecipeError


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=Path('artifacts/real-raw-review'))
    parser.add_argument('--limit',type=int)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();source=args.source.resolve();args.output.mkdir(parents=True,exist_ok=True)
    engine=RawTherapee(Path(__file__).resolve().parents[1],args.output/'cache')
    records=json.loads(args.selection.read_text())[:args.limit]
    (args.output/'frames').mkdir(exist_ok=True);(args.output/'thumbnails').mkdir(exist_ok=True)
    frames=[]
    real_run=subprocess.run
    for index,record in enumerate(records):
        relative=record['relative_path'];path=(source/relative).resolve()
        if not path.is_relative_to(source):raise ValueError('Selection escapes source directory')
        name=hashlib.sha256(relative.encode()).hexdigest()[:16];report_path=args.output/'frames'/(name+'.json')
        before=digest(path)
        if args.resume and report_path.is_file():
            saved=json.loads(report_path.read_text())
            if saved.get('source_sha256')==before and saved.get('settings_sha256')==engine.signature:
                frames.append(saved);print(f'{index+1}/{len(records)} cached {relative}',flush=True);continue
        frame={'source':relative,'source_sha256':before,'source_bytes':path.stat().st_size,'metadata':record,
            'settings_sha256':engine.signature,'application_extension_allowed':path.suffix.lower() in RAW_EXTENSIONS}
        calls=[]
        def logged_run(*positional,**kwargs):
            result=real_run(*positional,**kwargs)
            if '-c' in positional[0]:
                calls.append({'returncode':result.returncode,'output':result.stdout.decode(errors='replace').replace(str(source),'<RAW_ROOT>')[-12000:]})
            return result
        started=time.monotonic()
        try:
            with patch('spectral_app.rawtherapee.subprocess.run',side_effect=logged_run):result=engine.develop(path)
            frame['cold_seconds']=time.monotonic()-started
            rgb=result['ap1'];srgb=result['srgb']
            if rgb.shape!=srgb.shape:raise ValueError('Two branches have different dimensions')
            # One deterministic spatial grid, at most 100k samples; full-frame finite/ICC checks are in the real adapter.
            ys=np.linspace(0,rgb.shape[0]-1,min(256,rgb.shape[0])).astype(int)
            xs=np.linspace(0,rgb.shape[1]-1,min(384,rgb.shape[1])).astype(int)
            sample=rgb[ys[:,None],xs[None,:]].astype(np.float64);actual=srgb[ys[:,None],xs[None,:]].astype(np.float64)
            reference=colour.RGB_to_RGB(sample,colour.RGB_COLOURSPACES['ACEScg'],colour.RGB_COLOURSPACES['sRGB'],chromatic_adaptation_transform='Bradford',apply_cctf_encoding=True)
            error=np.max(np.abs(np.clip(reference,0,1)-np.clip(actual,0,1)),axis=-1)*255
            codes=lut_input(sample)
            independent=np.where(sample<=.0078125,10.5402377416545*sample+.0729055341958355,(np.log2(np.maximum(sample,1e-300))+9.72)/17.52)
            frame.update(status='passed' if np.mean(error<=2)>=.99 else 'color_bridge_failed',
                width=rgb.shape[1],height=rgb.shape[0],sample_count=int(error.size),conditions=result['metadata'],
                AP1_range=[float(rgb.min()),float(rgb.max())],srgb_unclipped_range=[float(srgb.min()),float(srgb.max())],
                srgb_bridge_codes={'mean':float(error.mean()),'P95':float(np.percentile(error,95)),'P99':float(np.percentile(error,99)),'max':float(error.max()),'fraction_within_2':float(np.mean(error<=2))},
                ACEScct_formula_max_error=float(np.max(np.abs(codes-independent))),
                LUT_domain={'min':-.25,'max':.75,'fraction_outside':float(np.mean(np.any((codes<-.25)|(codes>.75),axis=-1)))},
                extreme_samples=[{'AP1':sample.reshape(-1,3)[i].tolist(),'RT_sRGB':actual.reshape(-1,3)[i].tolist(),'independent_sRGB':reference.reshape(-1,3)[i].tolist(),'error_codes':float(error.ravel()[i])} for i in np.argsort(error.ravel())[-3:]])
            thumb=Application._resize_float(srgb,(320,220));image=Image.fromarray(np.rint(np.clip(thumb,0,1)*255).astype('uint8'))
            image.save(args.output/'thumbnails'/(name+'.png'),icc_profile=engine.profiles['srgb'])
            frame['thumbnail']=name+'.png'
            del result,rgb,srgb
            started=time.monotonic();again=engine.develop(path);frame['warm_seconds']=time.monotonic()-started
            frame['cache_readback']=again['metadata']['source_sha256']==before;del again
        except Exception as error:
            frame.update(status='failed',error_code=error.code if isinstance(error,RecipeError) else type(error).__name__,error=str(error),cold_seconds=time.monotonic()-started)
        frame['source_unchanged']=digest(path)==before
        frame['engine_failures']=[call for call in calls if call['returncode']]
        report_path.write_text(json.dumps(frame,ensure_ascii=False,indent=2)+'\n');frames.append(frame)
        summary={'completed':index+1,'selected':len(records),'frames':frames,'limits':'Deterministic spatial samples; camera profile accuracy is not measured without scene/color reference; previews stay local.'}
        (args.output/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        print(f'{index+1}/{len(records)} {frame["status"]} {frame["cold_seconds"]:.1f}s {relative} '+str(frame.get('srgb_bridge_codes',{})),flush=True)
    summary={'completed':len(frames),'selected':len(records),'frames':frames,'limits':'Deterministic spatial samples; no real-camera color-accuracy or physical-film accuracy claim.'}
    (args.output/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    successes=[f for f in frames if f.get('thumbnail')]
    sheet=Image.new('RGB',(960,270*((len(successes)+2)//3)),(245,245,247));draw=ImageDraw.Draw(sheet)
    for i,frame in enumerate(successes):
        image=Image.open(args.output/'thumbnails'/frame['thumbnail']);x=(i%3)*320;y=(i//3)*270
        sheet.paste(image,(x+(320-image.width)//2,y))
        draw.text((x+8,y+224),str(frame['metadata'].get('Model',frame['source'].split('/')[1]))[:42],fill=(30,30,30))
        draw.text((x+8,y+241),f'{frame["width"]} x {frame["height"]}  {Path(frame["source"]).suffix}',fill=(80,80,85))
    if successes:sheet.save(args.output/'contact-sheet.png',icc_profile=engine.profiles['srgb'])

if __name__=='__main__':main()
