"""Recompute a frozen, estimated scan calibration as a portable 65-cube.

This does not supply missing independently measured camera/lamp spectra. No RAW
development is performed. All numerical work and outputs stay on the data volume.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import numpy as np
import PyOpenColorIO as ocio
from spectral_app.storage import DataStorage
from spectral_app.model import SpectralModel
from spectral_app.scanning.inverse import MaterialInverse
from spectral_app.scanning.rendering import amounts_to_display
from spectral_app.scanning.export import export_scan_lut,material_density_domain
from spectral_lut.native import NativeCore
from spectral_lut.reference import Cube


def array_digest(values):
    return hashlib.sha256(np.asarray(values,dtype='<f8').tobytes()).hexdigest()


def retained_records(directory):
    return {str(p.relative_to(directory)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('manifest.json') if not p.name.startswith('._')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--view-ev',type=float,default=0)
    args=parser.parse_args()
    storage=DataStorage.configured();storage.validate();storage.activate_temporary_directory()
    if not storage.volume or not args.output.resolve().is_relative_to(storage.volume.resolve()):
        raise ValueError('Scan exports require the configured external data volume')
    if not np.isfinite(args.view_ev):raise ValueError('Viewing exposure must be finite')
    directory=args.calibration_dir;source=directory/'calibration.json'
    settings=json.loads(source.read_text());without_fingerprint=dict(settings)
    fingerprint=without_fingerprint.pop('fingerprint')
    if hashlib.sha256(json.dumps(without_fingerprint,sort_keys=True).encode()).hexdigest()!=fingerprint:
        raise ValueError('Frozen calibration fingerprint differs')
    arrays=np.load(directory/'calibration.npz');wave=arrays['wave'];weights=arrays['weights'];gain=arrays['gain']
    if (array_digest(weights)!=settings['effective_response_sha256']
            or array_digest(arrays['flat_coefficients'])!=settings['flat_coefficients_sha256']
            or not np.array_equal(gain,settings['base_alignment_gain'])
            or not np.array_equal(wave,np.arange(391,731.))):
        raise ValueError('Frozen response/flat/gain/band differs')
    retained=storage.root/'scanning/retained-raw';before=retained_records(retained)
    root=Path(__file__).resolve().parents[1];core=NativeCore()
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',
        root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',
        directory/'reference-runtime',core=core)
    material=model.negative
    for name,values in [('dyes',material.dyes),('base',material.base),('apd_weights',model.apd_weights)]:
        if array_digest(values)!=settings['material_arrays_sha256'][name]:
            raise ValueError('Frozen material/APD differs: '+name)
    if model.display_manager.config_metadata!=settings['display_config']:
        raise ValueError('Frozen ACES display configuration differs')
    dyes=np.column_stack([np.interp(wave,model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
    base=np.interp(wave,model.negative_wavelengths,material.base)
    inverse=MaterialInverse(dyes,base,weights*gain,material.amounts.min(0),material.amounts.max(0))
    low,high=material_density_domain(inverse)
    count=0;started=time.monotonic()
    def render(density):
        nonlocal count
        solved=inverse.solve(10**-density)
        output=amounts_to_display(model,material,solved['amounts'],exposure_ev=args.view_ev)
        count+=len(density)
        if count==len(density) or count//65536!=(count-len(density))//65536:
            print('Fresh float64 spectral inverse:',count,'/ 274625',flush=True)
        return output
    metadata={'status':'estimated-joint-response','camera':'Sony ILCE-7RM5 / A7R V',
        'material':'Kodak VISION3 250D 5207 / ECN-2 / Status M fitted material',
        'calibration_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'calibration_npz_sha256':hashlib.sha256((directory/'calibration.npz').read_bytes()).hexdigest(),
        'calibration_fingerprint':fingerprint,'view_exposure_ev':args.view_ev,
        'capture':settings['capture_metadata'],'raw_contract':settings['scan_development_records']['chart']['contract'],
        'response_band_nm':settings['response_band_nm'],'base_alignment_gain':gain.tolist(),
        'material_arrays_sha256':settings['material_arrays_sha256'],
        'display_config':settings['display_config'],'target_reference_sha256':settings['sources_sha256']['reference'],
        'target_nested_holdout_RMS_D':settings['nested_target_RMS_D'],
        'measured_camera_ssf':None,'measured_scan_illuminant_spd':None,
        'no_independent_real_negative_colour_ground_truth':True}
    result=export_scan_lut(args.output,render,metadata,size=65,domain_min=low,domain_max=high)
    if count!=65**3:raise ValueError('Not all 65-cube nodes were recomputed')
    output=Path(result['cube']).parent
    # Parse the published text independently; small 65-cube is 6.6 MB in float64.
    lines=Path(result['cube']).read_text().splitlines()
    first=next(i+1 for i,line in enumerate(lines) if line.startswith('DOMAIN_MAX'))
    nodes=np.loadtxt(result['cube'],skiprows=first)
    cube=Cube(nodes.reshape(65,65,65,3).transpose(2,1,0,3),low,high)
    processor=ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=result['clf'],
        interpolation=ocio.INTERP_TETRAHEDRAL))
    from spectral_app.metal_renderer import MetalRenderer
    metal=MetalRenderer(model);plan=metal.prepare_cube(cube,False)
    def lookup_checks(camera):
        density=-np.log10(np.maximum(camera,1e-12));solved=inverse.solve(camera)
        direct=amounts_to_display(model,material,solved['amounts'],exposure_ev=args.view_ev)
        reference=core.apply_cube(cube,density)
        gpu=metal.interpolate_cube(cube,density,'Display Encoding','sRGB',False,plan)
        actual=np.array(camera,dtype=np.float32)
        processor.getOptimizedCPUProcessor(ocio.OPTIMIZATION_LOSSLESS).applyRGB(actual)
        fast=np.array(camera,dtype=np.float32);processor.getDefaultCPUProcessor().applyRGB(fast)
        error=np.max(np.abs(reference-direct),axis=1)*255
        inside=np.all((density>=low)&(density<=high),axis=1)
        record={'count':len(camera),'valid_fraction':float(solved['valid'].mean()),
            'outside_LUT_domain_count':int(np.sum(~inside)),
            'all_LUT_vs_direct_codes_p50_p95_max':np.percentile(error,[50,95,100]).tolist(),
            'valid_LUT_vs_direct_codes_p50_p95_max':np.percentile(error[solved['valid']],[50,95,100]).tolist() if solved['valid'].any() else None,
            'valid_in_domain_LUT_vs_direct_codes_p50_p95_max':np.percentile(error[solved['valid']&inside],[50,95,100]).tolist() if np.any(solved['valid']&inside) else None,
            'OCIO_CLF_lossless_vs_float64_cube_max':float(np.max(np.abs(actual-reference))),
            'OCIO_CLF_default_vs_float64_cube_max':float(np.max(np.abs(fast-reference))),
            'Metal_vs_float64_cube_max':float(np.max(np.abs(gpu-reference)))}
        if (record['OCIO_CLF_lossless_vs_float64_cube_max']>3e-5
                or record['OCIO_CLF_default_vs_float64_cube_max']>.1/255
                or record['Metal_vs_float64_cube_max']>3e-5):
            raise ValueError('Published CLF/Metal differs from float64 file interpolation')
        return record
    rng=np.random.default_rng(652026)
    physical=lookup_checks(inverse.forward(rng.uniform(inverse.low,inverse.high,(4096,3))))
    real=[]
    for path in sorted(directory.glob('*-camera.npy')):
        if path.name.startswith('._'):continue
        pixels=np.load(path,mmap_mode='r');h,w=pixels.shape[:2]
        camera=np.array(pixels[int(.18*h):int(.84*h):max(1,int(.66*h)//12),
            int(.17*w):int(.82*w):max(1,int(.65*w)//16)]).reshape(-1,3).astype(float)
        pixels._mmap.close()
        real.append({'frame':path.stem.replace('-camera',''),**lookup_checks(camera)})
    if retained_records(retained)!=before:raise ValueError('RAW retention records changed during LUT export')
    audit={'fresh_nodes_evaluated_float64':count,'seconds':time.monotonic()-started,
        'published_cube_numeric_rows':len(nodes),'published_cube_min_max':[float(nodes.min()),float(nodes.max())],
        'physical_model_states':physical,'real_frames':real,'retained_RAW_records_unchanged':True,
        'retained_stage_count':len(before),'new_RAW_developments':0,
        'scope':'Interpolation and file implementation checks; not independent real-film colour accuracy',
        'bake_backend':'CPU float64 spectral inversion; Metal validates lookup application'}
    (output/'validation.json').write_text(json.dumps(audit,indent=2)+'\n')
    shutil.copyfile(root/'third_party/aces-v1.2/LICENSE.md',output/'Academy-ADX-LICENSE.md')
    for name in ('calibration.json','calibration.npz'):shutil.copyfile(directory/name,output/name)
    print(json.dumps({'cube':result['cube'],'clf':result['clf'],'seconds':audit['seconds'],
        'model_states':physical,'real_frame_count':len(real),'retained_stage_count':len(before)},indent=2),flush=True)


if __name__=='__main__':main()
