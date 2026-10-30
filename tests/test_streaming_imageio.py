from pathlib import Path
import numpy as np
import pytest
from PIL import Image


def test_scanline_png_roundtrip_matches_independent_decoder_and_profile(tmp_path):
    from spectral_app.imaging.png_codec import PngWriter,PngReader
    from spectral_lut.display import rgb_profile
    pixels=np.arange(17*31*3,dtype=np.uint16).reshape(17,31,3).astype(np.uint8)
    profile=rgb_profile('sRGB');path=tmp_path/'分块 图像.png'
    with PngWriter(path,(31,17),profile,fingerprint='a'*64) as writer:
        for row in range(0,17,6):writer.write(pixels[row:row+6])
    with Image.open(path) as image:
        np.testing.assert_array_equal(np.asarray(image),pixels)
        assert image.info['icc_profile']==profile
        assert image.info['SoftLoaf recipe fingerprint']=='a'*64
    with PngReader(path) as reader:
        assert reader.size==(31,17) and reader.icc==profile and reader.fingerprint=='a'*64
        restored=np.concatenate([reader.read(min(5,17-row)) for row in range(0,17,5)])
    np.testing.assert_array_equal(restored,pixels)


def test_png_rejects_incomplete_rows_and_corrupt_output(tmp_path):
    from spectral_app.imaging.png_codec import PngWriter,PngReader
    from spectral_lut.display import rgb_profile
    path=tmp_path/'partial.png'
    with pytest.raises((ValueError,OSError)):
        with PngWriter(path,(8,9),rgb_profile('sRGB')) as writer:writer.write(np.zeros((2,8,3),dtype=np.uint8))
    with pytest.raises((ValueError,OSError)):
        with PngReader(path) as reader:
            while reader.remaining:reader.read(min(2,reader.remaining))


def test_block_planning_limits_pixels_and_extreme_row_memory():
    from spectral_app.imaging.blocks import BlockPlan
    plan=BlockPlan(200_000,3,channels=31,itemsize=8,budget=16*1024**2)
    assert plan.tile_pixels<65536
    windows=[window for band in plan.bands() for window in band]
    assert sum(w.width*w.height for w in windows)==600_000
    assert max(w.width*w.height for w in windows)<=plan.tile_pixels
    with pytest.raises(ValueError):BlockPlan(100_000_000,1,budget=16*1024**2)


def test_streaming_regions_match_full_quantization_without_seams(tmp_path):
    from spectral_app.imaging.sources import ArraySource
    from spectral_app.imaging.pipeline import write_image
    from spectral_lut.display import rgb_profile
    values=np.linspace(-.2,1.2,101*177*3).reshape(101,177,3)
    expected=np.floor(np.clip(values*.9+.03,0,1)*255+.5).astype(np.uint8)
    path=tmp_path/'stream.png'
    record=write_image(path,ArraySource(values),lambda x:x*.9+.03,rgb_profile('sRGB'),budget=128*1024)
    with Image.open(path) as image:np.testing.assert_array_equal(np.asarray(image),expected)
    assert record['readback_exact'] and record['blocks']>1
    assert record['max_region_pixels']<values.shape[0]*values.shape[1]


def test_cancelled_stream_is_not_published(tmp_path):
    from spectral_app.imaging.sources import ArraySource
    from spectral_app.imaging.pipeline import write_image,ImageCancelled
    from spectral_lut.display import rgb_profile
    path=tmp_path/'cancelled.png'
    with pytest.raises(ImageCancelled):write_image(path,ArraySource(np.zeros((20,31,3))),lambda x:x,rgb_profile('sRGB'),cancelled=lambda:True)
    assert not path.exists()

@pytest.mark.parametrize('method',['BOX','BILINEAR'])
@pytest.mark.parametrize('shape',[(137,211),(136,210)])
def test_float_resampling_bands_preserve_global_sampling_and_no_seams(tmp_path,method,shape):
    from spectral_app.imaging.resample import resize_rows
    values=np.random.default_rng(63).uniform(-.1,2,(*shape,3)).astype(np.float32);size=(83,57)
    expected=np.stack([np.asarray(Image.fromarray(values[...,c]).resize(size,getattr(Image.Resampling,method))) for c in range(3)],axis=-1)
    actual=np.empty_like(expected)
    resize_rows(values,size,lambda y,rows:actual.__setitem__(slice(y,y+len(rows)),rows),getattr(Image.Resampling,method),rows=7)
    np.testing.assert_allclose(actual,expected,rtol=0,atol=3e-7)
