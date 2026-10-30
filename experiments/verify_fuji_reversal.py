"""Local source-node, float64, independent viewing and CUBE checks for E-6 presets."""
from pathlib import Path
import json
import numpy as np
import colour
from spectral_app.application import Application
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore
from spectral_lut.reference import density_transmittance


def main():
    root=Path(__file__).resolve().parents[1];out=root/'artifacts/fuji-reversal-review';out.mkdir(parents=True,exist_ok=True)
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out,core=NativeCore())
    app=Application(model);catalog=app.bootstrap()['reversal_presets'];records=[]
    rho=np.array([np.interp(model.source_wavelengths,sd.wavelengths,sd.values) for sd in colour.SDS_COLOURCHECKERS['BabelColor Average'].values()])
    weights=model.status_a_weights/model.status_a_weights.sum(0)
    for entry in catalog:
        stock=entry['id'];r=entry['recipe'];material=r['film']['custom_material'];film,meta=model.material(material)
        raw=json.loads((root/f'local/materials/reversal-presets-v1/{stock}-source-points.json').read_text());source_errors={}
        for i,c in enumerate('RGB'):
            a=np.array(raw['characteristic'][c]);amounts=np.column_stack([np.interp(a[:,0],film.log_h,film.amounts[:,j]) for j in range(3)])
            predicted=-np.log10(density_transmittance(amounts,film.dyes)@weights);source_errors[c]=float(np.max(np.abs(predicted[:,i]-a[:,1])))
        actual=model.sample_spectra(rho,**model.parameters(r));core=model.core
        try:model.core=None;reference=model.sample_spectra(rho,**model.parameters(r))
        finally:model.core=core
        differences={k:float(np.max(np.abs(actual[k]-reference[k]))) for k in ['transmission','XYZ','display_rgb']}
        assert max(differences.values())<3e-13
        observer=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(colour.SpectralShape(400,700,2));wl=model.view_wavelengths;light=model.light('D50');cmf=observer.values
        xyz=np.trapezoid(actual['transmission'][:,:,None]*light[None,:,None]*cmf[None,:,:],wl,axis=1)/np.trapezoid(light*cmf[:,1],wl)*r['viewing']['gain']
        independent_xyz_error=float(np.max(np.abs(xyz-actual['XYZ_view'])));assert independent_xyz_error<2e-5
        result=app.export({'recipe':r,'purpose':'display','grid':65});verification=result['verification'];assert verification['integrity_passed']
        records.append({'stock':stock,'source':material['provenance']['sources']['manufacturer'],'source_node_max_residual_D':source_errors,'neutral_fit_max_residual_D':meta['neutral_StatusA_max_error_D'],'neutral_fit_limit_D':meta['neutral_fit_limit_D'],'source_extraction':material['provenance']['extraction'],'native_vs_numpy_on_24_patches':differences,'independent_colour_CMF_trapezoid_view_XYZ_max_error':independent_xyz_error,'export_id':result['export_id'],'export_65_verification':verification})
        print(stock,'source-node max D',max(source_errors.values()),'fit D',meta['neutral_StatusA_max_error_D'],'LUT integrity',verification['integrity_passed'])
    (out/'verification.json').write_text(json.dumps({'records':records,'scope':'Original manufacturer chart interpretation and numerical/file checks. Local contour rejects are retained for review. Relative D55 normalization and declared unmeasured tails, not absolute ISO calibration or measured real-film color accuracy.'},ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
