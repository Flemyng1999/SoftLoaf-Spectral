"""Independent quantities and cross-implementation checks for APD/ADX."""
import numpy as np
import pytest
import PyOpenColorIO as ocio
from spectral_lut.negative import integrate_density, adx_codes, adx_to_aces


def test_density_is_log_after_weighted_transmission_and_preserves_base():
    w=np.array([[1.,0,1],[1,1,0],[0,1,1]])
    t=np.array([1,.1,.01])
    np.testing.assert_allclose(integrate_density(t,w),-np.log10([.55,.055,.505]),atol=1e-15)
    np.testing.assert_allclose(integrate_density(np.full(3,.01),w),[2]*3,atol=1e-15)
    with pytest.raises(ValueError):integrate_density(np.array([1,-.1,0]),w)


def test_adx_scaling_dmin_gains_and_continuous_footroom():
    base=np.array([.2,.6,.9])
    np.testing.assert_allclose(adx_codes(base,base),[1520]*3)
    np.testing.assert_allclose(adx_codes(base+1,base),[9520,8880,9120])
    np.testing.assert_allclose(adx_codes(base-0.1,base),[720,784,760])
    np.testing.assert_allclose(adx_codes(base+1,base,bits=10),[595,555,570])
    x=base+np.array([.5/8000,0,0]);assert adx_codes(x,base,quantize=True)[0]==1521


def test_float64_ctl_reproduction_matches_independent_ocio_builtin():
    # Cross-channel and below-toe points catch matrix orientation and branch errors.
    codes=np.vstack([np.array([[1520,1520,1520],[7120,7120,7120],[0,1000,1500],[7000,9000,12000]]),np.random.default_rng(7).uniform(0,26000,(200,3))])
    expected=codes.astype(np.float32)/65535
    processor=ocio.Config.CreateRaw().getProcessor(ocio.BuiltinTransform(style='ADX16_to_ACES2065-1')).getDefaultCPUProcessor()
    processor.applyRGB(expected)
    np.testing.assert_allclose(adx_to_aces(codes),expected,rtol=8e-5,atol=2e-7)


def test_native_generic_stage_keeps_base_exposure_sign_and_matches_reference():
    from spectral_lut.native import NativeCore
    core=NativeCore()
    spectra=np.array([[.1,.2,.3,.4],[.2,.4,.6,.8]])
    kernel=np.array([[1,0,0],[0,1,0],[0,0,1],[.5,.5,.5]])
    axis=np.array([-4.,0.,4.]);amounts=np.repeat(np.array([[0.],[1.],[2.]]),3,1)
    dyes=np.array([[1,0,0],[.1,.7,.2],[0,0,1.]])
    base=np.array([.2,.4,.6])
    h,a,t=core.spectral_stage(spectra,kernel,axis,amounts,dyes,base,0,1)
    expected_h=spectra@kernel*2
    expected_a=np.stack([np.interp(np.log10(expected_h[:,c]),axis,amounts[:,c]) for c in range(3)],-1)
    np.testing.assert_allclose(h,expected_h,atol=2e-15)
    np.testing.assert_allclose(a,expected_a,atol=2e-15)
    np.testing.assert_allclose(t,10**-(base+expected_a@dyes.T),atol=2e-15)
