"""Installed public Lensfun catalog; freeze its inverse map, never rematch pixels.

No database or code from another product is imported. Source XML hashes and the
public library's coordinate residual accompany each frozen profile selection.
"""
import ctypes as ct
from ctypes.util import find_library
from contextlib import contextmanager
import sys
from ..runtime_paths import packaged, resources, native_directory
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np


def normal(value):return re.sub('[^a-z0-9]','',str(value).lower())


class LensCatalog:
    def __init__(self,directory=None,library=None):
        self.entries={};self.cameras={};self.lib=None
        candidates=[Path(directory)] if directory else [resources()/'assets/lensfun/version_1'] if packaged() else [Path('/opt/homebrew/share/lensfun/version_1'),Path('/usr/share/lensfun/version_1'),Path('/usr/share/lensfun')]
        folder=next((p for p in candidates if p.is_dir()),None)
        if folder:
            for path in sorted(folder.glob('*.xml')):
                raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
                try:root=ET.fromstring(raw)
                except ET.ParseError:continue
                for camera in root.findall('camera'):
                    crop=camera.findtext('cropfactor')
                    if crop:self.cameras[normal(camera.findtext('model'))]=float(crop)
                for node in root.findall('lens'):
                    name=node.findtext('model');maker=node.findtext('maker');points=node.findall('calibration/distortion')
                    if not name or not maker or not points or node.findtext('type','rectilinear')!='rectilinear':continue
                    fragment=ET.tostring(node,encoding='utf-8');key=hashlib.sha256(sha.encode()+fragment).hexdigest()
                    self.entries[key]={'id':key,'name':maker+' · '+name,'maker':maker,'model':name,'source_sha256':sha,'fragment':fragment,
                        'focals':sorted({float(p.get('focal')) for p in points})}
        path=library or (str(native_directory()/('liblensfun.dll' if sys.platform=='win32' else 'liblensfun.1.dylib')) if packaged() else find_library('lensfun') or next((str(p) for p in [Path('/opt/homebrew/lib/liblensfun.dylib'),Path('/usr/local/lib/liblensfun.dylib')] if p.is_file()),None))
        if path:
            try:
                self.lib=ct.CDLL(path);lib=self.lib;P=ct.c_void_p;F=ct.c_float;I=ct.c_int
                lib.lf_db_new.restype=P;lib.lf_db_destroy.argtypes=[P]
                lib.lf_db_load_data.argtypes=[P,ct.c_char_p,ct.c_char_p,ct.c_size_t]
                lib.lf_db_find_lenses_hd.argtypes=[P,P,ct.c_char_p,ct.c_char_p,I];lib.lf_db_find_lenses_hd.restype=ct.POINTER(P)
                lib.lf_free.argtypes=[P]
                lib.lf_modifier_new.argtypes=[P,F,I,I];lib.lf_modifier_new.restype=P
                lib.lf_modifier_initialize.argtypes=[P,P,I,F,F,F,F,I,I,I]
                lib.lf_modifier_destroy.argtypes=[P]
                lib.lf_modifier_apply_geometry_distortion.argtypes=[P,F,F,I,I,ct.POINTER(F)]
            except (OSError,AttributeError):self.lib=None
        self.available=bool(self.lib and self.entries)
    def public(self):return [{k:v for k,v in e.items() if k in ('id','name','focals')} for e in self.entries.values()] if self.available else []
    def match(self,metadata):
        lens=normal(metadata.get('LensModel',''));matches=[e for e in self.entries.values() if normal(e['model'])==lens or normal(e['maker']+e['model'])==lens]
        return {'profile_id':matches[0]['id'] if len(matches)==1 and self.available else None,
            'crop_factor':self.cameras.get(normal(metadata.get('Model'))),'focal_length':metadata.get('FocalLength')}
    @contextmanager
    def oracle(self,identifier,focal,crop,width,height):
        if not self.available or identifier not in self.entries:raise ValueError('Lensfun profile unavailable')
        e=self.entries[identifier];lib=self.lib;db=lib.lf_db_new();modifier=None;lenses=None
        try:
            xml=b'<lensdatabase version="1">'+e['fragment']+b'</lensdatabase>'
            if lib.lf_db_load_data(db,b'SoftLoaf Spectral selected Lensfun profile',xml,len(xml))!=0:raise ValueError('Lensfun profile could not be loaded')
            lenses=lib.lf_db_find_lenses_hd(db,None,e['maker'].encode(),e['model'].encode(),0)
            if not lenses or not lenses[0]:raise ValueError('Lensfun profile could not be resolved')
            modifier=lib.lf_modifier_new(lenses[0],crop,width,height)
            flags=lib.lf_modifier_initialize(modifier,lenses[0],3,focal,5.6,1000.,1.,1,8,0)
            if not flags&8:raise ValueError('Lensfun has no distortion at this focal length')
            def point(x,y):
                out=(ct.c_float*2)()
                if not lib.lf_modifier_apply_geometry_distortion(modifier,x,y,1,1,out):raise ValueError('Lensfun coordinate evaluation failed')
                return [out[0],out[1]]
            yield point
        finally:
            if modifier:lib.lf_modifier_destroy(modifier)
            if lenses:lib.lf_free(ct.cast(lenses,ct.c_void_p))
            lib.lf_db_destroy(db)
    def resolve(self,identifier,focal,crop,width,height):
        if not np.isfinite([focal,crop]).all() or focal<=0 or not .1<=crop<=10:raise ValueError('Enter valid focal length and sensor crop factor')
        if identifier not in self.entries:raise ValueError('找不到所选镜头配置。')
        focals=self.entries[identifier]['focals']
        if focal<min(focals)-.05 or focal>max(focals)+.05:raise ValueError('镜头配置未覆盖这个焦距。')
        centre=np.array([(width-1)/2,(height-1)/2]);norm=.5*np.hypot(width,height)
        radii=np.linspace(.03,.99,40);points=centre+radii[:,None]*centre
        with self.oracle(identifier,float(focal),float(crop),int(width),int(height)) as oracle:
            actual=np.array([oracle(x,y) for x,y in points]);r=np.linalg.norm(points-centre,axis=1)/norm
            scale=np.sum((actual-centre)*(points-centre),axis=1)/np.sum((points-centre)**2,axis=1)
            coefficients=np.polynomial.polynomial.polyfit(r,scale,4)
            y,x=np.mgrid[0:height-1:17j,0:width-1:19j];xy=np.column_stack([x.ravel(),y.ravel()]);delta=xy-centre
            prediction=centre+delta*np.polynomial.polynomial.polyval(np.linalg.norm(delta,axis=1)/norm,coefficients)[:,None]
            error=float(np.max(np.abs(prediction-np.array([oracle(a,b) for a,b in xy]))))
        if error>.01:raise ValueError('Lensfun map cannot be frozen within the coordinate tolerance')
        e=self.entries[identifier]
        return {'radial':coefficients.tolist(),'profile':e['name'],'profile_id':identifier,'source_sha256':e['source_sha256'],
            'library_sha256':hashlib.sha256(Path(self.lib._name).read_bytes()).hexdigest() if Path(self.lib._name).is_file() else None,
            'focal_length':float(focal),'crop_factor':float(crop),'residual_pixels':error,'reference_geometry':[width,height],
            'database_license':'CC-BY-SA-3.0; Lensfun contributors','database_source':'https://github.com/lensfun/lensfun/tree/v0.3.4/data',
            'source':'Lensfun public database and library; distortion only, no vignetting or TCA'}
