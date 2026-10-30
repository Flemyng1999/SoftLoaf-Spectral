"""Resolve immutable library items without putting camera or UI logic in codecs."""
import copy
from .sources import MappedSource,RasterSource
from experiments.gui_recipe_server import RecipeError


class PhotoSourceProvider:
    def __init__(self,items,import_directory,raw_engine,storage,decode_rgb,to_ap1):
        self.items=items;self.import_directory=import_directory;self.raw_engine=raw_engine
        self.storage=storage;self.decode_rgb=decode_rgb;self.to_ap1=to_ap1
    def open(self,identifier):
        if identifier not in self.items:raise RecipeError('invalid_image','请先导入照片。')
        info=copy.deepcopy(self.items[identifier]);path=self.import_directory/(identifier+'.source')
        if info['kind']=='imported_raw_photo':path=self.storage.file(path)
        if self.raw_engine.files.digest(path)!=info['sha256']:raise RecipeError('changed_input','原照片已变化，请重新导入。')
        if info['kind']=='imported_raw_photo':
            values=self.raw_engine.develop(path,source_name=info['name'],routes=('ap1',),priority='background')['ap1']
            source=MappedSource.from_array(values);del values
        else:
            image,_=self.decode_rgb(path.read_bytes());source=RasterSource(image,self.to_ap1)
        source.info=info;return source
