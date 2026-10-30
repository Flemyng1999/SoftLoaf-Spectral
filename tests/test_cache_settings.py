import json
import time
from pathlib import Path
import numpy as np
import pytest
from spectral_app.cache_settings.policy import budgets,DEFAULTS
from spectral_app.cache_settings.service import CacheSettings,owned
from spectral_app.rendition_cache import RenditionCache
from spectral_app.photo_cache import PreviewStore
from spectral_app.storage import DataStorage
from experiments.gui_recipe_server import RecipeError


def wait(service):
    for _ in range(200):
        state=service.state()
        if state['job']['status']!='running':return state
        time.sleep(.01)
    raise AssertionError('maintenance timed out')

@pytest.fixture
def service(tmp_path):
    output=tmp_path/'app';output.mkdir();cache=RenditionCache(output/'renditions');inputs=PreviewStore({},output/'inputs');raw=output/'raw';raw.mkdir()
    result=CacheSettings(output,DataStorage(project=tmp_path),cache,inputs,raw);wait(result)
    yield result
    result.worker.shutdown()


def test_capacity_budget_stable_and_memory_bounded():
    first=budgets(DEFAULTS,1024**4,16*1024**3)
    assert first==budgets(DEFAULTS,1024**4,16*1024**3)
    assert first['reserve_bytes']>first['disk_bytes']
    assert sum(first[k] for k in ['inputs_bytes','encoded_bytes','browser_bytes','working_bytes'])<=first['memory_bytes']


def test_clear_only_disposable_assets_and_keep_raw(service):
    keep=service.raw/'preview.tiff';keep.write_bytes(b'RAW development')
    source=service.inputs.directory/'input.npy';source.write_bytes(b'float input')
    unknown=service.cache.directory/'notes.txt';unknown.write_text('user')
    key='a'*64;(service.cache.directory/(key+'.json')).write_text('{}');(service.cache.objects/(key+'.png')).write_bytes(b'png')
    assert wait(service)['job']['status']=='complete'
    service.start({'action':'clear'});assert wait(service)['job']['status']=='complete'
    assert keep.read_bytes()==b'RAW development' and source.exists() and unknown.exists()
    assert not (service.cache.objects/(key+'.png')).exists()


def test_policy_persist_and_apply_memory(service):
    state=service.update({'settings':{'memory_mode':'custom','memory_mib':256,'disk_mode':'off'}})
    assert service.inputs.budget==128*1024**2 and not service.cache.enabled
    assert json.loads(service.path.read_text())['disk_mode']=='off'
    with pytest.raises(RecipeError):service.update({'settings':{'memory_mib':1}})


def test_move_verified_keeps_old_and_does_not_touch_unowned(service,tmp_path):
    bad=tmp_path/'bad';bad.mkdir();(bad/'mine').write_text('precious')
    service.start({'action':'move','location':str(bad)})
    assert wait(service)['job']['status']=='failed' and (bad/'mine').read_text()=='precious'
    old=service.cache.directory;key='f'*64;record=old/(key+'.json');record.write_text('{}')
    dest=tmp_path/'new';service.start({'action':'move','location':str(dest)})
    assert wait(service)['job']['status']=='complete'
    assert service.cache.directory==dest and record.exists() and (dest/record.name).read_bytes()==record.read_bytes()
    assert str(old) in service.settings['old_locations']


def test_active_producer_prevents_clear_or_move(service,tmp_path):
    service.cache.pending['active']=object()
    service.start({'action':'clear'});assert wait(service)['job']['status']=='failed'
    service.start({'action':'move','location':str(tmp_path/'unused')});assert wait(service)['job']['status']=='failed'
    assert not (tmp_path/'unused').exists()


def test_disk_off_uses_bounded_session_assets_without_persistent_records(service):
    from spectral_lut.display import rgb_profile
    from spectral_app.imaging.png_codec import PngWriter
    service.update({'settings':{'disk_mode':'off'}})
    for i in range(21):
        path=service.cache.staging_path()
        with PngWriter(path,(2,2),rgb_profile('sRGB')) as writer:writer.write(np.full((2,2,3),i,dtype=np.uint8))
        url=service.cache.adopt_png(path)
        service.cache.get_or_compute('frame'+str(i),lambda:{'preview':{'data_url':url}},transport='url')
    assert len(service.cache.transient)<=16
    assert not any(p for p in service.cache.directory.glob('*.json') if not p.name.startswith('.'))
    assert service.cache.asset(url).startswith(b'\x89PNG')


def test_disk_reserve_stops_writes_before_raw_decode_or_output(service,monkeypatch):
    import shutil
    monkeypatch.setattr(shutil,'disk_usage',lambda p:shutil._ntuple_diskusage(10*1024**3,9*1024**3,1024**3))
    with pytest.raises(RecipeError) as error:service.admit_write(1)
    assert error.value.code=='disk_space'


def test_move_nonempty_pngs_survives_settings_restart(service,tmp_path):
    import hashlib
    from spectral_lut.display import rgb_profile
    from spectral_app.imaging.png_codec import PngWriter
    path=service.cache.staging_path()
    with PngWriter(path,(7,5),rgb_profile('sRGB')) as writer:writer.write(np.full((5,7,3),71,dtype=np.uint8))
    url=service.cache.adopt_png(path);service.cache.get_or_compute('migrate-frame',lambda:{'preview':{'data_url':url}},transport='url')
    expected=service.cache.asset(url);destination=tmp_path/'verified-cache'
    service.start({'action':'move','location':str(destination)});state=wait(service)
    assert state['job']['status']=='complete' and state['job']['completed_bytes']>len(expected)
    assert hashlib.sha256(service.cache.asset(url)).digest()==hashlib.sha256(expected).digest()
    restored=CacheSettings(service.path.parent,service.storage,RenditionCache(service.default),service.inputs,service.raw)
    try:
        wait(restored);assert restored.cache.directory==destination
        assert restored.cache.get_or_compute('migrate-frame',lambda:pytest.fail('should restore persisted frame'),transport='url')['preview']['data_url']==url
        assert restored.cache.asset(url)==expected
    finally:restored.worker.shutdown()


def test_migration_checksum_failure_preserves_original_settings(service,tmp_path,monkeypatch):
    import spectral_app.cache_settings.service as module
    old=service.cache.directory;record=old/('a'*64+'.json');record.write_text('{}')
    original=module.digest_file
    monkeypatch.setattr(module,'digest_file',lambda p:'bad-copy' if p.suffix=='.copying' else original(p))
    destination=tmp_path/'broken-copy';service.start({'action':'move','location':str(destination)})
    assert wait(service)['job']['status']=='failed'
    assert service.cache.directory==old and service.settings['location'] is None and record.exists()
    assert not list(destination.glob('*.copying'))
