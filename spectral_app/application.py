"""Application operations on the shared recipe workbench and native core."""
import base64
import binascii
import copy
from .file_lock import acquire_file_lock
import hashlib
import io
import json
import re
from pathlib import Path
import threading
import uuid
import tempfile

import numpy as np
import colour
import PyOpenColorIO as ocio
from PIL import Image, ImageCms, ImageOps

from experiments.gui_recipe_server import Workbench, RecipeError, json_bytes, version, png_preview
from experiments.hsi_raw_lut import AP1, D60, D65, apply_ocio, cat, sha, color_kernel, csv, interpolate
from . import __version__
from .pipeline_routes import PipelineRoutes
from .photo_cache import PreviewStore
from .rendition_cache import RenditionCache
from .preview_codec import interactive_encoding
from .storage import DataStorage
from .runtime_paths import state_path,packaged
from .preview_policy import PREVIEW_SHORT_EDGE,PREVIEW_SCHEMA,preview_size
from .rawtherapee import RawTherapee, DecodeGate, RAW_EXTENSIONS, lut_input
from .photo_jobs import PhotoJobs
from .compute_policy import retry_cpu
from .film_lighting import bind_reference_scene, reference_scene
from spectral_lut.native import sibling_library

MAX_IMAGE_BYTES = 16*1024*1024
MAX_PIXELS = 12_000_000
MAX_RAW_BYTES = 256*1024*1024


