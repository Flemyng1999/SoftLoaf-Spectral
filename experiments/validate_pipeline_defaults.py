"""Issue #2: external colorimetry, official ACES and manuscript comparisons.

Run with local, unredistributed spectral assets. Historical programs are never
imported. Saved arrays are comparison evidence, not measured film truth.
"""
import argparse
import copy
import json
from pathlib import Path

import numpy as np
import PyOpenColorIO as ocio
from PIL import Image,ImageCms

from experiments.gui_recipe_server import template
from experiments.hsi_raw_lut import load_scene,SCENES,sha
from spectral_app.model import SpectralModel,stage
from spectral_app.application import Application
from spectral_lut.native import NativeCore
from spectral_lut.display import ACES_CONFIG,ACES_VIEW,COLORIMETRIC_VIEW

# Independent published-primary matrix and piecewise file encoding. No app
# display graph, colour conversion helper, or archived rendering code is used.
XYZ_TO_SRGB=np.array([[3.2409699419,-1.5373831776,-.4986107603],
    [-.9692436363,1.8759675015,.0415550574],[.0556300797,-.2039769589,1.0569715142]])
BRADFORD=np.array([[.8951,.2664,-.1614],[-.7502,1.7135,.0367],[.0389,-.0685,1.0296]])
WHITE_D65=np.array([.3127/.329,1,(1-.3127-.329)/.329])


def adapt(source,dest=WHITE_D65):
    return np.linalg.inv(BRADFORD)@np.diag((BRADFORD@dest)/(BRADFORD@source))@BRADFORD


def encode(linear):
    return np.clip(np.where(linear<=.0031308,linear*12.92,
        1.055*np.maximum(linear,0)**(1/2.4)-.055),0,1)


def colorimetric(xyz):return encode(xyz@XYZ_TO_SRGB.T)


def cpu_apply(cpu,values):
    out=np.array(values,dtype=np.float32,order='C',copy=True);cpu.applyRGB(out)
    return np.clip(out.astype(float),0,1)


def diff(a,b):
    e=np.max(abs(np.clip(a,0,1)-np.clip(b,0,1)),axis=-1)*255
    return {'pixels':int(e.size),'mean_codes':float(e.mean()),'p95_codes':float(np.percentile(e,95)),
        'max_codes':float(e.max()),'fraction_within_2':float(np.mean(e<=2))}


def read_npz(path):
    with np.load(path) as z:return {k:z[k].astype(float) for k in z.files}


def independent_kernel(model,grid):
    root=model.archive.parent/'data'
    cmf=np.loadtxt(root/'CIE_xyz_official.csv',delimiter=',')
    light=np.loadtxt(root/'CIE_std_illum_D50.csv',delimiter=',')
    v=np.column_stack([np.interp(grid,cmf[:,0],cmf[:,i]) for i in [1,2,3]])
    v*=np.interp(grid,light[:,0],light[:,1])[:,None]
    widths=np.empty_like(grid);widths[0]=(grid[1]-grid[0])/2;widths[-1]=(grid[-1]-grid[-2])/2
    widths[1:-1]=(grid[2:]-grid[:-2])/2
    v*=widths[:,None];return v/v[:,1].sum()


