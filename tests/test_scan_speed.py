from pathlib import Path
import numpy as np
import pytest


def test_resampled_source_preserves_global_filter_phase_for_partial_regions():
    from spectral_app.imaging.resample import ResampledSource,resize_rows
    from spectral_app.imaging.sources import ArraySource
    from spectral_app.imaging.blocks import Region
    rng=np.random.default_rng(512);pixels=rng.random((135,203,3),dtype=np.float32)
    size=(79,51);expected=np.empty((size[1],size[0],3),np.float32)
    resize_rows(pixels,size,lambda y,a:expected.__setitem__(slice(y,y+len(a)),a),rows=7)
    source=ResampledSource(ArraySource(pixels),size,budget=1024*1024)
    for region in (Region(0,0,79,11),Region(17,9,31,19),Region(5,43,74,8)):
        with source.read(region) as actual:
            np.testing.assert_array_equal(actual,expected[region.y:region.y+region.height,region.x:region.x+region.width])
    source.close()


def test_scan_preview_streams_without_pixel_temp_and_matches_old_pipeline(tmp_path,monkeypatch):
    import tifffile
    from PIL import Image,ImageCms
    from spectral_app.scanning.preparation import prepare_camera
    from spectral_app.scanning.imaging import preview_image
    from spectral_app.imaging.sources import MappedSource
    from spectral_app.imaging.pipeline import write_image
    rng=np.random.default_rng(875);pixels=rng.integers(4000,25000,(137,209,3),dtype=np.uint16)
    native=tmp_path/'native.tif';tifffile.imwrite(native,pixels,photometric='rgb')
    flat=np.zeros((6,3));flat[1]=[.04,-.02,.01];flat[2]=[-.03,.02,.05]
    profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    prepared=prepare_camera(native,tmp_path/'old.npy',flat,short_edge=69)
    a=np.load(prepared,mmap_mode='r');render=lambda v:np.sqrt(np.maximum(v,0))
    old=tmp_path/'old.png'
    try:write_image(old,MappedSource.from_array(a),render,profile,fingerprint='same')
    finally:a._mmap.close()
    def forbid(*args,**kwargs):raise AssertionError('preview created a full-frame pixel temporary')
    monkeypatch.setattr(np.lib.format,'open_memmap',forbid)
    new=tmp_path/'new.png';preview_image(native,new,flat,profile,renderer=render,short_edge=69,fingerprint='same')
    with Image.open(old) as expected,Image.open(new) as actual:np.testing.assert_array_equal(actual,expected)


def test_linear_scan_table_reuses_physical_inversion_for_exposure_and_detects_damage(tmp_path):
    from spectral_app.scanning.transform_cache import LinearScanTable
    calls=[];low=np.array([.2,.4,.6]);high=low+2
    def direct(x):calls.append(len(x));return np.exp(-x)
    table=LinearScanTable.create(tmp_path,'a'*64,5,low,high,direct)
    points=low+np.array([[1,2,3],[4,0,2]])*(high-low)/4
    np.testing.assert_allclose(table.nodes[[86,54]],np.exp(-points),rtol=1e-14)
    count=sum(calls)
    again=LinearScanTable.create(tmp_path,'a'*64,5,low,high,lambda x:pytest.fail('repeated physical inversion'))
    renderer=again.renderer(lambda linear:linear*4)
    from spectral_app.exporting.lut_files import grid_blocks
    actual=np.concatenate([renderer(points) for _,points in grid_blocks(5,low,high,17)])
    np.testing.assert_allclose(actual,np.asarray(again.nodes)*4)
    assert sum(calls)==count==125
    table.close();again.close()
    folder=tmp_path/('a'*64);path=folder/'aces.npy'
    with path.open('r+b') as f:f.seek(-8,2);f.write(b'\0'*8)
    with pytest.raises(ValueError,match='changed'):LinearScanTable.create(tmp_path,'a'*64,5,low,high,direct)


def test_scan_source_integrity_reuses_verified_hash_until_file_changes(tmp_path,monkeypatch):
    import hashlib,os
    import spectral_app.scanning.raw as raw
    source=tmp_path/'original.raw';source.write_bytes(b'original');expected=hashlib.sha256(b'original').hexdigest()
    engine=raw.RawFiles(Path('unused-engine'),tmp_path/'retained')
    calls=[];digest=raw.digest
    def track(path):calls.append(Path(path));return digest(path)
    monkeypatch.setattr(raw,'digest',track)
    assert engine.verify_source(source,expected)==expected
    assert engine.verify_source(source,expected)==expected and calls==[source]
    stamp=source.stat();source.write_bytes(b'changed!');os.utime(source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError,match='identity'):engine.verify_source(source,expected)
    assert calls==[source,source]
