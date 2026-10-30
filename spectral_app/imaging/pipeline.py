"""Source → pointwise blocks → RGB8 rows → PNG → streaming readback."""
import hashlib
from pathlib import Path
import time
import numpy as np
from .blocks import BlockPlan
from .pixels import rgb8
from .png_codec import PngReader,PngWriter,PngLibrary


class ImageCancelled(Exception):pass


def write_image(path,source,render,profile,*,fingerprint='',budget=64*1024**2,rounding='export',cancelled=None,progress=None,library=None,compression=6,max_tile_pixels=65536):
    library=library or PngLibrary()
    path=Path(path);plan=BlockPlan(source.width,source.height,source.channels,source.itemsize,budget,max_tile_pixels)
    expected=hashlib.sha256();blocks=0;peak_region=0;peak_band=0;start=time.perf_counter()
    try:
        with PngWriter(path,(source.width,source.height),profile,fingerprint,compression,library) as writer:
            for windows in plan.bands():
                if cancelled and cancelled():raise ImageCancelled()
                band=np.empty((windows[0].height,source.width,3),dtype=np.uint8);peak_band=max(peak_band,band.nbytes)
                for window in windows:
                    if cancelled and cancelled():raise ImageCancelled()
                    with source.read(window) as values:
                        encoded=render(values);quantized=rgb8(encoded,rounding)
                        band[:,window.x:window.x+window.width]=quantized
                        peak_region=max(peak_region,window.width*window.height);blocks+=1
                        del values,encoded,quantized
                    time.sleep(0)  # Viewer work may enter between export regions.
                writer.write(band);expected.update(band)
                if progress:progress(windows[0].y+windows[0].height,source.height)
                del band
        actual=hashlib.sha256()
        with PngReader(path,library) as reader:
            if reader.size!=(source.width,source.height) or reader.icc!=profile or reader.fingerprint!=fingerprint:raise ValueError('PNG dimensions, profile or fingerprint differ on readback')
            while reader.remaining:
                if cancelled and cancelled():raise ImageCancelled()
                values=reader.read(min(plan.rows,reader.remaining));actual.update(values);del values
        if actual.digest()!=expected.digest():raise ValueError('PNG pixels differ on streaming readback')
        return {'readback_exact':True,'width':source.width,'height':source.height,'pixel_sha256':actual.hexdigest(),
            'blocks':blocks,'max_region_pixels':peak_region,'peak_rgb8_band_bytes':peak_band,
            'codec_sha256':library.sha256,'working_budget_bytes':budget,'decoder_bytes':source.decoder_bytes,'verification':'libpng rows, matching pixels/ICC/fingerprint',
            'wall_seconds':time.perf_counter()-start}
    except BaseException:
        path.unlink(missing_ok=True);raise
