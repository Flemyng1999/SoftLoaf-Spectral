"""Local measured-target experiment. Never changes the application's workspace.

The command requires explicit external input/output paths. Its float64 inverse
is an experimental oracle; baked lookup application can use existing Metal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
from PIL import Image,ImageDraw
import tifffile
from spectral_app.storage import DataStorage
from spectral_app.scanning.raw import RTScanRaw,digest
from spectral_app.rawtherapee import find_cli
from spectral_app.scanning.flatfield import fit_flatfield
from spectral_app.scanning.preparation import prepare_camera,patch_design
from spectral_app.scanning.calibration import select_response
from spectral_app.scanning.inverse import MaterialInverse
from spectral_app.scanning.rendering import amounts_to_display
from spectral_app.imaging.sources import MappedSource
from spectral_app.imaging.pipeline import write_image
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore
from spectral_lut.reference import Cube


def extract_patches(path,coefficients,layout):
    pixels=tifffile.memmap(path,mode='r');h,w=pixels.shape[:2];values=[];clipped=[]
    try:
        for point in layout['centres']:
            x,y=round(point[0]*w),round(point[1]*h);r=round(layout['half_height']*h)
            if x-r<0 or y-r<0 or x+r>w or y+r>h:raise ValueError('Chart ROI exceeds the sensor footprint')
            raw=np.asarray(pixels[y-r:y+r,x-r:x+r],float)/65535
            field=np.exp(patch_design(h,w,y-r,y+r,x-r,x+r)@coefficients)
            values.append(np.median(raw/field,(0,1)));clipped.append(np.mean(raw>=1,axis=(0,1)))
    finally:pixels._mmap.close()
    if np.max(clipped)>.001:raise ValueError('Transmission chart patches are clipped')
    return np.array(values),np.array(clipped)


def fixed_base(path,coefficients,roi):
    pixels=tifffile.memmap(path,mode='r');h,w=pixels.shape[:2]
    x0,y0,x1,y1=[int(v*s) for v,s in zip(roi,[w,h,w,h])]
    try:
        field=np.exp(patch_design(h,w,y0,y1,x0,x1)@coefficients)
        return np.median(np.asarray(pixels[y0:y1,x0:x1],float)/65535/field,(0,1))
    finally:pixels._mmap.close()


def bake(model,material,inverse,path,size=65):
    if path.exists():
        values=np.load(path)
        return {ev:Cube(values['ev'+str(ev)],np.zeros(3),np.ones(3)*4) for ev in (0,2)}
    output={ev:np.empty((size**3,3),np.float32) for ev in (0,2)}
    from spectral_app.exporting.lut_files import grid_blocks
    for start,points in grid_blocks(size,np.zeros(3),np.ones(3)*4,1024):
        amounts=inverse.solve(10**-points)['amounts']
        for ev in output:output[ev][start:start+len(points)]=amounts_to_display(model,material,amounts,exposure_ev=ev)
        if start%65536==0:print('bake',start,'/',size**3,flush=True)
    tables={ev:a.reshape(size,size,size,3).transpose(2,1,0,3).copy() for ev,a in output.items()}
    np.savez(path,**{'ev'+str(ev):a for ev,a in tables.items()})
    return {ev:Cube(a,np.zeros(3),np.ones(3)*4) for ev,a in tables.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir','chart','flat','reference','patch-map','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--backend',choices=['metal','cpu'],default='metal' if sys.platform=='darwin' else 'cpu')
    parser.add_argument('--frames',type=int,nargs='*');parser.add_argument('--short-edge',type=int,default=2048)
    args=parser.parse_args();storage=DataStorage.configured();storage.activate_temporary_directory();storage.validate()
    if not storage.volume or not args.output.resolve().is_relative_to(storage.volume.resolve()):raise ValueError('Scan outputs require the configured external volume')
    root=Path(__file__).resolve().parents[1];out=args.output;out.mkdir(exist_ok=True,parents=True)
    layout=json.loads(args.patch_map.read_text())
    if layout.get('raw_contract')!=RTScanRaw.contract:raise ValueError('Patch map must declare the current RT RAW contract and RT image coordinates')
    source_ids={name:digest(getattr(args,name)) for name in ('chart','flat','reference','patch_map')}
    engine=RTScanRaw(find_cli(root),storage.root/'scanning/rt-retained-raw')
    flat_dir=engine.develop(args.flat);flat=tifffile.memmap(flat_dir/'camera.tif',mode='r')
    small=np.asarray(flat[::8,::8],float)/65535;flat._mmap.close()
    field=fit_flatfield(small);alternate_field=fit_flatfield(small,degree=4)
    chart_dir=engine.develop(args.chart)
    camera,clipped=extract_patches(chart_dir/'camera.tif',field['coefficients'],layout)
    measured=np.loadtxt(args.reference);wave=np.arange(391,731.)
    if measured.shape!=(945,48) or not np.isfinite(measured).all() or np.any(np.diff(measured[:,0])<=0):raise ValueError('Unexpected target source grid')
    if not np.array_equal(measured[:,::2],np.repeat(measured[:,0,None],24,axis=1)):raise ValueError('Different target wavelength grids')
    if np.min(measured[:,1::2])<0 or np.max(measured[:,1::2])>1:raise ValueError('Expected fractional target transmittance')
    spectra=np.array([np.interp(wave,measured[:,0],measured[:,2*i+1]) for i in range(24)])
    response=select_response(wave,spectra,camera)
    print('nested held-out target RMS D',response['outer_RMS_log10'],flush=True)
    core=NativeCore();model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'reference-runtime',core=core);material=model.negative
    dyes=np.column_stack([np.interp(wave,model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
    base=np.interp(wave,model.negative_wavelengths,material.base)
    paths=sorted(p for p in args.input_dir.glob('*.ARW') if not p.name.startswith('._'))
    if not paths:raise ValueError('No scan RAW sources')
    fields=['Model','LensModel','ISO','ExposureTime','FNumber','WhiteBalance','ColorTemperature','ColorCompensationFilter']
    metadata=json.loads(subprocess.run(['exiftool','-j','-n']+['-'+f for f in fields]+[str(p) for p in [args.chart,args.flat,*paths]],capture_output=True,text=True,check=True).stdout)
    if any(any(row.get(f)!=metadata[0].get(f) for f in fields) for row in metadata):raise ValueError('Scan capture conditions differ from chart/flat metadata')
    # A physically inspected clear film-border ROI is frozen once for the roll.
    base_path=next((p for p in paths if p.name==layout['base_frame']),None)
    if base_path is None:raise ValueError('Frozen clear-border frame is missing')
    base_dir=engine.develop(base_path)
    measured_base=fixed_base(base_dir/'camera.tif',field['coefficients'],layout['base_roi'])
    model_base=10**-base@response['weights'];gain=measured_base/model_base
    weights=response['weights']*gain
    inverse=MaterialInverse(dyes,base,weights,material.amounts.min(0),material.amounts.max(0))
    kernel_digest=lambda a:hashlib.sha256(np.asarray(a,dtype='<f8').tobytes()).hexdigest()
    settings={'schema':'softloaf.scan-experiment/1','sources_sha256':source_ids,'model_material':material.metadata,
        'scan_development_records':{name:json.loads((folder/'manifest.json').read_text()) for name,folder in [('chart',chart_dir),('flat',flat_dir)]},
        'capture_metadata':{f:metadata[0].get(f) for f in fields},
        'effective_response_sha256':kernel_digest(response['weights']),'flat_coefficients_sha256':kernel_digest(field['coefficients']),
        'material_arrays_sha256':{name:kernel_digest(a) for name,a in [('dyes',material.dyes),('base',material.base),('apd_weights',model.apd_weights)]},
        'display_config':model.display_manager.config_metadata,
        'response_selection':response['candidates'],'nested_target_RMS_D':response['outer_RMS_log10'],
        'nested_target_max_D':response['outer_max_log10'],'response_band_nm':[391,730],
        'band_limit_assumption':'zero effective response outside 391..730; no measured lamp/SSF or IR rejection proof',
        'flat_clipped_channel_fraction':field['clipped_fraction'],'flat_unsaturated_holdout_ln_RMS':field['heldout_log_RMS'],
        'flat_degree4_difference_p95':np.percentile(np.abs(alternate_field['field']/field['field']-1),95,axis=(0,1)).tolist(),
        'measured_base_camera':measured_base.tolist(),'model_base_camera':model_base.tolist(),'base_alignment_gain':gain.tolist(),
        'base_scope':'one fixed clear-looking frame-border ROI; user has not independently measured same-roll unexposed Dmin',
        'base_roi':layout['base_roi'],'base_frame_sha256':digest(base_path),'dark_offset':0,
        'display':'APD -> continuous ADX16 -> ACES -> ACES 2.0 SDR 100 nits sRGB',
        'viewing_exposure_ev':[0,2],'per_image_adaptive_adjustments':False,'input_encoding':'camera RGB normalized by frozen spatial flat; density = -log10(camera RGB); not Status M/APD',
        'LUT_domain_camera_density':[0,4],'LUT_size':65,'private_data':'local-only; no redistribution grant inferred',
        'accuracy_limit':'No independent 5207 density, APD or scene-colour ground truth. Chart validation and solver residual do not prove negative accuracy.'}
    fingerprint=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
    settings['fingerprint']=fingerprint
    (out/'calibration.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2)+'\n')
    np.savez(out/'calibration.npz',wave=wave,weights=response['weights'],family=response['family'],gain=gain,
        flat_coefficients=field['coefficients'],camera=camera,spectra=spectra,outer_prediction=response['outer_prediction'])
    cubes=bake(model,material,inverse,out/('lookup-'+fingerprint[:16]+'.npz'))
    if args.backend=='metal':
        from spectral_app.metal_renderer import MetalRenderer
        metal=MetalRenderer(model);plans={ev:metal.prepare_cube(cube,False) for ev,cube in cubes.items()}
        def apply(ev,density):return metal.interpolate_cube(cubes[ev],density,'Display Encoding','sRGB',False,plans[ev])
    else:
        def apply(ev,density):return core.apply_cube(cubes[ev],density)
    records=[];thumbs=[]
    for index,path in enumerate(paths):
        number=int(path.stem.rsplit('_',1)[1])
        if args.frames and number not in args.frames:continue
        started=time.monotonic();folder=engine.develop(path)
        prepared=prepare_camera(folder/'camera.tif',out/(path.stem+'-camera.npy'),field['coefficients'],short_edge=args.short_edge)
        pixels=np.load(prepared,mmap_mode='r');h,w=pixels.shape[:2]
        roi=layout['picture_roi'];x0,y0,x1,y1=[int(v*s) for v,s in zip(roi,[w,h,w,h])]
        sy,sx=max(1,(y1-y0)//28),max(1,(x1-x0)//36)
        sample=np.array(pixels[y0:y1:sy,x0:x1:sx]).reshape(-1,3).astype(float)
        solved=inverse.solve(sample);density=-np.log10(np.maximum(sample,1e-12))
        direct=amounts_to_display(model,material,solved['amounts']);cpu=core.apply_cube(cubes[0],density);optimized=apply(0,density)
        if np.max(np.abs(cpu-optimized))>3e-5:raise ValueError('Metal lookup differs from independent float64 C++')
        checks={}
        for ev in cubes:
            target=out/(path.stem+f'-apd-aces2-view{ev:+d}.png')
            source=MappedSource.from_array(pixels)
            def render(block):return apply(ev,-np.log10(np.maximum(block,1e-12)))
            checks[str(ev)]=write_image(target,source,render,model.display_profile('sRGB'),fingerprint=fingerprint)
            if ev==2:
                with Image.open(target) as image:
                    crop=image.crop((x0,y0,x1,y1)).rotate(180);crop.thumbnail((360,240));thumbs.append((number,crop.copy()))
        records.append({'source_name':path.name,'source_sha256':digest(path),'number':number,
            'picture_sample_count':len(sample),'sample_inversion_fraction_below_0_01D':float(solved['valid'].mean()),
            'sample_at_material_bound_fraction':float(solved['at_bound'].mean()),
            'sample_jacobian_condition_p50_p95_max':np.percentile(solved['jacobian_condition'],[50,95,100]).tolist(),
            'sample_residual_D_p50_p95_max':np.percentile(solved['max_log10_residual'],[50,95,100]).tolist(),
            'sample_LUT_error_codes_p50_p95_max':np.percentile(np.max(np.abs(cpu-direct),axis=1)*255,[50,95,100]).tolist(),
            'Metal_vs_float64_cube_max':float(np.max(np.abs(cpu-optimized))),
            'image_verification':checks,'seconds':time.monotonic()-started})
        pixels._mmap.close();print(json.dumps(records[-1]),flush=True)
        (out/'frames.json').write_text(json.dumps(records,indent=2)+'\n')
    columns=4;rows=(len(thumbs)+columns-1)//columns
    sheet=Image.new('RGB',(columns*380,rows*280+45),'#202124');draw=ImageDraw.Draw(sheet)
    draw.text((12,10),'5207 / fixed roll calibration / APD + ACES 2.0 / +2 EV viewing / crops rotated 180 for inspection',fill='white')
    for i,(number,image) in enumerate(thumbs):
        x=(i%columns)*380+10;y=(i//columns)*280+45;draw.text((x,y),f'Frame {number:02}',fill='white');sheet.paste(image,(x,y+22))
    sheet.save(out/'contact-sheet.png',icc_profile=model.display_profile('sRGB'))
    print('completed',len(records),'frames; outputs:',out,flush=True)


if __name__=='__main__':main()
