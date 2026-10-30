"""Owned disposable caches. Retained RAW developments are never eviction candidates."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from .policy import DEFAULTS,validate,budgets
from ..imaging.files import digest_file
from experiments.gui_recipe_server import RecipeError

MARKER='.softloaf-spectral-cache.json'
RECORD=re.compile(r'[0-9a-f]{64}\.json$')
ASSET=re.compile(r'[0-9a-f]{64}\.png$')


def owned(root,adopt=False):
    root=Path(root)
    if root.is_symlink():raise ValueError('缓存目录不能是链接。')
    root.mkdir(parents=True,exist_ok=True);marker=root/MARKER
    if marker.exists():
        value=json.loads(marker.read_text())
        if value.get('application')!='SoftLoaf Spectral' or value.get('schema')!=1:raise ValueError('目录不属于此应用的缓存。')
    else:
        if any(root.iterdir()) and not adopt:raise ValueError('请选择空目录；不会覆盖已有文件。')
        marker.write_text(json.dumps({'application':'SoftLoaf Spectral','schema':1,'id':uuid.uuid4().hex}))
    objects=root/'objects'
    if objects.is_symlink():raise ValueError('缓存文件目录不能是链接。')
    objects.mkdir(exist_ok=True)
    return root


def recognized(root):
    for path in root.iterdir():
        if path.is_file() and not path.is_symlink() and RECORD.fullmatch(path.name):yield path
    for path in (root/'objects').iterdir():
        if path.is_file() and not path.is_symlink() and ASSET.fullmatch(path.name):yield path


def cleanup_sessions(root):
    for folder in root.glob('session-*'):
        if not folder.is_dir() or folder.is_symlink():continue
        try:
            record=json.loads((folder/'.session.json').read_text())
            if record.get('application')!='SoftLoaf Spectral' or type(record.get('pid'))!=int:continue
            try:os.kill(record['pid'],0);continue
            except ProcessLookupError:pass
            except PermissionError:continue
            for path in folder.iterdir():
                if not path.is_symlink() and path.is_file() and (ASSET.fullmatch(path.name) or re.fullmatch(r'[0-9a-f]{32}\.tmp',path.name)):path.unlink(missing_ok=True)
            if set(p.name for p in folder.iterdir())=={'.session.json'}:
                (folder/'.session.json').unlink();folder.rmdir()
        except (ValueError,OSError,KeyError):continue


class CacheSettings:
    def __init__(self,output,storage,renditions,inputs,raw_directory):
        self.path=Path(output)/'app-settings.json';self.storage=storage;self.cache=renditions;self.inputs=inputs
        self.default=renditions.directory.resolve();self.raw=Path(raw_directory);self.lock=threading.RLock()
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='cache-maintenance');self.job={'status':'idle'};self.inventory={}
        self.settings=copy.deepcopy(DEFAULTS)
        if self.path.is_file():
            saved=json.loads(self.path.read_text());validate({k:v for k,v in saved.items() if k in set(DEFAULTS)-{'schema','old_locations'}})
            if saved.get('schema')!=1:raise ValueError('缓存设置版本无法读取。')
            self.settings.update(saved)
        root=self._location(self.settings['location'])
        owned(root,adopt=root==self.default);cleanup_sessions(root)
        self.cache.directory=root;self.cache.objects=root/'objects'
        self._apply();self.start({'action':'refresh'})

    def _location(self,value):
        self.storage.validate();root=Path(value) if value else self.default
        if not root.is_absolute() or (self.storage.volume and not root.resolve().is_relative_to(self.storage.volume.resolve())):raise ValueError('缓存位置必须在 T7 Touch 上。')
        if root.resolve()==self.storage.volume:raise ValueError('不能把磁盘根目录作为缓存。')
        return root

    def _save(self,settings):
        temporary=self.path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temporary.write_text(json.dumps(settings,ensure_ascii=False,indent=2));temporary.replace(self.path)

    def _apply(self):
        disk=shutil.disk_usage(self.cache.directory);self.limits=budgets(self.settings,disk.total)
        self.cache.configure(budget=self.limits['disk_bytes'],memory_budget=self.limits['encoded_bytes'],enabled=self.settings['disk_mode']!='off')
        self.inputs.configure(self.limits['inputs_bytes'])
        self.cache.admit_write=self.admit_write

    def admit_write(self,size):
        self.storage.validate()
        if shutil.disk_usage(self.cache.directory).free-size<self.limits['reserve_bytes']:raise RecipeError('disk_space','T7 可用空间已到预留值，请清理空间或调整设置。')

    def state(self):
        try:self.storage.validate()
        except RuntimeError as error:return {'ok':False,'error':{'code':'external_storage','message':str(error)}}
        with self.lock:
            return {'ok':True,'settings':copy.deepcopy(self.settings),'limits':copy.deepcopy(self.limits),
                'location':str(self.cache.directory),'default_location':str(self.default),'job':copy.deepcopy(self.job),
                'inventory':copy.deepcopy(self.inventory),'free_bytes':shutil.disk_usage(self.cache.directory).free,
                'memory_used_bytes':self.cache.bytes+self.inputs.bytes}

    def update(self,request):
        try:
            values=validate(request.get('settings',{}))
            if 'location' in values:raise ValueError('请使用“更改位置”。')
            with self.lock:
                if self.job['status']=='running':raise ValueError('正在整理缓存，请稍后修改设置。')
                updated={**self.settings,**values};self._save(updated);self.settings=updated;self._apply()
            return self.state()
        except (ValueError,OSError,RuntimeError) as error:raise RecipeError('cache_settings',str(error)) from None

    def start(self,request):
        action=request.get('action')
        if action=='cancel':
            if hasattr(self,'cancel'):self.cancel.set()
            return self.state()
        if action not in ('refresh','clear','memory','move','old'):raise RecipeError('cache_settings','未知的缓存操作。')
        with self.lock:
            if self.job['status']=='running':raise RecipeError('cache_busy','正在整理缓存，请稍后再试。')
            self.cancel=threading.Event();self.job={'status':'running','action':action,'completed_bytes':0,'total_bytes':0}
            self.worker.submit(self._run,action,copy.deepcopy(request))
        return self.state()

    def _run(self,action,request):
        try:
            self.storage.validate()
            if action=='memory':
                self.inputs.configure(self.limits['inputs_bytes'],clear=True)
                with self.cache.lock:self.cache.memory.clear();self.cache.bytes=0
            elif action=='clear':
                owned(self.cache.directory);self.cache.clear();cleanup_sessions(self.cache.directory)
            elif action=='move':self._move(request.get('location'))
            elif action=='old':
                for value in self.settings['old_locations']:
                    root=self._location(value)
                    if root==self.cache.directory:continue
                    owned(root)
                    for path in recognized(root):path.unlink(missing_ok=True)
                with self.lock:
                    updated={**self.settings,'old_locations':[]};self._save(updated);self.settings=updated
            self._inventory()
            with self.lock:self.job['status']='cancelled' if self.cancel.is_set() else 'complete'
        except Exception as error:
            with self.lock:self.job.update(status='failed',error=str(error) if isinstance(error,(ValueError,OSError,RuntimeError,RecipeError)) else '缓存操作未完成。')

    def _inventory(self):
        self.storage.validate()
        def size(root):
            if not root.exists():return 0
            result=0
            for base,dirs,files in os.walk(root,followlinks=False):
                if self.cancel.is_set():return result
                for name in files:
                    path=Path(base)/name
                    if not path.is_symlink():
                        try:result+=path.stat().st_size
                        except FileNotFoundError:pass
            return result
        with self.cache.lock:
            display=sum(p.stat().st_size for p in recognized(self.cache.directory))
            session=sum(p.stat().st_size for p in self.cache.transient.values() if p.exists())
        snapshot={'display_bytes':display,'retained_raw_bytes':size(self.raw)+(size(self.storage.root/'scanning/rt-retained-raw') if self.storage.root else 0),'retained_preview_bytes':size(self.inputs.directory),'session_bytes':session}
        with self.lock:self.inventory=snapshot

    def _move(self,value):
        destination=self._location(value)
        if destination==self.cache.directory:return
        # Serialize with the cache, reject active producers instead of moving live assets.
        with self.cache.lock:
            if self.cache.pending:raise ValueError('正在生成预览，请稍后更改位置。')
            old=self.cache.directory;owned(destination)
            files=list(recognized(old));total=sum(p.stat().st_size for p in files)
            if shutil.disk_usage(destination).free-total<self.limits['reserve_bytes']:raise ValueError('目标磁盘空间不足，原位置保持不变。')
            with self.lock:self.job.update(total_bytes=total)
            for source in files:
                if self.cancel.is_set():return
                target=destination/source.relative_to(old);target.parent.mkdir(exist_ok=True)
                temp=target.with_suffix('.copying')
                try:
                    shutil.copyfile(source,temp)
                    if digest_file(source)!=digest_file(temp):raise ValueError('缓存复制校验失败，原位置保持不变。')
                    temp.replace(target)
                finally:temp.unlink(missing_ok=True)
                with self.lock:self.job['completed_bytes']+=source.stat().st_size
            if self.cancel.is_set():return
            with self.lock:
                updated={**self.settings,'location':str(destination) if destination!=self.default else None,
                    'old_locations':list(dict.fromkeys([*self.settings['old_locations'],str(old)]))}
                self._save(updated);self.settings=updated
                self.cache.directory=destination;self.cache.objects=destination/'objects';self.cache.verified.clear();self._apply()
