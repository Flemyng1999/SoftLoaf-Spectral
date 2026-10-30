"""Portable scan CUBE and self-contained linear-input CLF; local experiment."""
import hashlib
import json
from pathlib import Path
import uuid
import itertools
import numpy as np
import PyOpenColorIO as ocio
from spectral_app.exporting.lut_files import write_cube,read_cube
from spectral_app.storage import DataStorage


def material_density_domain(inverse,*,margin=.05):
    """Bound each camera density over the frozen coefficient box.

    A density is minus log-sum-exp of affine dye densities and is concave.
    Its minimum is attained at a box vertex; its maximum is a convex minimization.
    A 0.05 D margin and outward 0.01 D rounding avoid exact-boundary sampling.
    """
    from scipy.optimize import minimize
    if not np.isfinite(margin) or margin<0:raise ValueError('Invalid density margin')
    corners=np.array(list(itertools.product(*zip(inverse.low,inverse.high))))
    low=(-np.log10(inverse.forward(corners))).min(0);high=[]
    for channel in range(3):
        def objective(a):
            t=10**-(inverse.base+a@inverse.dyes.T)
            weighted=t*inverse.weights[:,channel];signal=weighted.sum()
            return np.log10(signal),-(weighted@inverse.dyes)/signal
        fit=minimize(objective,(inverse.low+inverse.high)/2,jac=True,
            bounds=list(zip(inverse.low,inverse.high)),method='L-BFGS-B',
            options={'ftol':1e-14,'gtol':1e-10,'maxiter':1000})
        gradient=fit.jac.copy()
        gradient[((fit.x-inverse.low<1e-8)&(gradient>=0))|((inverse.high-fit.x<1e-8)&(gradient<=0))]=0
        if not fit.success or np.max(np.abs(gradient))>1e-6:
            raise ValueError('Density-domain extremum did not converge')
        high.append(-fit.fun)
    return np.floor((low-margin)*100)/100,np.ceil((np.array(high)+margin)*100)/100


