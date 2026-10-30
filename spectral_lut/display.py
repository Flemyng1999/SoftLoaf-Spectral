"""Pinned SDR display graphs and deterministic RGB output profiles.

The primary config is the official ACES 2.0 CG config v4.0.0. OpenDRT remains
an independent view whose supplied cube renders into Rec.709. Old ACES views
in saved recipes are migrated to ACES 2.0 before use.
"""
import copy
import io
import hashlib
import struct
import threading

import colour
import numpy as np
from PIL import ImageCms
import PyOpenColorIO as ocio


ACES_CONFIG = 'cg-config-v4.0.0_aces-v2.0_ocio-v2.5'
ACES_VIEW = 'ACES 2.0 - SDR 100 nits'
COLORIMETRIC_VIEW = 'Display Encoding'
ROUTE_DEFAULT_VIEWS = {'slide': COLORIMETRIC_VIEW, 'print': COLORIMETRIC_VIEW,
                       'negative': ACES_VIEW}
DISPLAY_DEFAULTS_VERSION = 1
VIEWS = {COLORIMETRIC_VIEW: '色度转换', ACES_VIEW: 'ACES 2.0 · SDR 100 nits',
         'Default': 'OpenDRT Default', 'Colorful': 'OpenDRT Colorful',
         'Umbra': 'OpenDRT Umbra',
         'Bypass': 'Bypass · 原始数值'}
# Recognition only: no retired rendering graphs are constructed or executed.
RETIRED_ACES_VIEWS = frozenset(('ACES 1.0 - SDR Video','ACES 1.1 - SDR Video'))


def migrate_aces_display(recipe):
    result=copy.deepcopy(recipe)
    if isinstance(result,dict) and isinstance(result.get('display'),dict):
        view=result['display'].get('view')
        if isinstance(view,str) and view in RETIRED_ACES_VIEWS:
            result['display']['view']=ACES_VIEW
            if type(result.get('revision')) is int and result['revision']>=1:
                result['revision']+=1
    return result


def migrate_display_defaults(recipe):
    """Migrate the old shared Default once; preserve subsequent chosen views.

    Legacy files cannot distinguish an explicit OpenDRT Default choice from
    the old automatically filled default. Both migrate on first load under
    this policy. The original file is not modified; revision records the change.
    Other existing views retain their selection (retired ACES views use 2.0).
    """
    result=migrate_aces_display(recipe)
    if not isinstance(result,dict):return result
    display=result.get('display');route=result.get('route')
    if (isinstance(display,dict) and route in ROUTE_DEFAULT_VIEWS
            and 'defaults_version' not in display and display.get('view') in VIEWS):
        if display['view']=='Default':
            display['view']=ROUTE_DEFAULT_VIEWS[route]
            if type(result.get('revision')) is int and result['revision']>=1:
                result['revision']+=1
        display['defaults_version']=DISPLAY_DEFAULTS_VERSION
    return result


TARGETS = {'sRGB': {'label': 'sRGB', 'style': 'sRGB', 'space': 'sRGB',
                    'aces_display':'sRGB - Display', 'aces_view':ACES_VIEW+' (Rec.709)'},
           'Display P3': {'label': 'Display P3', 'style': 'DisplayP3', 'space': 'Display P3',
                          'aces_display':'Display P3 - Display', 'aces_view':ACES_VIEW+' (P3 D65)'},
           'Rec.1886': {'label': 'Rec.709 / Rec.1886',
                        'style': 'REC.1886-REC.709', 'space': 'sRGB',
                        'aces_display':'Rec.1886 Rec.709 - Display', 'aces_view':ACES_VIEW+' (Rec.709)'}}


def _matrix(values):
    m = np.eye(4); m[:3, :3] = values
    return ocio.MatrixTransform(matrix=m.ravel().tolist())


def _adapt(source, destination):
    return colour.adaptation.matrix_chromatic_adaptation_VonKries(
        colour.xy_to_XYZ(source), colour.xy_to_XYZ(destination), transform='Bradford')


