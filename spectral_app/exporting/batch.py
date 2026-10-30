"""Sequential batch publication; each photo uses the bounded original-size exporter."""
import copy
from pathlib import Path
import uuid
import zipfile
import numpy as np
from experiments.gui_recipe_server import RecipeError,version,json_bytes
from experiments.hsi_raw_lut import sha
from ..imaging.pipeline import ImageCancelled

class BatchExporter:
    def __init__(self,model,items,exporter,downloads,conditions):
        self.model=model;self.photo_sources=items;self.exporter=exporter;self.downloads=downloads;self.conditions=conditions
    def export(self,request,progress=None,cancelled=None):
        """One frozen recipe; per-image input EV; sequential bounded-memory rendering."""
        recipe=copy.deepcopy(self.model.validate(request.get('recipe'),compute=True)['normalized_recipe'])
        specs=request.get('inputs')
        if not isinstance(specs,list) or not 1<=len(specs)<=512:
            raise RecipeError('invalid_input','请选择 1–512 张已导入的照片。')
        seen=set();inputs=[]
        for spec in specs:
            if not isinstance(spec,dict) or not isinstance(spec.get('id'),str) or spec['id'] not in self.photo_sources or spec['id'] in seen:
                raise RecipeError('invalid_input','批量导出需要不重复的已导入照片。')
            ev=spec.get('exposure_ev',0)
            if type(ev) not in (int,float) or not np.isfinite(ev) or not -4<=ev<=4:
                raise RecipeError('invalid_input','照片输入曝光范围为 −4 到 +4 EV。')
            seen.add(spec['id']);inputs.append({'id':spec['id'],'exposure_ev':ev})
        directory=self.model.output/'exports'/uuid.uuid4().hex;directory.mkdir(parents=True)
        frozen=version(recipe);images=[];errors=[]
        archive=directory/'photos.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
            for index,spec in enumerate(inputs):
                if cancelled and cancelled():break
                name=self.photo_sources[spec['id']]['name']
                try:
                    rendered=self.exporter.export({'recipe':recipe,'input':spec},cancelled=cancelled)
                    image_file=next(f for f in rendered['files'] if f['name']=='image.png')
                    png=self.downloads[image_file['url']][0]
                    stem=''.join(c if c.isalnum() or c in '-_ ' else '_' for c in Path(name).stem).strip()[:100] or 'photo'
                    filename=f'images/{index+1:04d}-{stem}.png'
                    bundle.write(png,filename)
                    images.append({'file':filename,'input':{**self.photo_sources[spec['id']],**spec},
                        'verification':rendered['verification'],'image_sha256':sha(png)})
                except ImageCancelled:break
                except (RecipeError,OSError) as error:
                    errors.append({'id':spec['id'],'name':name,'message':str(error) if isinstance(error,RecipeError) else '原照片不可读，请重新导入。'})
                if progress:progress(index+1)
            report={'schema':'softloaf.batch-export/1','frozen':frozen,'recipe':recipe,
                'conditions':self.conditions(recipe),'images':images,'errors':errors,'total':len(inputs)}
            bundle.writestr('recipe.json',json_bytes(recipe));bundle.writestr('manifest.json',json_bytes(report))
        with zipfile.ZipFile(archive) as check:
            if check.testzip() is not None:raise RecipeError('image_integrity','批量文件包读回校验失败。')
        response={'ok':bool(images),'frozen':frozen,'total':len(inputs),'succeeded':len(images),'failed':len(errors),'errors':errors,'files':[]}
        if not images:
            response['error']={'code':'batch_failed','message':'没有照片成功导出，请检查原始文件。'}
            return response
        url=f'/downloads/{directory.name}/photos.zip';digest=sha(archive)
        self.downloads[url]=(archive.resolve(),digest)
        response['files']=[{'name':'photos.zip','url':url,'sha256':digest,'bytes':archive.stat().st_size}]
        return response
