"""Two explicit RawTherapee 5.12 handoffs; no display RGB round-trip for LUT input."""
from .file_lock import acquire_file_lock,release_file_lock
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from .diagnostics import event
import struct
import re
import errno
from collections import OrderedDict
from contextlib import contextmanager

import numpy as np
import tifffile
from experiments.gui_recipe_server import RecipeError
from spectral_lut.display import rgb_profile
from spectral_lut.reference import acescct_encode
from .storage import DataStorage

RAW_EXTENSIONS={'.dng','.cr2','.cr3','.crw','.nef','.nrw','.arw','.raf','.rw2','.orf','.ori','.pef','.srw','.raw','.iiq','.3fr','.fff','.mos','.kdc','.dcr','.erf','.mef','.rwl','.x3f'}
# RT starts from its neutral ProcParams; no -d/-s means user defaults/sidecars cannot override this.
BASE_PP3='''[Version]
AppVersion=5.12
Version=352
[Exposure]
Auto=false
Clip=0
Compensation=0
Brightness=0
Contrast=0
Saturation=0
Black=0
HighlightCompr=0
ShadowCompr=0
Curve=0;
Curve2=0;
[White Balance]
Enabled=true
Setting=Camera
[Color Management]
InputProfile=(cameraICC)
ToneCurve=false
ApplyLookTable=false
ApplyBaselineExposureOffset=true
ApplyHueSatMap=true
DCPIlluminant=0
WorkingProfile=ACESp1
WorkingTRC=0
OutputProfileIntent=Relative
OutputBPC=false
[RAW Bayer]
Method=amaze
[RAW X-Trans]
Method=3-pass (best)
[Sharpening]
Enabled=false
[PostDemosaicSharpening]
Enabled=false
[Directional Pyramid Denoising]
Enabled=false
[Impulse Denoising]
Enabled=false
[Defringing]
Enabled=false
[Shadows & Highlights]
Enabled=false
[EPD]
Enabled=false
[Retinex]
Enabled=false
[Crop]
Enabled=false
[Resize]
Enabled=false
'''


def find_cli(root):
    from .raw_runtime import RawRuntime
    return RawRuntime(root).cli


def lut_input(ap1):
    """LUT contract: linear ACEScg AP1/D60 → ACEScct AP1/D60, without clipping."""
    return acescct_encode(np.asarray(ap1,dtype=np.float64))


def white_balance_record(messages):
    unavailable=any('Cannot use camera white balance' in message for message in messages)
    return {'white_balance_requested':'Camera / AsShot','camera_white_balance_unavailable':unavailable,
        'white_balance':'RawTherapee native fallback; camera white balance unavailable' if unavailable else 'Camera / AsShot requested; no unavailable warning from RawTherapee'}


