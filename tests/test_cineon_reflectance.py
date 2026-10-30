"""Exposure normalization and independent ADX10/16 display checks."""
from pathlib import Path
import numpy as np
from experiments.audit_cineon_reflectance import evaluate


def test_flat_reflectance_exposure_is_normalized_at_18_percent_and_matches_official_adx(tmp_path):
    from spectral_app.model import SpectralModel
    from spectral_lut.native import NativeCore
    root=Path.cwd()
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path/'model',core=NativeCore())
    reflectance=np.array([0,.02,.18,.9])
    values=evaluate(model,np.repeat(reflectance[:,None],len(model.source_wavelengths),axis=1))
    np.testing.assert_allclose(values['relative_film_exposure'],np.repeat((reflectance/.18)[:,None],3,axis=1),rtol=2e-14,atol=2e-14)
    np.testing.assert_allclose(values['ADX10_float'][0],[95]*3,atol=.001)
    assert values['ADX16_minus_16_ADX10_max']==0
    assert values['official_ADX10_and_ACES2_max_codes']<.005


def test_adx_reference_445_is_18_percent_but_cineon_normal_negative_gray_470_is_distinct():
    from spectral_lut.negative import adx_to_aces
    values=adx_to_aces(np.repeat((np.array([445,470])*16)[:,None],3,axis=1))
    np.testing.assert_allclose(values[0], [.18,.18,.1799982],rtol=1e-12,atol=1e-12)
    assert np.all(values[1]>.22)
