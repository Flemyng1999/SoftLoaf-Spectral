"""Controlled comparison against saved manuscript APD/ACES arrays.

Reads numerical evidence only; never imports historical application programs,
profiles, camera data, or calibration code. Does not change workspace recipes.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image,ImageCms

from experiments.gui_recipe_server import template
from experiments.hsi_raw_lut import load_scene,cat,D60,D65
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore
from spectral_lut.negative import adx_codes,adx_to_aces,integrate_density
from spectral_lut.display import ACES_VIEW
import colour


def difference(a,b):
    error=np.max(np.abs(np.clip(a,0,1)-np.clip(b,0,1)),axis=-1)*255
    return {'mean_pixel_max_codes':float(error.mean()),'p95_pixel_max_codes':float(np.percentile(error,95)),
        'max_codes':float(error.max()),'fraction_within_2_codes':float(np.mean(error<=2))}


def compare(root,reference,output):
    output.mkdir(parents=True,exist_ok=True)
    archive=root/'local/film-color-slides/hyperspectral-demo'
    model=SpectralModel(archive,root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',output/'runtime',core=NativeCore())
    metadata=json.loads((reference/'report.json').read_text())
    historical=json.loads((archive/'output/5207-light-comparison/report.json').read_text())
    if (metadata['sources']['material_model']!=historical['source_material_model_sha256']
            or not historical['exposure_illuminant'].startswith('CIE D55')
            or metadata['display']!='sRGB - Display'):
        raise ValueError('The reference no longer has the reviewed source/display conditions')
    old_anchor=historical['camera_stop_for_18pct_reference']
    source=reference/'intermediate/scene43.npz'
    with np.load(source) as saved:
        old={k:saved[k].astype(np.float64) for k in saved.files}
        # Preserve the original float32 multiplication/rounding for PNG readback;
        # promoting before ×255 can move a half-code tie by one stored code.
        old_storage_codes=np.rint(np.clip(saved['sRGB_encoded'],0,1)*255).astype(np.uint8)
    ap0=colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ
    def xyz(aces):return aces@ap0.T@cat(D60,D65).T
    old_xyz=xyz(old['ACES2065_1'])
    scene=load_scene(archive,43)
    if scene.shape[:2]!=old_xyz.shape[:2]:raise ValueError('Different source geometry')
    recipe=model.validate(template('negative'))['normalized_recipe']
    def calculate(k,ev):
        r=copy.deepcopy(recipe);r['scene']={'illuminant':'CIE_D','temperature_k':k};r['film']['exposure_ev']=ev
        p=model.parameters(r)
        def sample(rows):
            s=model.sample_spectra(rows,**p)
            return np.concatenate([s['apd'],s['ACES'],s['XYZ']],axis=-1)
        flat=scene.reshape(-1,33)
        values=np.concatenate([sample(flat[i:i+2048]) for i in range(0,len(flat),2048)]).reshape(*scene.shape[:2],9)
        return {'APD':values[...,:3],'ACES':values[...,3:6],'XYZ':values[...,6:9]}
    current=calculate(6500,0);d55=calculate(5500,0);aligned=calculate(5500,old_anchor)
    render=lambda x,view:model.render(x,view,'sRGB')
    reference_aces2=render(old_xyz,ACES_VIEW)
    # The saved ACES data can be reused as input; every fresh ACES display
    # calculation uses 2.0. Historical display RGB is readback evidence only.
    decoded=adx_to_aces(old['ADX16'])
    old_continuous=adx_to_aces(adx_codes(old['APD'],metadata['APD_Dmin']))
    images={
        'reference_aces2':reference_aces2,
        'reference_opendrt':render(old_xyz,'Default'),
        'current_default':render(current['XYZ'],'Default'),
        'current_aces2':render(current['XYZ'],ACES_VIEW),
        'current_d55_aces2':render(d55['XYZ'],ACES_VIEW),
        'current_aligned_aces2':render(aligned['XYZ'],ACES_VIEW)}
    report={'scope':'scene43; saved numerical reference versus current model. Difference is not an accuracy score.',
        'reference_npz_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'reference_report_sha256':hashlib.sha256((reference/'report.json').read_bytes()).hexdigest(),
        'reference_png_matches_saved_float':bool(np.array_equal(np.asarray(Image.open(reference/'images/scene43.png').convert('RGB')),old_storage_codes)),
        'source_scene_sha256':hashlib.sha256((archive/'data/hsi_43.zip').read_bytes()).hexdigest(),
        'source_geometry':list(scene.shape),'current_material':model.negative.metadata,
        'comparison_display':{'view':ACES_VIEW,'target':'sRGB','config':model.display_manager.config_metadata},
        'archived_source_conditions':{'historical_display':metadata['view'],'historical_config':metadata['builtin_config'],
            'Dmin_APD':metadata['APD_Dmin'],'film_band_nm':metadata['wavelength_nm'],
            'film_illumination':historical['exposure_illuminant'],'camera_stops_for_18_percent':old_anchor,'ADX':'rounded uint16'},
        'current_conditions':{'display':'OpenDRT Default','config':model.display_manager.config_metadata,
            'film_band_nm':[float(model.negative_wavelengths[0]),float(model.negative_wavelengths[-1])],
            'film_illumination':'D65','camera_stops_for_18_percent':0,'ADX':'unquantized float64'},
        'replay':{'saved_codes_to_aces_max_abs':float(np.max(np.abs(decoded-old['ACES2065_1']))),
            'saved_codes_to_aces2_display':difference(render(xyz(decoded),ACES_VIEW),reference_aces2),
            'integer_vs_float_ADX_aces2':difference(render(xyz(old_continuous),ACES_VIEW),render(xyz(decoded),ACES_VIEW))},
        'comparison_to_reference_aces2':{k:difference(v,reference_aces2) for k,v in images.items() if k!='reference_aces2'},
        'shared_aces2_comparison':difference(images['current_aligned_aces2'],reference_aces2),
        'aligned_net_APD_RMS_D':np.sqrt(np.mean(((aligned['APD']-integrate_density(10**-model.negative.base,model.apd_weights))-
            (old['APD']-metadata['APD_Dmin']))**2,axis=(0,1))).tolist()}
    # Native UI uses the exact same nearest-neighbour spectral samples.
    h,w=scene.shape[:2];yy=np.minimum((np.arange(max(1,round(h*192/w)))*w/192).astype(int),h-1)
    xx=np.minimum((np.arange(192)*w/192).astype(int),w-1)
    direct=model.sample_spectra(model.measured_inputs['scene43_rgb'],**model.parameters(recipe))['display_rgb']
    report['preview_matches_full_calculation_max_abs']=float(np.max(np.abs(direct-images['current_default'][yy[:,None],xx[None,:]])))
    if report['preview_matches_full_calculation_max_abs']>1e-12 or not report['reference_png_matches_saved_float']:
        raise ValueError('The comparison does not match the actual preview/reference pixels')
    r=copy.deepcopy(recipe);r.update(id='aligned-aces2-recipe',name='5207 · 条件对齐 · ACES 2.0',revision=1)
    r['scene']={'illuminant':'CIE_D','temperature_k':5500};r['film']['exposure_ev']=old_anchor;r['display']={'view':ACES_VIEW,'target':'sRGB'}
    r=model.validate(r)['normalized_recipe']
    (output/'aligned-aces2-recipe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for key,value in images.items():
        codes=np.rint(np.clip(value,0,1)*255).astype(np.uint8)
        Image.fromarray(codes).save(output/(key+'.png'),icc_profile=icc)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    panels=[('reference_aces2','Archived ACES input: ACES 2.0'),('reference_opendrt','Archived ACES input: OpenDRT'),
        ('current_default','Current app: D65 / 0 EV / OpenDRT'),
        ('current_aces2','Current model: D65 / 0 EV / ACES 2.0'),
        ('current_d55_aces2','Current model: D55 / 0 EV / ACES 2.0'),
        ('current_aligned_aces2','Current model: D55 / -0.6 EV / ACES 2.0')]
    fig,axes=plt.subplots(2,3,figsize=(13,8.2))
    for axis,(key,label) in zip(axes.flat,panels):
        axis.imshow(np.clip(images[key],0,1));axis.set_title(label,fontsize=10);axis.axis('off')
    fig.suptitle('5207 / scene43: separate display, exposure and material differences',fontsize=13)
    fig.subplots_adjust(left=.015,right=.985,bottom=.025,top=.91,wspace=.035,hspace=.18)
    fig.savefig(output/'comparison.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13,3.9))
    for axis,(key,label) in zip(axes,[panels[0],panels[2],panels[5]]):
        axis.imshow(np.clip(images[key],0,1));axis.set_title(label,fontsize=10);axis.axis('off')
    fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.91,wspace=.035)
    fig.savefig(output/'summary.png',dpi=150);plt.close(fig)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=compare(Path(__file__).resolve().parents[1],args.reference,args.output)
    print(json.dumps({k:report[k] for k in ['replay','comparison_to_reference_aces2','shared_aces2_comparison','aligned_net_APD_RMS_D','preview_matches_full_calculation_max_abs']},indent=2))
