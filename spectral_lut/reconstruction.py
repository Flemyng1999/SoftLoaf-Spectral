"""Exposure-homogeneous spectral priors, fitted separately for each film family."""

import numpy as np
from scipy.spatial import cKDTree

from .reference import smooth_reconstruction_basis


def global_spectral_basis(spectra, kernel, ridge=1e-6):
    spectra, kernel = np.asarray(spectra, dtype=np.float64), np.asarray(kernel, dtype=np.float64)
    covariance = spectra.T @ spectra / len(spectra)
    covariance += ridge * np.trace(covariance) / len(kernel) * np.eye(len(kernel))
    return np.linalg.solve(kernel.T @ covariance @ kernel, kernel.T @ covariance)


class LocalSpectralPrior:
    def __init__(self, spectra, kernel, luminance, neighbors=64, ridge=.001):
        self.spectra, self.kernel = np.asarray(spectra, dtype=np.float64), np.asarray(kernel, dtype=np.float64)
        self.luminance = np.asarray(luminance, dtype=np.float64)
        self.neighbors, self.ridge = int(neighbors), float(ridge)
        if (self.spectra.ndim != 2 or self.kernel.shape != (self.spectra.shape[1], 3) or
                self.luminance.shape != (3,) or not np.isfinite(self.spectra).all() or
                not np.isfinite(self.kernel).all() or not np.isfinite(self.luminance).all() or
                self.neighbors < 4 or self.ridge <= 0 or not np.isfinite(self.ridge)):
            raise ValueError('Invalid spectral prior inputs')
        rgb = self.spectra @ self.kernel
        y = rgb @ self.luminance
        valid = y > 1e-8
        if np.count_nonzero(valid) < self.neighbors:
            raise ValueError('Not enough nonblack training spectra')
        self.normalized_spectra = self.spectra[valid] / y[valid, None]
        self.normalized_rgb = self.normalized_spectra @ self.kernel
        self.scale = np.maximum(np.std(self.normalized_rgb[:, [0, 2]], axis=0), 1e-4)
        self.tree = cKDTree(self.normalized_rgb[:, [0, 2]] / self.scale)
        self.base = smooth_reconstruction_basis(self.kernel)

    def reconstruct(self, rgb, project=True, batch=1024):
        rgb = np.asarray(rgb, dtype=np.float64)
        if not rgb.shape or rgb.shape[-1] != 3 or not np.isfinite(rgb).all():
            raise ValueError('Expected finite three-channel RGB')
        shape, points = rgb.shape[:-1], rgb.reshape(-1, 3)
        output = np.empty((len(points), len(self.kernel)), dtype=np.float64)
        for start in range(0, len(points), batch):
            p = points[start:start+batch]
            y = p @ self.luminance
            valid = y > 1e-8
            reconstructed = p @ self.base
            if np.any(valid):
                queries = (p[valid] / y[valid, None])[:, [0, 2]] / self.scale
                distance, index = self.tree.query(queries, k=self.neighbors)
                bandwidth = np.maximum(distance[:, -1:], 1e-12)
                weights = np.maximum(1 - (distance / bandwidth)**2, 0)**2
                zero = weights.sum(axis=1) < 1e-14
                weights[zero] = 1
                weights /= weights.sum(axis=1, keepdims=True)
                x = self.normalized_rgb[index]
                r = self.normalized_spectra[index]
                gram = np.einsum('nk,nki,nkj->nij', weights, x, x)
                regularization = self.ridge * np.trace(gram, axis1=1, axis2=2) / 3
                gram += regularization[:, None, None] * np.eye(3)
                target = np.einsum('nk,nki,nkb->nib', weights, x, r)
                target += regularization[:, None, None] * self.base
                coefficient = np.linalg.solve(gram, p[valid, :, None])[..., 0]
                reconstructed[valid] = np.einsum('ni,nib->nb', coefficient, target)
            output[start:start+len(p)] = np.maximum(reconstructed, 0) if project else reconstructed
        return output.reshape(*shape, len(self.kernel))

    def save(self, path, family):
        if family not in ('reversal', 'negative'):
            raise ValueError('Unknown family')
        np.savez_compressed(path, spectra=self.spectra, kernel=self.kernel, luminance=self.luminance,
                            neighbors=self.neighbors, ridge=self.ridge, family=family,
                            schema='softloaf.local-spectral-prior/1')

    @classmethod
    def load(cls, path, family):
        with np.load(path, allow_pickle=False) as data:
            if str(data['family']) != family or str(data['schema']) != 'softloaf.local-spectral-prior/1':
                raise ValueError('Model family or schema mismatch')
            return cls(data['spectra'], data['kernel'], data['luminance'],
                       int(data['neighbors']), float(data['ridge']))


