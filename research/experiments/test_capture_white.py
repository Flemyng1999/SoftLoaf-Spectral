import unittest
import numpy as np
from capture_white import normalize_capture_white


class CaptureWhiteTests(unittest.TestCase):
    def test_white_and_neutral_transmission_have_equal_channels(self):
        matrix = np.array([[2., -.2, .1], [-.4, 1.4, -.1], [.2, -.2, 1.]])
        white = np.ones(3) @ np.linalg.inv(matrix)
        neutral = np.array([0., .02, .18, .8, 1.])[:, None]
        raw, normalized_matrix = normalize_capture_white(neutral * white, matrix, white)
        np.testing.assert_allclose(raw, np.broadcast_to(neutral, raw.shape), atol=1e-15)
        np.testing.assert_allclose(raw @ normalized_matrix, np.broadcast_to(neutral, raw.shape), atol=1e-15)

    def test_non_neutral_image_preserves_matrix_output_without_mutation(self):
        matrix = np.array([[2., -.2, .1], [-.4, 1.4, -.1], [.2, -.2, 1.]])
        white = np.ones(3) @ np.linalg.inv(matrix)
        sample = np.array([[[.6, .2, .04], [.03, .08, .01]]]) * white
        original = sample.copy()
        raw, normalized_matrix = normalize_capture_white(sample, matrix, white)
        np.testing.assert_allclose(raw @ normalized_matrix, original @ matrix, atol=1e-15)
        np.testing.assert_array_equal(sample, original)
        np.testing.assert_allclose(raw[0, 0], [.6, .2, .04])  # Orange absorption remains.

    def test_matrix_must_match_its_declared_white(self):
        with self.assertRaises(ValueError):
            normalize_capture_white(np.ones((2, 3)), np.eye(3), [.5, .6, .7])

    def test_white_must_be_finite_and_positive(self):
        for white in ([0, 1, 1], [-1, 1, 1], [float('nan'), 1, 1]):
            with self.assertRaises(ValueError):
                normalize_capture_white(np.ones((2, 3)), np.eye(3), white)


if __name__ == '__main__':
    unittest.main()
