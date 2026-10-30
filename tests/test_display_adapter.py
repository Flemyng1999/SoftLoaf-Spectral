from pathlib import Path

import numpy as np
import pytest


def test_opendrt_display_to_srgb_file_encodes_instead_of_decoding_twice(tmp_path):
    from experiments.hsi_raw_lut import D65, apply_ocio, display_processor
    import PyOpenColorIO as ocio
    archive = Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists():
        pytest.skip('Optional official OpenDRT archive is not supplied.')
    processor, config_path = display_processor(archive, tmp_path)
    config = ocio.Config.CreateFromFile(str(config_path.resolve()))
    upstream = config.getProcessor('ACEScg', 'OpenDRT v1.0.0 Default - sRGB Display').getDefaultCPUProcessor()
    neutral = np.array([[0.01]*3, [0.18]*3, [1]*3])
    display_values = apply_ocio(upstream, neutral)
    # Independent IEC sRGB expression, not the package's misleadingly named
    # eocf_srgb_to_linear table or our display adapter.
    linear = display_values**2.2
    expected = np.where(linear <= 0.0031308, 12.92*linear,
                        1.055*linear**(1/2.4)-0.055)
    actual = apply_ocio(processor, neutral[:, :1]*D65)
    np.testing.assert_allclose(actual, expected, atol=8e-6)
