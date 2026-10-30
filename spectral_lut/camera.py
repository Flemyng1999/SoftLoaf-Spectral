"""A limited D65 DCP experiment, not a general RAW developer."""

import numpy as np
from colour import HSV_to_RGB, RGB_to_HSV


def dcp_matrix_xyz(raw_fraction, neutral, forward_matrix):
    return (np.asarray(raw_fraction, dtype=np.float64) / neutral) @ np.asarray(forward_matrix).T


def hue_sat_map(rgb, table):
    table = np.asarray(table, dtype=np.float64)
    if table.shape[0] != 1:
        raise ValueError('This experiment supports only value-independent DCP base tables.')
    hsv = RGB_to_HSV(np.maximum(np.asarray(rgb, dtype=np.float64), 0))
    nh, ns = table.shape[1:3]
    h = np.mod(hsv[..., 0], 1)*nh
    s = np.clip(hsv[..., 1], 0, 1)*(ns-1)
    hi, si = np.floor(h).astype(int), np.minimum(np.floor(s).astype(int), ns-2)
    hf, sf = (h-hi)[..., None], (s-si)[..., None]
    a = table[0, hi % nh, si]*(1-sf) + table[0, hi % nh, si+1]*sf
    b = table[0, (hi+1) % nh, si]*(1-sf) + table[0, (hi+1) % nh, si+1]*sf
    adjustment = a*(1-hf) + b*hf
    hsv[..., 0] = np.mod(hsv[..., 0]+adjustment[..., 0]/360, 1)
    hsv[..., 1] = np.minimum(hsv[..., 1]*adjustment[..., 1], 1)
    hsv[..., 2] = np.minimum(hsv[..., 2]*adjustment[..., 2], 1)
    return HSV_to_RGB(hsv)
