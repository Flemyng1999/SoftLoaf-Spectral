"""Issue #2: source-curve correction versus RGB spectral-approximation error.

Uses retained Kodak vector traces and measured BabelColor reflectances. These
comparisons do not provide exposure-paired measurements of real 5207 film.
Run alongside validate_pipeline_defaults for independent APD/ACES/colorimetry.
"""
import argparse
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import colour
import numpy as np

from experiments.gui_recipe_server import template
from experiments.hsi_raw_lut import csv
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore
from spectral_lut.reference import quadrature_widths
from spectral_lut.negative import integrate_density
from scipy.optimize import least_squares


def legacy_apd_fit(model,material):
    """Replay the retired /1–/2 calibration only for historical comparisons.

    Production material fitting must not call this APD-target approximation.
    """
    grid=model.negative_wavelengths;axis,targets,dyes,sens=model._tables(material,grid)
    calibration=model.calibration['status_m_to_apd']
    targets=targets@np.asarray(calibration['matrix']).T+calibration['offset']
    published=np.interp(grid,material['base']['wavelengths_nm'],material['base']['values'])
    weights=model.apd_weights;shapes=weights/weights.max(0)
    correction=least_squares(lambda x:integrate_density(10**-np.maximum(published+shapes@x,0),weights)-targets[0],np.zeros(3),ftol=1e-13,xtol=1e-13,gtol=1e-13)
    base=np.maximum(published+shapes@correction.x,0)
    from spectral_app.model import fit_amounts
    amounts,error=fit_amounts(dyes,base,weights,targets)
    return SimpleNamespace(axis=axis,amounts=amounts,dyes=dyes,base=base,sensitivity=sens,
        metadata={'name':material['name'],'fit_metric':'estimated APD (retired /1–/2)',
                  'neutral_max_error_D':error,'scope':'historical replay only'})


def errors(a,b):
    e=np.max(np.abs(np.clip(a,0,1)-np.clip(b,0,1)),axis=-1)*255
    return {'mean_max_channel_codes':float(e.mean()),'maximum_codes':float(e.max()),
            'fraction_within_2':float(np.mean(e<=2)),'per_patch_codes':e.tolist()}


def validate(root,output):
    output.mkdir(parents=True,exist_ok=True)
    m=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',
        root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',output/'runtime',core=NativeCore())
    # Reconstruct the two prior defects from their pinned inputs. Separate
    # instances keep the calibration denominators fixed within each model.
    old=copy.copy(m);old.negative_material=copy.deepcopy(m.negative_material)
    table=csv(m.material_directory/'5207_dyes.csv',1)
    old.negative_material['dyes']['quantity']='spectral_density'
    for i,c in enumerate('CMY'):old.negative_material['dyes']['channels'][c]=table[:,i+1].tolist()
    old.negative_denominators=.18*np.sum(m.negative.sensitivity*m._daylight(5500,m.source_wavelengths)[:,None]*quadrature_widths(m.source_wavelengths)[:,None],0)
    old.negative=legacy_apd_fit(old,old.negative_material)
    del old.paper_denominators
    old.paper=old._paper_fit(old.paper_material)
    # Isolate the signed-basis change at the old exposure normalization too.
    signed=copy.copy(old)
    signed.negative=legacy_apd_fit(signed,m.negative_material)
    del signed.paper_denominators
    signed.paper=signed._paper_fit(signed.paper_material)

    patches=colour.SDS_COLOURCHECKERS['BabelColor Average']
    spectra=np.stack([np.interp(m.source_wavelengths,s.wavelengths,s.values) for s in patches.values()])
    rgb=spectra@m.source_to_ap1
    reconstructed=rgb@m.basis
    report={'scope':'24 measured reflectance patches; all are development inputs, not blind film measurements. Reference is direct spectral evaluation of the same approximate film model.',
        'model':m.negative_refs,'patches':list(patches),'illuminant':'CIE D55 for scene and exposure anchor; fixed D65 input reference',
        'observer':'CIE 1931 2 degree','input':'linear AP1 / D60 derived from measured reflectances under D65',
        'output':'sRGB D65, 0–1, errors are maximum RGB channel difference multiplied by 255',
        'source_wavelengths_nm':m.source_wavelengths.tolist(),'density_wavelengths_nm':m.negative_wavelengths.tolist(),
        'negative_metadata':m.negative.metadata,'paper_metadata':m.paper.metadata,'routes':{},
        'unclipped_RGB_prior_min_reflectance':float(reconstructed.min()),
        'clamped_RGB_prior_max_AP1_reprojection_error':float(np.max(abs(np.maximum(reconstructed,0)@m.source_to_ap1-rgb))),
        'physical_accuracy_established':False}
    neutral=np.full(len(m.source_wavelengths),.18)
    report['D55_18_percent_gray']={name:model._film_stage(neutral,0,5500,model.negative)[0].tolist() for name,model in [('before',old),('after',m)]}
    for route in ['negative','print']:
        recipe=m.validate(template(route))['normalized_recipe']
        direct=m.sample_spectra(spectra,**m.parameters(recipe))
        approximate=m.sample(rgb,**m.parameters(recipe))
        before=old.sample_spectra(spectra,**old.parameters(recipe))
        signed_only=signed.sample_spectra(spectra,**signed.parameters(recipe))
        report['routes'][route]={'display':recipe['display'],
            'correction_change':errors(before['display_rgb'],direct['display_rgb']),
            'signed_basis_only_change':errors(before['display_rgb'],signed_only['display_rgb']),
            'RGB_approximation_vs_direct_spectral':errors(direct['display_rgb'],approximate['display_rgb']),
            'direct_RGB':direct['display_rgb'].tolist(),'approximate_RGB':approximate['display_rgb'].tolist(),
            'before_RGB':before['display_rgb'].tolist(),
            'transmission_min_max':[float(direct['transmission'].min()),float(direct['transmission'].max())]}
        if route=='print':report['routes'][route]['paper_reflectance_min_max']=[float(direct['paper_reflectance'].min()),float(direct['paper_reflectance'].max())]
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    report=validate(Path(__file__).resolve().parents[1],args.output.resolve())
    print(json.dumps({'D55_gray':report['D55_18_percent_gray'],
        'routes':{k:{n:v[n] for n in ['correction_change','signed_basis_only_change','RGB_approximation_vs_direct_spectral']} for k,v in report['routes'].items()}},indent=2))