def export_scan_lut(destination,render,metadata,*,size=65,domain_min=(0,0,0),domain_max=(4,4,4),node_render=None):
    """Bake pointwise camera density -> display RGB and its log-input wrapper.

    `render` accepts Nx3 camera-channel log densities, not Status M or APD.
    The caller owns the frozen physical model and its float64 reference.
    """
    if metadata.get('status')!='estimated-joint-response':
        raise ValueError('Independently measured camera and scan-light sources have not been supplied/reviewed')
    if not isinstance(size,int) or not 2<=size<=129:raise ValueError('Invalid CUBE size')
    low,high=np.asarray(domain_min,float),np.asarray(domain_max,float)
    if low.shape!=(3,) or high.shape!=(3,) or not np.isfinite([low,high]).all() or np.any(high<=low):
        raise ValueError('Invalid camera density domain')
    destination=Path(destination).resolve();storage=DataStorage.configured();storage.validate()
    if storage.volume and not destination.is_relative_to(storage.volume.resolve()):raise ValueError('Scan export must use the configured external volume')
    if destination.exists():raise ValueError('Scan export destination already exists')
    directory=destination.with_name(destination.name+'.working-'+uuid.uuid4().hex)
    directory.mkdir(parents=True)
    comments=['Software: SoftLoaf Spectral','Author: Yangming Feng',
        'Purpose: scan-negative-to-display; local experimental calibration',
        'Response: estimated-joint-response; not an independently measured camera SSF',
        'Input: dRGB = -log10(linear native camera RGB / frozen spatial flat); no DCP, WB, gamma',
        'Input is camera-channel density, NOT Status M, APD, sRGB or ACEScct',
        'Input domain per channel: '+str(low.tolist())+' to '+str(high.tolist()),
        'Flat-field correction is spatial and must happen BEFORE this LUT',
        'Output: standard encoded sRGB D65; includes APD / ADX and ACES 2.0 SDR 100 nits',
        'Camera: '+str(metadata.get('camera','unspecified')),
        'Material: '+str(metadata.get('material','unspecified')),
        'Calibration SHA256: '+str(metadata.get('calibration_sha256','unspecified')),
        'Viewing exposure EV: '+str(metadata.get('view_exposure_ev',0)),
        'Measured A7R V SSF: unavailable; measured scan-lamp SPD: unavailable',
        'Existing modeled material transmittance; finite-band scan response assumption 391..730 nm',
        'Private measurement / material source rights remain unresolved for redistribution']
    path=directory/f'scan-density-{size}.cube'
    nodes=write_cube(path,size,low,high,node_render or render,'SoftLoaf Spectral scan / estimated joint response',comments,block=1024)
    cube=read_cube(path,directory/'readback.nodes',nodes,expected_low=low,expected_high=high)
    # Independent OCIO file execution also verifies red-fast ordering and domain.
    rng=np.random.default_rng(659);probe=rng.uniform(low,high,(1024,3))
    expected=cube.apply(probe)
    direct=np.asarray(render(probe),float)
    if direct.shape!=expected.shape or not np.isfinite(direct).all():raise ValueError('Invalid direct scan validation')
    codes=np.max(np.abs(expected-direct),axis=1)*255
    interpolation={'samples':len(probe),'mean_codes':float(np.mean(codes)),
        'p95_codes':float(np.percentile(codes,95)),'max_codes':float(np.max(codes)),
        'method':'uniform camera-density domain / float64 direct model vs tetrahedral LUT; not real-film colour accuracy'}
    graph=ocio.GroupTransform()
    logarithm=ocio.LogAffineTransform(logSideSlope=[-1,-1,-1]);logarithm.setBase(10)
    graph.appendTransform(logarithm)
    graph.appendTransform(ocio.FileTransform(src=str(path),interpolation=ocio.INTERP_TETRAHEDRAL))
    group=ocio.Config.CreateRaw().getProcessor(graph).createGroupTransform()
    group.getFormatMetadata().setName('SoftLoaf Spectral / estimated scan / linear camera input')
    group.getFormatMetadata().addChildElement('Description','\n'.join(comments)+'\nCLF input: flat-corrected linear native camera RGB; the Log node computes dRGB internally.')
    clf=directory/f'scan-linear-{size}.clf';group.write('Academy/ASC Common LUT Format',str(clf))
    if '/Volumes/' in clf.read_text() or '/Users/' in clf.read_text():raise ValueError('CLF retained a private source path')
    processor=ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=str(clf),interpolation=ocio.INTERP_TETRAHEDRAL))
    # Default OCIO enables approximate log math. Check a lossless reference
    # separately so that fast-log error is not mistaken for a file/domain bug.
    maxima={}
    for label,cpu in [('lossless',processor.getOptimizedCPUProcessor(ocio.OPTIMIZATION_LOSSLESS)),
                      ('default',processor.getDefaultCPUProcessor())]:
        actual=np.asarray(10**-probe,dtype=np.float32);cpu.applyRGB(actual)
        maxima[label]=float(np.max(np.abs(expected-actual)))
    if maxima['lossless']>3e-5 or maxima['default']>.1/255:
        raise ValueError('Independent CLF execution differs from the CUBE: '+str(maxima))
    # Retain exact byte identities; intermediate mapped tables are disposable.
    for array in (cube.table,):
        while isinstance(getattr(array,'base',None),np.memmap):array=array.base
        if hasattr(array,'_mmap'):array._mmap.close()
    for name in (path.with_suffix('.nodes').name,'readback.nodes'):(directory/name).unlink()
    record={'schema':'softloaf.scan-lut/1','metadata':metadata,'grid':size,
        'cube_input':'camera-channel dRGB=-log10(flat-corrected linear native camera RGB)',
        'density_domain':[low.tolist(),high.tolist()],
        'linear_camera_domain':[(10**-high).tolist(),(10**-low).tolist()],
        'clf_input':'flat-corrected linear native camera RGB; per-channel mathematical domain recorded below',
        'outside_domain':'endpoint limiting by LUT; not proof of valid film recovery',
        'output':'encoded sRGB D65 / ACES 2.0 SDR 100 nits; no additional display transform',
        'all_nodes_readback_exact':True,'interpolation':interpolation,'independent_clf_lossless_max_abs':maxima['lossless'],
        'independent_clf_default_max_abs':maxima['default'],
        'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,clf)}}
    (directory/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    (directory/'README.txt').write_text('SoftLoaf Spectral — Yangming Feng\nEXPERIMENTAL: estimated combined scan response, not an independent A7R V spectral measurement.\n\n'
        f'scan-density-{size}.cube: input dRGB=-log10(flat-corrected native camera RGB); read DOMAIN_MIN / DOMAIN_MAX.\n'
        f'scan-linear-{size}.clf: includes the log operation; input is already flat-corrected LINEAR NATIVE CAMERA RGB, not display RGB or an ordinary DCP-developed photo.\n'
        'Both outputs include APD/ADX and ACES 2.0 display rendering to standard encoded sRGB. Do not apply another ODT.\n'
        'Apply the frozen spatial flat and RAW black/white scale with UNIT technical channel gains before the LUT. Film-border alignment gains are ALREADY baked in; do not apply them again. No RAW mosaic can be passed directly to these files.\n'
        'This is conditional on the frozen target, acquisition and material calibration. No independent real-negative colour accuracy is claimed. Local use only; source-rights review remains pending.\n')
    directory.replace(destination)
    return {'cube':str(destination/path.name),'clf':str(destination/clf.name),**record}
