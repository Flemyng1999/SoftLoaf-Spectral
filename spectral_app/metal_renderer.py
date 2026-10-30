"""Shared Metal image/LUT renderer with retained float64 material preparation.

Only frozen, image-independent kernels/curves are prepared on CPU. Per-pixel
spectral reconstruction, both developments, APD/ADX and OCIO run on the GPU.
"""
from collections import OrderedDict
from pathlib import Path
import hashlib
import re
import threading
import time

import colour
import numpy as np
import PyOpenColorIO as ocio

from experiments.gui_recipe_server import fingerprint
from experiments.hsi_raw_lut import cat,color_kernel,csv,interpolate,D60,D65,AP1
from spectral_lut.metal import MetalBackend
from spectral_lut.shaders import shader_path,hlsl_ocio
from spectral_lut.negative import CDD_TO_CID,EXP_TO_ACES,integrate_density
from spectral_lut.reference import quadrature_widths

SLOTS='NS NV NC PC MODE ROUTE PURPOSE BASIS EXPOSURE AXIS AMOUNTS DYES BASE KERNEL ADAPT PAXIS PAMOUNTS PDYES PBASE PEXPOSURE PRINTFACTOR PREFLASH APD DMIN CID EXPACES AP0XYZ REFMATRIX REFKERNEL FANCHOR PANCHOR FILMSCALE INPUTSCALE PRIOR PN PK PRGB PSPECTRA PSCALE PLUMA PRIDGE LUTSIZE LUTTABLE LUTLOW LUTHIGH LUTDISPLAY'.split()
INDEX={name:i for i,name in enumerate(SLOTS)}
MAX_TILE_PIXELS=65536


class _Pack:
    def __init__(self):self.meta=np.zeros(len(SLOTS),dtype=np.uint32);self.parts=[np.zeros(1,dtype=np.float32)];self.size=1
    def count(self,name,value):self.meta[INDEX[name]]=value
    def add(self,name,value):
        a=np.ascontiguousarray(value,dtype=np.float32).ravel()
        if not np.isfinite(a).all():raise ValueError('Nonfinite Metal material table')
        self.meta[INDEX[name]]=self.size;self.parts.append(a);self.size+=len(a)
    def finish(self):return np.concatenate(self.parts),self.meta


