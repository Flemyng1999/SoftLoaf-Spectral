"""Pointwise scan-output reference. No simulated scene exposure is applied."""
import numpy as np
import colour
from spectral_lut.negative import integrate_density,adx_codes,adx_to_aces
from experiments.hsi_raw_lut import cat,D60,D65
from spectral_lut.display import ACES_VIEW


def amounts_to_aces(model,material,amounts):
    t=10**-(material.base+np.asarray(amounts)@material.dyes.T)
    apd=integrate_density(t,model.apd_weights)
    dmin=integrate_density(10**-material.base,model.apd_weights)
    return adx_to_aces(adx_codes(apd,dmin))


def aces_to_display(model,aces,*,exposure_ev=0):
    aces=np.asarray(aces)*np.exp2(exposure_ev)
    xyz=aces@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ.T@cat(D60,D65).T
    return model.render(xyz,ACES_VIEW,'sRGB')


def amounts_to_display(model,material,amounts,*,exposure_ev=0):
    return aces_to_display(model,amounts_to_aces(model,material,amounts),exposure_ev=exposure_ev)
