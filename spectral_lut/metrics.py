"""Error limits in final bounded, standard-encoded sRGB code values."""

import numpy as np


def srgb_code_error(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.shape != b.shape or not a.size or a.shape[-1] != 3:
        raise ValueError('Expected matching, nonempty RGB arrays.')
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('Nonfinite output cannot satisfy an error limit.')
    a, b = np.clip(a, 0, 1)*255, np.clip(b, 0, 1)*255
    pixel_float = np.max(np.abs(a-b), axis=-1)
    # Convert before subtraction, otherwise uint8 values can wrap.
    pixel_u8 = np.max(np.abs(np.rint(a).astype(np.int16)-np.rint(b).astype(np.int16)), axis=-1).astype(np.uint8)
    return summarize_code_errors(pixel_float, pixel_u8), pixel_float, pixel_u8


def summarize_code_errors(pixel_float, pixel_u8):
    floats, codes = np.asarray(pixel_float).ravel(), np.asarray(pixel_u8).ravel()
    over_float, over_u8 = floats > 2+1e-10, codes > 2
    accepted_float = bool(np.mean(~over_float) >= 0.99)
    accepted_u8 = bool(np.mean(~over_u8) >= 0.99)
    return {'pixel_count': int(floats.size), 'max_abs_code_float': float(np.max(floats)),
            'p95_pixel_max_code_float': float(np.percentile(floats, 95)),
            'mean_pixel_max_code_float': float(np.mean(floats, dtype=np.float64)),
            'max_abs_code_u8': int(np.max(codes)),
            'p95_pixel_max_code_u8': float(np.percentile(codes, 95)),
            'pixels_over_2_codes_float': int(np.count_nonzero(over_float)),
            'pixels_over_2_codes_u8': int(np.count_nonzero(over_u8)),
            'fraction_within_2_codes_float': float(np.mean(~over_float)),
            'fraction_within_2_codes_u8': float(np.mean(~over_u8)),
            'all_pixels_pass_float': bool(not np.any(over_float)),
            'all_pixels_pass_u8': bool(not np.any(over_u8)),
            'all_pixels_pass': bool(not np.any(over_float) and not np.any(over_u8)),
            'required_fraction': 0.99,
            'accepted_float': accepted_float,
            'accepted_u8': accepted_u8,
            'accepted': accepted_float and accepted_u8}
