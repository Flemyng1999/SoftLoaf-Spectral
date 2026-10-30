"""Disposable, versioned display renditions; independent of retained RAW stages."""
import base64
from collections import OrderedDict
from concurrent.futures import Future
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
import threading
import uuid

_ASSET=re.compile(r'^/previews/([0-9a-f]{64})\.png$')


class RenditionCache:
    def __init__(self,directory,budget=2*1024**3,memory_budget=128*1024**2):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.objects=self.directory/'objects';self.objects.mkdir(exist_ok=True)
        self.budget=budget;self.memory_budget=memory_budget;self.lock=threading.RLock()
        self.memory=OrderedDict();self.bytes=0;self.verified={};self.pending={}
        self.hits=0;self.misses=0;self.enabled=True;self.transient=OrderedDict()

    @staticmethod
    def identity(value):return hashlib.sha256(value.encode()).hexdigest()

    def _remember(self,digest,data):
        if digest in self.memory:self.bytes-=len(self.memory.pop(digest))
        if len(data)<=self.memory_budget:
            while self.memory and self.bytes+len(data)>self.memory_budget:
                _,old=self.memory.popitem(last=False);self.bytes-=len(old)
            self.memory[digest]=data;self.bytes+=len(data)

    def _asset(self,digest):
        path=self.transient.get(digest,self.objects/(digest+'.png'));stat=path.stat()
        identity=(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        if self.verified.get(digest)!=identity:
            data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Changed rendition asset')
            self.verified[digest]=identity;self._remember(digest,data)
        if digest in self.memory:self.memory.move_to_end(digest);return self.memory[digest]
        data=path.read_bytes();self._remember(digest,data);return data

    def asset(self,url):
        match=_ASSET.fullmatch(url)
        if not match:raise FileNotFoundError('Unknown preview asset')
        with self.lock:
            try:return self._asset(match[1])
            except (ValueError,OSError):raise FileNotFoundError('Preview asset unavailable') from None

    def asset_path(self,url):
        match=_ASSET.fullmatch(url)
        if not match:raise FileNotFoundError('Unknown preview asset')
        with self.lock:
            try:
                self._asset(match[1])
                return self.transient.get(match[1],self.objects/(match[1]+'.png'))
            except (ValueError,OSError):raise FileNotFoundError('Preview asset unavailable') from None

    def _lookup(self,key):
        if not self.enabled:return None
        path=self.directory/(key+'.json')
        try:
            entry=json.loads(path.read_text())
            if entry['schema']!=1 or entry['key']!=key:return None
            for digest in entry['assets']:self._asset(digest)
            os.utime(path,None)
            return entry['result']
        except (OSError,ValueError,KeyError,TypeError):return None

    def _store(self,key,result):
        result=copy.deepcopy(result);assets=set()
        def visit(value):
            if isinstance(value,dict):
                url=value.get('data_url')
                if isinstance(url,str):
                    if url.startswith('data:image/png;base64,'):
                        data=base64.b64decode(url.split(',',1)[1],validate=True);digest=hashlib.sha256(data).hexdigest()
                        if hasattr(self,'admit_write'):self.admit_write(len(data))
                        path=(self.session_directory if not self.enabled else self.objects)/(digest+'.png')
                        if not self.enabled:self.transient[digest]=path
                        try:valid=path.is_file() and self._asset(digest)==data
                        except (ValueError,OSError):valid=False
                        if not valid:
                            tmp=path.with_name(uuid.uuid4().hex+'.tmp');tmp.write_bytes(data);tmp.replace(path)
                            self.verified.pop(digest,None)
                        self._remember(digest,data);value['data_url']='/previews/'+digest+'.png';assets.add(digest)
                    else:
                        match=_ASSET.fullmatch(url)
                        if match:assets.add(match[1])
                for child in value.values():visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        visit(result)
        path=self.directory/(key+'.json');tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        if not self.enabled:
            self.trim_session(result)
            return result
        tmp.write_text(json.dumps({'schema':1,'key':key,'assets':sorted(assets),'result':result},separators=(',',':')));tmp.replace(path)
        self._prune(key)
        return result

    def _prune(self,current):
        if not self.enabled or self.pending:return  # Producers can still hold asset dependencies.
        entries=[]
        for path in self.directory.glob('*.json'):
            if not re.fullmatch(r'[0-9a-f]{64}\.json',path.name):continue
            try:
                entry=json.loads(path.read_text());entries.append((path.stat().st_mtime_ns,path,entry))
            except (OSError,ValueError):continue
        sizes={p.stem:p.stat().st_size for p in self.objects.glob('*.png') if re.fullmatch(r'[0-9a-f]{64}',p.stem)}
        referenced={d for _,_,entry in entries for d in entry.get('assets',[])}
        total=sum(sizes.get(d,0) for d in referenced)+sum(p.stat().st_size for _,p,_ in entries)
        for _,path,entry in sorted(entries,key=lambda e:e[0]):
            if total<=self.budget:break
            if path.stem==current or path.stem in self.pending:continue
            # Delete only a recognized rendition record, never a source stage.
            path.unlink(missing_ok=True)
            remaining=[e for e in entries if e[1].exists()]
            keep={d for _,_,e in remaining for d in e.get('assets',[])}
            total=sum(sizes.get(d,0) for d in keep)+sum(p.stat().st_size for _,p,_ in remaining)
        referenced={d for _,p,e in entries if p.exists() for d in e.get('assets',[])}
        for digest in sizes.keys()-referenced:
            (self.objects/(digest+'.png')).unlink(missing_ok=True);self.verified.pop(digest,None)
            if digest in self.memory:self.bytes-=len(self.memory.pop(digest))

    def _present(self,result,transport):
        result=copy.deepcopy(result)
        if transport=='url':return result
        def visit(value):
            if isinstance(value,dict):
                url=value.get('data_url')
                if isinstance(url,str) and _ASSET.fullmatch(url):value['data_url']='data:image/png;base64,'+base64.b64encode(self.asset(url)).decode('ascii')
                for child in value.values():visit(child)
            elif isinstance(value,list):
                for child in value:visit(child)
        visit(result);return result

    def get_or_compute(self,identity,produce,transport='inline'):
        if transport not in ('inline','url'):raise ValueError('Unknown preview transport')
        key=self.identity(identity)
        with self.lock:
            cached=self._lookup(key)
            if cached is not None:self.hits+=1;return self._present(cached,transport)
            future=self.pending.get(key);leader=future is None
            if leader:future=Future();self.pending[key]=future;self.misses+=1
        if not leader:return self._present(future.result(),transport)
        try:
            produced=produce()
            with self.lock:
                result=self._store(key,produced);future.set_result(result)
            return self._present(result,transport)
        except BaseException as error:
            if not future.done():future.set_exception(error)
            raise
        finally:
            with self.lock:
                self.pending.pop(key,None)
                if not self.pending:self._prune(key)

    def staging_path(self):
        with self.lock:
            root=self.session_directory if not self.enabled else self.objects
            return root/(uuid.uuid4().hex+'.tmp')

    def adopt_png(self,path):
        from .imaging.files import digest_file
        with self.lock:
            digest=digest_file(path);root=self.session_directory if not self.enabled else self.objects
            destination=root/(digest+'.png')
            Path(path).replace(destination)
            if not self.enabled:self.transient[digest]=destination;self.transient.move_to_end(digest)
            self.verified.pop(digest,None)
            return '/previews/'+digest+'.png'

    def configure(self,*,budget,memory_budget,enabled=True):
        with self.lock:
            self.budget=budget;self.memory_budget=memory_budget;self.enabled=enabled
            while self.memory and self.bytes>memory_budget:
                _,old=self.memory.popitem(last=False);self.bytes-=len(old)
            if not enabled and (not hasattr(self,'session_directory') or self.session_directory.parent!=self.directory):
                self.session_directory=Path(tempfile.mkdtemp(prefix='session-',dir=self.directory))
                (self.session_directory/'.session.json').write_text(json.dumps({'application':'SoftLoaf Spectral','pid':os.getpid(),'schema':1}))

    def clear(self):
        with self.lock:
            if self.pending:raise ValueError('正在生成预览，请稍后清理。')
            self.memory.clear();self.bytes=0;self.verified.clear()
            for path in self.directory.glob('*.json'):
                if re.fullmatch(r'[0-9a-f]{64}\.json',path.name):path.unlink(missing_ok=True)
            for path in self.objects.glob('*.png'):
                if re.fullmatch(r'[0-9a-f]{64}\.png',path.name):path.unlink(missing_ok=True)
            for path in self.transient.values():path.unlink(missing_ok=True)
            self.transient.clear()

    def trim_session(self,result):
        # Keep this response plus a small set of recent frames while disk caching is off.
        if self.enabled:return
        while len(self.transient)>16:
            digest,path=self.transient.popitem(last=False);path.unlink(missing_ok=True)
            self.verified.pop(digest,None)
            if digest in self.memory:self.bytes-=len(self.memory.pop(digest))