class Application(PipelineRoutes, Workbench):
    def __init__(self, model):
        from .preferences import Preferences
        self.preferences=Preferences(state_path('local/ui-settings.json'))
        self.workspace_directory=state_path('workspace') if packaged() else model.output
        self.workspace_directory.mkdir(parents=True,exist_ok=True)
        self.storage=DataStorage.configured()
        self.storage.validate()
        super().__init__(model)
        self.import_lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.session_revision, self.session = 0, None
        self.session_warning = None
        self.session_notice = None
        self.photo_sources = {}
        # Colorimetric original-scene reference. No film or OpenDRT operation.
        transform = ocio.BuiltinTransform(style='DISPLAY - CIE-XYZ-D65_to_sRGB')
        self.reference_processor = model.config.getProcessor(transform).getDefaultCPUProcessor()
        self._install_colour_chart()
        self.srgb_profile = self.model.display_profile('sRGB')
        preview_directory=self.storage.directory(self.model.output/'preview-cache')
        self.storage.directory(self.model.output/'exports')
        self.model.inputs=PreviewStore({k:v for k,v in self.model.inputs.items() if not k.startswith('user_')},preview_directory)
        self.render_gate=DecodeGate()
        self.renditions=RenditionCache(self.storage.directory(self.model.output/'rendition-cache'))
        code_root=Path(__file__).resolve().parents[1]
        implementation={name:sha(Path(__file__).parent/name) for name in
            ['application.py','pipeline_routes.py','model.py','metal_renderer.py','preview_codec.py','rendition_cache.py','imaging/pipeline.py','imaging/rendering.py','imaging/previews.py','imaging/pixels.py','imaging/png_codec.py']}
        implementation['workbench']=sha(code_root/'experiments/gui_recipe_server.py')
        implementation['reference']=sha(code_root/'experiments/hsi_raw_lut.py')
        self.rendition_identity=hashlib.sha256(json.dumps({
            'schema':1,'sources':self.model.source_refs,'implementation':implementation,
            'colour_version':colour.__version__,'numpy_version':np.__version__,'ocio_version':ocio.__version__,
            'core':sha(self.model.core.path) if self.model.core else None,
            'image_codec':sha(sibling_library(self.model.core.path,'softloaf_imageio')) if self.model.core else None,
            'renderer':self.model.metal.metadata() if getattr(self.model,'metal',None) else {'cpu':'float64'}
        },sort_keys=True).encode()).hexdigest()
        self.raw_engine=RawTherapee(Path(__file__).resolve().parents[1],self.model.output/'raw-cache')
        from .cache_settings import CacheSettings
        from .imaging.previews import ImagePreviews
        self.cache_settings=CacheSettings(self.model.output,self.storage,self.renditions,self.model.inputs,self.raw_engine.cache)
        self.raw_engine.admit_write=self.cache_settings.admit_write
        self.image_previews=ImagePreviews(model,self.renditions,lambda:self.cache_settings.limits['working_bytes'])
        self.raw_references={}
        self.pending_preview_upgrades={}
        self.pending_preview_checks={}
        self.preview_check_lock=threading.RLock()
        self.photo_jobs=PhotoJobs(self.export_images)
        self.input_thumbnails = {}
        self.import_directory = self.model.output/'inputs'
        self.import_directory.mkdir(parents=True, exist_ok=True)
        from .imaging.photo_sources import PhotoSourceProvider
        from .exporting.photos import PhotoExporter
        sources=PhotoSourceProvider(self.photo_sources,self.import_directory,self.raw_engine,self.storage,self._decode,self.model.srgb_to_ap1)
        self.photo_exporter=PhotoExporter(self.model,self.model.output,sources,self.conditions,self.downloads,budget=lambda:self.cache_settings.limits['working_bytes'])

        from .exporting.batch import BatchExporter
        self.batch_exporter=BatchExporter(model,self.photo_sources,self.photo_exporter,self.downloads,self.conditions)
        from .exporting.luts import LutExporter
        self.lut_exporter=LutExporter(model,self.storage,self.conditions,self.downloads,self.cache_settings)
        self.scans=None
        if getattr(model,'negative',None) is not None:
            from .scanning.service import ScanService
            self.scans=ScanService(model,self.storage,self.renditions,self.cache_settings.admit_write,
                budget=lambda:self.cache_settings.limits['working_bytes'])

        for path in sorted(self.import_directory.glob('*.json')):
            try:
                item = json.loads(path.read_text())
                identifier = item['id']
                source = self.storage.file(self.import_directory/(identifier+'.source')) if item.get('kind')=='imported_raw_photo' else self.import_directory/(identifier+'.source')
                if (identifier != 'user_'+item['sha256'] or path.stem != identifier or
                        len(item['sha256']) != 64 or not all(c in '0123456789abcdef' for c in item['sha256'])):
                    continue
                if source.stat().st_size > MAX_RAW_BYTES or (item.get('kind')!='imported_raw_photo' and sha(source) != item['sha256']):
                    continue
                # Decode and revalidate rather than trusting persisted dimensions / ICC.
                if not self._restore_preview(item,allow_legacy=True):
                    restored=self._register(source.read_bytes(), item['name'], item['sha256'])
                    self._save_photo_metadata(restored)
            except (OSError, KeyError, TypeError, ValueError):
                continue
        session_path = self.workspace_directory/'workspace.json'
        if session_path.is_file():
            try:
                saved = json.loads(session_path.read_text())
                self.session = self._validated_session(saved['session'])
                if any(old.get('recipe',{}).get('display',{}).get('view')!=new['recipe']['display']['view']
                        for old,new in zip(saved['session']['documents'],self.session['documents'])):
                    self.session_notice='已更新旧默认显示：反转片与相纸用色度转换，APD 用 ACES 2.0；曝光与材料设置保留。'
                if any(old.get('recipe',{}).get('input_model')!=new['recipe'].get('input_model') for old,new in zip(saved['session']['documents'],self.session['documents'])):
                    self.session_notice='已直接升级优化采样：反转片与负片分别使用已选模型。'
                if any(old.get('recipe',{}).get('asset_refs',{}).get('model') in ('5207-paper-reference/1','5207-paper-reference/2','5207-paper-reference/3')
                        for old in saved['session']['documents']):
                    notice='5207 使用 Status M 拟合；旧默认拍摄光已改为 5500 K，曝光与自定义色温保留。'
                    self.session_notice=(self.session_notice+' '+notice) if self.session_notice else notice
                if type(saved['revision']) is not int or saved['revision'] < 1:
                    raise ValueError('Invalid workspace revision.')
                self.session_revision = saved['revision']
            except (OSError, KeyError, TypeError, ValueError):
                self.session_warning = '上次工作区无法完整复现；原文件保留，请检查材料版本或重新打开配方。'

    def update_cache_settings(self,request):return self.cache_settings.update(request)

    def update_preferences(self,request):
        try:return self.preferences.update(request)
        except ValueError as error:raise RecipeError('preferences',str(error)) from None

    def scan_action(self,request):
        if not self.scans:raise RecipeError('unsupported','当前材料服务没有负片扫描能力。')
        return self.scans.request(request)

    def scan_upload(self,stream,length,name,kind):
        if not self.scans:raise RecipeError('unsupported','当前材料服务没有负片扫描能力。')
        try:return self.scans.upload(stream,length,name,kind)
        except (ValueError,RuntimeError) as error:raise RecipeError('scan_import',str(error)) from None

    def cache_maintenance(self,request):return self.cache_settings.start(request)

    def bootstrap(self):
        result = super().bootstrap()
        for group in ('templates','recipe_presets','reversal_presets'):
            for entry in result.get(group,[]):
                if entry.get('recipe'):
                    r=bind_reference_scene(entry['recipe'])
                    if hasattr(self.model,'input_priors'):
                        r.setdefault('input_model',self.model.input_priors.descriptor(r['route']))
                        r=self.model.validate(r)['normalized_recipe']
                    entry['recipe']=r
        result['default_recipe']=copy.deepcopy(result['templates'][0]['recipe'])
        result['capture_references']={}
        for stock,material in result.get('spectral_assets',{}).items():
            reference=reference_scene({'film':{'stock':stock,'custom_material':material}})
            if reference is not None:result['capture_references'][stock]=reference
        result['inputs'] = [copy.deepcopy(item) for item in result['inputs'] if item.get('name') != 'softloaf-first-image.png']
        result['chart_layout'] = {'rows': 4, 'columns': 6}
        for item in result['inputs']:
            if item['id'] == 'scene43_rgb':
                item['name'] = '内置高光谱场景'
            if 'thumbnail' not in item and item['id'] in self.model.original_scene_xyz:
                if item['id'] not in self.input_thumbnails:
                    xyz=self.model.original_scene_xyz[item['id']]
                    rgb=np.clip(apply_ocio(self.reference_processor,xyz),0,1)
                    image=Image.fromarray(np.rint(rgb*255).astype('uint8'))
                    self.input_thumbnails[item['id']]=self._thumbnail(image)
                item['thumbnail']=self.input_thumbnails[item['id']]
        result['cache_settings']={'limits':copy.deepcopy(self.cache_settings.limits)}
        result['scan']={'available':self.scans is not None,'stocks':list(self.scans.materials) if self.scans else []}
        result['application'] = {'name': 'SoftLoaf Spectral', 'version': __version__,
                                 'stage': 'installation preview' if packaged() else 'local development', 'desktop': True}
        result['session'] = copy.deepcopy(self.session)
        result['session_revision'] = self.session_revision
        result['session_warning'] = self.session_warning
        result['session_notice'] = self.session_notice
        result['capabilities'].update({'image_import': True, 'image_export': True,
            'preview_short_edge':PREVIEW_SHORT_EDGE,'pixel_compute':self.model.metal.metadata() if self.model.metal else {'backend':'CPU reference','precision':'float64'},
            'session_persistence': True,
            'recipe_deletion': True,
            'image_batch_export': True,
            'fixed_scene_reference': True,
            'image_formats': ['PNG 8-bit RGB', 'JPEG RGB'], 'image_max_pixels': MAX_PIXELS,
            'image_max_bytes': MAX_IMAGE_BYTES, 'raw_max_bytes':MAX_RAW_BYTES,
            'raw_supported': self.raw_engine.cli is not None,
            'raw_engine':'RawTherapee 5.12', 'raw_extensions':sorted(RAW_EXTENSIONS)})
        return result

    def _install_colour_chart(self):
        records=colour.SDS_COLOURCHECKERS['BabelColor Average']
        spectra=np.array([np.interp(self.model.source_wavelengths,sd.wavelengths,sd.values) for sd in records.values()])
        kernel=color_kernel(self.model.source_wavelengths,self.model.source_light,
            interpolate(csv(self.model.archive.parent/'data/CIE_xyz_official.csv'),self.model.source_wavelengths))
        ap1=spectra@self.model.source_to_ap1
        xyz=spectra@kernel@cat(kernel.sum(axis=0),D65).T
        srgb=np.clip(apply_ocio(self.reference_processor,xyz),0,1)
        self.model.samples=[{'id':f'cc{i+1:02d}','name':f'{i+1:02d} · {name}',
            'input_ap1':ap1[i].tolist(),'input_srgb':srgb[i].tolist()} for i,name in enumerate(records)]
        self.model.chart_columns=6
        self.model.inputs['chart']=np.repeat(np.repeat(ap1.reshape(4,6,3),64,axis=0),64,axis=1)
        self.model.original_scene_xyz['chart']=np.repeat(np.repeat(xyz.reshape(4,6,3),64,axis=0),64,axis=1)
        self.model.measured_inputs['chart']=np.repeat(np.repeat(spectra.reshape(4,6,-1),64,axis=0),64,axis=1)
        self.model.input_info[:]=[i for i in self.model.input_info if i['id']!='chart']+[
            {'id':'chart','name':'Colour 24 色卡','kind':'spectral_chart','width':384,'height':256}]
        self.model.verification_input_sources['chart']='Colour 0.4.7 BabelColor Average, 24 measured reflectances; D65; CIE 1931 2 degree; native records resampled only within coverage'

    def conditions(self,recipe):
        result=super().conditions(recipe)
        from .input_priors import LEGACY
        result['input_model']=copy.deepcopy(recipe.get('input_model') or (self.model.input_priors.descriptor(recipe['route']) if hasattr(self.model,'input_priors') else LEGACY))
        if hasattr(self.model,'input_priors'):result['spectral_prior']=result['input_model']['id']+'; nonnegative projection; no upper reflectance cap'
        if self.model.metal:result['pixel_compute']=self.model.metal.metadata()
        return result

    @retry_cpu
    def evaluate(self,request):
        try:self.storage.validate()
        except RuntimeError as error:raise RecipeError('external_storage',str(error)) from None
        spec=request.get('input') or {'id':'scene43_rgb' if 'scene43_rgb' in self.model.inputs else 'chart','exposure_ev':0}
        if isinstance(spec,dict):
            if request.get('priority')=='prefetch' and spec.get('id') in self.pending_preview_upgrades:raise RecipeError('preview_not_ready','预取只使用已准备的预览。')
            self._ensure_preview(spec.get('id'))
        recipe=self.model.validate(request.get('recipe'),compute=True)['normalized_recipe']
        identifier=spec.get('id') if isinstance(spec,dict) else None
        source=self.photo_sources.get(identifier,{})
        path=getattr(self.model.inputs,'paths',{}).get(identifier)
        revision=tuple(getattr(path.stat(),name) for name in ('st_size','st_mtime_ns')) if path and path.is_file() else None
        identity=json.dumps({'renderer':self.rendition_identity,'recipe':recipe,'input':spec,'selection':request.get('selection'),'source':source.get('sha256'),'preview_revision':revision},sort_keys=True)
        transport=request.get('preview_transport','inline')
        if transport not in ('inline','url'):raise RecipeError('invalid_request','未知的预览传递方式。')
        def produce():
            with self.render_gate.slot('background' if request.get('priority')=='prefetch' else 'interactive'):
                if transport=='url':
                    with interactive_encoding():return self._evaluate_uncached(request)
                return self._evaluate_uncached(request)
        return self.renditions.get_or_compute(identity,produce,transport=transport)

    def _evaluate_uncached(self, request):
        spec=request.get('input')
        if isinstance(spec,dict):self._ensure_preview(spec.get('id'))
        # Old recipe snapshots remain recoverable in workspace files, but they
        # can no longer replace A or cause it to run a second film simulation.
        result = super().evaluate({**request, 'baseline': None})
        identifier = result['input']['id']
        ev = result['input']['exposure_ev']
        gpu=self.model.metal
        measured = identifier in self.model.original_scene_xyz
        pixel_stats=copy.deepcopy(gpu.last_stats) if gpu else None
        raw_reference=self.raw_references.get(identifier)
        if raw_reference is not None:
            reference_values=np.load(raw_reference,allow_pickle=False,mmap_mode='r');kind='raw_srgb'
        elif measured:
            reference_values=self.model.measured_inputs[identifier] if gpu else self.model.original_scene_xyz[identifier]
            kind='spectral' if gpu else 'xyz'
        else:reference_values=self.model.inputs[identifier];kind='ap1'
        preview=self.image_previews.render(reference_values,reference=kind,input_ev=ev,reference_processor=self.reference_processor)
        if identifier == 'chart':
            index = next(i for i, sample in enumerate(self.model.samples)
                         if sample['id'] == result['selection']['sample_id'])
            y, x = (index//6)*64+32, (index%6)*64+32
        else:
            x = min(int(result['selection']['x']*reference_values.shape[1]), reference_values.shape[1]-1)
            y = min(int(result['selection']['y']*reference_values.shape[0]), reference_values.shape[0]-1)
        sample_xyz=(self.model.original_scene_xyz[identifier][y,x] if measured else self.model.inputs[identifier][y,x]@AP1.matrix_RGB_to_XYZ.T@cat(D60,D65).T)*np.exp2(ev)
        if raw_reference is not None:
            value=reference_values[y,x]
            sample_srgb=np.clip(value if ev==0 else colour.models.eotf_inverse_sRGB(colour.models.eotf_sRGB(value)*np.exp2(ev)),0,1)
        else:sample_srgb=np.clip(apply_ocio(self.reference_processor,sample_xyz.reshape(1,3))[0],0,1)
        result['reference'] = {'preview': preview,
            'method': 'spectral_XYZ_to_sRGB' if measured else 'characterized_RGB_XYZ_to_sRGB',
            'label': 'A · 原始场景参考' if measured else 'A · 原始 RGB 参考',
            'has_measured_spectrum': measured, 'includes_film': False, 'includes_opendrt': False,
            'sample': {'xyz_d65': sample_xyz.tolist(), 'srgb': sample_srgb.tolist()},
            'conditions': {'observer': 'CIE 1931 2 degree', 'scene_illuminant': 'D65',
                'source': 'native measured reflectance × D65 × CIE XYZ × quadrature widths' if measured else 'characterized input RGB; no measured spectrum available',
                'wavelengths_nm': self.model.source_wavelengths.tolist() if measured else None,
                'adaptation': 'finite-band D65 reference white → standard D65 Bradford' if measured else 'AP1/D60 → XYZ/D65 Bradford',
                'encoding': 'OCIO builtin DISPLAY - CIE-XYZ-D65_to_sRGB → clamp 0–1; no OpenDRT',
                'input_exposure_ev': ev}}
        result['conditions']['reference_A'] = result['reference']['conditions']
        if gpu:result['conditions']['pixel_compute']={**gpu.metadata(),'current_frame':pixel_stats,'reference_frame':copy.deepcopy(gpu.last_stats)}
        if raw_reference is not None:
            result['reference'].update(method='RawTherapee_RAW_to_sRGB',label='A · RawTherapee 原图')
            result['reference']['sample']['srgb']=sample_srgb.tolist()
            result['reference']['conditions'].update(source='RawTherapee independent sRGB output; shared camera profile and AsShot white balance',encoding='RawTherapee float32 sRGB D65 → display clamp 0–1')
            result['conditions']['raw_handoff']=self.photo_sources[identifier]['interpretation']
            result['conditions']['raw_lut_input']={'space':'ACEScct','primaries':'AP1','white':'D60',
                'sample':lut_input(self.model.inputs[identifier][y,x]*np.exp2(ev)).tolist(),
                'preview_processing':'continuous film reference consumes the corresponding linear ACEScg; exported CUBE consumes ACEScct',
                'exposure_ev':ev,'clipped_before_encoding':False}
        physical = measured and getattr(self.model, 'direct_spectral_preview', False)
        result['conditions']['preview_input_method'] = 'measured_spectral' if physical else 'RGB_spectral_prior'
        result['warnings'] = ['B 使用原始反射光谱直接计算胶片；LUT 的 RGB 近似误差另行测量。' if physical else 'B 的普通 RGB 光谱近似不能恢复同色异谱信息。',
            '当前材料为中性密度标定模型，不代表整款胶片或相纸的实测色彩精度。',
            'A 使用原始场景光谱直接积分 XYZ，再转 sRGB；没有原始光谱的 RGB 试片明确使用输入颜色参考。']
        return result

    def _validated_session(self, state):
        if not isinstance(state, dict) or not isinstance(state.get('documents'), list) or not 0 <= len(state['documents']) <= 64:
            raise RecipeError('invalid_session', '工作区最多打开 64 份配方。')
        def validated_document(doc):
            if not isinstance(doc, dict):
                raise RecipeError('invalid_session', '工作区配方格式错误。')
            recipe = self.model.validate(doc.get('recipe'))['normalized_recipe']
            baseline = doc.get('baseline')
            if baseline is not None:
                baseline = self.model.validate(baseline)['normalized_recipe']
            return {'recipe': recipe, 'baseline': baseline}
        documents=[validated_document(doc) for doc in state['documents']]
        identifiers={doc['recipe']['id'] for doc in documents}
        if len(identifiers)!=len(documents):raise RecipeError('invalid_session', '工作区配方标识重复。')
        if (identifiers and state.get('active_id') not in identifiers) or (not identifiers and state.get('active_id') is not None):
            raise RecipeError('invalid_session', '找不到当前配方。')
        deleted=state.get('deleted_documents',[])
        if not isinstance(deleted,list):
            raise RecipeError('invalid_session','删除记录格式错误。')
        deleted_documents=[];deletion_ids=set()
        for entry in deleted:
            if (not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or not 1<=len(entry['id'])<=200
                    or entry['id'] in deletion_ids or type(entry.get('index')) is not int or not 0<=entry['index']<=64):
                raise RecipeError('invalid_session','删除记录的标识或位置不正确。')
            deletion_ids.add(entry['id'])
            deleted_documents.append({'id':entry['id'],'index':entry['index'],'document':validated_document(entry.get('document'))})
        result={'documents': documents, 'active_id': state.get('active_id'),
            **({'deleted_documents':deleted_documents} if deleted_documents else {})}
        if 'photo_workspace' in state:
            photos=state['photo_workspace']
            if (not isinstance(photos,dict) or not isinstance(photos.get('order'),list) or len(photos['order'])>1024
                    or any(not isinstance(i,str) or len(i)>200 for i in photos['order'])
                    or len(set(photos['order']))!=len(photos['order'])
                    or not isinstance(photos.get('exposures',{}),dict)
                    or len(photos.get('exposures',{}))>1024
                    or (photos.get('active_input_id') is not None and photos['active_input_id'] not in photos['order'])):
                raise RecipeError('invalid_session','照片工作区格式错误。')
            exposures=photos.get('exposures',{})
            if any(k not in photos['order'] or type(v) not in (int,float) or not np.isfinite(v) or not -4<=v<=4 for k,v in exposures.items()):
                raise RecipeError('invalid_session','照片输入曝光范围为 −4 到 +4 EV。')
            result['photo_workspace']={'order':photos['order'][:],'active_input_id':photos.get('active_input_id'),'exposures':dict(exposures)}
            if 'panels' in photos:
                panels=photos['panels']
                if (not isinstance(panels,dict) or any(k not in ('recipes_collapsed','filmstrip_collapsed') or type(v) is not bool for k,v in panels.items())):
                    raise RecipeError('invalid_session','面板展开状态须为布尔值。')
                result['photo_workspace']['panels']=dict(panels)
        return result

    def save_session(self, request):
        # Serialize threads and independent services sharing the same workspace.
        with self.session_lock, (self.workspace_directory/'.workspace.lock').open('a+b') as lock:
            acquire_file_lock(lock)
            if self.session_warning:
                raise RecipeError('invalid_session', '上次工作区无法复现；原文件保留，请先下载配方并检查本地工作区。')
            expected = request.get('expected_revision')
            path = self.workspace_directory/'workspace.json'
            try:
                disk_revision = json.loads(path.read_text())['revision'] if path.is_file() else 0
                if type(disk_revision) is not int or disk_revision < 0:
                    raise ValueError('Invalid workspace revision.')
            except (OSError, KeyError, TypeError, ValueError):
                raise RecipeError('invalid_session', '本机工作区文件已变化或损坏，未覆盖原文件。') from None
            if type(expected) is not int or expected != self.session_revision or expected != disk_revision:
                raise RecipeError('session_conflict', '另一窗口已经更新工作区；未覆盖其保存内容，请先下载当前配方。')
            state = self._validated_session(request.get('session'))
            revision = self.session_revision+1
            temporary = self.workspace_directory/'workspace.tmp'
            temporary.write_bytes(json_bytes({'revision': revision, 'session': state}))
            temporary.replace(self.workspace_directory/'workspace.json')
            self.session_revision, self.session = revision, state
            return {'ok': True, 'revision': revision}

    def _decode(self, data):
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise RecipeError('invalid_image', '照片须在 16 MiB 以内。')
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('PNG', 'JPEG') or image.mode != 'RGB':
                    raise RecipeError('invalid_image', '目前只接收 8 位 RGB PNG / JPEG；RAW、透明、灰度或 CMYK 图像需要先正确转换。')
                if image.width*image.height > MAX_PIXELS or getattr(image, 'n_frames', 1) != 1:
                    raise RecipeError('invalid_image', '目前支持不超过 1200 万像素的单张照片。')
                # Pillow otherwise silently reduces 16-bit RGB PNG to 8 bits.
                if image.format == 'PNG' and data[24] != 8:
                    raise RecipeError('invalid_image', '当前试片入口只支持 8 位 RGB PNG。')
                icc = image.info.get('icc_profile')
                image = ImageOps.exif_transpose(image)
                if icc:
                    try:
                        image = ImageCms.profileToProfile(image,
                            ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                            ImageCms.ImageCmsProfile(io.BytesIO(self.srgb_profile)), outputMode='RGB', renderingIntent=1)
                    except (ValueError, OSError, ImageCms.PyCMSError):
                        raise RecipeError('invalid_icc', '内嵌 ICC 无法正确转换；请提供有效配置文件的 RGB 照片。') from None
                image.load()
                return image.copy(), bool(icc)
        except RecipeError:
            raise
        except (OSError, ValueError, Image.DecompressionBombError):
            raise RecipeError('invalid_image', '无法读取照片，请选择完整的 RGB PNG / JPEG。') from None

    def _register(self, data, name, digest):
        if Path(name).suffix.lower() in RAW_EXTENSIONS:
            return self._register_raw(data,name,digest)
        image, has_icc = self._decode(data)
        identifier = 'user_'+digest
        item = {'id': identifier, 'name': name, 'kind': 'imported_rgb_photo',
            'width': image.width, 'height': image.height, 'sha256': digest,
            'interpretation': {'assumed_srgb': not has_icc, 'scene_referred': False,
                'raw_development': False, 'input': 'embedded ICC converted to sRGB' if has_icc else 'untagged RGB assumed encoded sRGB',
                'bridge': 'sRGB decoding → XYZ D65 → Bradford D60 → linear AP1; rendered RGB trial, not camera characterization'}}
        item['thumbnail']=self._thumbnail(image)
        size=preview_size(*image.size)
        if image.size!=size:image=image.resize(size,Image.Resampling.LANCZOS)
        self.model.inputs[identifier] = self.model.srgb_to_ap1(np.asarray(image, dtype=np.float64)/255)
        self.model.input_info[:] = [i for i in self.model.input_info if i['id'] != identifier] + [item]
        self.photo_sources[identifier] = {k:v for k,v in item.items() if k!='thumbnail'}
        return item

    @staticmethod
    def _resize_float(rgb,size=None):
        if size is None:width,height=preview_size(rgb.shape[1],rgb.shape[0])
        else:
            scale=min(1.,size[0]/rgb.shape[1],size[1]/rgb.shape[0]);width,height=max(1,round(rgb.shape[1]*scale)),max(1,round(rgb.shape[0]*scale))
        from .imaging.resample import resize_rows
        output=np.empty((height,width,3),dtype=np.float32)
        resize_rows(rgb,(width,height),lambda y,values:output.__setitem__(slice(y,y+len(values)),values))
        return output

    def _register_raw(self,data,name,digest):
        raw_temporary=self.storage.directory(self.model.output/'raw-import-temp')
        with tempfile.TemporaryDirectory(dir=raw_temporary,prefix='ingest-') as temporary:
            source=Path(temporary)/('original'+Path(name).suffix)
            source.write_bytes(data)
            developed=self.raw_engine.develop(source,preview=True)
        rgb=developed['ap1'];reference=developed['srgb'];identifier='user_'+digest
        if rgb.shape!=reference.shape:raise RecipeError('raw_handoff','RAW 两条输出的尺寸不同。')
        item={'id':identifier,'name':name,'kind':'imported_raw_photo','width':developed['metadata']['original_size'][0],'height':developed['metadata']['original_size'][1],'sha256':digest,
            'interpretation':{'raw_development':True,'scene_referred':True,'assumed_srgb':False,**developed['metadata']}}
        from .imaging.resample import resize_npy
        preview=self.model.inputs.directory/(identifier+'.npy')
        resize_npy(rgb,preview_size(rgb.shape[1],rgb.shape[0]),preview)
        self.model.inputs.attach(identifier,preview)
        path=self.model.output/'preview-cache'/(identifier+'-reference.npy')
        resize_npy(reference,preview_size(reference.shape[1],reference.shape[0]),path)
        self.raw_references[identifier]=path
        image=Image.fromarray(np.rint(np.clip(self._resize_float(reference,(112,80)),0,1)*255).astype('uint8'))
        item['thumbnail']=self._thumbnail(image)
        self.model.input_info[:]=[i for i in self.model.input_info if i['id']!=identifier]+[item]
        self.photo_sources[identifier]={k:v for k,v in item.items() if k!='thumbnail'}
        return item

    def _thumbnail(self,image):
        thumb=image.copy();thumb.thumbnail((112,80),Image.Resampling.LANCZOS)
        return png_preview(np.asarray(thumb,dtype=float)/255,self.srgb_profile)['data_url']

    def _save_photo_metadata(self,item):
        identifier=item['id'];preview=self.model.output/'preview-cache'/(identifier+'.npy')
        record={**item,'preview_sha256':sha(preview),'preview_schema':PREVIEW_SCHEMA,'preview_short_edge':PREVIEW_SHORT_EDGE}
        if item['kind']=='imported_raw_photo':
            record['reference_sha256']=sha(self.raw_references[identifier])
            record['raw_settings_sha256']=self.raw_engine.preview_signature
        metadata=self.import_directory/(identifier+'.json');temporary=metadata.with_suffix('.tmp')
        temporary.write_bytes(json_bytes(record));temporary.replace(metadata)

    def _restore_preview(self,item,allow_legacy=False):
        try:
            identifier=item['id'];preview=self.model.output/'preview-cache'/(identifier+'.npy')
            legacy=allow_legacy and item.get('preview_schema') in (1,2)
            if (not legacy and (item.get('preview_schema')!=PREVIEW_SCHEMA or item.get('preview_short_edge')!=PREVIEW_SHORT_EDGE)) or not preview.is_file() or not re.fullmatch('[0-9a-f]{64}',item['preview_sha256']) or not item['thumbnail'].startswith('data:image/png;base64,'):return False
            if legacy:
                edge=384 if item.get('preview_schema')==1 else 2048
                scale=min(1.,edge/max(item['width'],item['height']))
                expected=(max(1,round(item['width']*scale)),max(1,round(item['height']*scale)))
            else:
                decoded=item.get('interpretation',{}).get('decoded_size',[item['width'],item['height']])
                expected=preview_size(*decoded)
            array=np.load(preview,allow_pickle=False,mmap_mode='r')
            if array.shape!=(expected[1],expected[0],3):return False
            raw=item['kind']=='imported_raw_photo'
            if raw:
                reference=preview.with_name(identifier+'-reference.npy')
                if not reference.is_file() or not re.fullmatch('[0-9a-f]{64}',item['reference_sha256']):return False
                if legacy:
                    # Attach only as an upgrade placeholder; evaluate always rebuilds
                    # it from the verified immutable original before using pixels.
                    if 'AP1 D60' not in item.get('interpretation',{}).get('film_input',''):return False
                if np.load(reference,allow_pickle=False,mmap_mode='r').shape!=array.shape:return False
                self.raw_references[identifier]=reference
            public={k:v for k,v in item.items() if k not in ('preview_sha256','preview_schema','preview_long_edge','preview_short_edge','reference_sha256','raw_settings_sha256')}
            self.model.inputs.attach(identifier,preview)
            self.model.input_info[:]=[i for i in self.model.input_info if i['id']!=identifier]+[public]
            self.photo_sources[identifier]={k:v for k,v in public.items() if k!='thumbnail'}
            self.pending_preview_checks[identifier]=item
            if legacy:self.pending_preview_upgrades[identifier]=item
            # A valid half-size snapshot stays frozen across executable upgrades.
            return True
        except (OSError,KeyError,TypeError,ValueError):return False

    def _ensure_preview(self,identifier):
        if identifier in self.pending_preview_checks:
            with self.preview_check_lock:
                item=self.pending_preview_checks.get(identifier)
                if item is not None:
                    path=self.model.output/'preview-cache'/(identifier+'.npy')
                    try:
                        valid=self.raw_engine.files.digest(path)==item['preview_sha256']
                        if item['kind']=='imported_raw_photo':valid=valid and self.raw_engine.files.digest(self.raw_references[identifier])==item['reference_sha256']
                    except (OSError,ValueError):valid=False
                    if not valid:self.pending_preview_upgrades[identifier]=item
                    self.pending_preview_checks.pop(identifier,None)
        if identifier not in self.pending_preview_upgrades:return
        with self.import_lock:
            item=self.pending_preview_upgrades.get(identifier)
            if item is None:return
            source=self.storage.file(self.import_directory/(identifier+'.source')) if item.get('kind')=='imported_raw_photo' else self.import_directory/(identifier+'.source')
            data=source.read_bytes()
            if hashlib.sha256(data).hexdigest()!=item['sha256']:raise RecipeError('changed_input','原照片已变化，未覆盖缓存。请重新导入。')
            restored=self._register(data,item['name'],item['sha256']);self._save_photo_metadata(restored)
            del self.pending_preview_upgrades[identifier]

    def import_image(self, request):
        try:self.storage.validate()
        except RuntimeError as error:raise RecipeError('external_storage',str(error)) from None
        name = request.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 240 or any(c in name for c in '/\\\x00'):
            raise RecipeError('invalid_image', '请提供照片的文件名。')
        try:
            encoded = request['data_base64']
            limit=MAX_RAW_BYTES if Path(name).suffix.lower() in RAW_EXTENSIONS else MAX_IMAGE_BYTES
            if not isinstance(encoded, str) or len(encoded) > (limit+2)//3*4:
                raise ValueError()
            data = base64.b64decode(encoded, validate=True)
        except (KeyError, ValueError, binascii.Error):
            raise RecipeError('invalid_image', '照片数据不完整或超过 16 MiB。') from None
        digest = hashlib.sha256(data).hexdigest()
        self._ensure_preview('user_'+digest)
        with self.import_lock:
            identifier = 'user_'+digest
            if identifier in self.photo_sources:
                item=next(i for i in self.model.input_info if i['id']==identifier)
                return {'ok':True,'input':copy.deepcopy(item),'warnings':[]}
            if len(self.photo_sources)>=512:raise RecipeError('library_full','当前工作区最多导入 512 张照片。')
            # Validate fully before committing source bytes or the library entry.
            if Path(name).suffix.lower() not in RAW_EXTENSIONS:self._decode(data)
            item = self._register(data, name, digest)
            identifier = 'user_'+digest
            source = self.storage.file(self.import_directory/(identifier+'.source')) if item.get('kind')=='imported_raw_photo' else self.import_directory/(identifier+'.source')
            temp = source.with_suffix('.tmp')
            temp.write_bytes(data)
            temp.replace(source)
            self._save_photo_metadata(item)
        return {'ok': True, 'input': item,
            'warnings': [] if item['kind']=='imported_raw_photo' else ['试片为已渲染 RGB，不含 RAW / DCP 校准；没有 ICC 时按 sRGB 解释。']}

    @retry_cpu
    def _export(self,recipe,purpose,size=65):
        # The standalone historical E100Model remains an explicit test/reference
        # harness. The application startup always constructs SpectralModel.
        if not hasattr(self.model,'input_priors'):return super()._export(recipe,purpose,size)
        return self.lut_exporter.export(recipe,purpose,size)

    @retry_cpu
    def export_image(self,request):
        return self.photo_exporter.export(request)

    def start_photo_export(self,request):
        frozen=copy.deepcopy(request)
        frozen['recipe']=self.model.validate(request.get('recipe'),compute=True)['normalized_recipe']
        if not isinstance(frozen.get('inputs'),list) or not 1<=len(frozen['inputs'])<=512:
            raise RecipeError('invalid_input','请选择 1–512 张已导入的照片。')
        return self.photo_jobs.start(frozen)

    def photo_job(self,request):
        return self.photo_jobs.get(request.get('id'),cancel=request.get('cancel') is True)

    @retry_cpu
    def export_images(self,request,progress=None,cancelled=None):
        return self.batch_exporter.export(request,progress=progress,cancelled=cancelled)
