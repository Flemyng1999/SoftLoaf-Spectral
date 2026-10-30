import numpy as np
import pytest


def test_rt_srgb_geometry_preview_never_reapplies_native_scale_or_gamma(tmp_path):
    import tifffile
    from spectral_app.scanning.fused import FusedScanSource
    from spectral_app.imaging.blocks import Region
    from spectral_lut.metal import MetalBackend
    pixels=np.broadcast_to(np.float32([.2,.4,.6]),(60,90,3)).copy()
    path=tmp_path/'rt-srgb.tif';tifffile.imwrite(path,pixels,photometric='rgb')
    for backend in (None,MetalBackend()):
        source=FusedScanSource(path,np.zeros((6,3)),None,encoded_srgb=True,backend=backend)
        with source.read(Region(20,10,30,20)) as actual:np.testing.assert_allclose(actual,pixels[10:30,20:50],atol=1e-6)
        source.close()


def test_combined_geometry_rotates_and_crops_directly_in_source_coordinates():
    from spectral_app.imaging.geometry import Geometry
    from spectral_app.imaging.blocks import Region
    g=Geometry({'rotation':1,'crop':[.25,0,.75,1]},120,80)
    assert g.size()==(40,120)
    coordinates=g.coordinates(Region(0,0,40,120),g.size())
    # Clockwise: output left/top maps to original left/bottom, after crop.
    np.testing.assert_allclose(coordinates[0,:2]+coordinates[0,2:4],[0,59],atol=1e-6)
    np.testing.assert_allclose(coordinates[-1,:2]+coordinates[-1,2:4],[119,20],atol=1e-6)
    with pytest.raises(ValueError):Geometry({'radial':[1,0,-1,0,0]},120,80)


def test_fused_scan_gpu_matches_float64_for_flat_geometry_and_lut(tmp_path):
    import tifffile
    from spectral_app.scanning.fused import FusedScanSource
    from spectral_app.imaging.blocks import Region
    from spectral_lut.reference import Cube
    from spectral_lut.metal import MetalBackend
    x=np.linspace(0,2,9);d=np.stack(np.meshgrid(x,x,x,indexing='ij'),-1)
    cube=Cube(np.exp(-d),np.zeros(3),np.ones(3)*2)
    rng=np.random.default_rng(891);pixels=rng.integers(3000,45000,(91,137,3),dtype=np.uint16)
    path=tmp_path/'native.tif';tifffile.imwrite(path,pixels,photometric='rgb')
    flat=np.zeros((6,3));flat[0]=[-.03,.04,.01];flat[1]=[.1,-.04,.03]
    settings={'rotation':3,'crop':[.1,.15,.9,.85],'radial':[1,0,.035,0,0],'zoom':1.04}
    cpu=FusedScanSource(path,flat,cube,geometry=settings,short_edge=53)
    gpu=FusedScanSource(path,flat,cube,geometry=settings,short_edge=53,backend=MetalBackend())
    r=Region(0,0,cpu.width,cpu.height)
    with cpu.read(r) as expected,gpu.read(r) as actual:
        np.testing.assert_allclose(actual,expected,rtol=2e-5,atol=3e-6)
    assert gpu.resampling_passes==1 and gpu.max_source_pixels<=262144
    cpu.close();gpu.close()


def test_fused_scan_identity_preserves_pixels_and_bounds_source_halo(tmp_path):
    import tifffile
    from spectral_app.scanning.fused import FusedScanSource
    from spectral_app.imaging.blocks import Region
    rng=np.random.default_rng(913);pixels=rng.integers(100,60000,(90,140,3),dtype=np.uint16)
    path=tmp_path/'native.tif';tifffile.imwrite(path,pixels,photometric='rgb')
    source=FusedScanSource(path,np.zeros((6,3)),None,geometry={},technical=False)
    with source.read(Region(7,13,31,29)) as result:
        np.testing.assert_allclose(result,pixels[13:42,7:38]/65535,atol=1e-7)
    source.close()


def test_spatial_flat_grid_and_invalid_support_match_gpu_reference(tmp_path):
    import tifffile
    from spectral_app.scanning.flat_assets import FlatCorrection
    from spectral_app.scanning.fused import FusedScanSource
    from spectral_app.imaging.blocks import Region
    from spectral_lut.metal import MetalBackend
    rng=np.random.default_rng(441);native=rng.integers(200,50000,(67,93,3),dtype=np.uint16)
    path=tmp_path/'grid-native.tif';tifffile.imwrite(path,native,photometric='rgb')
    flat=FlatCorrection(gain=rng.uniform(.8,1.4,(5,7,3)),confidence=rng.integers(0,2,(5,7)))
    settings={'rotation':1,'crop':[.1,.05,.9,.95],'radial':[1,0,.03,0,0],'zoom':1.04}
    cpu=FusedScanSource(path,flat,None,geometry=settings,short_edge=35)
    gpu=FusedScanSource(path,flat,None,geometry=settings,short_edge=35,backend=MetalBackend())
    region=Region(0,0,cpu.width,cpu.height)
    with cpu.read(region) as a,gpu.read(region) as b:np.testing.assert_allclose(b,a,atol=3e-6,rtol=2e-5)
    cpu.close();gpu.close()
