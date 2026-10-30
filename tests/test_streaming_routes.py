"""Byte-identical tile boundaries, plus the independent float64 science oracle."""
import copy
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from experiments.gui_recipe_server import template
from spectral_app.imaging.pipeline import write_image
from spectral_app.imaging.sources import ArraySource,MappedSource
from spectral_app.imaging.rendering import ImageRenderer
from spectral_app.imaging.pixels import rgb8

@pytest.fixture(scope='module')
def model(tmp_path_factory):
    from spectral_app.model import SpectralModel
    from spectral_app.metal_renderer import MetalRenderer
    from spectral_lut.native import NativeCore
    root=Path.cwd();core=NativeCore();m=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path_factory.mktemp('stream-model'),core=core)
    m.metal=MetalRenderer(m);return m

@pytest.mark.parametrize('route',['slide','negative','print'])
@pytest.mark.parametrize('target',['sRGB','Display P3'])
def test_streamed_routes_equal_whole_renderer_and_float64(model,tmp_path,route,target):
    recipe=model.validate(template(route))['normalized_recipe'];recipe['display']['target']=target
    if route=='print':recipe['printing']=model.modern_printing(recipe)
    values=np.random.default_rng(72).uniform(-.02,1.5,(37,93,3));ev=.3
    whole=model.metal.render(values,recipe,input_ev=ev)
    reference=model.sample(values*2**ev,**model.parameters(recipe))['display_rgb']
    np.testing.assert_allclose(whole,reference,rtol=0,atol=3e-4)
    path=tmp_path/(route+'-'+target+'.png');renderer=ImageRenderer(model,recipe,input_ev=ev)
    result=write_image(path,ArraySource(values),renderer,model.display_profile(target),budget=32*1024,max_tile_pixels=79)
    with Image.open(path) as image:np.testing.assert_array_equal(np.asarray(image),rgb8(whole,'export'))
    assert result['blocks']>10 and result['max_region_pixels']<=79


def test_mapped_source_releases_regions_and_preserves_float_values(tmp_path):
    path=tmp_path/'source.bin';values=np.arange(71*103*3,dtype=np.float32).reshape(71,103,3)
    values.tofile(path);mapping=np.memmap(path,mode='r',dtype=np.float32,shape=values.shape)
    source=MappedSource.from_array(mapping);del mapping
    from spectral_app.imaging.blocks import Region
    with source.read(Region(63,19,11,7)) as region:np.testing.assert_array_equal(region,values[19:26,63:74])
    assert region.base._mmap.closed
