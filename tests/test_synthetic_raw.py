import numpy as np
import tifffile


def test_synthetic_dng_preserves_cfa_codes_and_embeds_its_d65_technical_profile(tmp_path):
    from experiments.hsi_raw_lut import write_synthetic_dng
    profile = {'color': np.eye(3), 'forward': np.eye(3), 'copyright': 'test fixture',
               'table': np.broadcast_to([0, 1, 1], (1, 2, 2, 3)).copy()}
    path = tmp_path/'SYNTHETIC.dng'
    write_synthetic_dng(path, np.array([[[0.2, 0.4, 0.8]]]), np.ones(3), profile, 'Test', 'Synthetic')
    with tifffile.TiffFile(path) as tf:
        np.testing.assert_array_equal(tf.asarray(), [[3763, 7014], [7014, 13517]])
        tags = tf.pages[0].tags
        values = np.array(tags[50964].value)
        np.testing.assert_allclose((values[::2]/values[1::2]).reshape(3, 3), np.eye(3))
        np.testing.assert_array_equal(tags[50937].value, [2, 2, 1])
        np.testing.assert_allclose(np.asarray(tags[50938].value).reshape(1, 2, 2, 3), profile['table'])
        assert tags[50778].value == 21
