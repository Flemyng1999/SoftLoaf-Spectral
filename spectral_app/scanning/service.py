"""Application orchestration for frozen scan calibration and positive LUTs.

RAW stages, target analysis, rendering, codecs and file publication stay in their
own modules. All pixel-bearing artifacts are on the external data volume.
"""
import copy
import hashlib
import json
from pathlib import Path
import threading
import uuid
import zipfile
import numpy as np
import tifffile
from experiments.gui_recipe_server import RecipeError,template
from ..photo_jobs import PhotoJobs
from ..presets import load_recipe_presets,visible_negative_presets
from .assets import ScanAssets,match_capture
from .raw import RTScanRaw,digest
from .targets import load_target,extract_patches,border_reading,target_guide,PATCH_IDS
from .flatfield import fit_flatfield
from .flat_assets import FlatCorrection,from_raw_stages,verify_compatibility,save_flat,load_flat
from ..imaging.geometry import Geometry,DEFAULT,auto_zoom
from ..imaging.lens_profiles import LensCatalog
from ..imaging.thumbnails import thumbnail as make_thumbnail
from .calibration import select_response
from .sensitivity import align_border
from .inverse import MaterialInverse
from .rendering import amounts_to_display,amounts_to_aces,aces_to_display
from .transform_cache import LinearScanTable
from .export import export_scan_lut,material_density_domain
from .imaging import preview_image,preview_srgb,export_image,ScanRenderer
from spectral_lut.reference import Cube
from spectral_lut.shaders import shader_path
from ..compute_policy import GPUUnavailable,retry_cpu


