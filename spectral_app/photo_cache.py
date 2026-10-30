"""Disk-backed preview store, bounded decoded memory; independent of immutable originals."""
from collections import OrderedDict
from collections.abc import MutableMapping
from pathlib import Path
import threading
import uuid
import numpy as np


class PreviewStore(MutableMapping):
    def __init__(self,builtins,directory,budget=512*1024*1024):
        self.builtins=dict(builtins);self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.paths={};self.memory=OrderedDict();self.bytes=0;self.budget=budget;self.lock=threading.RLock()
    def __getitem__(self,key):
        with self.lock:
            if key in self.builtins:return self.builtins[key]
            if key in self.memory:self.memory.move_to_end(key);return self.memory[key]
            value=np.load(self.paths[key],allow_pickle=False,mmap_mode='r')
            if value.nbytes<=self.budget:
                while self.memory and self.bytes+value.nbytes>self.budget:
                    _,old=self.memory.popitem(last=False);self.bytes-=old.nbytes
                self.memory[key]=value;self.bytes+=value.nbytes
            return value
    def __setitem__(self,key,value):
        with self.lock:
            if key in self.builtins:self.builtins[key]=value;return
            if not isinstance(key,str) or not key.startswith('user_') or any(c not in '0123456789abcdef' for c in key[5:]):raise KeyError('Invalid preview identifier')
            path=self.directory/(key+'.npy');tmp=path.with_name(uuid.uuid4().hex+'.tmp')
            with tmp.open('wb') as stream:np.save(stream,value,allow_pickle=False)
            tmp.replace(path);self.paths[key]=path
            if key in self.memory:self.bytes-=self.memory.pop(key).nbytes
    def attach(self,key,path):
        """Attach a hash-verified persisted array without decoding all photos at startup."""
        with self.lock:self.paths[key]=Path(path)
    def __delitem__(self,key):
        with self.lock:
            if key in self.builtins:del self.builtins[key]
            else:
                self.paths.pop(key).unlink(missing_ok=True)
                if key in self.memory:self.bytes-=self.memory.pop(key).nbytes
    def __iter__(self):return iter([*self.builtins,*self.paths])
    def __len__(self):return len(self.builtins)+len(self.paths)
    def __contains__(self,key):return key in self.builtins or key in self.paths

    def configure(self,budget,clear=False):
        with self.lock:
            self.budget=budget
            while self.memory and (clear or self.bytes>budget):
                _,old=self.memory.popitem(last=False);self.bytes-=old.nbytes
