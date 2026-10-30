"""Compare reviewed local RAW sources in Bayer preview and full RT modes.

Supply the authorized RAW corpus with --raw-root. Derivative caches are new for
every run; operating-system source-file pages may already be cached.
"""
import argparse
import json
from pathlib import Path
import time
import uuid

import colour
import numpy as np
from PIL import Image

from spectral_app.application import Application
from spectral_app.rawtherapee import RawTherapee


def area64(values):
    return np.stack([np.asarray(Image.fromarray(values[...,c]).resize((64,64),Image.Resampling.BOX)) for c in range(3)],axis=-1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root',type=Path,required=True)
    parser.add_argument('--selection',type=Path,default=Path('artifacts/real-raw-review/report.json'))
    parser.add_argument('--output',type=Path,default=Path('artifacts/raw-superpixel-integrated'))
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    reviewed=json.loads(args.selection.read_text())['frames']
    frames=[f for f in reviewed if any(k in f['source'] for k in ['EOS R6/','D850/','1 S2/','X-T30'])]
    output=args.output/uuid.uuid4().hex;output.mkdir(parents=True);records=[]
    for frame in frames:
        source=args.raw_root/frame['source'];engine=RawTherapee(root,output/'cache')
        assert engine.files.digest(source)==frame['source_sha256']
        start=time.perf_counter();preview=engine.develop(source,preview=True);pt=time.perf_counter()-start
        start=time.perf_counter();full=engine.develop(source);ft=time.perf_counter()-start
        assert preview['metadata']['original_size']==[full['ap1'].shape[1],full['ap1'].shape[0]]
        pixels=Application._resize_float(preview['ap1']);assert min(pixels.shape[:2])<=2048
        step=(max(1,preview['ap1'].shape[0]//120),max(1,preview['ap1'].shape[1]//160))
        ap1=preview['ap1'][::step[0],::step[1]].astype(float)
        srgb=preview['srgb'][::step[0],::step[1]]
        independent=colour.RGB_to_RGB(ap1,colour.RGB_COLOURSPACES['ACEScg'],colour.RGB_COLOURSPACES['sRGB'],chromatic_adaptation_transform='Bradford',apply_cctf_encoding=True)
        bridge=np.max(np.abs(np.clip(independent,0,1)-np.clip(srgb,0,1)),axis=-1)*255
        differences=np.abs(area64(preview['srgb'])-area64(full['srgb']))*255
        record={'source':frame['source'],'source_sha256':frame['source_sha256'],
            'engine_sha256':preview['metadata']['engine_sha256'],'worker_threads':preview['metadata']['worker_threads'],
            'original_size':preview['metadata']['original_size'],'decoded_size':preview['metadata']['decoded_size'],
            'app_preview_size':[pixels.shape[1],pixels.shape[0]],'method':preview['metadata']['preview_method'],
            'preview_cold_seconds':pt,'full_cold_seconds':ft,'speedup':ft/pt,
            'independent_bridge_P99_codes':float(np.percentile(bridge,99)),
            'area64_full_vs_preview_mean_codes':float(np.mean(differences)),
            'area64_full_vs_preview_P95_codes':float(np.percentile(differences,95))}
        records.append(record);print(json.dumps(record),flush=True)
        (output/'verification.json').write_text(json.dumps({'records':records,'limits':[
            'Timings include two RT outputs, empty derivative caches and validation; OS source pages may be cached.',
            'Area-reduced full-vs-preview differences measure changed spatial reconstruction, not camera/material accuracy.']},indent=2))
        assert np.percentile(bridge,99)<.2
        assert engine.files.digest(source)==frame['source_sha256']


if __name__=='__main__':main()
