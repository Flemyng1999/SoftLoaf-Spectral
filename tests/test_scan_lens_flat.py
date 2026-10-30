import numpy as np
import pytest


def test_public_lensfun_profile_freezes_an_independently_checked_map():
    from spectral_app.imaging.lens_profiles import LensCatalog
    from spectral_app.imaging.geometry import Geometry
    catalog=LensCatalog()
    if not catalog.available:pytest.skip('Lensfun library/database unavailable')
    match=catalog.match({'Model':'ILCE-7RM5','LensModel':'105mm F2.8 DG DN MACRO | Art 020'})
    assert match['profile_id'] and match['crop_factor']==1
    frozen=catalog.resolve(match['profile_id'],105,1,1201,801)
    g=Geometry({'radial':frozen['radial']},1201,801)
    y,x=np.mgrid[50:760:65j,40:1160:71j];ours=np.stack(g.map(x,y,(1201,801)),-1)
    with catalog.oracle(match['profile_id'],105,1,1201,801) as oracle:
        reference=np.array([oracle(a,b) for a,b in zip(x.ravel(),y.ravel())]).reshape(ours.shape)
    assert np.max(np.abs(ours-reference))<.002
    assert frozen['source_sha256'] and frozen['residual_pixels']<.002
    with pytest.raises(ValueError,match='焦距'):catalog.resolve(match['profile_id'],50,1,1201,801)


def test_spatial_flat_preserves_channel_centre_and_refuses_clipped_centre():
    from spectral_app.scanning.flat_assets import build_flat,FlatCorrection
    y,x=np.mgrid[-1:1:240j,-1:1:360j];shade=np.exp(-.23*(x*x+y*y))
    native=shade[...,None]*[.15,.35,.25]
    field,report=build_flat([native])
    gain=field.evaluate(240,360,0,240,0,360)
    corrected=native*gain
    np.testing.assert_allclose(np.median(gain[108:132,162:198],axis=(0,1)),1,atol=.02)
    assert np.max(np.std(corrected,axis=(0,1))/np.mean(corrected,axis=(0,1)))<.02
    np.testing.assert_allclose(np.mean(corrected,axis=(0,1))/np.mean(corrected,axis=(0,1))[1],[.15/.35,1,.25/.35],atol=.003)
    assert np.min(field.gain)>=.25 and np.max(field.gain)<=4
    clipped=native.copy();clipped[80:160,100:260,1]=1
    with pytest.raises(ValueError,match='G'):build_flat([clipped])


def test_flat_invalid_support_blends_toward_identity_instead_of_valid_extrapolation():
    from spectral_app.scanning.flat_assets import FlatCorrection
    field=FlatCorrection(gain=np.full((3,4,3),2.),confidence=np.zeros((3,4)))
    np.testing.assert_array_equal(field.evaluate(90,120,0,90,0,120),np.ones((90,120,3)))
