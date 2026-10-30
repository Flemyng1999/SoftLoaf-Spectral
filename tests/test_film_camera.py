import numpy as np

from spectral_lut.camera import dcp_matrix_xyz, hue_sat_map
from spectral_lut.film import ReversalFilm, fit_neutral_amounts


def test_neutral_fit_recovers_known_independent_density_channels():
    targets = np.array([[3, 2, 1], [2, 1, 0.5], [1, 0.5, 0.2]])
    amounts = fit_neutral_amounts(np.eye(3), np.eye(3), targets)
    np.testing.assert_allclose(amounts, targets, atol=1e-9)


def test_more_reversal_exposure_increases_transmittance_and_endpoint_holds():
    film = ReversalFilm(np.array([-2, 0, 2]), np.array([[2]*3, [1]*3, [0]*3]),
                        np.eye(3)/0.18, np.eye(3), np.eye(3), 0, 1)
    values = np.array([[0.000018]*3, [0.0018]*3, [0.18]*3, [18]*3, [180]*3])
    np.testing.assert_allclose(film.evaluate(values),
                               [[0.01]*3, [0.01]*3, [0.1]*3, [1]*3, [1]*3], atol=1e-12)


def test_dcp_white_balance_uses_native_neutral_and_forward_matrix_direction():
    neutral = np.array([0.5, 1, 0.25])
    forward = np.array([[0.5, 0.3, 0.1], [0.2, 0.7, 0.1], [0.05, 0.1, 0.75]])
    # Two neutral exposures must differ by a scalar, not by hue.
    actual = dcp_matrix_xyz([[0.09, 0.18, 0.045], [0.045, 0.09, 0.0225]], neutral, forward)
    np.testing.assert_allclose(actual, [[0.162, 0.18, 0.162], [0.081, 0.09, 0.081]])


def test_hue_table_wraps_hue_and_scales_saturation_and_value():
    table = np.empty((1, 2, 2, 3))  # value, hue, saturation, adjustment
    table[...] = [120, 1, 1]
    np.testing.assert_allclose(hue_sat_map([[0.4, 0.1, 0.1], [0.1, 0.4, 0.1]], table),
                               [[0.1, 0.4, 0.1], [0.1, 0.1, 0.4]], atol=1e-12)