def validate(root,output,scenes=SCENES,exports=False):
    output.mkdir(parents=True,exist_ok=True)
    archive=root/'local/film-color-slides/hyperspectral-demo'
    model=SpectralModel(archive,root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',output/'runtime',core=NativeCore())
    app=Application(model)
    recipes={r:model.validate(template(r))['normalized_recipe'] for r in ['slide','negative','print']}
    official=ocio.Config.CreateFromBuiltinConfig(ACES_CONFIG)
    aces_cpu=official.getProcessor(ocio.DisplayViewTransform(src='ACES2065-1',display='sRGB - Display',
        view='ACES 2.0 - SDR 100 nits (Rec.709)')).getDefaultCPUProcessor()
    adx_cpu=ocio.Config.CreateRaw().getProcessor(ocio.BuiltinTransform(style='ADX16_to_ACES2065-1')).getDefaultCPUProcessor()
    e100=archive/'output/reversal-E100';paper=archive/'output/5207-light-comparison/optical-print'
    old_film=read_npz(e100/'intermediate/model.npz');old_paper=read_npz(paper/'intermediate/paper_model.npz')
    manuscript=root/'video/assets/aces2-2026-10-27'
    apd_reference=root/'video/assets/experiments/apd-standard-reference-v1'
    report={'scope':'Float64 physical calculation, independent colorimetry and official ACES input/output; saved manuscript evidence. No measured full-color film accuracy claim.',
        'defaults':{k:v['display'] for k,v in recipes.items()},'observer':'CIE 1931 2 degree',
        'output':'sRGB / D65, piecewise transfer, clipped 0–1; all code errors multiply by 255',
        'conditions':{k:app.conditions(v) for k,v in recipes.items()},
        'material_comparison_is_not_accuracy':True,'scenes':{},'sources':{},
        'limits':['E100 default retains its D65-calibrated exposure kernel; archived D55 kernel is used only for a separate controlled replay.',
            'Paper manufacturer-only density model differs from measured-reflectance-constrained manuscript model; its exposure-to-reflectance accuracy is unvalidated.',
            'Paper reference includes a recorded per-image observation-density offset; no per-image alignment is introduced into the application or LUT.',
            'Finite source bands and model assumptions are retained; graph display limits do not define integration coverage.']}
    def record(path):report['sources'][str(path.relative_to(root))]=sha(path)
    for p in [e100/'intermediate/model.npz',paper/'intermediate/paper_model.npz',
              manuscript/'report.json',root/'local/materials/5207-v1/provenance.json']:record(p)
    slide_kernel=independent_kernel(model,model.view_wavelengths)
    paper_kernel=independent_kernel(model,model.negative_wavelengths)
    direct_max={'slide':0.,'print':0.,'negative':0.}
    panels={}
    def calculate(scene,recipe):
        rows=scene.reshape(-1,scene.shape[-1]);xyz=[];rgb=[];route=recipe['route']
        for i in range(0,len(rows),2048):
            s=model.sample_spectra(rows[i:i+2048],**model.parameters(recipe))
            if route=='negative':
                # Independently integrate the standard responsivities, encode
                # continuous ADX, then use OCIO's separately maintained builtin.
                t=s['transmission'];raw=np.loadtxt(model.material_directory/'apd_weights.csv',delimiter=',',skiprows=1)
                grid=raw[:,0];w=raw[:,1:]
                d=-np.log10(np.trapezoid(t[:,:,None]*w[None,:,:],grid,axis=1)/np.trapezoid(w,grid,axis=0))
                base=-np.log10(np.trapezoid(10.**-model.negative.base[:,None]*w,grid,axis=0)/np.trapezoid(w,grid,axis=0))
                codes=(d-base)*np.array([8000,7360,7600])+1520
                aces=np.array(codes/65535,dtype=np.float32,order='C');adx_cpu.applyRGB(aces)
                expected=cpu_apply(aces_cpu,aces)
            else:
                k=slide_kernel if route=='slide' else paper_kernel
                spectrum=s['transmission'] if route=='slide' else s['paper_reflectance']
                observed=spectrum@k*recipe['viewing']['gain']
                expected=colorimetric(observed@adapt(k.sum(0)).T)
            direct_max[route]=max(direct_max[route],float(np.max(abs(expected-s['display_rgb']))*255))
            xyz.append(s['XYZ']);rgb.append(s['display_rgb'])
        shape=(*scene.shape[:2],3)
        return np.concatenate(xyz).reshape(shape),np.concatenate(rgb).reshape(shape)

    for number in scenes:
        name=f'scene{number:02d}';scene=load_scene(archive,number);record(archive/f'data/hsi_{number}.zip')
        result={};current={r:calculate(scene,v)[1] for r,v in recipes.items()}
        # Controlled E100 material replay, independent of the old program.
        reversal=[]
        for ev in [-1,0,1]:
            path=e100/f'intermediate/{name}_ev{ev:+d}.npz';saved=read_npz(path);record(path)
            raw=[]
            rows=scene.reshape(-1,scene.shape[-1])
            for i in range(0,len(rows),2048):
                t=stage(rows[i:i+2048],old_film['exposure_kernel'],model.film.log_h,model.film.amounts,
                    model.film.dyes,np.zeros(len(model.film.dyes)),model.film.gray_log_h,ev,model.core)[2]
                raw.append(t@slide_kernel)
            raw=np.concatenate(raw).reshape(*scene.shape[:2],3)
            replay=model.render(raw@adapt(slide_kernel.sum(0)).T*1.8,COLORIMETRIC_VIEW)
            reference=encode(saved['linear_sRGB_lightbox']*1.8)
            reversal.append({'ev':ev,'raw_XYZ_max_abs':float(np.max(abs(raw-saved['XYZ_D50']))),
                'display':diff(replay,reference)})
            if ev==0:
                result['e100_default_vs_manuscript']=diff(current['slide'],reference)
                if number==43:panels.update(e100_reference=reference,e100_current=current['slide'],e100_replay=replay)
        result['e100_D55_material_replay']=reversal
        path=paper/f'intermediate/{name}_print.npz';old=read_npz(path);record(path)
        path=manuscript/f'intermediate/{name}_paper_aligned.npz';aligned=read_npz(path);record(path)
        scalar=10**-float(aligned['neutral_observation_density_offset'])
        replay=model.render(old['XYZ_D50']@old_paper['adapt_D50_to_D65'].T*scalar,COLORIMETRIC_VIEW)
        result['paper_saved_XYZ_display_replay']=diff(replay,aligned['sRGB_encoded'])
        result['paper_default_vs_manuscript']=diff(current['print'],aligned['sRGB_encoded'])
        # Match only the recorded negative capture conditions; paper filters,
        # calibration, reflectance basis and bands still differ explicitly.
        aligned_recipe=copy.deepcopy(recipes['print']);aligned_recipe['scene']={'illuminant':'CIE_D','temperature_k':5500};aligned_recipe['film']['exposure_ev']=-.6
        result['paper_D55_minus_06_capture_only_vs_manuscript']=diff(calculate(scene,aligned_recipe)[1],aligned['sRGB_encoded'])
        path=apd_reference/f'intermediate/{name}.npz';old=read_npz(path);record(path)
        reference=cpu_apply(aces_cpu,old['ACES2065_1'])
        result['apd_default_vs_archived_ACES_input_rendered_2']=diff(current['negative'],reference)
        aligned_recipe=copy.deepcopy(recipes['negative']);aligned_recipe['scene']={'illuminant':'CIE_D','temperature_k':5500};aligned_recipe['film']['exposure_ev']=-.6
        result['apd_D55_minus_06_vs_archived_ACES_input_rendered_2']=diff(calculate(scene,aligned_recipe)[1],reference)
        if number==43:
            panels.update(paper_reference=aligned['sRGB_encoded'],paper_current=current['print'],paper_replay=replay,
                apd_reference=reference,apd_current=current['negative'],apd_aligned=calculate(scene,aligned_recipe)[1])
        report['scenes'][name]=result
        print(name,'compared',flush=True)
    report['independent_pipeline_max_code_error']=direct_max
    report['independent_pipeline_pass']=all(v<.02 for v in direct_max.values())
    report['saved_reference_replay_pass']=all(
        all(e['raw_XYZ_max_abs']<1e-7 and e['display']['max_codes']<.2 for e in s['e100_D55_material_replay'])
        and s['paper_saved_XYZ_display_replay']['max_codes']<.05 for s in report['scenes'].values())
    report['exports']={}
    if exports:
        for route,r in recipes.items():
            exported=app.export({'recipe':r,'purpose':'display','grid':65})
            report['exports'][route]=exported
            print(route,'65^3 export',exported['ok'],flush=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for key,value in panels.items():Image.fromarray(np.rint(np.clip(value,0,1)*255).astype('uint8')).save(output/(key+'.png'),icc_profile=icc)
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,3,figsize=(12,10))
    labels=[('e100_reference','E100 manuscript: D55 / D50 / gain 1.8'),('e100_current','E100 new default: D65 calibrated'),('e100_replay','E100 controlled D55 material replay'),
        ('apd_reference','Archived ACES input: official ACES 2.0'),('apd_current','APD new default: D55 / 0 EV / ACES 2.0'),('apd_aligned','APD: D55 / -0.6 EV / ACES 2.0'),
        ('paper_reference','Paper manuscript: measured-constrained model'),('paper_current','Paper new default: manufacturer-only model'),('paper_replay','Archived paper XYZ: new colorimetric display')]
    for ax,(key,title) in zip(axes.flat,labels):ax.imshow(panels[key]);ax.set_title(title,fontsize=9);ax.axis('off')
    fig.subplots_adjust(left=.01,right=.99,bottom=.01,top=.96,wspace=.025,hspace=.12)
    fig.savefig(output/'comparison.png',dpi=140);plt.close(fig)
    if not report['independent_pipeline_pass'] or not report['saved_reference_replay_pass']:
        raise AssertionError('External pipeline/reference replay verification failed; inspect report')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--exports',action='store_true');args=p.parse_args()
    report=validate(Path(__file__).resolve().parents[1],args.output.resolve(),exports=args.exports)
    print(json.dumps({'independent_pipeline_max_code_error':report['independent_pipeline_max_code_error'],
        'scene43':report['scenes']['scene43']},indent=2))
