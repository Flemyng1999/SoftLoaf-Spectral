"""Bounded original-size export with frozen inputs and atomic publication."""
from spectral_lut.native import sibling_library
import copy
from pathlib import Path
import threading
import uuid
import zipfile
import numpy as np
from experiments.gui_recipe_server import RecipeError,version,json_bytes
from ..imaging.pipeline import write_image,ImageCancelled
from ..imaging.rendering import ImageRenderer
from ..imaging.png_codec import PngLibrary
from ..imaging.files import digest_file
from .. import __version__


class PhotoExporter:
    def __init__(self,model,output,sources,conditions,downloads,budget=lambda:64*1024**2):
        self.model=model;self.output=Path(output);self.sources=sources
        self.conditions=conditions;self.downloads=downloads;self.budget=budget;self.lock=threading.Lock()
        self.library=PngLibrary(sibling_library(model.core.path,'softloaf_imageio')) if model.core else PngLibrary()
    def export(self,request,cancelled=None,progress=None):
        try:self.sources.storage.validate()
        except RuntimeError as error:raise RecipeError('external_storage',str(error)) from None
        recipe=copy.deepcopy(self.model.validate(request.get('recipe'),compute=True)['normalized_recipe'])
        spec=copy.deepcopy(request.get('input'))
        if not isinstance(spec,dict) or spec.get('id') not in self.sources.items:raise RecipeError('invalid_image','请先导入照片。')
        ev=spec.get('exposure_ev',0)
        if type(ev) not in (int,float) or not np.isfinite(ev) or not -4<=ev<=4:raise RecipeError('invalid_input','输入曝光范围为 −4 到 +4 EV。')
        with self.lock:return self._render(recipe,spec,ev,cancelled,progress)
    def _render(self,recipe,spec,ev,cancelled,progress):
        if cancelled and cancelled():raise ImageCancelled()
        if hasattr(self.sources.raw_engine,'admit_write'):
            # Maximum admitted camera image; PNG plus ZIP staging, before development.
            self.sources.raw_engine.admit_write(64_000_000*8)
        source=self.sources.open(spec['id']);identifier=uuid.uuid4().hex
        parent=self.output/'exports';work=parent/('.working-'+identifier);work.mkdir(parents=True)
        final=parent/identifier;target=recipe['display'].get('target','sRGB');frozen=version(recipe)
        try:
            if hasattr(self.sources.raw_engine,'admit_write'):self.sources.raw_engine.admit_write(source.width*source.height*8)
            renderer=ImageRenderer(self.model,recipe,input_ev=ev)
            report=write_image(work/'image.png',source,renderer,self.model.display_profile(target),fingerprint=frozen['fingerprint'],
                budget=self.budget(),cancelled=cancelled,progress=progress,library=self.library,max_tile_pixels=renderer.max_tile_pixels)
            verification={**report,'encoding':f'8-bit {target} D65, embedded matching ICC','processing':'continuous spectral recipe at full resolution; no LUT interpolation','streaming':True}
            if getattr(self.model,'metal',None):verification['pixel_compute']={**self.model.metal.metadata(),**renderer.stats}
            metadata={'schema':'softloaf.image-export/2','application_version':__version__,'frozen':frozen,'recipe':recipe,
                'input':{**source.info,'exposure_ev':ev},'conditions':self.conditions(recipe),'verification':verification,'image_sha256':digest_file(work/'image.png')}
            (work/'image.json').write_bytes(json_bytes(metadata))
            with zipfile.ZipFile(work/'image.zip','w',zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(work/'image.png','image.png');bundle.write(work/'image.json','image.json')
            if cancelled and cancelled():raise ImageCancelled()
            with zipfile.ZipFile(work/'image.zip') as check:
                if check.testzip() is not None:raise ValueError('Export archive readback failed')
            hashes={name:digest_file(work/name) for name in ('image.png','image.json','image.zip')}
            work.rename(final)
            files=[]
            for name in ('image.png','image.json','image.zip'):
                path=final/name;url=f'/downloads/{identifier}/{name}';digest=hashes[name]
                self.downloads[url]=(path.resolve(),digest);files.append({'name':name,'url':url,'sha256':digest,'bytes':path.stat().st_size})
            return {'ok':True,'frozen':frozen,'verification':verification,'files':files}
        except ImageCancelled:raise
        except (ValueError,OSError) as error:raise RecipeError('image_integrity','图像分块导出未完成；未发布半成品。') from error
        finally:
            source.close()
            if work.exists():
                for name in ('image.png','image.json','image.zip'):
                    (work/name).unlink(missing_ok=True);(work/('._'+name)).unlink(missing_ok=True)
                try:work.rmdir()
                except OSError:pass
