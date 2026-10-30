import numpy as np


def test_linear_srgb_display_flat_is_separate_from_native_camera_flat_and_matches_gpu(tmp_path):
    import tifffile
    from spectral_app.scanning.previews import fit_display_flat
    from spectral_app.scanning.fused import FusedScanSource
    from spectral_app.imaging.blocks import Region
    from spectral_lut.metal import MetalBackend
    from colour.models import eotf_inverse_sRGB
    h,w=97,131;y,x=np.mgrid[-1:1:complex(h),-1:1:complex(w)]
    illumination=np.exp(x[...,None]*[.15,-.08,.11]+y[...,None]*[.04,.09,-.02])
    flat=eotf_inverse_sRGB(illumination*[.3,.35,.4]).astype(np.float32)
    path=tmp_path/'RT-flat.tif';tifffile.imwrite(path,flat,photometric='rgb')
    coefficients=fit_display_flat([path])['coefficients']
    np.testing.assert_allclose(coefficients[0],0,atol=1e-12)
    photo=tmp_path/'RT-photo.tif';tifffile.imwrite(photo,eotf_inverse_sRGB(illumination*[.1,.2,.3]).astype(np.float32),photometric='rgb')
    for backend in (None,MetalBackend()):
        source=FusedScanSource(photo,np.zeros((6,3)),None,encoded_srgb=True,
            display_flat_coefficients=coefficients,backend=backend)
        with source.read(Region(10,10,80,60)) as actual:
            np.testing.assert_allclose(actual,np.broadcast_to(eotf_inverse_sRGB([.1,.2,.3]),actual.shape),atol=2e-5)
        source.close()
