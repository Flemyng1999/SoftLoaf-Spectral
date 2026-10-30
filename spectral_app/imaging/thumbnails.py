"""Small disposable thumbnails from encoded previews, never another RAW pass."""
import numpy as np
from PIL import Image
from .png_codec import PngReader
from .sources import ArraySource
from .pipeline import write_image


def thumbnail(source,destination,*,short_edge=80,budget=64*1024**2):
    with PngReader(source) as reader:
        width,height=reader.size;factor=min(1,short_edge/min(width,height));w=max(1,round(width*factor));h=max(1,round(height*factor))
        result=np.zeros((h,w,3),float);y=0
        while reader.remaining:
            rows=reader.read(min(32,reader.remaining));small=np.asarray(Image.fromarray(rows).resize((w,len(rows)),Image.Resampling.BOX),float)
            for i,row in enumerate(small):
                a=(y+i)*h/height;b=(y+i+1)*h/height
                for k in range(int(a),min(h,int(np.ceil(b)))):result[k]+=row*(min(b,k+1)-max(a,k))
            y+=len(rows)
        values=np.clip(np.rint(result),0,255).astype(np.uint8)
        return write_image(destination,ArraySource(values),lambda x:x/255,reader.icc,
            fingerprint=reader.fingerprint,budget=budget,compression=3)
