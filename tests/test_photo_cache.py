import numpy as np
from spectral_app.photo_cache import PreviewStore

def test_preview_lru_is_bounded_and_evicted_images_reload_without_loss(tmp_path):
    cache=PreviewStore({'chart':np.zeros((1,1,3))},tmp_path,budget=100)
    a=np.full((2,2,3),.123456789);b=a*2
    cache['user_aa']=a;cache['user_bb']=b
    np.testing.assert_array_equal(cache['user_aa'],a)
    np.testing.assert_array_equal(cache['user_bb'],b)
    assert cache.bytes<=100 and len(cache.memory)==1
    np.testing.assert_array_equal(cache['user_aa'],a)
    assert list(cache)==['chart','user_aa','user_bb']
