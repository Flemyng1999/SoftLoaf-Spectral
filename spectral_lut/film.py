"""Independent-layer reversal-film calculation, evaluated in float64."""

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from .reference import decreasing_projection, density_transmittance


def fit_neutral_amounts(dyes, density_weights, target_density):
    dyes = np.asarray(dyes, dtype=np.float64)
    weights = np.asarray(density_weights, dtype=np.float64)
    weights = weights/weights.sum(axis=0)
    fitted = []
    guess = np.ones(3)
    for target in np.asarray(target_density, dtype=np.float64):
        def residual(a):
            return -np.log10(density_transmittance(a, dyes) @ weights) - target
        solution = least_squares(residual, guess, bounds=(0, np.inf),
                                 ftol=1e-13, xtol=1e-13, gtol=1e-13)
        if not solution.success:
            raise RuntimeError('Neutral-density fitting did not converge.')
        guess = solution.x
        fitted.append(guess)
    fitted = np.asarray(fitted)
    return np.column_stack([decreasing_projection(fitted[:, i]) for i in range(3)])


@dataclass
class ReversalFilm:
    log_h: np.ndarray
    amounts: np.ndarray
    exposure_kernel: np.ndarray
    dyes: np.ndarray
    view_kernel: np.ndarray
    gray_log_h: float
    view_gain: float = 1.8

    def evaluate(self, reflectance):
        reflectance = np.asarray(reflectance, dtype=np.float64)
        h = reflectance @ self.exposure_kernel
        logs = self.gray_log_h + np.log10(np.maximum(h, 1e-30))
        amounts = np.stack([np.interp(logs[..., i], self.log_h, self.amounts[:, i])
                            for i in range(3)], axis=-1)
        return density_transmittance(amounts, self.dyes) @ self.view_kernel * self.view_gain
