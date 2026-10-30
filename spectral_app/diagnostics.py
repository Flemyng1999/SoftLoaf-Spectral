"""Bounded local diagnostics. No image pixels, paths, user text or credentials."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import time
import traceback
import uuid

FIELDS=frozenset(('job_id','action','phase','completed','total','elapsed_ms','status',
    'backend','requested_backend','reason','stage','cache_hit','source_id','code','port',
    'language','version','pid','compiler','device','count','shader_sha256','native_code','source_line'))


class DiagnosticLog:
    def __init__(self,directory,*,max_bytes=2*1024**2,backups=4):
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        self.session=uuid.uuid4().hex;self.started=time.monotonic();self.lock=threading.RLock()
        self.logger=logging.Logger('softloaf.diagnostics.'+self.session)
        self.logger.propagate=False
        self.handler=RotatingFileHandler(directory/'events.jsonl',maxBytes=max_bytes,backupCount=backups,encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(message)s'));self.logger.addHandler(self.handler)

    def event(self,name,*,error=None,**fields):
        record={'schema':1,'time':datetime.now(timezone.utc).isoformat(),'session':self.session,
            'monotonic_ms':round((time.monotonic()-self.started)*1000,3),'event':name}
        for key,value in fields.items():
            if key in FIELDS and isinstance(value,(str,int,float,bool,type(None))):
                record[key]=(value.split(' · ',1)[0] if key=='phase' else value)[:160] if isinstance(value,str) else value
        if error is not None:
            record['error_type']=type(error).__name__
            record['stack']=[{'module':Path(f.filename).name,'function':f.name,'line':f.lineno}
                for f in traceback.extract_tb(error.__traceback__)[-12:]]
        with self.lock:self.logger.info(json.dumps(record,ensure_ascii=False,allow_nan=False))

    def close(self):
        with self.lock:self.logger.removeHandler(self.handler);self.handler.close()


_runtime=None


def configure(directory):
    global _runtime
    if _runtime:_runtime.close()
    _runtime=DiagnosticLog(directory)
    return _runtime


def event(name,**fields):
    # Diagnostics must never change pixel processing or a job's terminal state.
    if _runtime:
        try:_runtime.event(name,**fields)
        except (OSError,ValueError,TypeError):pass


def install_exception_hooks():
    import sys
    def uncaught(kind,error,tb):
        event('service.uncaught',error=error)
        sys.stderr.write(json.dumps({'ok':False,'error_type':kind.__name__,'diagnostics':'events.jsonl'})+'\n')
    sys.excepthook=uncaught
    threading.excepthook=lambda args:event('thread.uncaught',error=args.exc_value)
