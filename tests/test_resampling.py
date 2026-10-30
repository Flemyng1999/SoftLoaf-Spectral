import numpy as np
import pytest

from spectral_lut.resampling import fit_trilinear_nodes


def test_fitted_nodes_preserve_affine_and_trilinear_cross_terms():
    axis = np.linspace(-0.25, 0.75, 7)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1)
    r, g, b = np.moveaxis(grid, -1, 0)
    values = np.stack([2*r+g-3*b, r*g+2*b, r*g*b], axis=-1)
    result = fit_trilinear_nodes(values)
    np.testing.assert_allclose(result, values[::2, ::2, ::2], atol=2e-14)


def test_quadratic_coefficients_match_independent_small_least_squares_solution():
    axis = np.linspace(0, 1, 5)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1)
    result = fit_trilinear_nodes(grid**2)
    # For one axis, A.T@A has diagonal (1.25, 1.5, 1.25), off-diagonal .25.
    # Its correction to exact quadratic nodes is (-1/56, -1/28, -1/56).
    coefficients = np.array([-1/56, 0.25-1/28, 1-1/56])
    want = np.stack(np.meshgrid(coefficients, coefficients, coefficients, indexing='ij'), axis=-1)
    np.testing.assert_allclose(result, want, atol=2e-14)


@pytest.mark.parametrize('shape', [(4, 4, 4, 3), (3, 5, 3, 3), (1, 1, 1, 3)])
def test_incompatible_dense_grid_is_rejected(shape):
    with pytest.raises(ValueError):
        fit_trilinear_nodes(np.zeros(shape))