class VerifiedFiles:
    """Stream hashes once per unchanged file identity, with bounded metadata memory."""
    def __init__(self,limit=1024,memoize=True):
        self.entries=OrderedDict();self.limit=limit;self.lock=threading.Lock();self.memoize=memoize

    @staticmethod
    def _hash(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

    def digest(self,path):
        path=Path(path)
        with self.lock:
            stat=path.stat();identity=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            previous=self.entries.get(path)
            if self.memoize and previous and previous[0]==identity:
                self.entries.move_to_end(path);return previous[1]
            digest=self._hash(path)
            after=path.stat()
            if identity!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                raise RecipeError('changed_input','文件在读取时发生变化，请重新导入。')
            self.entries[path]=(identity,digest);self.entries.move_to_end(path)
            while len(self.entries)>self.limit:self.entries.popitem(last=False)
            return digest


class DecodeGate:
    """One expensive RAW pair at a time; queued viewer work precedes exports."""
    def __init__(self):
        self.condition=threading.Condition();self.queue=[];self.running=False;self.serial=0

    @property
    def waiting(self):
        with self.condition:return len(self.queue)

    @contextmanager
    def slot(self,priority):
        if priority not in ('interactive','background'):raise ValueError('Unknown RAW task priority')
        with self.condition:
            token=(0 if priority=='interactive' else 1,self.serial);self.serial+=1;self.queue.append(token)
            self.condition.wait_for(lambda:not self.running and token==min(self.queue))
            self.queue.remove(token);self.running=True
        try:yield
        finally:
            with self.condition:self.running=False;self.condition.notify_all()


def typed_raw_source(source,target,expected_digest):
    """Preserve the extension without requiring Windows developer privileges."""
    try:target.symlink_to(source)
    except OSError as error:
        if error.errno not in (errno.EPERM,errno.EOPNOTSUPP,errno.ENOSYS) and getattr(error,'winerror',None)!=1314:raise
        shutil.copyfile(source,target)
        with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=expected_digest:raise RecipeError('changed_input','RAW 原件在读取时发生变化。')
    return target


class RawTherapee:
    def __init__(self,root,cache,cli=None):
        from .raw_runtime import RawRuntime
        self.runtime=RawRuntime(root,cli)
        self.cli=self.runtime.cli
        storage=DataStorage.configured()
        self.storage=storage
        self.cache=storage.directory(cache)
        # Removable filesystems can have coarse timestamps. Rehash across RAW
        # handoffs instead of trusting an unchanged size/time tuple there.
        self.gate=DecodeGate();self.files=VerifiedFiles(memoize=True)
        self.identity=None
        if self.cli:
            self.identity=hashlib.sha256(self.cli.read_bytes()).hexdigest()
        share=self.runtime.resources
        self.resource_hashes={}
        for name in ('camconst.json','cammatrices.json','dcraw.json','dcpprofiles','iccprofiles/input'):
            path=share/name
            for file in sorted(path.rglob('*') if path.is_dir() else [path]):
                if file.is_file():self.resource_hashes[str(file.relative_to(share))]=hashlib.sha256(file.read_bytes()).hexdigest()
        self.profiles={'srgb':rgb_profile('sRGB'),'ap1':rgb_profile('ACEScg Linear')}
        # LCMS creates an sRGB profile with today's timestamp. Normalize it so a
        # restart does not invalidate otherwise identical RAW developments.
        srgb=bytearray(self.profiles['srgb']);srgb[24:36]=struct.pack('>6H',2026,1,1,0,0,0)
        self.profiles['srgb']=bytes(srgb)
        self.version_checked=False
        self.signature=hashlib.sha256((BASE_PP3+'raw-handoff/2; typed originals; WB availability').encode()+b''.join(self.profiles.values())+b'one-decode-shared-Lab/1'+json.dumps(self.resource_hashes,sort_keys=True).encode()).hexdigest()
        self.preview_cli=self.runtime.preview
        self.preview_identity=self.files.digest(self.preview_cli) if self.preview_cli.is_file() else None
        self.preview_signature=hashlib.sha256((self.signature+'bayer-quartet/1; RT preprocessing and color conversion').encode()).hexdigest()
        self.checked_clis=set()
        self.thread_count=min(4,max(1,(os.cpu_count() or 2)//2))
        self.integrated=self.runtime.integrated
        self.reference_cli=self.runtime.reference
        self.reference_identity=self.files.digest(self.reference_cli) if self.reference_cli.is_file() else None
        # Executable replacement does not invalidate an already frozen development.
        self._reference=None;self._sensors={}

    def _reference_for_sensor(self,source,digest):
        if self.cli.resolve()!=self.integrated.resolve():return None
        if digest not in self._sensors:
            try:
                run=subprocess.run([str(self.integrated),'--softloaf-identify',str(source)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False,env=self.runtime.environment(self.integrated))
                self._sensors[digest]=json.loads(run.stdout).get('filters') if run.returncode==0 else None
            except (OSError,ValueError,subprocess.TimeoutExpired):self._sensors[digest]=None
        if self._sensors[digest]!=9:return None
        if not self.reference_identity:raise RecipeError('raw_compatibility','当前 X-Trans 读取保留官方 RT 5.12 路径，请配置经过验证的兼容读取器。')
        if self.files.digest(self.reference_cli)!=self.reference_identity:raise RecipeError('raw_engine_changed','RAW 兼容读取器已更新，请重新启动应用。')
        return self.reference_cli

    @contextmanager
    def _stage_lock(self,key):
        directory=self.cache/'locks';directory.mkdir(exist_ok=True)
        with (directory/(key+'.lock')).open('a+b') as stream:
            acquire_file_lock(stream)
            try:yield
            finally:release_file_lock(stream)

    def _retained_location(self,record,key,signature,digest):
        try:
            state=json.loads(record.read_text());folder=state.get('directory','')
            if state.get('status')=='complete' and state.get('source_sha256')==digest and re.fullmatch('[0-9a-f]{64}',folder):return self.cache/folder,state.get('data_signature',signature)
        except (OSError,ValueError,TypeError):pass
        return self.cache/key,signature

    def _adopt_legacy(self,digest,signature,preview,record,compatibility):
        database=hashlib.sha256(json.dumps(self.resource_hashes,sort_keys=True).encode()).hexdigest()
        for path in self.cache.glob('*/manifest.json'):
            try:
                m=json.loads(path.read_text())
                if m['source_sha256']!=digest or m.get('processing_mode','full-quality')!=('preview' if preview else 'full-quality'):continue
                if m.get('camera_database_sha256')!=database or any(m.get(k) is not v for k,v in [('dcp_tone_curve',False),('dcp_look_table',False),('dcp_hue_sat_map',True),('display_rendering',False)]):continue
                if compatibility and m['engine_sha256']!=self.reference_identity:continue
                legacy=hashlib.sha256((BASE_PP3+'raw-handoff/2; typed originals; WB availability').encode()+b''.join(self.profiles.values())+m['engine_sha256'].encode()+json.dumps(self.resource_hashes,sort_keys=True).encode()).hexdigest()
                candidates={legacy}
                if preview:
                    old=hashlib.sha256((legacy+m['engine_sha256']+'bayer-quartet/1; RT preprocessing and color conversion').encode()).hexdigest()
                    candidates={old,hashlib.sha256((old+str(self.reference_identity)).encode()).hexdigest()}
                if m['settings_sha256'] not in candidates or not self._valid(path.parent,m['settings_sha256']):continue
                for route,profile in self.profiles.items():
                    with tifffile.TiffFile(path.parent/(route+'.tif')) as tif:
                        if tif.pages[0].tags[34675].value!=profile:raise ValueError('Different legacy output profile')
                tmp=record.with_suffix('.tmp');tmp.write_text(json.dumps({'status':'complete','directory':path.parent.name,'data_signature':m['settings_sha256'],'source_sha256':digest,'stage':'half' if preview else 'full','adopted_legacy':True}));tmp.replace(record)
                return path.parent,m['settings_sha256']
            except (OSError,ValueError,KeyError,TypeError):continue
        return None

    def develop(self,source,source_name=None,*,routes=('srgb','ap1'),priority='interactive',preview=False):
        self.storage.validate()
        if not self.cli:raise RecipeError('raw_unavailable','未找到 RawTherapee CLI。')
        routes=tuple(routes)
        if not routes or len(set(routes))!=len(routes) or any(r not in self.profiles for r in routes):raise ValueError('Unknown RAW output branch')
        cli=self.preview_cli if preview else self.cli
        if preview and not self.preview_identity:raise RecipeError('raw_preview_unavailable','请先构建 RAW 预览读取器。')
        expected=self.preview_identity if preview else self.identity
        if self.files.digest(cli)!=expected:raise RecipeError('raw_engine_changed','RAW 引擎已更新，请重新启动应用后再读取。')
        source=Path(source).resolve();digest=self.files.digest(source)
        signature=self.preview_signature if preview else self.signature
        key=hashlib.sha256((digest+signature).encode()).hexdigest();directory=self.cache/key
        ledger=self.cache/'ledger';ledger.mkdir(exist_ok=True);record=ledger/(key+'.json')
        directory,data_signature=self._retained_location(record,key,signature,digest)
        cached=self._cached(directory,routes,data_signature,digest)
        if cached is not None:return cached
        with self.gate.slot(priority),self._stage_lock(key):
            directory,data_signature=self._retained_location(record,key,signature,digest)
            cached=self._cached(directory,routes,data_signature,digest)
            if cached is not None:return cached
            if record.exists():raise RecipeError('raw_cache_integrity','已保留的 RAW 开发数据损坏或上次开发中断；需要明确重建，不会自动再次读取 RAW。')
            compatibility=self._reference_for_sensor(source,digest)
            adopted=self._adopt_legacy(digest,signature,preview,record,compatibility)
            if adopted:return self._read(adopted[0],routes)
            if compatibility:cli=compatibility
            shared=cli.resolve()==self.integrated.resolve()
            if str(cli) not in self.checked_clis:
                try:help_text=subprocess.run([str(cli),'-h'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=15,env=self.runtime.environment(cli)).stdout.decode(errors='replace')
                except (OSError,subprocess.TimeoutExpired):help_text=''
                if 'version 5.12,' not in help_text:raise RecipeError('raw_version','当前接入已核验 RawTherapee 5.12；请配置这一版本的 CLI。')
                self.checked_clis.add(str(cli));self.version_checked=True
            if hasattr(self,'admit_write'):self.admit_write(64_000_000*24+source.stat().st_size)
            with tempfile.TemporaryDirectory(prefix='develop-',dir=self.cache) as temporary:
                tmp=Path(temporary);raw_source=source
                if source_name and source.suffix.lower()!=Path(source_name).suffix.lower():
                    suffix=Path(source_name).suffix.lower()
                    if suffix not in RAW_EXTENSIONS:raise RecipeError('invalid_image','原件的 RAW 扩展名不受支持。')
                    raw_source=tmp/('original'+suffix)
                    typed_raw_source(source,raw_source,digest)
                (tmp/'settings').mkdir()
                env={**self.runtime.environment(cli),'RT_SETTINGS':str(tmp/'settings'),'RT_CACHE':str(tmp/'rt-cache'),'OMP_NUM_THREADS':str(2 if compatibility else self.thread_count),'OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1'}
                for name in ('SOFTLOAF_RT_SUPERPIXEL','SOFTLOAF_RT_SECONDARY_PROFILE','SOFTLOAF_RT_SECONDARY_OUTPUT','SOFTLOAF_RT_NATIVE_OUTPUT'):env.pop(name,None)
                if preview and shared:env['SOFTLOAF_RT_SUPERPIXEL']='1'
                for route,icc in self.profiles.items():(tmp/(route+'.icc')).write_bytes(icc)
                if shared:env.update(SOFTLOAF_RT_SECONDARY_PROFILE=str(tmp/'srgb.icc'),SOFTLOAF_RT_SECONDARY_OUTPUT=str(tmp/'srgb.tif'))
                pp3=tmp/'ap1.pp3';pp3.write_text(BASE_PP3.replace('OutputBPC=false','OutputBPC=false\nOutputProfile=file:'+(tmp/'ap1.icc').as_posix()))
                command=[str(cli),'-q','-a','-Y','-p',str(pp3),'-o',str(tmp/'ap1.tif'),'-t','-b32','-c',str(raw_source)]
                record.write_text(json.dumps({'source_sha256':digest,'stage':'half' if preview else 'full','status':'developing','decode_attempts':1}))
                started=time.monotonic();event('raw.development.started',source_id=key,stage='half' if preview else 'full')
                try:run=subprocess.run(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180,check=False)
                except (OSError,subprocess.TimeoutExpired) as error:
                    event('raw.development.finished',source_id=key,stage='half' if preview else 'full',status='failed',elapsed_ms=round((time.monotonic()-started)*1000,3),error=error)
                    raise RecipeError('raw_development','RAW 开发未完成，请检查文件与运行环境。') from None
                event('raw.development.finished',source_id=key,stage='half' if preview else 'full',status=run.returncode,elapsed_ms=round((time.monotonic()-started)*1000,3))
                if run.returncode or not (tmp/'ap1.tif').is_file():raise RecipeError('raw_development','RawTherapee 无法开发这张 RAW。')
                message=run.stdout.decode(errors='replace');messages=[message]
                geometry=re.findall(r'SOFTLOAF_RAW_GEOMETRY (\d+) (\d+) ([12])',message)
                with tifffile.TiffFile(tmp/'ap1.tif') as tif:original_size=[tif.pages[0].imagewidth,tif.pages[0].imagelength]
                if shared:
                    if message.count('SOFTLOAF_RAW_DECODE 1')!=1 or 'SOFTLOAF_RAW_HANDOFF shared-Lab' not in message:raise RecipeError('raw_handoff','RAW 读取器没有确认一次解码、两路输出。')
                    if preview:
                        if len(geometry)!=1:raise RecipeError('raw_handoff','RAW 预览尺寸记录不完整。')
                        original_size=list(map(int,geometry[0][:2]))
                        if geometry[0][2]=='1':
                            from .raw_handoff import half_compatibility_output
                            original_size=half_compatibility_output(tmp/'ap1.tif',self.profiles['ap1'])
                            half_compatibility_output(tmp/'srgb.tif',self.profiles['srgb'])
                else:
                    from .raw_handoff import half_compatibility_output,srgb_from_ap1
                    if preview:original_size=half_compatibility_output(tmp/'ap1.tif',self.profiles['ap1'])
                    srgb_from_ap1(tmp/'ap1.tif',tmp/'srgb.tif',self.profiles)
                for route,icc in self.profiles.items():
                    with tifffile.TiffFile(tmp/(route+'.tif')) as tif:
                        page=tif.pages[0]
                        if page.imagewidth*page.imagelength>64_000_000:raise RecipeError('invalid_image','当前 RAW 入口支持不超过 6400 万像素。')
                        pixels=tifffile.memmap(tmp/(route+'.tif'),mode='r')
                        if pixels.dtype!=np.float32 or pixels.ndim!=3 or pixels.shape[-1]!=3:raise RecipeError('raw_handoff','RAW 输出必须是有限的 32 位浮点 RGB。')
                        from .imaging.sources import MappedSource
                        from .imaging.blocks import Region
                        validation=MappedSource.from_array(pixels)
                        for row in range(0,validation.height,32):
                            with validation.read(Region(0,row,validation.width,min(32,validation.height-row))) as block:
                                if not np.isfinite(block).all():raise RecipeError('raw_handoff','RAW 输出包含非有限数值。')
                        if page.tags.get(34675) is None or page.tags[34675].value!=icc:raise RecipeError('raw_handoff','RAW 输出 ICC 与声明的空间不符。')
                    del pixels
                method=('bayer-2x2' if geometry and geometry[0][2]=='2' else 'RT full demosaic → half-size output (non-quartet geometry)') if preview and shared else 'official RT full demosaic → half-size output' if preview else 'not applicable'
                metadata={'schema':'softloaf.raw-handoff/2','source_sha256':digest,'engine':'RawTherapee 5.12','engine_sha256':self.files.digest(cli),'settings_sha256':signature,
                    'processing_mode':'preview' if preview else 'full-quality','raw_decode_count':1,'handoff':'shared RT Lab → independent ICC outputs' if shared else 'official RT → float AP1 → relative-colorimetric LCMS2 sRGB',
                    'worker_threads':int(re.findall(r'SOFTLOAF_RAW_THREADS (\d+)',message)[0]) if 'SOFTLOAF_RAW_THREADS ' in message else 2 if compatibility else self.thread_count,
                    'requested_worker_threads':self.thread_count,'preview_method':method,'original_size':original_size,'decoded_size':[page.imagewidth,page.imagelength],
                    'camera_database_sha256':hashlib.sha256(json.dumps(self.resource_hashes,sort_keys=True).encode()).hexdigest(),
                    'camera_profile':'RawTherapee cameraICC auto (DCP/ICC, otherwise camera matrix)',**white_balance_record(messages),
                    'reference':'standard sRGB D65, relative colorimetric, float32 TIFF','film_input':'linear ACEScg AP1 D60 float32 TIFF → ACEScct AP1 D60 LUT coordinates',
                    'display_rendering':False,'dcp_tone_curve':False,'dcp_look_table':False,'dcp_hue_sat_map':True,
                    'files':{r:self.files.digest(tmp/(r+'.tif')) for r in self.profiles}}
                (tmp/'manifest.json').write_text(json.dumps(metadata,indent=2));directory.mkdir(exist_ok=True)
                for name in ('srgb.tif','ap1.tif','manifest.json'):(tmp/name).replace(directory/name)
            committed=record.with_suffix('.tmp');committed.write_text(json.dumps({'status':'complete','decode_attempts':1,'source_sha256':digest,'stage':'half' if preview else 'full','directory':key}));committed.replace(record)
            return self._read(directory,routes)

    def _cached(self,directory,routes,signature=None,source_digest=None):
        try:
            if not self._valid(directory,signature):return None
            result=self._read(directory,routes)
            if source_digest and result['metadata']['source_sha256']!=source_digest:return None
            os.utime(directory,None)  # Immutable manifest; directory time tracks LRU.
            return result
        except (OSError,ValueError,tifffile.TiffFileError):return None

    def _prune(self,current,budget=4*1024**3):
        # RAW developments are retained source stages, never disposable LRU entries.
        # Only downstream renditions have an automatic disk budget.
        return

    def _valid(self,directory,signature=None):
        try:
            metadata=json.loads((directory/'manifest.json').read_text())
            return metadata['settings_sha256']==(signature or self.signature) and all(self.files.digest(directory/(r+'.tif'))==metadata['files'][r] for r in self.profiles)
        except (OSError,ValueError,KeyError):return False

    @staticmethod
    def _read(directory,routes=('srgb','ap1')):
        # RT writes uncompressed TIFF. Read-only mappings avoid two full RGB copies
        # on every hit; the OS pages in only what the downstream tile touches.
        result={r:tifffile.memmap(directory/(r+'.tif'),mode='r') for r in routes}
        result['metadata']=json.loads((directory/'manifest.json').read_text())
        return result
