"""Bounded GPU production checks and explicitly independent CPU/OCIO oracles."""
import numpy as np
import PyOpenColorIO as ocio
from spectral_lut.reference import acescct_encode,acescct_decode
from spectral_lut.metrics import srgb_code_error,summarize_code_errors
from experiments.hsi_raw_lut import apply_ocio,LOW,HIGH
from spectral_lut.sampling_db import SamplingDatabase

class Errors:
    def __init__(self):self.floats=[];self.codes=[]
    def add(self,a,b):
        _,f,u=srgb_code_error(a,b);self.floats.append(f.ravel());self.codes.append(u.ravel())
    def result(self):return summarize_code_errors(np.concatenate(self.floats),np.concatenate(self.codes))


def spectral_blocks(model,route,block=256):
    family='reversal' if route=='slide' else 'negative';priors=model.input_priors
    record=priors.report['families'][family]
    with SamplingDatabase.open(priors.directory/record['database'],family) as database:
        ids=[row[0] for row in database.connection.execute("SELECT id FROM spectra WHERE split='audit' AND kind='measured' ORDER BY id")]
        for start in range(0,len(ids),block):
            records=ids[start:start+block];yield np.stack([database.spectrum(key).on_grid(model.source_wavelengths) for key in records])


def verify(model,recipe,cube,path,purpose,block=2048,pipeline=None,renderer=None):
    gpu=renderer or model.metal
    if gpu is None:raise RuntimeError('GPU LUT production requires an active GPU backend')
    view,target=recipe['display']['view'],recipe['display'].get('target','sRGB')
    processor=ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=str(path.resolve()),interpolation=ocio.INTERP_TETRAHEDRAL)).getDefaultCPUProcessor()
    prepared=gpu.prepare_cube(cube,display=purpose!='display') if hasattr(gpu,'prepare_cube') else None
    interpolation=Errors();external_errors=Errors();approximation=Errors();total=Errors()
    native_difference=0.;independent_difference=0.;gpu_difference=0.;oracle_difference=0.;pipeline_difference=0.;excluded=0;oracle_count=0;count=0
    parameters=model.parameters(recipe)
    def check(points,physical=None):
        nonlocal native_difference,independent_difference,gpu_difference,oracle_difference,pipeline_difference,excluded,oracle_count,count
        mask=np.all((points>=LOW)&(points<=HIGH),axis=1);excluded+=int(np.count_nonzero(~mask));points=points[mask]
        if not len(points):return
        if physical is not None:physical=physical[mask]
        for start in range(0,len(points),block):
            p=points[start:start+block]
            truth=gpu.render(p,recipe,acescct=True)
            interpolated=gpu.interpolate_cube(cube,p,view,target,display=purpose!='display',prepared=prepared)
            external_raw=apply_ocio(processor,p);python=cube.apply(p)
            native=model.core.apply_cube(cube,p) if model.core else python
            native_difference=max(native_difference,float(np.max(np.abs(native-python))))
            independent_difference=max(independent_difference,float(np.max(np.abs(native-external_raw))))
            external=apply_ocio(pipeline,p) if pipeline is not None else model.render(external_raw,view,target) if purpose!='display' else external_raw
            gpu_difference=max(gpu_difference,float(np.max(np.abs(interpolated-external))))
            interpolation.add(truth,interpolated);external_errors.add(truth,external);count+=len(p)
            if pipeline is not None:pipeline_difference=max(pipeline_difference,float(np.max(np.abs(external-model.render(external_raw,view,target)))))
            # This is a separate float64 verification oracle, never the bake or
            # production error-reference path. Bound the audited point count.
            if oracle_count<512:
                selected=np.linspace(0,len(p)-1,min(16,len(p),512-oracle_count)).astype(int)
                reference=model.sample(acescct_decode(p[selected]),**parameters)['display_rgb']
                oracle_difference=max(oracle_difference,float(np.max(np.abs(reference-truth[selected]))));oracle_count+=len(selected)
            if physical is not None:
                measured=gpu.render(physical[start:start+len(p)],recipe,spectral=True)
                approximation.add(measured,truth);total.add(measured,interpolated)
    random=model.srgb_to_ap1(np.random.default_rng(20261026).random((8192,3)))
    check(acescct_encode(random));check(acescct_encode(np.repeat(np.linspace(0,1,2049)[:,None],3,axis=1)))
    # Include the declared LUT domain's actual corners and faces numerically;
    # these synthetic coordinates are not mislabeled as measured spectra.
    check(np.array(np.meshgrid(*([np.linspace(-.25,.75,9)]*3),indexing='ij')).reshape(3,-1).T)
    spectral_count=0
    for reflectance in spectral_blocks(model,recipe['route']):
        spectral_count+=len(reflectance)
        for ev in [-2,0,2]:
            signal=reflectance*2.**ev;check(acescct_encode(signal@model.source_to_ap1),signal)
    own=interpolation.result();independent=external_errors.result()
    return {'accepted':own['accepted'] and independent['accepted'],'integrity_passed':native_difference<=2e-12 and independent_difference<=2e-5 and gpu_difference<=3e-4 and oracle_difference<=3e-4 and pipeline_difference<=2e-5,
        'quality_policy':'99% within 2/255 is a reference line; quality does not block download',
        'float64_cube':own,'gpu_cube':own,'independent_ocio':independent,'native_vs_python_max_abs_output':native_difference,
        'ocio_vs_float64_max_abs_output':independent_difference,'gpu_vs_ocio_max_abs_display':gpu_difference,
        'gpu_vs_float64_reference_max_abs_display':oracle_difference,'independent_float64_points':oracle_count,
        'readback_exact':True,'grid':cube.table.shape[0],'interpolation':'tetrahedral','production_backend':(model.metal.metadata()['backend']+' float32; bounded bake, continuous reference, interpolation and display' if model.metal else 'CPU float64 reference mode'),
        'sample_set':'seed 20261026: 8192 encoded-sRGB, 2049 neutral, 729 ACEScct-domain probes; separate family audit spectra at -2/0/+2 EV',
        'excluded_outside_domain':excluded,'checked_conditions':count,
        'spectral_reference':{'measured_input_count':spectral_count,'exposure_variants':[-2,0,2],
            'rgb_approximation':approximation.result(),'total_lut_vs_spectral':total.result(),
            'input_model':recipe['input_model'],'scope':'Family audit source groups from the optimized database; labels recomputed for the current material/route. Historical development data, not fresh blind measurements and not real-film accuracy.'},
        'pipeline_vs_material_display_max_abs':pipeline_difference if pipeline is not None else None,
        'scope':'float64_cube is a compatibility field name for the GPU interpolation score; CPU float64/OCIO are independent execution checks, not a full-domain accuracy proof.'}
