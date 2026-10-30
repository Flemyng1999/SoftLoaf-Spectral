"""Check original chart points, physical bounds, independent colorimetry and files.

These numerical/source checks are not exposure-paired measurements of real paper.
"""
import copy
import json
from pathlib import Path

import colour
import numpy as np
import pymupdf
from PIL import Image,ImageDraw

from experiments.validate_pipeline_defaults import independent_kernel,colorimetric
from experiments.build_paper_presets import ROOT,SPECS,sha
from spectral_app.application import Application
from spectral_app.model import SpectralModel
from spectral_app.paper_presets import load_paper_presets
from spectral_lut.native import NativeCore


def main():
    out=ROOT/'artifacts/paper-presets';out.mkdir(exist_ok=True,parents=True)
    model=SpectralModel(ROOT/'local/film-color-slides/hyperspectral-demo',ROOT/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'verify-runtime',core=NativeCore())
    app=Application(model);boot=app.bootstrap();catalog=load_paper_presets(ROOT)
    negatives={e['recipe']['film']['stock']:e['recipe'] for e in boot['recipe_presets'] if e['recipe']['route']=='print'}
    patches=np.array([np.interp(model.source_wavelengths,sd.wavelengths,sd.values) for sd in colour.SDS_COLOURCHECKERS['BabelColor Average'].values()])
    records=[];frames=[]
    for entry in catalog:
        material=entry['material'];fit=model._paper_fit(material)
        source_file=ROOT/'local/materials/paper-presets-v1'/entry['source_file']
        assert sha(source_file)==entry['source_sha256']
        source=json.loads(source_file.read_text());residual={}
        # Re-evaluate the retained original vertices, not just the 321 fit points.
        weights=model._paper_weights()
        for i,c in enumerate('RGB'):
            points=np.array(source['curves']['char_'+c]);points=points[(points[:,0]>=fit.axis[0])&(points[:,0]<=fit.axis[-1])]
            a=np.column_stack([np.interp(points[:,0],fit.axis,fit.amounts[:,j]) for j in range(3)])
            density=-np.log10((10**-(fit.base+a@fit.dyes.T))@weights)
            residual[c]=float(abs(density[:,i]-points[:,1]).max())
        assert max(residual.values())<.02
        # Source overlay in original PDF coordinates catches axes/curve selection errors.
        pdf=pymupdf.open(ROOT/'local/reference-assets/paper-survey-20261028'/(SPECS[entry['id']]['source']+'.pdf'))
        colors={'R':(1,0,0),'G':(0,.7,0),'B':(0,0,1),'C':(0,.7,.7),'M':(.8,0,.8),'Y':(.8,.65,0)}
        pages=set()
        for name,g in source['geometry'].items():
            page=pdf[g['page']-1];page.draw_polyline([pymupdf.Point(*p) for p in g['pdf_points']],color=colors[name[-1]],width=.7,overlay=True);pages.add(g['page'])
        for page in pages:pdf[page-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(out/f'{entry["id"]}-source-p{page}.png')
        combinations=[]
        for stock,original in negatives.items():
            r=copy.deepcopy(original);r['printing'].update(paper=entry['id'],custom_material=copy.deepcopy(material));r=model.validate(r)['normalized_recipe']
            checks=[]
            for ev in [-2,0,2]:
                test=copy.deepcopy(r);test['film']['exposure_ev']=ev
                actual=model.sample_spectra(patches,**model.parameters(test));native=model.core
                try:
                    model.core=None;reference=model.sample_spectra(patches,**model.parameters(test))
                finally:model.core=native
                error=max(float(abs(actual[k]-reference[k]).max()) for k in ('paper_exposure','paper_reflectance','XYZ','display_rgb'))
                assert error<2e-12
                assert np.all(actual['paper_reflectance']>=0) and np.all(actual['paper_reflectance']<=1)
                assert 'apd' not in actual and 'ACES' not in actual
                raw=actual['paper_reflectance']@independent_kernel(model,model.negative_wavelengths)*r['viewing']['gain']
                xyz_error=float(abs(raw-actual['XYZ_view']).max());assert xyz_error<2e-13
                rgb_error=float(abs(colorimetric(actual['XYZ'])-actual['display_rgb']).max());assert rgb_error<2e-5
                film_only=model.sample_spectra(patches,**model.parameters(original))
                if ev==0:np.testing.assert_array_equal(actual['transmission'],film_only['transmission'])
                checks.append({'film_ev':ev,'native_numpy_max_abs':error,'independent_D50_CMF_integral_max_abs':xyz_error,'independent_sRGB_matrix_encoding_max_abs':rgb_error})
            combinations.append({'negative':stock,'checks_24_patches':checks})
            if stock=='5207':
                scene=model.measured_inputs['scene43_rgb'];shape=scene.shape[:2]
                rgb=model.sample_spectra(scene.reshape(-1,scene.shape[-1]),**model.parameters(r))['display_rgb'].reshape(*shape,3)
                im=Image.fromarray(np.rint(np.clip(rgb,0,1)*255).astype('uint8')).resize((480,320));im.save(out/(entry['id']+'-5207.png'),icc_profile=model.display_profile('sRGB'))
                frame=Image.new('RGB',(480,350),'white');frame.paste(im,(0,30));ImageDraw.Draw(frame).text((8,8),entry['name'],fill='black');frames.append(frame)
                exported=app.export({'recipe':r,'purpose':'display','grid':65});assert exported['verification']['integrity_passed']
        records.append({'id':entry['id'],'source':entry['source'],'original_StatusA_vertices_max_residual_D':residual,'combinations':combinations,'export_65':exported,'missing_measurements':material['provenance']['missing_measurements']})
        print(entry['id'],'source and 4 negative combinations, C++/NumPy, independent XYZ/sRGB, 65 CUBE integrity passed',flush=True)
    sheet=Image.new('RGB',(960,700),'white')
    for i,frame in enumerate(frames):sheet.paste(frame,((i%2)*480,(i//2)*350))
    sheet.save(out/'four-papers-5207.png',icc_profile=model.display_profile('sRGB'))
    report={'schema':'softloaf.paper-preset-validation/1','records':records,'limits':['Neutral original-chart fit and independent colorimetry do not establish real-print color accuracy.','No paired exposure/print spectral measurements, measured paper white, fluorescence or angular scattering.','EDGE/ROYAL exposure durations are unspecified; Metallic directional appearance is omitted.','LUT interpolation quality is reported independently of file integrity and does not gate download.']}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
