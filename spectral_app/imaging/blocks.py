"""Byte-budget geometry for pointwise image operations; no implicit halo."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    x:int
    y:int
    width:int
    height:int


class BlockPlan:
    def __init__(self,width,height,channels=3,itemsize=4,budget=64*1024**2,max_tile_pixels=65536):
        if any(type(v)!=int or v<=0 for v in (width,height,channels,itemsize,budget,max_tile_pixels)):raise ValueError('Invalid image block plan')
        self.width=width;self.height=height;self.channels=channels;self.budget=budget
        # Reserve a row band and codec filtering separately from input, CPU/GPU
        # conversion, output and quantization buffers. Decoder memory is separate.
        if width*3>budget//8:raise ValueError('One image row exceeds the bounded codec budget')
        per_pixel=channels*(itemsize+8)+64
        self.tile_pixels=min(max_tile_pixels,max(1,(budget//2)//per_pixel))
        self.rows=min(64,max(1,self.tile_pixels//min(width,self.tile_pixels)),max(1,(budget//8)//(width*3)))
        self.columns=max(1,self.tile_pixels//self.rows)
    def bands(self):
        for y in range(0,self.height,self.rows):
            h=min(self.rows,self.height-y)
            yield [Region(x,y,min(self.columns,self.width-x),h) for x in range(0,self.width,self.columns)]
