"""Reproducible local audit: physical spectra, RGB approximation and LUT errors.

Run after material extraction and a CMake core build. Output contains no private
absolute paths; restricted manufacturer tables are not copied into this report.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from experiments.gui_recipe_server import template
from experiments.hsi_raw_lut import batched,load_scene,apply_ocio
from spectral_app.model import SpectralModel
from spectral_app.application import Application
from spectral_lut.native import NativeCore
from spectral_lut.metrics import srgb_code_error
from spectral_lut.negative import adx_to_aces
import PyOpenColorIO as ocio


def audit(output=Path('artifacts/pipeline-audit')):
    m=SpectralModel(Path('local/film-color-slides/hyperspectral-demo'),Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'),output,core=NativeCore())
    app=Application(m)
    spectra=[];groups=[]
    for scene in [1,5,6,16,31,38,43,50]:
        hsi=load_scene(m.archive,scene);h,w=hsi.shape[:2]
        # Fixed spatial samples before every transform, same indices all routes.
        r=hsi[np.linspace(0,h-1,32).astype(int)[:,None],np.linspace(0,w-1,48).astype(int)[None,:]].reshape(-1,hsi.shape[-1])
        spectra.append(r);groups.extend([f'scene{scene}']*len(r))
    spectra.append(m.measured_inputs['chart'][32::64,32::64].reshape(24,-1));groups.extend(['BabelColor24']*24)
    spectra=np.concatenate(spectra);groups=np.array(groups);rgb=spectra@m.source_to_ap1
    report={'scope':'Local numerical audit, eight historical development HSI scenes plus measured BabelColor24. Not a fresh blind evaluation or real-film material accuracy test. Each group includes EV -2, 0, +2.',
        'sample_count_per_exposure':len(spectra),'negative':m.negative.metadata,'paper':m.paper.metadata,'routes':{},'sources':m.negative_refs,
        'fixes':['5207 routes now calculate real material intermediates instead of draft-only recipes.','HSI and Colour24 B previews use measured spectra, ordinary photographs use the RGB approximation.','Paper gray exposure anchor solves D50 Y=0.1 before default gain1.8 instead of an arbitrary log exposure midpoint.','APD route does not use viewing lamps, recapture cameras or paper; printing does not use APD/ACES output as its paper exposure.']}
    codes=np.random.default_rng(11).uniform(0,26000,(1024,3));p=ocio.Config.CreateRaw().getProcessor(ocio.BuiltinTransform(style='ADX16_to_ACES2065-1')).getDefaultCPUProcessor()
    independent=apply_ocio(p,codes/65535);ours=adx_to_aces(codes)
    report['ACES_1_2_cross_implementation']={'reference':'independent OCIO builtin ADX16_to_ACES2065-1','points':len(codes),'max_abs_AP0':float(np.max(np.abs(ours-independent))),'max_relative_AP0':float(np.max(np.abs(ours-independent)/np.maximum(np.abs(ours),1e-8)))}
    for route in ['slide','negative','print']:
        r=m.validate(template(route))['normalized_recipe'];params=m.parameters(r)
        measured=[];approx=[];perframe={};native_max=0
        for ev in [-2,0,2]:
            physical=batched(lambda x:m.sample_spectra(x,**params)['sRGB'],spectra*2.**ev,chunk=512)
            estimated=batched(lambda x:m.sample(x,**params)['sRGB'],rgb*2.**ev,chunk=512)
            measured.append(physical);approx.append(estimated)
            for group in np.unique(groups):perframe[group+f'_EV{ev:+}']=srgb_code_error(physical[groups==group],estimated[groups==group])[0]
        # Native/reference comparison includes off-neutral channels and all EV.
        random=np.random.default_rng(23).uniform(0,2,(257,3));a=m.sample(random,**params)
        core=m.core
        try:m.core=None;b=m.sample(random,**params)
        finally:m.core=core
        native_max=max(float(np.max(np.abs(a[k]-b[k]))) for k in ['exposure','dye_amounts','transmission','XYZ']+(['apd'] if route!='slide' else [])+(['paper_exposure','paper_reflectance'] if route=='print' else []))
        exported=app.export({'recipe':r,'purpose':'pipeline','grid':65})
        report['routes'][route]={'RGB_approximation_vs_physical':srgb_code_error(np.concatenate(measured),np.concatenate(approx))[0],'per_group':perframe,'native_vs_float64_max_abs_intermediate':native_max,'LUT_65':exported['verification'],'export_id':exported['export_id']}
        # A/builtin source remains the colorimetric scene, without film or DRT.
        if 'scene43_rgb' in m.measured_inputs:
            physical=batched(lambda x:m.sample_spectra(x,**params)['sRGB'],m.measured_inputs['scene43_rgb'],chunk=1024)
            Image.fromarray(np.floor(np.clip(physical,0,1)*255+.5).astype('uint8')).save(output/(route+'-physical.png'))
    path=output/'audit.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'report':str(path),'routes':{k:{'RGB_approx_fraction':v['RGB_approximation_vs_physical']['fraction_within_2_codes_float'],'LUT65_fraction':v['LUT_65']['float64_cube']['fraction_within_2_codes_float'],'integrity':v['LUT_65']['integrity_passed'],'native_max':v['native_vs_float64_max_abs_intermediate']} for k,v in report['routes'].items()}},indent=2))

if __name__=='__main__':audit()
