"""Frozen pointwise rendering adapter; independent from codecs and publication."""
import copy
import time
import numpy as np
import colour
from experiments.hsi_raw_lut import AP1,D60,D65,cat,apply_ocio


class ImageRenderer:
    def __init__(self,model,recipe=None,*,spectral=False,reference=None,input_ev=0,reference_processor=None):
        self.model=model;self.recipe=copy.deepcopy(recipe);self.spectral=spectral;self.reference=reference
        self.input_ev=input_ev;self.processor=reference_processor
        self.parameters=model.parameters(self.recipe) if self.recipe else None
        self.stats={'pixels':0,'gpu_seconds':0.,'wall_seconds':0.,'tiles':0,'tile_pixels':0,'input_channels':0}
        self.max_tile_pixels=65536 if getattr(model,'metal',None) else 512
    def __call__(self,values):
        started=time.perf_counter();gpu=getattr(self.model,'metal',None)
        if gpu:
            result=gpu.reference(values,kind=self.reference,input_ev=self.input_ev) if self.reference else gpu.render(values,self.recipe,spectral=self.spectral,input_ev=self.input_ev)
            stats=gpu.last_stats
            for key in ['pixels','gpu_seconds','tiles']:self.stats[key]+=stats[key]
            self.stats['tile_pixels']=max(self.stats['tile_pixels'],stats['tile_pixels'])
            self.stats['input_channels']=stats['input_channels'];self.stats['program_sha256']=stats['program_sha256']
        else:
            if self.reference=='raw_srgb':
                result=values if self.input_ev==0 else colour.models.eotf_inverse_sRGB(colour.models.eotf_sRGB(values)*np.exp2(self.input_ev))
            elif self.reference:
                xyz=values if self.reference=='xyz' else values@AP1.matrix_RGB_to_XYZ.T@cat(D60,D65).T
                result=apply_ocio(self.processor,xyz*np.exp2(self.input_ev))
            else:
                compute=self.model.sample_spectra if self.spectral else self.model.sample
                result=compute(values*np.exp2(self.input_ev),**self.parameters)['display_rgb']
            self.stats['pixels']+=values.shape[0]*values.shape[1];self.stats['tiles']+=1
            self.stats['tile_pixels']=max(self.stats['tile_pixels'],values.shape[0]*values.shape[1])
        self.stats['wall_seconds']+=time.perf_counter()-started
        return result
