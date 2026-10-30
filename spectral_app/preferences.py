"""Machine UI preferences, separate from film recipes and calibration identity."""
import json
from pathlib import Path
import threading
import uuid

LANGUAGES=('system','zh-CN','en')


class Preferences:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.language='system';self.warning=None
        if self.path.exists():
            try:
                saved=json.loads(self.path.read_text(encoding='utf-8'))
                if saved.get('schema')!=1 or saved.get('language') not in LANGUAGES:raise ValueError()
                self.language=saved['language']
            except (OSError,ValueError,TypeError,AttributeError):self.warning='语言设置损坏，原文件保留。'

    def state(self):
        with self.lock:return {'ok':True,'language':self.language,'languages':list(LANGUAGES),'warning':self.warning}

    def update(self,request):
        value=request.get('language')
        if value not in LANGUAGES:raise ValueError('Unsupported UI language')
        with self.lock:
            if self.warning:raise ValueError(self.warning)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_text(json.dumps({'schema':1,'language':value}),encoding='utf-8');temporary.replace(self.path)
            finally:temporary.unlink(missing_ok=True)
            self.language=value
        return self.state()