def rgb_profile(target):
    """Own matrix/TRC ICC v4 profile; no imported device/vendor calibration."""
    if target == 'sRGB':
        return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    linear_ap1 = target == 'ACEScg Linear'
    cs = colour.RGB_COLOURSPACES['ACEScg' if linear_ap1 else TARGETS[target]['space']]
    d50 = np.array([.3457, .3585])
    adapt = _adapt(cs.whitepoint, d50)
    colorants = adapt @ cs.matrix_RGB_to_XYZ
    fixed = lambda x: struct.pack('>i', round(float(x)*65536))
    xyz = lambda x: b'XYZ '+bytes(4)+b''.join(fixed(v) for v in x)
    def text(value):
        encoded = value.encode('utf-16-be')
        return b'mluc'+bytes(4)+struct.pack('>II', 1, 12)+b'enUS'+struct.pack('>II',len(encoded),28)+encoded
    if linear_ap1:
        trc = b'para'+bytes(4)+struct.pack('>HH',0,0)+fixed(1)
    elif target == 'Rec.1886':
        trc = b'para'+bytes(4)+struct.pack('>HH',0,0)+fixed(2.4)
    else:
        trc = b'para'+bytes(4)+struct.pack('>HH',4,0)+b''.join(
            fixed(v) for v in [2.4,1/1.055,.055/1.055,1/12.92,.04045,0,0])
    tags = {'desc':text('SoftLoaf '+target), 'cprt':text('SoftLoaf Spectral; standard RGB colorimetry'),
            'wtpt':xyz(colour.xy_to_XYZ(d50)),
            'chad':b'sf32'+bytes(4)+b''.join(fixed(v) for v in adapt.ravel())}
    for i, c in enumerate('rgb'):
        tags[c+'XYZ'] = xyz(colorants[:,i]); tags[c+'TRC'] = trc
    offset = 128+4+12*len(tags); entries = []; payload = bytearray()
    for tag, value in tags.items():
        entries.append(tag.encode('ascii')+struct.pack('>II',offset+len(payload),len(value)))
        payload.extend(value); payload.extend(bytes((-len(value)) % 4))
    header = bytearray(128)
    struct.pack_into('>I',header,0,offset+len(payload))
    header[4:8]=b'SLsp'; struct.pack_into('>I',header,8,0x04300000)
    header[12:24]=b'mntrRGB XYZ '; struct.pack_into('>6H',header,24,2026,1,1,0,0,0)
    header[36:44]=b'acspAPPL'; struct.pack_into('>I',header,64,1)
    header[68:80]=xyz(colour.xy_to_XYZ(d50))[8:]; header[80:84]=b'SLsp'
    result=bytes(header)+struct.pack('>I',len(tags))+b''.join(entries)+payload
    ImageCms.ImageCmsProfile(io.BytesIO(result))  # Validate with LittleCMS.
    return result


