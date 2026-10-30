"""Explicit float64 reference mode. Never selected after a Metal failure."""
from spectral_lut.reference import acescct_decode

class ReferenceRenderer:
    def __init__(self,model):self.model=model
    def render(self,values,recipe,acescct=False,purpose='display',spectral=False):
        rgb=acescct_decode(values) if acescct else values
        compute=self.model.sample_spectra if spectral else self.model.sample
        return compute(rgb,**self.model.parameters(recipe))['display_rgb' if purpose=='display' else 'XYZ']
    def interpolate_cube(self,cube,points,view,target,display=False,prepared=None):
        values=cube.apply(points)
        return self.model.render(values,view,target) if display else values
