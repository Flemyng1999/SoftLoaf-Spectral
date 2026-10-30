"""Analytic-grid coefficient fitting for an experimental trilinear LUT."""

import numpy as np


def fit_trilinear_nodes(values):
    """Fit N^3 coefficients to exact reference samples on a (2N-1)^3 grid.

    Minimize unweighted squared output error for trilinear interpolation at
    every supplied sample, using separability. This does not fit photographs
    or minimize display-code error. Coefficients may overshoot; the caller
    must declare any constraints and validate their effects separately.
    """
    values = np.asarray(values, dtype=np.float64)
    m = values.shape[0]
    if (values.ndim != 4 or values.shape != (m, m, m, 3) or m < 3 or m % 2 != 1
            or not np.isfinite(values).all()):
        raise ValueError('Expected a finite odd-sized (2N-1)^3 three-channel grid.')
    n = (m+1)//2
    position = np.arange(m)/2
    left = np.minimum(position.astype(int), n-2)
    fraction = position-left
    matrix = np.zeros((m, n))
    matrix[np.arange(m), left] = 1-fraction
    matrix[np.arange(m), left+1] = fraction
    inverse = np.linalg.pinv(matrix)
    return np.einsum('ia,jb,kc,abco->ijko', inverse, inverse, inverse, values, optimize=True)