class DisplayManager:
    def __init__(self, config, config_path):
        self.config_id=ACES_CONFIG
        self.config=ocio.Config.CreateFromBuiltinConfig(ACES_CONFIG)
        self.config.validate()
        self.config_metadata={'id':ACES_CONFIG,'config_version':'4.0.0','aces_version':'2.0',
            'profile':'2.5','sha256':hashlib.sha256(self.config.serialize().encode()).hexdigest()}
        self.opendrt_config=config; self.groups={}; self.processors={}
        self._trace_cache={}; self._trace_lock=threading.Lock()
        self.profiles={target:rgb_profile(target) for target in TARGETS}
        ap1=colour.RGB_COLOURSPACES['ACEScg']
        srgb=colour.RGB_COLOURSPACES['sRGB']; d65=srgb.whitepoint
        for target in TARGETS:
            for view in VIEWS:
                graph=ocio.GroupTransform()
                resolver=config
                if view==COLORIMETRIC_VIEW:
                    # Observed colorimetry is already image-formed. Do not
                    # send it through an AP1 bridge or an OpenDRT encoding LUT.
                    graph.appendTransform(ocio.BuiltinTransform(
                        style='DISPLAY - CIE-XYZ-D65_to_'+TARGETS[target]['style']))
                    resolver=ocio.Config.CreateRaw()
                elif view==ACES_VIEW:
                    # Invert the official AP0/D60→XYZ/D65 utility, then execute
                    # the official config's target-specific ACES 2.0 view once.
                    graph.appendTransform(ocio.BuiltinTransform(
                        style='UTILITY - ACES-AP0_to_CIE-XYZ-D65_BFD',direction=ocio.TRANSFORM_DIR_INVERSE))
                    graph.appendTransform(ocio.DisplayViewTransform(src='ACES2065-1',
                        display=TARGETS[target]['aces_display'],view=TARGETS[target]['aces_view']))
                    resolver=self.config
                else:
                    graph.appendTransform(_matrix(ap1.matrix_XYZ_to_RGB @ _adapt(d65,ap1.whitepoint)))
                    display='Rec.1886' if target=='Rec.1886' else 'sRGB Display'
                    actual_view='OpenDRT v1.0.0 '+view if view in ('Default','Colorful','Umbra') else view
                    if actual_view not in list(config.getViews(display)):
                        raise ValueError('Missing packaged display/view: '+display+'/'+actual_view)
                    graph.appendTransform(ocio.DisplayViewTransform(src='ACEScg',display=display,view=actual_view))
                    graph.appendTransform(ocio.ColorSpaceTransform(src=display,dst='Rec.709 - Linear'))
                    if target=='sRGB':
                        graph.appendTransform(ocio.FileTransform(src=str((config_path.parent/'transfer_functions/eocf_srgb_to_linear.spi1d').resolve()),interpolation=ocio.INTERP_LINEAR))
                    else:
                        graph.appendTransform(_matrix(srgb.matrix_RGB_to_XYZ))
                        graph.appendTransform(ocio.BuiltinTransform(style='DISPLAY - CIE-XYZ-D65_to_'+TARGETS[target]['style']))
                resolved=resolver.getProcessor(graph)
                self.groups[target,view]=resolved.createGroupTransform()
                self.processors[target,view]=resolved.getDefaultCPUProcessor()

    @staticmethod
    def _apply(processor, values):
        buffer=np.array(values,dtype=np.float32,order='C',copy=True)
        processor.applyRGB(buffer)
        return buffer.astype(np.float64)

    def _trace_operations(self,view,target):
        key=target,view
        with self._trace_lock:
            if key in self._trace_cache:return self._trace_cache[key]
            # Merge identity/adjacent operations as OCIO does for execution.
            graph=self.config.getProcessor(self.groups[key]).getOptimizedProcessor(
                ocio.OPTIMIZATION_DEFAULT).createGroupTransform()
            operations=[]
            for transform in graph:
                processor=ocio.Config.CreateRaw().getProcessor(transform).getDefaultCPUProcessor()
                record={'operator':type(transform).__name__,
                        'direction':'inverse' if transform.getDirection()==ocio.TRANSFORM_DIR_INVERSE else 'forward'}
                if isinstance(transform,ocio.MatrixTransform):
                    matrix=np.asarray(transform.getMatrix()).reshape(4,4)
                    offset=np.asarray(transform.getOffset())
                    if transform.getDirection()==ocio.TRANSFORM_DIR_INVERSE:
                        matrix=np.linalg.inv(matrix);offset=-matrix@offset
                    record.update(kind='matrix',matrix=matrix.tolist(),offset=offset.tolist())
                else:
                    record['kind']='function'
                    if isinstance(transform,ocio.Lut1DTransform):
                        record.update(kind='lut1d',length=transform.getLength(),
                                      interpolation=str(transform.getInterpolation()).split('.')[-1])
                    elif isinstance(transform,ocio.Lut3DTransform):
                        record.update(kind='lut3d',grid=transform.getGridSize(),
                                      interpolation=str(transform.getInterpolation()).split('.')[-1])
                    if hasattr(transform,'getStyle'):record['style']=str(transform.getStyle()).split('.')[-1]
                    if isinstance(transform,ocio.ExponentWithLinearTransform):
                        record.update(gamma=list(transform.getGamma()),offset=list(transform.getOffset()))
                    ramp=np.linspace(0,1,65)
                    values=self._apply(processor,np.repeat(ramp[:,None],3,axis=1))
                    record['curve']={'input':ramp.tolist(),
                        'output':[[float(v) if np.isfinite(v) else None for v in row] for row in values],
                        'meaning':'Equal-component input slice v1=v2=v3, 0–1; actual operator evaluation, not a wavelength spectrum or an assumption that internal coordinates are RGB'}
                    if isinstance(transform,ocio.FixedFunctionTransform):
                        record['parameters']=list(transform.getParams())
                operations.append((record,processor))
            self._trace_cache[key]=operations
            return operations

    def trace(self,xyz,view,target='sRGB'):
        value=np.asarray(xyz,dtype=np.float64)
        steps=[]
        for record,processor in self._trace_operations(view,target):
            output=self._apply(processor,value)
            steps.append({**record,'input':value.tolist(),'output':output.tolist()})
            value=output
        bounded=np.clip(value,0,1)
        steps.append({'kind':'clamp','operator':'RangeTransform','minimum':0,'maximum':1,
                      'input':value.tolist(),'output':bounded.tolist()})
        return {'input_xyz_d65':np.asarray(xyz).tolist(),'target':target,'view':view,
                'input_space':'relative XYZ / D65','output_space':target+' / D65 encoded RGB',
                'matrix_convention':'column vector; output = matrix × input + offset; alpha = 1',
                'optimization':'OCIO OPTIMIZATION_DEFAULT; identity/adjacent operations may be merged',
                'steps':steps,'output':bounded.tolist()}

    def metadata(self, view, target='sRGB'):
        return {'view':view,'label':VIEWS[view], 'target':target,
                'ocio_config':dict(self.config_metadata),
                **({'display':TARGETS[target]['aces_display'],'display_view':TARGETS[target]['aces_view']} if view==ACES_VIEW else {}),
                'primaries':TARGETS[target]['space']+' / D65',
                'encoding':'gamma 2.4' if target=='Rec.1886' else 'standard piecewise sRGB transfer function',
                'rendering_gamut':('P3-D65' if target=='Display P3' else 'Rec.709')
                    if view==ACES_VIEW else
                    'Rec.709 (packaged OpenDRT v1.0.0)' if view in ('Default','Colorful','Umbra') else
                    TARGETS[target]['space'] if view==COLORIMETRIC_VIEW else 'selected OCIO view',
                'rendering':'colorimetric' if view==COLORIMETRIC_VIEW else 'scene_to_display' if view!= 'Bypass' else 'diagnostic_bypass',
                'gamut_handling':'component clipping at final encoded 0–1; no perceptual gamut mapping',
                'chain':('XYZ D65 → target linear RGB matrix → target transfer function → clamp 0–1'
                    if view==COLORIMETRIC_VIEW else 'XYZ D65 → selected OCIO view → target RGB encoding; bounded 0–1'),
                'ocio_version':ocio.__version__}
