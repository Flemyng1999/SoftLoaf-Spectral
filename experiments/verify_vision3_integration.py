"""Original-chart, separate standard-table, OCIO, C++ and file checks.

Numerical/source validation is not a paired real-film color measurement.
"""
from pathlib import Path
import copy
import json

import colour
import numpy as np
import PyOpenColorIO as ocio
from PIL import Image

from experiments.integrate_vision3_materials import ROOT, build_material
from experiments.validate_status_m_pipelines import primary_table,products,measured_density
from experiments.validate_pipeline_defaults import colorimetric,independent_kernel
from spectral_app.application import Application
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore
from spectral_lut.display import ACES_CONFIG


def main():
    out=ROOT/'artifacts/vision3-integration';out.mkdir(parents=True,exist_ok=True)
    m=SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'runtime',core=NativeCore());app=Application(m);boot=app.bootstrap()
    recipes={(e['recipe']['film']['stock'],e['recipe']['route']):e['recipe'] for e in boot['recipe_presets']}
    standard,identity=primary_table(ROOT);weights=products(standard,m.negative_wavelengths)
    patches=np.array([np.interp(m.source_wavelengths,sd.wavelengths,sd.values) for sd in colour.SDS_COLOURCHECKERS['BabelColor Average'].values()])
    adx_cpu=ocio.Config.CreateRaw().getProcessor(ocio.BuiltinTransform(style='ADX16_to_ACES2065-1')).getDefaultCPUProcessor()
    aces_cpu=ocio.Config.CreateFromBuiltinConfig(ACES_CONFIG).getProcessor(ocio.DisplayViewTransform(src='ACES2065-1',display='sRGB - Display',view='ACES 2.0 - SDR 100 nits (Rec.709)')).getDefaultCPUProcessor()
    records=[]
    for stock in ['5203','5207','5213','5219']:
        material,_,traces=build_material(ROOT,stock);n=m.route_material(recipes[stock,'negative']);errors={}
        for i,c in enumerate('RGB'):
            p=traces['characteristic_'+c];p=p[(p[:,0]>=n.axis[0])&(p[:,0]<=n.axis[-1])]
            amounts=np.column_stack([np.interp(p[:,0],n.axis,n.amounts[:,j]) for j in range(3)])
            back=measured_density(10**-(n.base+amounts@n.dyes.T),m.negative_wavelengths,weights)
            errors[c]=float(np.max(np.abs(back[:,i]-p[:,1])))
        assert max(errors.values())<.01,(stock,errors)
        item={'stock':stock,'original_chart_and_independent_standard_max_residual_D':errors,'material_fit_D':n.metadata['neutral_max_error_D'],'source':material['provenance']['sources'],'density_metric_evidence':material['provenance']['density_metric_evidence'],'minimum_absolute_density_bound_D':n.metadata['minimum_absolute_density_bound_D'],'routes':{}}
        for route in ['negative','print']:
            r=recipes[stock,route];runs=[];checks={}
            for ev in [-2,0,2]:
                test=copy.deepcopy(r);test['film']['exposure_ev']=ev
                result=m.sample_spectra(patches,**m.parameters(test));core=m.core
                try:m.core=None;reference=m.sample_spectra(patches,**m.parameters(test))
                finally:m.core=core
                delta=max(float(np.max(abs(result[k]-reference[k]))) for k in ['transmission','XYZ','display_rgb']);assert delta<2e-12
                if route=='negative':
                    z=result['adx16_float'].astype(np.float32)/65535;adx_cpu.applyRGB(z)
                    np.testing.assert_allclose(result['ACES'],z,rtol=8e-5,atol=3e-7)
                    aces_error=float(np.max(np.abs(result['ACES']-z)))
                    external=np.array(result['ACES'],dtype=np.float32,order='C');aces_cpu.applyRGB(external);external=np.clip(external,0,1)
                    display_error=float(abs(external-result['display_rgb']).max());assert display_error<2e-5
                    assert 'paper_reflectance' not in result
                    checks[str(ev)]={'native_numpy_max_abs':delta,'independent_ocio_ADX_max_abs':aces_error,'official_ACES2_output_max_abs':display_error}
                else:
                    raw=result['paper_reflectance']@independent_kernel(m,m.negative_wavelengths)*r['viewing']['gain'];raw_error=float(abs(raw-result['XYZ_view']).max());assert raw_error<2e-13
                    display_error=float(abs(colorimetric(result['XYZ'])-result['display_rgb']).max());assert display_error<2e-5
                    assert 'apd' not in result and 'ACES' not in result
                    checks[str(ev)]={'native_numpy_max_abs':delta,'independent_CMF_trapezoid_XYZ_max_abs':raw_error,'independent_sRGB_matrix_encoding_max_abs':display_error}
                runs.append(result)
            other=m.sample_spectra(patches,**m.parameters(recipes[stock,'print' if route=='negative' else 'negative']))
            np.testing.assert_array_equal(runs[1]['transmission'],other['transmission'])
            scene=m.measured_inputs['scene43_rgb'];shape=scene.shape[:2]
            img=m.sample_spectra(scene.reshape(-1,scene.shape[-1]),**m.parameters(r))['display_rgb'].reshape(*shape,3)
            Image.fromarray(np.rint(np.clip(img,0,1)*255).astype('uint8')).resize((576,384)).save(out/f'{stock}-{route}.png',icc_profile=m.display_profile('sRGB'))
            exported=app.export({'recipe':r,'purpose':'display','grid':65});assert exported['verification']['integrity_passed']
            item['routes'][route]={'checks_24_patches_three_EV':checks,'export':exported}
            print(stock,route,'original max D',max(errors.values()),'65 cube integrity passed',flush=True)
        records.append(item)
    report={'schema':'softloaf.vision3-integration-validation/1','records':records,'independent_density_standard':identity,'observer':'CIE 1931 2 degree','output':'encoded sRGB/D65; negative ACES 2.0 SDR100, print colorimetric','limits':['Original charts and separate standard tables verify source interpretation; there are no exposure-paired measurements of actual developed colored film.','5203 complete 2015 source is independent of the simplified 2025 source; 5219 Status M interpretation is inferred and recorded.','Own endpoint dye/D-min tails and zero sensitivity tails are declared assumptions, not new measured spectra.','65-cube approximation errors are reported as measured; file integrity does not guarantee the 99% / 2-code reference line.']}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
