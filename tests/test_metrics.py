import numpy as np
import pytest

from spectral_lut.metrics import srgb_code_error


def test_two_codes_is_inclusive_and_one_bad_channel_fails_the_pixel():
    a = np.zeros((4, 3))
    b = np.array([[2, 0, 0], [0, 2, 0], [0, 0, 3], [0, 0, 0]])/255
    summary, floats, codes = srgb_code_error(a, b)
    np.testing.assert_allclose(floats, [2, 2, 3, 0])
    np.testing.assert_array_equal(codes, [2, 2, 3, 0])
    assert summary['fraction_within_2_codes_u8'] == 0.75
    assert summary['pixels_over_2_codes_u8'] == 1
    assert summary['max_abs_code_u8'] == 3
    assert not summary['all_pixels_pass']


def test_code_difference_does_not_wrap_unsigned_bytes():
    summary, _, _ = srgb_code_error([[0, 0, 0]], [[1, 0, 0]])
    assert summary['max_abs_code_u8'] == 255


def test_float_limit_and_actual_png_quantization_are_reported_separately():
    summary, _, _ = srgb_code_error([[0, 0, 0]], [[2.4/255, 0, 0]])
    assert summary['all_pixels_pass_u8']
    assert not summary['all_pixels_pass_float']
    assert not summary['all_pixels_pass']


def test_display_clipping_matches_actual_output_and_nonfinite_values_are_rejected():
    summary, _, _ = srgb_code_error([[-1, 0, 2]], [[0, 0, 1]])
    assert summary['all_pixels_pass']
    with pytest.raises(ValueError):
        srgb_code_error([[np.nan, 0, 0]], [[0, 0, 0]])


@pytest.mark.parametrize('bad_pixels, accepted', [(0, True), (1, True), (2, False)])
def test_acceptance_includes_exactly_99_percent_of_pixels(bad_pixels, accepted):
    a = np.zeros((100, 3))
    b = a.copy()
    b[:bad_pixels, 1] = 3/255
    summary, _, _ = srgb_code_error(a, b)
    assert summary['accepted_float'] is accepted
    assert summary['accepted_u8'] is accepted
    assert summary['accepted'] is accepted


def test_acceptance_keeps_continuous_and_rounded_checks_separate():
    a = np.zeros((100, 3))
    b = a.copy()
    b[:2, 2] = 2.4/255
    summary, _, _ = srgb_code_error(a, b)
    assert summary['accepted_u8']
    assert not summary['accepted_float']
    assert not summary['accepted']
