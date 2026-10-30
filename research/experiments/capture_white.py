"""Change capture units to a no-film white of (1, 1, 1).

Channels are linear row vectors: output = capture @ matrix. This is a unit
change, not a color calibration fit. No film-base subtraction is performed.
"""
import numpy as np


def normalize_capture_white(capture, matrix, white):
    capture = np.asarray(capture, dtype=np.float64)
    matrix = np.asarray(matrix, dtype=np.float64)
    white = np.asarray(white, dtype=np.float64)
    if matrix.shape != (3, 3) or white.shape != (3,) or capture.shape[-1] != 3:
        raise ValueError('Expected RGB row vectors, a 3x3 matrix and an RGB white.')
    if not all(np.isfinite(a).all() for a in (capture, matrix, white)) or (white <= 0).any():
        raise ValueError('Capture/matrix must be finite; white must be finite and positive.')
    if not np.allclose(white @ matrix, np.ones(3), rtol=0, atol=2e-7):
        raise ValueError('Matrix output is not unit white for the declared input white.')
    return capture / white, white[:, None] * matrix
