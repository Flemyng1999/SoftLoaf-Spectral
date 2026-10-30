"""Protected native-camera and sRGB stages from one direct RawTherapee decode."""
from ..file_lock import acquire_file_lock
import hashlib
import json
import os
from pathlib import Path
import subprocess
from collections import OrderedDict
import threading
import tifffile
import re
import numpy as np
from spectral_app.storage import DataStorage


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class RawFiles:
    def __init__(self,executable,cache):
        self.executable=Path(executable).resolve()
        self.storage=DataStorage.configured()
        self.cache=self.storage.directory(cache)
        self.verified=OrderedDict();self.verify_lock=threading.RLock()
        self.storage.activate_temporary_directory()

    def _verified_digest(self,path):
        path=Path(path).resolve()
        def stamp():
            s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        with self.verify_lock:
            before=stamp();cached=self.verified.get(path)
            if cached and cached[0]==before:self.verified.move_to_end(path);return cached[1]
            value=digest(path)
            if stamp()!=before:raise ValueError('Scan file changed during verification')
            self.verified[path]=(before,value);self.verified.move_to_end(path)
            while len(self.verified)>1024:self.verified.popitem(last=False)
            return value

    def verify_source(self,source,expected_sha256=None):
        identity=self._verified_digest(source)
        if expected_sha256 is not None and identity!=expected_sha256:raise ValueError('Imported RAW identity changed; original stage was not replaced')
        return identity

class RTScanRaw(RawFiles):
    contract='scan-camera-rt/1; RT native unit gain before WB and DCP; sRGB D65; shared original decode'
    def develop(self,source,*,stage='half',expected_sha256=None):
        from ..rawtherapee import BASE_PP3
        from spectral_lut.display import rgb_profile
        import struct
        self.storage.validate()
        if stage not in ('half','full'):raise ValueError('Unknown RAW stage')
        source=Path(source).resolve();identity=self.verify_source(source,expected_sha256)
        profile=bytearray(rgb_profile('sRGB'));profile[24:36]=struct.pack('>6H',2026,1,1,0,0,0)
        key=hashlib.sha256((identity+self.contract+BASE_PP3+stage).encode()+profile).hexdigest()
        folder=self.cache/key;folder.mkdir(exist_ok=True)
        with (folder/'lock').open('a+b') as lock:
            acquire_file_lock(lock)
            manifest=folder/'manifest.json';ledger=folder/'decode.json'
            if manifest.exists():
                record=json.loads(manifest.read_text())
                for name in ('camera','srgb'):
                    path=folder/(name+'.tif')
                    if not path.is_file() or self._verified_digest(path)!=record[name+'_sha256']:raise ValueError('Corrupt retained RT RAW stage; explicit rebuild required')
                return folder
            if ledger.exists():raise ValueError('Interrupted retained RT RAW stage; explicit rebuild required')
            ledger.write_text(json.dumps({'source_sha256':identity,'stage':stage,'decode_attempts':1,'contract':self.contract}))
            (folder/'srgb.icc').write_bytes(profile)
            settings=BASE_PP3.replace('OutputBPC=false','OutputBPC=false\nOutputProfile=file:'+(folder/'srgb.icc').as_posix())
            (folder/'settings.pp3').write_text(settings)
            from ..raw_runtime import RawRuntime
            env={**RawRuntime(Path(__file__).resolve().parents[2]).environment(self.executable),'RT_SETTINGS':str(folder/'settings'),'RT_CACHE':str(folder/'rt-cache'),'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1'}
            for name in ('SOFTLOAF_RT_SUPERPIXEL','SOFTLOAF_RT_SECONDARY_PROFILE','SOFTLOAF_RT_SECONDARY_OUTPUT','SOFTLOAF_RT_NATIVE_OUTPUT'):env.pop(name,None)
            env['SOFTLOAF_RT_NATIVE_OUTPUT']=str(folder/'camera.working.tif')
            if stage=='half':env['SOFTLOAF_RT_SUPERPIXEL']='1'
            run=subprocess.run([str(self.executable),'-q','-a','-Y','-p',str(folder/'settings.pp3'),'-o',str(folder/'srgb.working.tif'),'-t','-b32','-c',str(source)],
                capture_output=True,text=True,env=env,timeout=240)
            if run.returncode:raise ValueError('RawTherapee RAW development failed: '+(run.stdout+run.stderr)[-1500:])
            message=run.stdout
            geometry=re.findall(r'SOFTLOAF_SCAN_SOURCE (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',message)
            if message.count('SOFTLOAF_RAW_DECODE 1')!=1 or len(geometry)!=1 or 'SOFTLOAF_RAW_NATIVE unit-gain-camera' not in message:
                raise ValueError('RT 未确认同次 RAW 解码生成两路数据，请更新 RAW 引擎。')
            left,top,width,height,binning,rotation=map(int,geometry[0])
            if stage=='half' and binning==1:
                # Non-quartet sensors use RT full demosaic, then reduce retained
                # outputs together. This never opens the original RAW again.
                from ..imaging.resample import resize_rows
                for name in ('camera','srgb'):
                    path=folder/(name+'.working.tif');a=tifffile.memmap(path,mode='r')
                    h,w=a.shape[:2];small=folder/(name+'.half.tif');dtype=a.dtype
                    output=tifffile.memmap(small,shape=((h+1)//2,(w+1)//2,3),dtype=dtype,photometric='rgb',
                        extratags=[(34675,'B',len(profile),bytes(profile),False)] if name=='srgb' else [])
                    try:
                        def write(y,v):output[y:y+len(v)]=np.clip(np.rint(v),0,65535).astype(dtype) if name=='camera' else v
                        resize_rows(a,(output.shape[1],output.shape[0]),write)
                        output.flush()
                    finally:a._mmap.close();output._mmap.close()
                    small.replace(path)
                binning=2
            with tifffile.TiffFile(folder/'camera.working.tif') as image:
                shape=image.pages[0].shape
                if image.pages[0].dtype!=np.uint16 or len(shape)!=3 or shape[-1]!=3 or 34675 in image.pages[0].tags:raise ValueError('Invalid RT native camera handoff')
            with tifffile.TiffFile(folder/'srgb.working.tif') as image:
                if image.pages[0].shape!=shape or image.pages[0].dtype!=np.float32 or image.pages[0].tags[34675].value!=bytes(profile):raise ValueError('RT 两路图像尺寸或 sRGB 编码不一致。')
            if digest(source)!=identity:raise ValueError('RAW changed while developing')
            record={'schema':'softloaf.scan-raw/2','source_sha256':identity,'stage':stage,'contract':self.contract,
                'engine_sha256':digest(self.executable),'encoding':'linear native camera RGB / uint16 full range; RT no WB or characterization',
                'engine':{'name':'RawTherapee 5.12','raw_decode_count':1,'native_white_balance':'off','display_encoding':'sRGB D65',
                    'width':shape[1],'height':shape[0],'left':left,'top':top,'bin':binning,'rotation':rotation,'sensor_width':width,'sensor_height':height}}
            for name in ('camera','srgb'):
                (folder/(name+'.working.tif')).replace(folder/(name+'.tif'));record[name+'_sha256']=digest(folder/(name+'.tif'))
            (folder/'manifest.working.json').write_text(json.dumps(record,indent=2));(folder/'manifest.working.json').replace(manifest)
            return folder
