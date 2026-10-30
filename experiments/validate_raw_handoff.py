"""Check the real RawTherapee handoffs against independent colour-science math.

Synthetic DNGs are development inputs; this does not measure a real camera's
profile accuracy. Run from the repository root after generating these local DNGs.
"""
import argparse
import json
from pathlib import Path
import colour
import numpy as np
from spectral_app.rawtherapee import RawTherapee,lut_input


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/raw-handoff-review'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1];engine=RawTherapee(root,args.output/'cache')
    frames=[]
    for camera in ('r5','d850'):
        source=root/f'artifacts/hsi-raw-lut/raw/scene43_{camera}_ev+0_SYNTHETIC.dng'
        result=engine.develop(source)
        rgb=result['ap1'].astype(float)
        independent=colour.RGB_to_RGB(rgb,colour.RGB_COLOURSPACES['ACEScg'],colour.RGB_COLOURSPACES['sRGB'],chromatic_adaptation_transform='Bradford',apply_cctf_encoding=True)
        error=np.max(np.abs(np.clip(independent,0,1)-np.clip(result['srgb'],0,1)),axis=-1)*255
        expected=np.where(rgb<=.0078125,10.5402377416545*rgb+.0729055341958355,(np.log2(np.maximum(rgb,1e-300))+9.72)/17.52)
        frames.append({'input':source.name,'conditions':result['metadata'],'shape':list(rgb.shape),
            'AP1_range':[float(rgb.min()),float(rgb.max())],
            'sRGB_branch_vs_independent_AP1_matrix_and_IEC_sRGB_codes':{
                'mean':float(error.mean()),'P99':float(np.percentile(error,99)),'max':float(error.max()),
                'fraction_within_2':float(np.mean(error<=2))},
            'ACEScct_vs_independent_formula_max':float(np.max(np.abs(lut_input(rgb)-expected)))})
    report={'schema':'softloaf.raw-handoff-review/1','engine_source_commit':'a8a3d1bc7b419ed1c974c39276c97e618a4f9a1b',
        'observer':'CIE 1931 2 degree colorimetric RGB definition','white_balance':'AsShot, shared RT settings',
        'input_to_film':'float32 linear AP1/D60; no sRGB decode on this branch',
        'lut_input':'ACEScct AP1/D60, float64 encode; no pre-encoding clamp',
        'frames':frames,'limitations':['Synthetic scene43 development inputs, not blind real-camera validation',
            'Profile accuracy and white balance under LED/mixed light are not established',
            'Does not prove upstream RAW processing preserves every negative or HDR value',
            'No physical-film accuracy or new LUT approximation accuracy claim']}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'input':f['input'],**f['sRGB_branch_vs_independent_AP1_matrix_and_IEC_sRGB_codes']} for f in frames],indent=2))

if __name__=='__main__':main()
