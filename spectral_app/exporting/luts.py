"""Frozen GPU LUT production, streamed CUBE I/O and atomic publication."""
import copy
from datetime import datetime,timezone
from pathlib import Path
import shutil
import threading
import uuid
import zipfile
import numpy as np
import PyOpenColorIO as ocio
from experiments.gui_recipe_server import RecipeError,version,json_bytes
from experiments.hsi_raw_lut import LOW,HIGH,sha
from spectral_lut.export_metadata import lut_metadata
from .lut_files import write_cube,read_cube
from .lut_checks import verify
from .. import __version__

class LutExporter:
    def __init__(self,model,storage,conditions,downloads,cache_settings):
        self.model=model;self.storage=storage;self.conditions=conditions;self.downloads=downloads;self.cache_settings=cache_settings
    def export(self,recipe,purpose,size):
        self.storage.validate();self.model.input_priors.verify_sources()
        from .lut_reference import ReferenceRenderer
        renderer=self.model.metal or ReferenceRenderer(self.model)
        self.cache_settings.admit_write(size**3*128)
        frozen=version(recipe);conditions=self.conditions(recipe);export_id=uuid.uuid4().hex
        parent=self.storage.directory(self.model.output/'exports');directory=parent/('.working-'+export_id);directory.mkdir()
        final=parent/export_id;cube=None
        try:
            metadata=lut_metadata(recipe,frozen,purpose,conditions,__version__,datetime.now(timezone.utc).isoformat(timespec='seconds'))
            metadata['comments'].append('Input spectral prior: '+recipe['input_model']['id']+' / '+recipe['input_model']['family'])
            for key in ['model_sha256','database_sha256','selection_report_sha256']:
                if key in recipe['input_model']:metadata['comments'].append(key+': '+recipe['input_model'][key])
            metadata['comments'].append(('Bake: '+self.model.metal.metadata()['backend']+' float32' if self.model.metal else 'Bake: CPU float64 reference, float32 serialized nodes')+', streamed blocks; CUBE decimal nodes round-trip exactly to float32')
            metadata['comments'].append('Sampling sources: Manchester hyperspectral scenes; Colour ColorChecker reflectances; Wolf Faust IT8 Set14-5; original source-specific rights remain pending')
            block=min(8192,max(256,self.cache_settings.limits['working_bytes']//8192));gpu=renderer
            path=directory/'recipe.cube'
            mapped=write_cube(path,size,LOW,HIGH,lambda p:gpu.render(p,recipe,acescct=True,purpose='display' if purpose=='display' else 'XYZ'),metadata['title'],metadata['comments'],block)
            cube=read_cube(path,directory/'readback.nodes',mapped,block,expected_low=LOW,expected_high=HIGH)
            pipeline=None
            if purpose=='pipeline':pipeline=self._pipeline(directory,recipe,path,metadata,conditions,frozen)
            verification=verify(self.model,recipe,cube,path,purpose,block=min(2048,block),pipeline=pipeline,renderer=renderer)
            self.model.input_priors.verify_sources()
            verification['streaming']={'grid_points':size**3,'bake_block_points':block,'host_table':'mapped float32; no full coordinate mesh or Python row list',
                'working_budget_bytes':self.cache_settings.limits['working_bytes'],'max_node_table_bytes':size**3*3*4}
            manifest={'schema':'softloaf.lut-manifest/2','export_id':export_id,'frozen':frozen,'application':metadata['application'],
                'created_utc':metadata['created_utc'],'purpose':purpose,'recipe':recipe,'conditions':conditions,'input_model':recipe['input_model'],
                'input':{'space':'ACEScct','primaries':'AP1','white':'D60','domain_min':LOW.tolist(),'domain_max':HIGH.tolist()},
                'output':{'space':recipe['display'].get('target','sRGB') if purpose!='internal' else 'relative XYZ','white':'D65','includes_display':purpose in ('display','pipeline'),'format':'CTF complete graph' if purpose=='pipeline' else 'CUBE','cube_role':'material ACEScct to relative XYZ D65' if purpose!='display' else 'display encoded RGB D65'},'verification':verification,'cube_sha256':sha(path)}
            names=self._licenses(directory,recipe,purpose,conditions,metadata,manifest)
            (directory/'recipe.json').write_bytes(json_bytes(recipe));(directory/'manifest.json').write_bytes(json_bytes(manifest))
            if not verification['integrity_passed']:
                return {'ok':False,'frozen':frozen,'verification':verification,'files':[],
                    'error':{'code':'integrity_failed','message':'GPU、float64 或独立文件执行校验未通过，未发布 LUT。'}}
            with zipfile.ZipFile(directory/'recipe.zip','w',zipfile.ZIP_DEFLATED) as package:
                for name in names:package.write(directory/name,name)
            with zipfile.ZipFile(directory/'recipe.zip') as check:
                if check.testzip() is not None:raise ValueError('LUT archive CRC differs')
            hashes={name:sha(directory/name) for name in names+['recipe.zip']}
            self._unmap(cube);cube=None
            mapped.unlink();(directory/'readback.nodes').unlink();directory.rename(final)
            files=[]
            for name,digest in hashes.items():
                url=f'/downloads/{export_id}/{name}';file=final/name;self.downloads[url]=(file.resolve(),digest)
                files.append({'name':name,'url':url,'sha256':digest,'size':file.stat().st_size})
            warnings=[] if verification['accepted'] else [{'code':'quality_reference_missed','message':'本次抽样误差超过参考线，可结合误差与体积选择 LUT 规模。'}]
            return {'ok':True,'export_id':export_id,'frozen':frozen,'verification':verification,'warnings':warnings,'files':files}
        finally:
            if cube is not None:self._unmap(cube)
            # This UUID working directory was created by this export, never a
            # user-selected location or a retained RAW/spectral source folder.
            if directory.exists():
                for name in ['recipe.cube','recipe.nodes','readback.nodes','recipe.ctf','recipe.json','manifest.json','recipe.zip','ACES-LICENSE.md','OpenDRT-LICENSE.md','SPEKTRAFILM_LICENSE.txt','CHANGELOG.txt']:
                    (directory/name).unlink(missing_ok=True);(directory/('._'+name)).unlink(missing_ok=True)
                try:directory.rmdir()
                except OSError:pass
    @staticmethod
    def _unmap(cube):
        array=cube.table
        while isinstance(getattr(array,'base',None),np.memmap):array=array.base
        if hasattr(array,'_mmap'):array._mmap.close()
    def _pipeline(self,directory,recipe,path,metadata,conditions,frozen):
        graph=ocio.GroupTransform();graph.appendTransform(ocio.FileTransform(src=str(path.resolve()),interpolation=ocio.INTERP_TETRAHEDRAL))
        graph.appendTransform(self.model.display_group(recipe['display']['view'],recipe['display'].get('target','sRGB')))
        graph.appendTransform(ocio.RangeTransform(minInValue=0,minOutValue=0,maxInValue=1,maxOutValue=1))
        resolved=self.model.config.getProcessor(graph).createGroupTransform();resolved.getFormatMetadata().setName(metadata['title'])
        display=lut_metadata(recipe,frozen,'display',conditions,__version__,metadata['created_utc'])
        resolved.getFormatMetadata().addChildElement('Description','Container: CTF complete material and display graph\n'+'\n'.join(display['comments']))
        output=directory/'recipe.ctf';resolved.write('Color Transform Format',str(output.resolve()))
        return ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=str(output.resolve()))).getDefaultCPUProcessor()
    def _licenses(self,directory,recipe,purpose,conditions,metadata,manifest):
        root=Path(__file__).resolve().parents[2];names=['recipe.cube','recipe.json','manifest.json']
        if recipe['route']=='negative':
            (directory/'ACES-LICENSE.md').write_bytes((root/'third_party/aces-v1.2/LICENSE.md').read_bytes());names.append('ACES-LICENSE.md')
        if purpose=='pipeline':
            names.append('recipe.ctf');manifest['ctf_sha256']=sha(directory/'recipe.ctf')
            if recipe['display']['view'] in ('Default','Colorful','Umbra'):
                (directory/'OpenDRT-LICENSE.md').write_bytes(self.model.opendrt_license);names.append('OpenDRT-LICENSE.md')
        upstream=bool(conditions.get('optical_sources')) or bool(conditions.get('material',{}).get('provenance',{}).get('sources',{}).get('processed_sensitivity'))
        if upstream:
            source=root/'local/reference-assets/spektrafilm/SPEKTRAFILM_LICENSE.txt'
            if not source.is_file():raise RecipeError('missing_license','缺少上游资料许可，未发布 LUT。')
            (directory/source.name).write_bytes(source.read_bytes());names.extend([source.name,'CHANGELOG.txt'])
            (directory/'CHANGELOG.txt').write_text('SoftLoaf Spectral derived local export\nAuthor: Yangming Feng and contributors\nOriginal profile author: Andrea Volpato / spektrafilm\nChanges and sources:\n'+'\n'.join(metadata['comments'])+'\n')
            manifest['spektrafilm']={'author':'Andrea Volpato','repository':'https://github.com/andreavolpato/spektrafilm','profile_license':'CC BY-SA 4.0','license_sha256':sha(source),'changes':'CHANGELOG.txt'}
        return names
