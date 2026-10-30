import base64
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image


def frame():
    out=io.BytesIO();Image.fromarray(np.full((8,12,3),120,dtype=np.uint8)).save(out,format='PNG')
    return {'ok':True,'current':{'preview':{'kind':'image','width':12,'height':8,'data_url':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()}}}


def test_single_flight_binary_assets_restart_and_inline_readback(tmp_path):
    from spectral_app.rendition_cache import RenditionCache
    cache=RenditionCache(tmp_path);calls=[];gate=threading.Barrier(3)
    def produce():calls.append(1);time.sleep(.03);return frame()
    def run():gate.wait();return cache.get_or_compute('one-photo-one-recipe',produce,transport='url')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run) for _ in range(2)];gate.wait();a,b=[f.result() for f in futures]
    assert len(calls)==1
    assert a['current']['preview']['data_url']==b['current']['preview']['data_url']
    url=a['current']['preview']['data_url'];assert url.startswith('/previews/')
    assert Image.open(io.BytesIO(cache.asset(url))).size==(12,8)
    restarted=RenditionCache(tmp_path)
    restored=restarted.get_or_compute('one-photo-one-recipe',lambda:(_ for _ in ()).throw(AssertionError('rerendered')))
    assert restored['current']['preview']['data_url']==frame()['current']['preview']['data_url']


def test_recipe_change_misses_and_corrupt_disposable_assets_rebuild_without_raw(tmp_path):
    from spectral_app.rendition_cache import RenditionCache
    cache=RenditionCache(tmp_path);calls=[]
    def produce():calls.append(1);return frame()
    cache.get_or_compute('recipe1',produce)
    cache.get_or_compute('recipe2',produce)
    assert len(calls)==2
    asset=next((tmp_path/'objects').glob('*.png'));asset.write_bytes(b'broken')
    restarted=RenditionCache(tmp_path);restarted.get_or_compute('recipe1',produce)
    assert len(calls)==3


def test_rendition_eviction_never_touches_retained_developments(tmp_path):
    from spectral_app.rendition_cache import RenditionCache
    pinned=tmp_path/'raw';pinned.mkdir();(pinned/'half.tif').write_bytes(b'retained')
    cache=RenditionCache(tmp_path/'renditions',budget=1)
    for i in range(3):cache.get_or_compute(str(i),frame)
    assert (pinned/'half.tif').read_bytes()==b'retained'
    assert len([p for p in (tmp_path/'renditions').glob('*.json') if len(p.stem)==64])<=1
