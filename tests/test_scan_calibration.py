"""Scan-domain checks use camera channels, never scene DCP or display RGB."""
from pathlib import Path
import numpy as np
import pytest


def test_scan_raw_preserves_linear_native_channels_and_retains_stage(tmp_path):
    from spectral_app.scanning.raw import RTScanRaw
    from spectral_app.rawtherapee import find_cli
    from experiments.hsi_raw_lut import write_synthetic_dng
    import tifffile
    native=np.broadcast_to([.08,.16,.32],(100,120,3)).copy()
    profile={'color':np.eye(3),'forward':np.eye(3),'copyright':'test',
             'table':np.broadcast_to([0,1,1],(1,2,2,3)).copy()}
    source=tmp_path/'known.dng'
    write_synthetic_dng(source,native,np.ones(3),profile,'Test','Synthetic')
    engine=RTScanRaw(find_cli(Path.cwd()),tmp_path/'retained')
    first=engine.develop(source)
    pixels=tifffile.memmap(first/'camera.tif',mode='r').astype(float)/65535
    # The fixture has four stops of linear coding headroom. Its DCP is irrelevant.
    np.testing.assert_allclose(np.median(pixels,(0,1)),native[0,0]/4,atol=5/65535)
    assert engine.develop(source)==first
    assert RTScanRaw(engine.executable,engine.cache).develop(source)==first
    assert len(list(engine.cache.glob('*/manifest.json')))==1
    (first/'camera.tif').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='retained'):
        engine.develop(source)


def test_nonnegative_combined_response_fits_independent_transmission_patches():
    from spectral_app.scanning.calibration import fit_response
    wave=np.linspace(400,750,71)
    rng=np.random.default_rng(177)
    # Independent non-film filters with known broad response; hold out real spectra.
    centres=np.array([450,540,650])
    weights=np.exp(-.5*((wave[:,None]-centres)/25)**2)
    weights/=weights.sum(0)
    spectra=np.exp(-rng.uniform(.1,3,(48,4))@np.array([
        np.exp(-.5*((wave-c)/40)**2) for c in [420,490,570,680]]))
    camera=spectra@weights
    fitted=fit_response(wave,spectra[:36],camera[:36],sigma=15,ridge=1e-6)
    assert np.min(fitted['weights'])>=0
    np.testing.assert_allclose(fitted['weights'].sum(0),1,atol=.01)
    assert np.max(np.abs(spectra[36:]@fitted['weights']-camera[36:]))<.007


def test_material_inverse_recovers_known_coefficients_and_marks_outside_domain():
    from spectral_app.scanning.inverse import MaterialInverse
    wave=np.arange(400,751,5.)
    dyes=np.column_stack([np.exp(-.5*((wave-c)/25)**2) for c in [640,540,450]])
    weights=np.column_stack([np.exp(-.5*((wave-c)/35)**2) for c in [620,530,450]])
    weights/=weights.sum(0)
    base=.1+wave*0
    inverse=MaterialInverse(dyes,base,weights,np.zeros(3),np.ones(3)*2)
    a=np.array([[.2,.5,1.2],[1.4,.1,.8],[.9,.9,.9]])
    camera=10**-(base+a@dyes.T)@weights
    recovered=inverse.solve(camera)
    np.testing.assert_allclose(recovered['amounts'],a,atol=1e-7)
    assert recovered['valid'].all()
    bad=inverse.solve([[2,2,2],[0,0,0]])
    assert not bad['valid'].any()
    assert np.isfinite(bad['amounts']).all()


def test_flatfield_extrapolates_only_with_declared_saturation_mask():
    from spectral_app.scanning.flatfield import fit_flatfield
    y,x=np.mgrid[-1:1:80j,-1:1:120j]
    true=np.exp(.1*x-.08*y-.4*x*x-.2*y*y)[...,None]*[.4,1.12,.7]
    measured=np.minimum(true,1)
    fit=fit_flatfield(measured)
    np.testing.assert_allclose(fit['field'],true,atol=1e-6)
    assert fit['clipped_fraction'][1]>.1
    assert fit['extrapolated_mask'][...,1].any()
    with pytest.raises(ValueError,match='unsaturated'):
        fit_flatfield(np.ones((30,40,3)))


def test_scan_preparation_uses_global_coordinates_and_retained_linear_pixels(tmp_path):
    from spectral_app.scanning.preparation import prepare_camera
    import tifffile
    # Constant native response in an analytically known varying field.
    y,x=np.mgrid[-1:1:40j,-1:1:60j]
    field=np.exp(.2*x+.1*y)
    source=tmp_path/'native.tif'
    tifffile.imwrite(source,np.uint16(np.rint(field[...,None]*[.1,.2,.3]*65535)),photometric='rgb')
    # terms are [1,y,x,y²,xy,x²].
    beta=np.zeros((6,3));beta[1]=.1;beta[2]=.2
    path=prepare_camera(source,tmp_path/'prepared.npy',beta,short_edge=100,rows=7)
    a=np.load(path,mmap_mode='r')
    assert a.shape==(40,60,3)  # Never upscale a smaller retained preview.
    np.testing.assert_allclose(a,np.broadcast_to([.1,.2,.3],a.shape),atol=2/65535)


def test_scan_positive_matches_independent_ocio_adx_and_aces2_output(tmp_path):
    from spectral_app.model import SpectralModel
    from spectral_app.scanning.rendering import amounts_to_display
    from spectral_lut.native import NativeCore
    from spectral_lut.negative import integrate_density
    import PyOpenColorIO as ocio
    root=Path.cwd()
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path/'model',core=NativeCore())
    material=model.negative
    amounts=np.array([[.1,.2,.3],[.6,.9,.7],[1.5,1.2,1.1]])
    t=10**-(material.base+amounts@material.dyes.T)
    apd=integrate_density(t,model.apd_weights)
    dmin=integrate_density(10**-material.base,model.apd_weights)
    encoded=((apd-dmin)*[1,.92,.95]*8000+1520).astype(np.float32)/65535
    graph=ocio.GroupTransform()
    graph.appendTransform(ocio.BuiltinTransform(style='ADX16_to_ACES2065-1'))
    graph.appendTransform(ocio.DisplayViewTransform(src='ACES2065-1',display='sRGB - Display',view='ACES 2.0 - SDR 100 nits (Rec.709)'))
    model.display_manager.config.getProcessor(graph).getDefaultCPUProcessor().applyRGB(encoded)
    np.testing.assert_allclose(amounts_to_display(model,material,amounts),np.clip(encoded,0,1),atol=4e-5)


def test_three_identical_camera_channels_do_not_establish_a_unique_material_state():
    from spectral_app.scanning.inverse import MaterialInverse
    wave=np.arange(400,751,5.)
    dyes=np.column_stack([np.exp(-.5*((wave-c)/25)**2) for c in [640,540,450]])
    weights=np.ones((len(wave),3))/len(wave)
    inverse=MaterialInverse(dyes,np.full(len(wave),.1),weights,np.zeros(3),np.ones(3)*2)
    solved=inverse.solve(inverse.forward([[.4,.6,.8]]))
    assert solved['max_log10_residual'][0]<1e-8
    assert not solved['valid'][0], 'An exact three-channel fit can still be underdetermined'
    assert solved['jacobian_condition'][0]>1e12