def identity(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def array_identity(value):
    value=np.asarray(value,dtype='<f8')
    return {'sha256':hashlib.sha256(value.tobytes()).hexdigest(),'shape':list(value.shape)}


class ScanService:
    def __init__(self,model,storage,renditions,admit=lambda n:None,budget=lambda:64*1024**2):
        self.model=model;self.storage=storage;self.renditions=renditions;self.admit=admit;self.budget=budget
        self.root=storage.directory(storage.root/'scanning/workbench' if storage.root else model.output/'scanning')
        self.lock=threading.RLock();self.resources={};self.warning=None
        self.assets=ScanAssets(self.root/'originals',admit)
        from ..rawtherapee import find_cli
        self.raw=RTScanRaw(find_cli(Path(__file__).resolve().parents[2]),
            storage.root/'scanning/rt-retained-raw' if storage.root else self.root/'rt-retained-raw')
        self.index={'schema':1,'assets':{},'profiles':{},'images':[],'results':{},'active_profile':None,'border':None}
        if (self.root/'index.json').exists():
            try:
                saved=json.loads((self.root/'index.json').read_text())
                if saved['schema']!=1 or not all(isinstance(saved[k],dict) for k in ('assets','profiles','results')):raise ValueError()
                self.index=saved
            except (ValueError,KeyError,OSError):self.warning='扫描工作区记录损坏，请恢复记录后再继续；原件和 RAW 阶段未删除。'
        self.index.setdefault("deleted_profiles",{});self.index.setdefault("deleted_profile_order",[])
        self.index.setdefault("flats",{});self.index.setdefault("geometry",copy.deepcopy(DEFAULT))
        self.lenses=LensCatalog()
        self.jobs=PhotoJobs(self._execute)
        self.prepare_jobs=PhotoJobs(self._execute,workers=2,max_pending=16,name='scan-prepare')
        self.materials={'5207':None}
        try:
            for p in visible_negative_presets(load_recipe_presets(Path(__file__).resolve().parents[2])):
                stock=p['recipe']['film']['stock']
                if stock!='5207':self.materials[stock]=p['recipe']['film']['custom_material']
        except (OSError,ValueError,KeyError):pass
        self.material_ids={s:identity(m or self.model.negative_material) for s,m in self.materials.items()}
        self.preview_implementation=identity({n:digest(Path(__file__).with_name(n+'.py')) for n in ('previews','flatfield','imaging','fused')})
        self.processing_id=identity({**{n:digest(Path(__file__).with_name(n+'.py')) for n in ('raw','inverse','rendering','export','imaging','fused','flat_assets','sensitivity','calibration')},'shaders':{n:digest(Path(__file__).resolve().parents[2]/'core'/n/('scan.hlsl' if n=='d3d12' else 'scan.metal')) for n in ('metal','d3d12')}})
    def _save(self):
        if self.warning:raise ValueError(self.warning)
        temporary=self.root/'index.working.json';temporary.write_text(json.dumps(self.index,ensure_ascii=False));temporary.replace(self.root/'index.json')
    def state(self):
        with self.lock:
            return {'ok':True,**copy.deepcopy(self.index),'warning':self.warning,
                'stocks':list(self.materials),'material_ids':self.material_ids,'processing_id':self.processing_id,'supported':self.raw.executable.is_file(),'prepare_window':16,
                'raw_contract':self.raw.contract,'target_patch_keys':list(PATCH_IDS),'preview_context':self._preview_context()}
    def upload(self,stream,length,name,kind):
        self.storage.validate()
        if self.warning:raise ValueError(self.warning)
        asset=self.assets.import_stream(stream,length,name,kind)
        with self.lock:self.index['assets'].setdefault(asset['id'],asset);self._save()
        return {'ok':True,'asset':asset}
    def _asset(self,identifier):
        with self.lock:
            if identifier not in self.index['assets']:raise ValueError('找不到导入原件，请重新选择。')
            return copy.deepcopy(self.index['assets'][identifier])
    def _native(self,identifier,stage='half'):
        asset=self._asset(identifier)
        if asset['kind']!='raw':raise ValueError('需要 RAW 原件。')
        return self.raw.develop(self.assets.path(asset),stage=stage,expected_sha256=asset['sha256'])/'camera.tif'
    def _preview_context(self,profile=None,geometry=None):
        backend=getattr(getattr(self.model,'metal',None),'backend',None)
        return identity({'profile':self.index.get('active_profile') if profile is None else profile,
            'geometry':self.index.get('geometry',DEFAULT) if geometry is None else geometry,
            'renderer':self.preview_implementation,'shader':digest(shader_path(backend,'scan')) if backend else None,
            'backend':getattr(backend,'name','float64'),'raw_contract':self.raw.contract})
    def _display_flat(self,profile):
        from .previews import fit_display_flat
        if not profile:return None
        record=self.index['profiles'][profile];source=record['source_assets']
        inputs=[source['flat']] if source.get('flat') else [a['id'] for a in self.index['flats'][record['flat_asset']]['sources']['assets']] if record.get('flat_asset') else []
        if not inputs:return None
        paths=[self._native(i).parent/'srgb.tif' for i in inputs]
        field=self.renditions.get_or_compute('scan-display-flat/1:'+profile+':'+self.preview_implementation,
            lambda:fit_display_flat(paths),'url')
        return field['coefficients']
    def _chart_preview(self,identifier):
        from .previews import raw_preview
        native=self._native(identifier);record=json.loads((native.parent/'manifest.json').read_text())
        def produce():
            path=self.renditions.staging_path()
            report=raw_preview(native.parent/'srgb.tif',path,self.model.display_profile('sRGB'),budget=self.budget())
            return {'preview':{'data_url':self.renditions.adopt_png(path)},'report':report}
        result=self.renditions.get_or_compute('scan-rt-srgb/1:'+identifier+':'+record['srgb_sha256'],produce,'url')
        with self.lock:self.index['assets'][identifier]['chart_preview_url']=result['preview']['data_url'];self._save()
        return result
    def _frame_preview(self,identifier,profile=None,geometry=None):
        from .previews import corrected_preview
        profile=profile or self.index.get('active_profile');geometry=copy.deepcopy(geometry or self.index['geometry'])
        asset=self._asset(identifier)
        if profile:match_capture(self.index['profiles'][profile]['capture'],asset['metadata'])
        self._chart_preview(identifier)
        native=self._native(identifier);record=json.loads((native.parent/'manifest.json').read_text())
        context=self._preview_context(profile,geometry);field=self._display_flat(profile)
        key='scan-corrected/1:'+identifier+':'+record['srgb_sha256']+':'+context
        def produce():
            path=self.renditions.staging_path()
            report=corrected_preview(native.parent/'srgb.tif',path,self.model.display_profile('sRGB'),geometry=geometry,
                display_flat=field,backend=getattr(getattr(self.model,'metal',None),'backend',None),budget=self.budget())
            return {'preview':{'data_url':self.renditions.adopt_png(path)},'report':report}
        result=self.renditions.get_or_compute(key,produce,'url');url=result['preview']['data_url']
        def thumb():
            path=self.renditions.staging_path();make_thumbnail(self.renditions.asset_path(url),path,budget=self.budget())
            return {'preview':{'data_url':self.renditions.adopt_png(path)}}
        thumbnail=self.renditions.get_or_compute(key+':thumbnail',thumb,'url')['preview']['data_url']
        with self.lock:
            self.index['assets'][identifier].update(preview_url=url,thumbnail_url=thumbnail,preview_engine=self.raw.contract,
                preview_context=context,preview_report=result['report']);self._save()
        return result
    def _refresh_previews(self,inputs,profile,geometry,progress=None,cancelled=None):
        if progress:progress(0,phase='更新预览',total=len(inputs))
        for n,identifier in enumerate(inputs):
            if cancelled and cancelled():break
            if progress:progress(n,phase=f'矫正预览 {n+1}/{len(inputs)} · {self._asset(identifier)["name"]}')
            self._frame_preview(identifier,profile,geometry)
            if progress:progress(n+1)
    def _resolve_geometry(self,identifier,settings):
        native=tifffile.memmap(self._native(identifier),mode='r')
        try:h,w=native.shape[:2]
        finally:native._mmap.close()
        settings=copy.deepcopy(settings or DEFAULT);mode=settings.get('mode','off')
        if mode=='profile':
            proof=self.lenses.resolve(settings.get('profile_id'),float(settings.get('focal_length',0)),float(settings.get('crop_factor',0)),w,h)
            settings['radial']=proof['radial'];settings['lens']=proof
        elif mode=='manual':settings['radial']=[1,0,float(settings.get('strength',0)),0,0];settings.pop('lens',None)
        elif mode=='off':settings['radial']=[1,0,0,0,0];settings.pop('lens',None)
        else:raise ValueError('未知镜头矫正模式。')
        settings['zoom']=auto_zoom(settings['radial']) if settings.get('auto_crop',True) else 1.
        Geometry(settings,w,h)
        return settings
    def _target(self,identifier):
        asset=self._asset(identifier)
        if asset['kind']!='reference':raise ValueError('请先导入实测透射光谱 CSV。')
        path=self.assets.path(asset)
        if digest(path)!=asset['sha256']:raise ValueError('色卡测量文件发生变化，请重新导入。')
        return load_target(path)
    def _target_guide(self,reference,chart=None):
        from .targets import equivalent_layout
        target=self._target(reference)
        if target.get('id_scheme')!='CC':
            # Old files keep their original fit order. A separately imported,
            # exactly equivalent numbered file is preferred for new positioning.
            for asset in sorted(self.index['assets'].values(),key=lambda a:(a['metadata'].get('id_scheme')!='CC',not a['metadata'].get('keyed',False))):
                if asset['kind']!='reference' or not asset['metadata'].get('numbered'):continue
                candidate=self._target(asset['id'])
                if candidate['target']==target['target'] and equivalent_layout(target,candidate,None) is not None:
                    reference=asset['id'];target=candidate;break
        known=None
        if chart and target['numbered']:
            for profile in self.index['profiles'].values():
                if profile.get('raw_contract')!=self.raw.contract or profile['source_assets']['chart']!=chart:continue
                source=self._target(profile['source_assets']['reference'])
                known=equivalent_layout(source,target,profile['sources']['corners'])
                if known is not None:break
        return {'ok':True,**target_guide(target),'reference':reference,'known_corners':known}
    def resource(self,url):
        with self.lock:
            paths={a.get('preview_url'):(self.root/'native-previews'/(a['id']+'.png'),'image/png',False,None) for a in self.index['assets'].values() if a.get('preview_url')}
            for result in self.index['results'].values():
                for file in result.get('files',[]):paths[file['url']]=(self.root/file['path'],file['kind'],file['name'] if file['download'] else False,file['sha256'])
            if url not in paths:raise FileNotFoundError()
            path,kind,download,sha=paths[url]
        path=path.resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file() or (sha and digest(path)!=sha):raise FileNotFoundError()
        return path,kind,download
    @retry_cpu
    def request(self,request):
        try:
            self.storage.validate()
            if self.warning:raise ValueError(self.warning)
            action=request.get('action')
            if action=='state':return self.state()
            if action=='panels':
                collapsed=request.get('sidebar_collapsed')
                if type(collapsed) is not bool:raise ValueError('侧栏展开状态必须为布尔值。')
                with self.lock:
                    self.index.setdefault('panels',{})['sidebar_collapsed']=collapsed;self._save()
                return self.state()
            if action=='layout':
                from .targets import patch_centres
                return {'ok':True,'centres':patch_centres(request.get('corners')).tolist()}
            if action=='target-guide':return self._target_guide(request['reference'],request.get('chart'))
            if action=='job':
                with self.prepare_jobs.lock:is_prepare=request['id'] in self.prepare_jobs.jobs
                return (self.prepare_jobs if is_prepare else self.jobs).get(request['id'],request.get('cancel',False))
            if action=='new-roll':
                self._require_idle()
                with self.lock:
                    self.index.update(images=[],border=None,active_result=None,geometry=copy.deepcopy(DEFAULT));self._save()
                return self.state()
            if action=='lenses':
                asset=self._asset(request['asset']) if request.get('asset') else None
                metadata=copy.deepcopy(asset['metadata']) if asset else {}
                if asset and not metadata.get('FocalLength'):
                    from .assets import read_metadata
                    metadata.update(read_metadata(self.assets.path(asset)))
                return {'ok':True,'profiles':self.lenses.public(),'match':self.lenses.match(metadata),'metadata':metadata}
            if action=='geometry-preview':
                self._require_idle()
                settings=self._resolve_geometry(request['asset'],request.get('settings'))
                asset=self._asset(request['asset']);result=self.index['results'].get(request.get('result'))
                if result and (result['profile']!=self.index.get('active_profile') or result.get('processing_id')!=self.processing_id):result=None
                renderer=None;field=np.zeros((6,3))
                if result and result.get('lut_id'):
                    lut=self.root/'luts'/result['lut_id'];size=result['size'];manifest=json.loads((lut/'manifest.json').read_text())
                    cube_path=lut/f'scan-density-{size}.cube'
                    if digest(cube_path)!=manifest['files'][cube_path.name]:raise ValueError('LUT 数据发生变化。')
                    renderer=ScanRenderer(self.model,Cube.read(cube_path))
                    record=self.index['profiles'][result['profile']];data=self.root/'profiles'/result['profile']/'calibration.npz'
                    if digest(data)!=record['data_sha256']:raise ValueError('标定数据发生变化。')
                    with np.load(data) as a:field=FlatCorrection.profile(a)
                key=identity({'asset':asset['id'],'settings':settings,'result':result.get('id') if result else None,'processing':self.processing_id,'view':self._preview_context()})
                def produce():
                    path=self.renditions.staging_path()
                    if renderer:
                        report=preview_image(self._native(asset['id']),path,field,self.model.display_profile('sRGB'),renderer=renderer,
                            fingerprint=key,short_edge=2048,budget=self.budget(),geometry=settings,backend=getattr(getattr(self.model,'metal',None),'backend',None))
                    else:
                        report=preview_srgb(self._native(asset['id']).parent/'srgb.tif',path,self.model.display_profile('sRGB'),geometry=settings,
                            budget=self.budget(),backend=getattr(getattr(self.model,'metal',None),'backend',None),
                            display_flat_coefficients=self._display_flat(self.index.get('active_profile')))
                    return {'preview':{'data_url':self.renditions.adopt_png(path)},'report':report}
                preview=self.renditions.get_or_compute('scan-geometry/1:'+key,produce,'url')
                return {'ok':True,'settings':settings,**preview,'technical':renderer is None}
            if action in ('delete-profile','restore-profile'):
                self._require_idle();identifier=request.get('profile')
                with self.lock:
                    deleted=self.index.setdefault('deleted_profiles',{});order=self.index.setdefault('deleted_profile_order',[])
                    if action=='delete-profile':
                        if identifier not in self.index['profiles']:raise ValueError('找不到扫描标定。')
                        was_active=self.index.get('active_profile')==identifier
                        deleted[identifier]={'profile':self.index['profiles'].pop(identifier),'was_active':was_active}
                        if identifier in order:order.remove(identifier)
                        order.append(identifier)
                        if was_active:self.index['active_profile']=None
                    else:
                        if identifier not in deleted:raise ValueError('找不到可恢复的扫描标定。')
                        if identifier in self.index['profiles']:raise ValueError('扫描标定已经存在，未覆盖。')
                        entry=deleted.pop(identifier);self.index['profiles'][identifier]=entry['profile']
                        if identifier in order:order.remove(identifier)
                        if entry['was_active'] and self.index.get('active_profile') is None:self.index['active_profile']=identifier
                    self._save()
                return self.state()
            if action=='select':
                self._require_idle()
                with self.lock:
                    if request['profile'] not in self.index['profiles']:raise ValueError('找不到扫描标定。')
                    self.index['active_profile']=request['profile'];self._save()
                return self.state()
            if action not in ('prepare','refresh','geometry','calibrate','positive','export','flat','refit-flat'):raise ValueError('未知扫描操作。')
            body=copy.deepcopy(request)
            if action in ('geometry','refresh'):body['inputs']=body.get('inputs') or self.index['images'] or [body.get('asset')]
            body.setdefault('profile',self.index.get('active_profile'));body.setdefault('geometry',copy.deepcopy(self.index['geometry']))
            body['inputs']=body.get('inputs') or [body.get('chart') or self.index['profiles'].get(body.get('profile'),{}).get('source_assets',{}).get('chart')]
            if not isinstance(body['inputs'],list) or not 1<=len(body['inputs'])<=512 or len(set(body['inputs']))!=len(body['inputs']):raise ValueError('请选择不重复的 RAW 原件。')
            for identifier in body['inputs']:self._asset(identifier)
            # Immutable IDs and explicit border/settings are copied into the queued request.
            if action=='prepare':
                # Publish in admission order, not worker completion order. The
                # index lock prevents workers publishing previews before rows.
                with self.lock:
                    job=self.prepare_jobs.start(body)
                    if body.get('roll'):
                        self.index['images'].extend(i for i in body['inputs'] if i not in self.index['images']);self._save()
                return job
            return self.jobs.start(body)
        except GPUUnavailable:raise
        except (ValueError,KeyError,RuntimeError) as e:raise RecipeError('scan_input',str(e)) from None
    def _require_idle(self):
        for queue in (self.jobs,self.prepare_jobs):
            with queue.lock:
                if any(j['status'] in ('queued','running') for j in queue.jobs.values()):raise ValueError('请等待当前扫描任务完成。')
    def _execute(self,request,progress=None,cancelled=None):
        try:
            if request['action']=='geometry':
                if progress:progress(0,phase='应用几何矫正',total=0)
                settings=self._resolve_geometry(request['asset'],request['settings'])
                with self.lock:self.index['geometry']=settings;self._save()
                self._refresh_previews(request['inputs'],request.get('profile'),settings,progress,cancelled)
                return self.state()
            if request['action']=='refresh':
                self._refresh_previews(request['inputs'],request.get('profile'),request['geometry'],progress,cancelled)
                return self.state()
            if request['action']=='prepare':
                if progress:progress(0,phase='RT 读取与预览',total=len(request['inputs']))
                for n,identifier in enumerate(request['inputs']):
                    if cancelled and cancelled():break
                    if request.get('chart'):self._chart_preview(identifier)
                    else:self._frame_preview(identifier,request.get('profile'),request.get('geometry'))
                    if progress:progress(n+1)
                return self.state()
            if request['action']=='flat':
                if progress:progress(0,phase='分析平场',total=0)
                records=[self._asset(i) for i in request['inputs']]
                for asset in records:
                    if asset['metadata'].get('Model')!=records[0]['metadata'].get('Model'):raise ValueError('平场机身不一致。')
                field,report=from_raw_stages([self._native(a['id']) for a in records])
                source={'assets':[{'id':a['id'],'capture':a['metadata']} for a in records],'raw_contract':self.raw.contract,'algorithm':digest(Path(__file__).with_name('flat_assets.py'))}
                report['reference_warnings']=sorted({k for a in records[1:] for k in ('LensModel','FNumber','ISO','ExposureTime') if a['metadata'].get(k)!=records[0]['metadata'].get(k)})
                report['name']='平场 · '+Path(records[0]['name']).stem[:80]+(' · '+str(len(records))+' 张' if len(records)>1 else '')
                key=identity(source);record=save_flat(self.root/'flats',key,field,report,source,records[0]['metadata'])
                with self.lock:self.index['flats'][key]=record;self._save()
                return {'ok':True,'flat':record}
            if request['action']=='refit-flat':
                old=self.index['profiles'].get(request.get('profile'))
                if not old:raise ValueError('请先选择扫描标定。')
                if progress:progress(0,phase='重新计算色卡',total=0)
                fitted=self._calibrate({**old['source_assets'],'flat':None,'flat_asset':request.get('flat_asset'),
                    'corners':old['sources']['corners'],'name':old['name'],'geometry':request.get('geometry')})
                self._refresh_previews(list(self.index['images']),fitted['profile']['id'],self.index['geometry'],progress,cancelled)
                return fitted
            if request['action']=='calibrate':
                if progress:progress(0,phase='计算色卡标定',total=0)
                return self._calibrate(request)
            return self._positive(request,progress,cancelled)
        except GPUUnavailable:raise
        except (ValueError,RuntimeError,OSError,KeyError) as e:raise RecipeError('scan_failed',str(e)) from None
    def _calibrate(self,r):
        chart=self._asset(r['chart']);reference=self._asset(r['reference']);flat=None;warnings=[]
        source={'chart':chart['sha256'],'flat':self._asset(r['flat'])['sha256'] if r.get('flat') else r.get('flat_asset'),'reference':reference['sha256'],'corners':r['corners'],
            'normalise_response':bool(r.get('flat')),'raw_contract':self.raw.contract,'algorithm':{n:digest(Path(__file__).with_name(n+'.py')) for n in ('calibration','targets','flatfield','flat_assets')}}
        key=identity(source);folder=self.root/'profiles'/key;folder.mkdir(parents=True,exist_ok=True)
        if (folder/'profile.json').exists():
            record=json.loads((folder/'profile.json').read_text())
            if digest(folder/'calibration.npz')!=record['data_sha256']:raise ValueError('已有扫描标定发生变化，未覆盖。')
            if r.get('name'):
                record['name']=str(r['name'])[:120];(folder/'profile.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
            with self.lock:self.index['profiles'][key]=record;self.index['active_profile']=key;self._save()
            return {'ok':True,'profile':record}
        target=self._target(reference['id'])
        if r.get('flat'): # Captured flat, fitted in the same RT camera coordinates.
            flat=self._asset(r['flat']);match_capture(chart['metadata'],flat['metadata'])
            native=tifffile.memmap(self._native(flat['id']),mode='r')
            try:small=np.asarray(native[::8,::8],float)/65535
            finally:native._mmap.close()
            report=fit_flatfield(small);field=FlatCorrection(coefficients=report['coefficients']);normalise=True
        elif r.get('flat_asset'):
            record=self.index['flats'].get(r['flat_asset'])
            if not record:raise ValueError('找不到平场文件。')
            native=tifffile.memmap(self._native(chart['id']),mode='r')
            try:warnings=verify_compatibility(record,chart['metadata'],native.shape)
            finally:native._mmap.close()
            field=load_flat(self.root/'flats',record);report=record;normalise=False
        else:
            field=FlatCorrection(coefficients=np.zeros((6,3)));report={'clipped_fraction':[0,0,0]};normalise=False
        camera,layout=extract_patches(self._native(chart['id']),r['corners'],field)
        wave=np.arange(max(391,np.ceil(target['wavelengths'][0])),min(730,np.floor(target['wavelengths'][-1]))+1)
        spectra=np.array([np.interp(wave,target['wavelengths'],t) for t in target['transmission']])
        response=select_response(wave,spectra,camera,normalise=normalise)
        np.savez(folder/'calibration.npz',wave=wave,weights=response['weights'],camera=camera,spectra=spectra,family=response['family'],**field.arrays())
        record={'id':key,'name':str(r.get('name') or target['target'])[:120],'target':target['target'],'raw_contract':self.raw.contract,
            'capture':chart['metadata'],'sources':source,'source_assets':{'chart':chart['id'],'flat':flat['id'] if flat else None,'reference':reference['id']},
            'layout':layout,'response_band_nm':[float(wave[0]),float(wave[-1])],
            'RMS_D':response['outer_RMS_log10'],'max_D':response['outer_max_log10'],
            'flat_clipped_fraction':report['clipped_fraction'],'flat_asset':r.get('flat_asset'),'flat_warnings':warnings,'flat_mode':'polynomial' if flat else 'spatial' if r.get('flat_asset') else 'off','data_sha256':digest(folder/'calibration.npz'),
            'method':'estimated joint response; measured transmission target; no independent camera/lamp separation'}
        (folder/'profile.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        with self.lock:self.index['profiles'][key]=record;self.index['active_profile']=key;self._save()
        return {'ok':True,'profile':record}
    def _positive(self,r,progress,cancelled):
        if progress:progress(0,phase='准备扫描 LUT',total=0)
        profile_id=r.get('profile')
        with self.lock:profile=copy.deepcopy(self.index['profiles'].get(profile_id))
        if profile is None:raise ValueError('请先建立并选择扫描标定。')
        if profile.get('raw_contract')!=self.raw.contract:raise ValueError('标定与当前 RAW 引擎不匹配，请重新建立色卡标定。')
        data_path=self.root/'profiles'/profile_id/'calibration.npz'
        if digest(data_path)!=profile['data_sha256']:raise ValueError('扫描标定数据已改变，未继续处理。')
        a=np.load(data_path);border=r.get('border') or {};base_id=border.get('asset')
        base_asset=self._asset(base_id);match_capture(profile['capture'],base_asset['metadata'])
        for identifier in r['inputs']:match_capture(profile['capture'],self._asset(identifier)['metadata'])
        field=FlatCorrection.profile(a)
        observed=border_reading(self._native(base_id),border.get('roi'),field)
        geometry=copy.deepcopy(r.get('geometry') or self.index.get('geometry') or DEFAULT)
        stock=r.get('stock','5207');ev=r.get('view_ev',0);size=r.get('size',65)
        if stock not in self.materials or type(ev) not in (int,float) or not np.isfinite(ev) or not -4<=ev<=4:raise ValueError('片种或观看曝光无效。')
        if type(size)!=int or not 2<=size<=129:raise ValueError('LUT 尺寸应为2–129的整数。')
        recipe=template('negative');recipe['film'].update(stock=stock,custom_material=copy.deepcopy(self.materials[stock]))
        material=self.model.route_material(recipe);wave=a['wave']
        dyes=np.column_stack([np.interp(wave,self.model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
        base=np.interp(wave,self.model.negative_wavelengths,material.base)
        weights,gain=align_border(a['weights'],10**-base,observed)
        from spectral_lut import negative as density_reference
        physical={'schema':'softloaf.scan-linear-ACES/1','arrays':{name:array_identity(value) for name,value in
            [('scan_wavelengths',wave),('scan_dyes',dyes),('scan_base',base),('scan_weights',weights),
             ('amount_low',material.amounts.min(0)),('amount_high',material.amounts.max(0)),
             ('output_wavelengths',self.model.negative_wavelengths),('output_dyes',material.dyes),
             ('output_base',material.base),('APD_weights',self.model.apd_weights)]},
            'algorithms':{n:digest(Path(__file__).with_name(n+'.py')) for n in ('inverse','rendering')},
            'ADX_to_ACES_sha256':digest(Path(density_reference.__file__))}
        frozen={'schema':'softloaf.scan-positive/1','profile':profile,'stock':stock,
            'material_sha256':identity(recipe['film']['custom_material'] or self.model.negative_material),
            'border':{'asset_sha256':base_asset['sha256'],'roi':border['roi'],'observed':observed.tolist(),'gain':gain.tolist()},
            'view_ev':ev,'size':size,'display':self.model.display_manager.config_metadata,
            'processing_id':self.processing_id,
            'physical_transform':physical,
            'implementation':{n:digest(Path(__file__).with_name(n+'.py')) for n in ('inverse','rendering','export','sensitivity','calibration')}}
        key=identity(frozen);view_key=identity({'lut':key,'geometry':geometry,'sampling':'single-pass/1','processing_id':self.processing_id});folder=self.root/'luts'/key
        if not folder.exists():
            if progress:progress(0,phase=f'生成 {size}³ LUT',total=0)
            self.admit(size**3*160+16*1024**2)
            inverse=MaterialInverse(dyes,base,weights,material.amounts.min(0),material.amounts.max(0));low,high=material_density_domain(inverse)
            def render(density):return amounts_to_display(self.model,material,inverse.solve(10**-density)['amounts'],exposure_ev=ev)
            linear_key=identity({'physical':physical,'size':size,'low':low.tolist(),'high':high.tolist()})
            table=LinearScanTable.create(self.root/'transforms',linear_key,size,low,high,
                lambda density:amounts_to_aces(self.model,material,inverse.solve(10**-density)['amounts']))
            try:
                export_scan_lut(folder,render,{'status':'estimated-joint-response','camera':profile['capture']['Model'],
                    'material':'Kodak '+stock+' / ECN-2 / Status M fitted','calibration_sha256':key,
                    'view_exposure_ev':ev,'frozen':frozen,'linear_transform_sha256':linear_key},size=size,domain_min=low,domain_max=high,
                    node_render=table.renderer(lambda aces:aces_to_display(self.model,aces,exposure_ev=ev)))
            finally:table.close()
        manifest=json.loads((folder/'manifest.json').read_text())
        for name,sha in manifest['files'].items():
            if digest(folder/name)!=sha:raise ValueError('已冻结 LUT 文件发生变化。')
        cube=Cube.read(folder/f'scan-density-{size}.cube');renderer=ScanRenderer(self.model,cube)
        self.admit(16*1024**2)
        files=[];outputs={}
        for file in manifest['files']:
            path=folder/file;url='/scan-files/lut/'+key+'/'+file
            files.append({'url':url,'path':str(path.relative_to(self.root)),'name':file,'kind':'application/octet-stream','download':True,'sha256':digest(path)})
        if progress:progress(0,phase='导出正片' if r['action']=='export' else '正相处理',total=len(r['inputs']))
        for n,identifier in enumerate(r['inputs']):
            if cancelled and cancelled():break
            asset=self._asset(identifier);full=r['action']=='export'
            self.raw.verify_source(self.assets.path(asset),asset['sha256'])
            parent=self.root/('exports' if full else 'positives')/view_key;parent.mkdir(parents=True,exist_ok=True)
            path=parent/(identifier+'.png');record=parent/(identifier+'.json')
            if full:
                if not path.exists() or not record.exists():
                    if progress:progress(n,phase=f'RT 全尺寸开发 · {n+1}/{len(r["inputs"])}')
                    native=self._native(identifier,'full')
                    if progress:progress(n,phase='导出正片')
                    temporary=path.with_name(path.stem+'.working.png')
                    self.admit(2*native.stat().st_size)
                    report=export_image(native,temporary,field,renderer,self.model.display_profile('sRGB'),fingerprint=view_key,budget=self.budget(),geometry=geometry,
                        progress=(lambda rows,total:progress(n+rows/total)) if progress else None)
                    temporary.replace(path);record.write_text(json.dumps({'report':report,'sha256':digest(path)}))
                saved=json.loads(record.read_text())
                if digest(path)!=saved['sha256']:raise ValueError('已保存的正片发生变化，请恢复文件。')
                url='/scan-files/export/'+view_key+'/'+identifier+'.png'
                entry={'url':url,'path':str(path.relative_to(self.root)),'name':Path(asset['name']).stem+'.png',
                    'kind':'image/png','download':True,'sha256':saved['sha256']}
                files.append(entry);outputs[identifier]={'url':url,'report':saved['report'],'name':asset['name']}
            else:
                def produce():
                    native=self._native(identifier)
                    temporary=self.renditions.staging_path()
                    report=preview_image(native,temporary,field,self.model.display_profile('sRGB'),renderer=renderer,fingerprint=view_key,budget=self.budget(),geometry=geometry)
                    small=self.renditions.staging_path();make_thumbnail(temporary,small,budget=self.budget())
                    return {'preview':{'data_url':self.renditions.adopt_png(temporary)},'thumbnail':{'data_url':self.renditions.adopt_png(small)},'report':report}
                saved=self.renditions.get_or_compute('scan-positive/3:'+view_key+identifier,produce,'url')
                outputs[identifier]={'url':saved['preview']['data_url'],'thumbnail_url':saved['thumbnail']['data_url'],'report':saved['report'],'name':asset['name']}
            result_id=view_key+('-full' if full else '')
            with self.lock:
                self.index['results'][result_id]={'id':result_id,'profile':profile_id,'files':copy.deepcopy(files),'outputs':copy.deepcopy(outputs),'stock':stock,'view_ev':ev,'size':size,'border':copy.deepcopy(border),'interpolation':manifest.get('interpolation'),'material_id':self.material_ids[stock],'processing_id':self.processing_id,'geometry':copy.deepcopy(geometry),'lut_id':key}
                self.index['border']=copy.deepcopy(border)
                if not full:self.index['active_result']=view_key
                self._save()
            if progress:progress(n+1)
        if r['action']=='export' and len(outputs)>1:
            if progress:progress(0,phase='打包导出',total=0)
            archive=self.root/'exports'/view_key/'positives.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as z:
                for identifier,value in outputs.items():
                    source=self.root/next(f['path'] for f in files if f['url']==value['url'])
                    z.write(source,identifier[-8:]+'-'+Path(value['name']).stem+'.png')
                z.writestr('processing.json',json.dumps({**frozen,'geometry':geometry},ensure_ascii=False))
            with zipfile.ZipFile(archive) as z:
                if z.testzip() is not None:raise ValueError('批量正片包校验失败。')
            files.append({'url':'/scan-files/export/'+view_key+'/positives.zip','path':str(archive.relative_to(self.root)),
                'name':'positives.zip','kind':'application/zip','download':True,'sha256':digest(archive)})
            with self.lock:self.index['results'][view_key+'-full']['files']=files;self._save()
        return {'ok':True,'id':view_key,'lut_id':key,'outputs':outputs,'files':files,'frozen':{'stock':stock,'profile':profile_id,'view_ev':ev,'size':size}}
