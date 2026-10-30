"""Pinned results of the separate sampling-database model selections."""
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from spectral_lut.reconstruction import LocalSpectralPrior,RootPolynomialPrior
from spectral_lut.sampling_db import SamplingDatabase
from experiments.hsi_raw_lut import sha

LEGACY={'schema':'softloaf.input-prior/1','id':'smooth-baseline/1','family':'shared-legacy'}

class InputPriors:
    def __init__(self,kernel,wavelengths,directory=None):
        self.directory=Path(directory or Path(__file__).resolve().parents[1]/'artifacts/sampling-database')
        report_path=self.directory/'report.json'
        pinned=json.loads((Path(__file__).resolve().parents[1]/'data/sampling-priors-manifest.json').read_text())
        if sha(report_path)!=pinned['report_sha256']:raise ValueError('Sampling selection report changed')
        self.report=json.loads(report_path.read_text());self.models={};self.identities={}
        grid=np.asarray(wavelengths,dtype=float)
        for family,kind in [('reversal',LocalSpectralPrior),('negative',RootPolynomialPrior)]:
            record=self.report['families'][family];selected=record['model'];path=self.directory/selected['file']
            if sha(path)!=selected['sha256']:raise ValueError('Optimized spectral prior changed: '+family)
            model=kind.load(path,family)
            if model.kernel.shape!=kernel.shape or not np.allclose(model.kernel,kernel,rtol=0,atol=2e-14):raise ValueError('Optimized prior input kernel differs')
            database=self.directory/record['database']
            if sha(database)!=pinned['families'][family]['database_sha256']:raise ValueError('Sampling database changed: '+family)
            with SamplingDatabase.open(database,family) as db:
                if db.metadata('selected_input_model')!=selected:raise ValueError('Selected database model differs')
                conditions=db.metadata('conditions')
                lo,hi,step=conditions['processing_grid_nm']
                if not np.array_equal(grid,np.arange(lo,hi+step*.5,step)) or not np.allclose(conditions['input_kernel'],kernel,rtol=0,atol=2e-14):raise ValueError('Sampling database spectral grid or color integral differs')
            self.models[family]=model
            self.identities[family]={'schema':'softloaf.input-prior/1','id':selected['name'],'family':family,
                'model_sha256':selected['sha256'],'database_sha256':sha(database),'selection_report_sha256':sha(report_path),
                'wavelengths_nm':grid.tolist(),'input':'linear ACEScg AP1 D60; fixed D65 input color integral',
                'selection_scope':'E100 development output error' if family=='reversal' else 'negative input-spectrum RMSE; no APD/print output optimization',
                'training_count':512 if family=='reversal' else record['eligible_fit_samples'],
                'rights':'local reference only; source-specific model/LUT distribution review pending'}
    def descriptor(self,route):return copy.deepcopy(self.identities['reversal' if route=='slide' else 'negative'])
    def validate(self,descriptor,route):
        if descriptor==LEGACY:return copy.deepcopy(LEGACY)
        expected=self.descriptor(route)
        if descriptor is not None and descriptor!=expected:raise ValueError('配方的采样模型、片类或来源版本不匹配。')
        return expected
    def reconstruct(self,rgb,route,descriptor=None):
        if descriptor==LEGACY:return None
        return self.models['reversal' if route=='slide' else 'negative'].reconstruct(rgb)
    def pack(self,builder,route,descriptor):
        if descriptor==LEGACY:builder.count('PRIOR',0);return
        model=self.models['reversal' if route=='slide' else 'negative']
        if isinstance(model,LocalSpectralPrior):
            if len(model.normalized_rgb)>512:raise ValueError('Local GPU prior exceeds declared training capacity')
            builder.count('PRIOR',1);builder.count('PN',len(model.normalized_rgb));builder.count('PK',model.neighbors)
            builder.add('PRGB',model.normalized_rgb);builder.add('PSPECTRA',model.normalized_spectra)
            builder.add('PSCALE',model.scale);builder.add('PLUMA',model.luminance);builder.add('PRIDGE',model.ridge)
        else:
            builder.count('PRIOR',2);builder.count('PN',len(model.scale));builder.add('PSPECTRA',model.coefficients)
            builder.add('PSCALE',model.scale)
        builder.add('BASIS',model.base)

    def verify_sources(self):
        for family,identity in self.identities.items():
            record=self.report['families'][family]
            for path,expected in [(self.directory/record['database'],identity['database_sha256']),
                                  (self.directory/record['model']['file'],identity['model_sha256']),
                                  (self.directory/'report.json',identity['selection_report_sha256'])]:
                if sha(path)!=expected:raise ValueError('Optimized sampling sources changed during LUT export: '+family)
