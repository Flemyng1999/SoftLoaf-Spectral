"""Bounded immutable scan imports; acquisition metadata, never pixel processing."""
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
from ..rawtherapee import RAW_EXTENSIONS
from .targets import load_target

CAPTURE=('Model','LensModel','ISO','ExposureTime','FNumber')


def read_metadata(path):
    try:
        run=subprocess.run(['exiftool','-j','-n',*['-'+k for k in (*CAPTURE,'FocalLength','FocalLengthIn35mmFormat','Make')],str(path)],capture_output=True,text=True,check=True,timeout=20)
        raw=json.loads(run.stdout)[0];result={k:raw.get(k) for k in (*CAPTURE,'FocalLength','FocalLengthIn35mmFormat','Make')}
        if not result['Model'] or any(not isinstance(result[k],(int,float)) or result[k]<=0 for k in ('ISO','ExposureTime','FNumber')):
            raise ValueError('RAW 缺少机型、ISO、快门或光圈信息。')
        return result
    except (FileNotFoundError,subprocess.SubprocessError,json.JSONDecodeError):
        raise ValueError('无法读取 RAW 拍摄条件，请检查 ExifTool 和文件格式。') from None


def match_capture(reference,actual):
    for key in CAPTURE:
        if reference.get(key)!=actual.get(key):raise ValueError('拍摄条件不匹配：'+key+'；请使用同光源、机身、镜头、ISO、曝光和光圈的标定。')


class ScanAssets:
    def __init__(self,root,admit=lambda n:None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.admit=admit
    def import_stream(self,stream,length,name,kind):
        name=Path(str(name).replace('\\','/')).name[:180]
        if kind not in ('raw','reference') or not name:raise ValueError('导入类型或文件名无效。')
        limit=256*1024**2 if kind=='raw' else 2*1024**2
        if type(length)!=int or not 0<length<=limit:raise ValueError('文件超过大小限制。')
        if Path(name).suffix.lower() not in (RAW_EXTENSIONS if kind=='raw' else {'.csv'}):raise ValueError('请选择 RAW 或规定的透射光谱 CSV。')
        self.admit(length+4096);temporary=self.root/(uuid.uuid4().hex+'.working');digest=hashlib.sha256()
        try:
            with temporary.open('wb') as output:
                remaining=length
                while remaining:
                    block=stream.read(min(512*1024,remaining))
                    if not block:raise ValueError('文件上传中断，未保存半成品。')
                    output.write(block);digest.update(block);remaining-=len(block)
            sha=digest.hexdigest();identifier='a'+sha;path=self.root/(identifier+('.raw' if kind=='raw' else '.csv'))
            if kind=='raw':info=read_metadata(temporary)
            else:
                target=load_target(temporary);info={'target':target['target'],'numbered':target['numbered'],'keyed':target['keyed'],'id_scheme':target['id_scheme']}
            if path.exists():
                with path.open('rb') as existing:
                    if hashlib.file_digest(existing,'sha256').hexdigest()!=sha:raise ValueError('已保留的原件发生变化，未覆盖。')
            else:temporary.replace(path)
            return {'id':identifier,'name':name,'kind':kind,'sha256':sha,'bytes':length,'metadata':info}
        finally:temporary.unlink(missing_ok=True)
    def path(self,asset):
        identifier=asset['id']
        if len(identifier)!=65 or identifier[0]!='a' or any(c not in '0123456789abcdef' for c in identifier[1:]):raise ValueError('无效原件身份。')
        return self.root/(identifier+('.raw' if asset['kind']=='raw' else '.csv'))