class RootPolynomialPrior:
    """Learn nonlinear spectral residuals in the color-integral null space.

    Root features remain homogeneous under positive exposure scaling. Their
    signed extension outside positive RGB is an explicit numerical convention.
    """

    def __init__(self, spectra, kernel, degree=3, ridge=1e-5, weights=None):
        spectra, self.kernel = np.asarray(spectra, dtype=np.float64), np.asarray(kernel, dtype=np.float64)
        self.degree, self.ridge = int(degree), float(ridge)
        if (spectra.ndim != 2 or self.kernel.shape != (spectra.shape[1], 3) or
                len(spectra) < 16 or self.degree not in (1, 2, 3) or
                not np.isfinite(spectra).all() or not np.isfinite(self.kernel).all() or
                not np.isfinite(ridge) or ridge <= 0):
            raise ValueError('Invalid root-polynomial prior inputs')
        self.base = smooth_reconstruction_basis(self.kernel)
        rgb = spectra @ self.kernel
        phi = self.features(rgb)
        weights = np.ones(len(spectra)) if weights is None else np.array(weights, dtype=np.float64, copy=True)
        if weights.shape != (len(spectra),) or not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError('Invalid fitting weights')
        weights /= weights.mean()
        self.scale = np.maximum(np.sqrt(np.mean(phi**2, axis=0)), 1e-8)
        phi /= self.scale
        residual = spectra - rgb @ self.base
        gram = phi.T @ (weights[:, None] * phi)
        penalty = self.ridge * np.trace(gram) / len(gram)
        self.coefficients = np.linalg.solve(gram + penalty*np.eye(len(gram)),
                                             phi.T @ (weights[:, None] * residual))

    def features(self, rgb):
        channels = [rgb[..., i] for i in range(3)]
        terms = list(channels)
        for degree in range(2, self.degree+1):
            for r in range(degree+1):
                for g in range(degree-r+1):
                    b = degree-r-g
                    if max(r, g, b) == degree:
                        continue
                    product = channels[0]**r * channels[1]**g * channels[2]**b
                    terms.append(np.sign(product) * np.abs(product)**(1/degree))
        return np.stack(terms, axis=-1)

    def reconstruct(self, rgb, project=True):
        rgb = np.asarray(rgb, dtype=np.float64)
        if not rgb.shape or rgb.shape[-1] != 3 or not np.isfinite(rgb).all():
            raise ValueError('Expected finite three-channel RGB')
        result = rgb @ self.base + (self.features(rgb)/self.scale) @ self.coefficients
        return np.maximum(result, 0) if project else result

    def save(self, path, family):
        if family not in ('reversal', 'negative'):
            raise ValueError('Unknown family')
        np.savez_compressed(path, kernel=self.kernel, base=self.base, scale=self.scale,
                            coefficients=self.coefficients, degree=self.degree, ridge=self.ridge,
                            family=family, schema='softloaf.root-spectral-prior/1')

    @classmethod
    def load(cls, path, family):
        with np.load(path, allow_pickle=False) as data:
            if str(data['family']) != family or str(data['schema']) != 'softloaf.root-spectral-prior/1':
                raise ValueError('Model family or schema mismatch')
            result = cls.__new__(cls)
            result.kernel, result.base, result.scale, result.coefficients = (data[k].copy(order='K')
                for k in ('kernel', 'base', 'scale', 'coefficients'))
            result.degree, result.ridge = int(data['degree']), float(data['ridge'])
            return result
