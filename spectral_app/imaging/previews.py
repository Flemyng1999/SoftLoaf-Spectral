"""The viewer uses the same bounded image path as original-size export."""
from spectral_lut.native import sibling_library
import copy
from .sources import ArraySource,MappedSource
from .rendering import ImageRenderer
from .pipeline import write_image
from .png_codec import PngLibrary

class ImagePreviews:
    def __init__(self,model,cache,budget):
        self.model=model;self.cache=cache;self.budget=budget
        self.library=PngLibrary(sibling_library(model.core.path,'softloaf_imageio')) if model.core else PngLibrary()
    def render(self,array,recipe=None,*,spectral=False,reference=None,input_ev=0,reference_processor=None):
        import numpy as np
        if array.ndim==2:array=array.reshape(1,*array.shape)
        source=MappedSource.from_array(array) if isinstance(array,np.memmap) and array.flags.c_contiguous else ArraySource(array)
        renderer=ImageRenderer(self.model,recipe,spectral=spectral,reference=reference,input_ev=input_ev,reference_processor=reference_processor)
        target=recipe['display'].get('target','sRGB') if recipe else 'sRGB'
        path=self.cache.staging_path()
        try:
            if hasattr(self.cache,'admit_write'):self.cache.admit_write(source.width*source.height*4)
            write_image(path,source,renderer,self.model.display_profile(target),budget=self.budget(),rounding='preview',
                library=self.library,compression=1,max_tile_pixels=renderer.max_tile_pixels)
            url=self.cache.adopt_png(path)
        finally:source.close();path.unlink(missing_ok=True)
        if getattr(self.model,'metal',None):self.model.metal.record_image_stats(renderer.stats)
        return {'kind':'image','width':source.width,'height':source.height,'data_url':url}