class MetalRenderer:
    def __init__(self,model,library=None,backend=None):
        self.model=model;self.backend=backend or MetalBackend(library);self.programs=OrderedDict();self.plans=OrderedDict();self.lock=threading.RLock()
        self.shader_path=shader_path(self.backend,'spectral');self.shader=self.shader_path.read_text(encoding='utf-8')
        self.shader_sha256=hashlib.sha256(self.shader.encode()).hexdigest();self._stats=threading.local()

    @property
    def last_stats(self):return getattr(self._stats,'last',{})

    def record_image_stats(self,stats):
        self._stats.last=dict(stats)

    def metadata(self):
        d3d=self.backend.name=='d3d12'
        return {'backend':'D3D12' if d3d else 'Metal','device':self.backend.device_name,'precision':'float32','reference_precision':'float64',
            'library_sha256':self.backend.sha256,'spectral_shader_sha256':self.shader_sha256,
            'display':'OCIO native '+('HLSL' if d3d else 'MSL')+' with original 1D/2D/3D textures; no additional display bake',
            'tile_pixels':MAX_TILE_PIXELS,'local_prior_tile_pixels':4096,'max_parameter_bytes':32*1024**2,'max_programs':12,'max_material_plans':16,
            'fallback':'explicitly logged CPU retry on device failure' if d3d else 'none; CPU reference is an explicit startup choice',
            'timing':getattr(self.backend,'timing_kind','Metal command GPU duration'),
            'boundaries':'RawTherapee decode, image-independent float64 fitting, single-point diagnostics and file encoding remain CPU'}

    def _program(self,view,target):
        key=view,target
        with self.lock:
            if key in self.programs:self.programs.move_to_end(key);return self.programs[key]
            d3d=self.backend.name=='d3d12'
            desc=ocio.GpuShaderDesc.CreateShaderDesc();desc.setLanguage(ocio.GPU_LANGUAGE_HLSL_DX11 if d3d else ocio.GPU_LANGUAGE_MSL_2_0);desc.setFunctionName('sl_display');desc.setResourcePrefix('sl_ocio_')
            processor=ocio.Config.CreateRaw().getProcessor(self.model.display_group(view,target)).getDefaultGPUProcessor()
            processor.extractGpuShaderInfo(desc)
            if list(desc.getUniforms()):raise RuntimeError('Dynamic OCIO uniforms are not part of the frozen Metal display contract.')
            text=desc.getShaderText();textures=[];bindings={};typed_bindings={}
            for tex in [*desc.get3DTextures(),*desc.getTextures()]:
                three=hasattr(tex,'edgeLen');dimension=3 if three else 1 if tex.dimensions==desc.TEXTURE_1D else 2
                width=tex.edgeLen if three else tex.width;height=width if three else tex.height;depth=width if three else 1
                channels=3 if three or tex.channel==desc.TEXTURE_RGB_CHANNEL else 1
                values=np.array(tex.getValues(),dtype=np.float32).ravel()
                if len(values)!=width*height*depth*channels:raise RuntimeError('Unexpected OCIO texture layout')
                binding=tex.textureShaderBindingIndex;bindings[tex.textureName]=binding;bindings[tex.samplerName]=binding
                typed_bindings[tex.textureName]=('texture',binding);typed_bindings[tex.samplerName]=('sampler',binding)
                textures.append({'name':tex.textureName,'binding':binding,'dimension':dimension,'width':width,'height':height,'depth':depth,'channels':channels,'linear':int(tex.interpolation==ocio.INTERP_LINEAR),'values':values})
            if d3d:
                text=hlsl_ocio(text,typed_bindings,textures)
                source=self.shader.replace('/* OCIO_SOURCE */',text)
                program=self.backend.program(source,textures);self.programs[key]=program
                while len(self.programs)>12:self.programs.popitem(last=False)
                return program
            signature=text[text.rfind('float4 sl_display('):].split(')')[0].split('(',1)[1]
            parameters=[];arguments=[]
            for parameter in signature.split(','):
                parameter=parameter.strip()
                if not parameter or parameter=='float4 inPixel':continue
                name=parameter.split()[-1]
                if name not in bindings:raise RuntimeError('Unknown OCIO shader parameter '+name)
                annotation='sampler' if parameter.startswith('sampler ') else 'texture'
                parameters.append(f', {parameter} [[{annotation}({bindings[name]})]]');arguments.append(name+', ')
            source=self.shader.replace('/* OCIO_SOURCE */',text).replace('/* OCIO_PARAMETERS */',''.join(parameters)).replace('/* OCIO_ARGUMENTS */',''.join(arguments))
            program=self.backend.program(source,textures);self.programs[key]=program
            # Running tiles hold a strong program reference. Eviction only
            # removes the cache reference; destruction waits for the last user.
            while len(self.programs)>12:self.programs.popitem(last=False)
            return program

    def _plan(self,recipe,spectral=False,purpose='display',acescct=False):
        key=fingerprint(recipe),spectral,purpose,acescct
        with self.lock:
            if key in self.plans:self.plans.move_to_end(key);return self.plans[key]
            m=self.model;r=recipe;p=m.parameters(r);b=_Pack();ns=len(m.source_wavelengths)
            b.count('NS',ns);b.count('MODE',1 if spectral else 2 if acescct else 0);b.count('ROUTE',{'slide':0,'negative':1,'print':2}[r['route']]);b.count('PURPOSE',0 if purpose=='display' else 2 if purpose=='apd' else 3 if purpose=='exposure' else 1)
            b.add('BASIS',m.basis);b.add('INPUTSCALE',1);b.add('FILMSCALE',2**p['exposure_ev'])
            if r['route']=='slide':
                film,_=m.material(p['custom_material']);grid=m.view_wavelengths
                b.count('NC',len(film.log_h));b.add('AXIS',film.log_h);b.add('AMOUNTS',film.amounts);b.add('DYES',film.dyes);b.add('BASE',np.zeros(len(grid)));b.add('FANCHOR',film.gray_log_h)
                b.add('EXPOSURE',film.exposure_kernel*(m.scene_light(p['scene_temperature_k'])/m.source_light)[:,None])
                b.add('KERNEL',color_kernel(grid,m.light(p['viewing_light']),m.cmfs)*p['viewing_gain']);b.add('ADAPT',m.fixed_adaptation)
            else:
                film=m.route_material(r);grid=m.negative_wavelengths
                b.count('NC',len(film.axis));b.add('AXIS',film.axis);b.add('AMOUNTS',film.amounts);b.add('DYES',film.dyes);b.add('BASE',film.base);b.add('FANCHOR',0)
                b.add('EXPOSURE',film.sensitivity*m.scene_light(p['scene_temperature_k'] or 5500,p.get('scene_illuminant'))[:,None]*quadrature_widths(m.source_wavelengths)[:,None]/getattr(film,'denominators',m.negative_denominators))
                if r['route']=='negative':
                    b.add('APD',m.apd_weights/m.apd_weights.sum(0));b.add('DMIN',integrate_density(10**-film.base,m.apd_weights));b.add('CID',CDD_TO_CID.T);b.add('EXPACES',EXP_TO_ACES.T)
                    b.add('AP0XYZ',cat(D60,D65)@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ)
                else:
                    paper=m.route_paper(r);s=r['printing'];modern=s.get('pipeline')=='spectral-v2'
                    if s['light']=='custom':
                        spd=s['custom_spd'];lamp=np.interp(grid,spd['wavelengths_nm'],spd['values']);y=interpolate(csv(m.archive.parent/'data/CIE_xyz_official.csv'),grid)[:,1]*quadrature_widths(grid);lamp*=float(m.printer_light(3200)@y)/float(lamp@y)
                    else:lamp=m.printer_light(s['temperature_k'])
                    if modern:
                        heat,lens=m.printer_optics(s);lamp=lamp*heat*lens
                    filters=s.get('custom_filters',m.printing_assets['filters'] if modern else m.printing_filter_curves)
                    f=np.column_stack([np.interp(grid,filters['wavelengths_nm'],filters['channels'][c]) for c in 'CMY'])
                    from .printing_optics import dichroic_transmission
                    transmission=dichroic_transmission(f,s['filters']) if modern else 10**-(f@np.asarray(s['filters']))
                    b.add('PRINTFACTOR',lamp*transmission*2**s['exposure_ev'])
                    flash=s.get('preflash');b.add('PREFLASH',lamp*dichroic_transmission(f,flash['filters'])*10**-film.base*flash['exposure'] if modern else np.zeros(len(grid)))
                    b.count('PC',len(paper.axis));b.add('PAXIS',paper.axis);b.add('PAMOUNTS',paper.amounts);b.add('PDYES',paper.dyes);b.add('PBASE',paper.base);b.add('PANCHOR',paper.anchor)
                    b.add('PEXPOSURE',paper.sensitivity*quadrature_widths(grid)[:,None]/paper.normal)
                    light=np.interp(grid,p['viewing_light']['wavelengths_nm'],p['viewing_light']['values']) if isinstance(p['viewing_light'],dict) else interpolate(csv(m.archive.parent/f'data/CIE_std_illum_{p["viewing_light"]}.csv'),grid)[:,0]
                    cmf=interpolate(csv(m.archive.parent/'data/CIE_xyz_official.csv'),grid);d50=interpolate(csv(m.archive.parent/'data/CIE_std_illum_D50.csv'),grid)[:,0]
                    b.add('KERNEL',color_kernel(grid,light,cmf)*p['viewing_gain']);b.add('ADAPT',cat(color_kernel(grid,d50,cmf).sum(0),D65))
            if hasattr(m,'input_priors'):m.input_priors.pack(b,r['route'],r.get('input_model'))
            b.count('NV',len(grid));result=b.finish();self.plans[key]=result
            while len(self.plans)>16:self.plans.popitem(last=False)
            return result

    def _run(self,values,plan,view,target,tile_pixels=MAX_TILE_PIXELS,input_ev=0):
        if not 1<=tile_pixels<=MAX_TILE_PIXELS or not np.isfinite(input_ev):raise ValueError('Invalid Metal tile size or input exposure')
        data,metadata=plan
        if metadata[INDEX['PRIOR']]==1 and metadata[INDEX['MODE']]!=1:tile_pixels=min(tile_pixels,4096)
        if input_ev!=0:
            data=data.copy();data[metadata[INDEX['INPUTSCALE']]]=2**input_ev
        channels=int(metadata[INDEX['NS']]) if metadata[INDEX['MODE']]==1 else 3
        source=np.asarray(values)
        if source.ndim<1 or source.shape[-1]!=channels:raise ValueError('Invalid Metal input channels')
        shape=source.shape[:-1];flat=source.reshape(-1,channels);output=np.empty((len(flat),3),dtype=np.float32);gpu=0;start=time.perf_counter()
        program=self._program(view,target)
        for i in range(0,len(flat),tile_pixels):
            output[i:i+tile_pixels],seconds=program.run(flat[i:i+tile_pixels],data,metadata);gpu+=seconds
            # Allow an interactive preview to enter between export tiles.
            if len(flat)>tile_pixels:time.sleep(0)
        self._stats.last={'pixels':len(flat),'gpu_seconds':gpu,'wall_seconds':time.perf_counter()-start,'tiles':(len(flat)+tile_pixels-1)//tile_pixels,'tile_pixels':tile_pixels,'input_channels':channels,'program_sha256':program.source_sha256}
        return output.reshape(*shape,3)

    def render(self,values,recipe,spectral=False,purpose='display',acescct=False,tile_pixels=MAX_TILE_PIXELS,input_ev=0):
        if purpose not in ('display','XYZ','apd','exposure') or (purpose=='apd' and recipe['route']!='negative'):raise ValueError('Unknown Metal output quantity')
        if spectral and acescct:raise ValueError('Spectral reflectance is not ACEScct RGB')
        return self._run(values,self._plan(recipe,spectral,purpose,acescct),recipe['display']['view'],recipe['display'].get('target','sRGB'),tile_pixels,input_ev)

    def _reference_plan(self,kind):
        m=self.model;b=_Pack();b.count('ROUTE',4 if kind=='raw_srgb' else 3);b.count('NS',len(m.source_wavelengths));b.count('MODE',1 if kind=='spectral' else 0);b.add('INPUTSCALE',1)
        b.add('REFMATRIX',np.eye(3) if kind=='xyz' else cat(D60,D65)@AP1.matrix_RGB_to_XYZ)
        kernel=color_kernel(m.source_wavelengths,m.source_light,interpolate(csv(m.archive.parent/'data/CIE_xyz_official.csv'),m.source_wavelengths))
        b.add('REFKERNEL',kernel@cat(kernel.sum(0),D65).T)
        return b.finish()

    def reference(self,values,kind='ap1',input_ev=0):
        if kind not in ('ap1','xyz','raw_srgb','spectral'):raise ValueError('Unknown original-reference input quantity')
        return self._run(values,self._reference_plan(kind),'Display Encoding','sRGB',input_ev=input_ev)
    def display(self,xyz,view,target):return self._run(xyz,self._reference_plan('xyz'),view,target)

    def prepare_cube(self,cube,display=False):
        b=_Pack();b.count('ROUTE',5);b.count('MODE',0);b.count('PURPOSE',0 if display else 1)
        b.count('NS',3);b.count('LUTSIZE',cube.table.shape[0]);b.count('LUTDISPLAY',int(display));b.add('INPUTSCALE',1)
        b.add('LUTLOW',cube.domain_min);b.add('LUTHIGH',cube.domain_max)
        b.add('LUTTABLE',cube.table.transpose(2,1,0,3))
        return b.finish()

    def interpolate_cube(self,cube,values,view,target,display=False,prepared=None):
        return self._run(values,prepared if prepared is not None else self.prepare_cube(cube,display),view,target)
