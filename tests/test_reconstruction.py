import numpy as np
import pytest

from spectral_lut.reconstruction import LocalSpectralPrior, RootPolynomialPrior


def fixtures():
    kernel = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [.2, .4, .1]])
    rng = np.random.default_rng(91)
    spectra = rng.uniform(.03, .9, (100, 4))
    return spectra, kernel


def test_local_reconstruction_preserves_unprojected_RGB():
    spectra, kernel = fixtures()
    model = LocalSpectralPrior(spectra, kernel, [0.2, .7, .1], neighbors=24, ridge=.001)
    rgb = spectra[::7] @ kernel
    restored = model.reconstruct(rgb, project=False)
    np.testing.assert_allclose(restored @ kernel, rgb, atol=1e-10)


def test_local_reconstruction_is_exposure_homogeneous_and_black_is_zero():
    spectra, kernel = fixtures()
    model = LocalSpectralPrior(spectra, kernel, [.2, .7, .1], neighbors=24, ridge=.001)
    rgb = spectra[::7] @ kernel
    np.testing.assert_allclose(model.reconstruct(rgb*4), model.reconstruct(rgb)*4, atol=1e-10)
    np.testing.assert_array_equal(model.reconstruct(np.zeros((1, 3))), np.zeros((1, 4)))


def test_local_reconstruction_roundtrip_retains_model_parameters(tmp_path):
    spectra, kernel = fixtures()
    model = LocalSpectralPrior(spectra, kernel, [.2, .7, .1], neighbors=24, ridge=.001)
    path = tmp_path/'prior.npz'
    model.save(path, family='reversal')
    with pytest.raises(ValueError, match='family'):
        LocalSpectralPrior.load(path, family='negative')
    restored = LocalSpectralPrior.load(path, family='reversal')
    rgb = spectra[::7] @ kernel
    np.testing.assert_array_equal(model.reconstruct(rgb), restored.reconstruct(rgb))


def test_local_reconstruction_handles_single_RGB_and_rejects_nan():
    spectra, kernel = fixtures()
    model = LocalSpectralPrior(spectra, kernel, [.2, .7, .1], neighbors=24, ridge=.001)
    assert model.reconstruct([.1, .2, .3]).shape == (4,)
    with pytest.raises(ValueError):
        model.reconstruct([np.nan, 0, 0])


def test_root_polynomial_prior_preserves_color_and_exposure():
    spectra, kernel = fixtures()
    model = RootPolynomialPrior(spectra, kernel, degree=3, ridge=1e-5)
    rgb = spectra[::7] @ kernel
    np.testing.assert_allclose(model.reconstruct(rgb, project=False) @ kernel, rgb, atol=1e-10)
    np.testing.assert_allclose(model.reconstruct(rgb*4), model.reconstruct(rgb)*4, atol=1e-10)
    np.testing.assert_array_equal(model.reconstruct([0, 0, 0]), np.zeros(4))


def test_root_prior_does_not_modify_source_weights_and_roundtrips(tmp_path):
    spectra, kernel = fixtures()
    weights = np.linspace(1., 2., len(spectra))
    original = weights.copy()
    model = RootPolynomialPrior(spectra, kernel, weights=weights)
    np.testing.assert_array_equal(weights, original)
    path = tmp_path/'negative.npz'
    model.save(path, 'negative')
    with pytest.raises(ValueError, match='family'):
        RootPolynomialPrior.load(path, 'reversal')
    restored = RootPolynomialPrior.load(path, 'negative')
    rgb = spectra[:7] @ kernel
    np.testing.assert_array_equal(restored.reconstruct(rgb), model.reconstruct(rgb))
