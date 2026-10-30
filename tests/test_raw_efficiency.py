"""RAW cache and admission scheduling behavior; no replacement demosaic."""
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import tifffile


def test_raw_read_is_readonly_mapping_and_export_reads_only_requested_branch(tmp_path):
    import json
    from spectral_app.rawtherapee import RawTherapee
    pixels=np.arange(48,dtype=np.float32).reshape(4,4,3)
    tifffile.imwrite(tmp_path/'ap1.tif',pixels)
    (tmp_path/'manifest.json').write_text(json.dumps({'test':True}))
    result=RawTherapee._read(tmp_path,('ap1',))
    assert isinstance(result['ap1'],np.memmap)
    assert not result['ap1'].flags.writeable
    assert 'srgb' not in result
    np.testing.assert_array_equal(result['ap1'],pixels)


def test_verified_cache_avoids_rehash_until_file_identity_changes(tmp_path,monkeypatch):
    from spectral_app.rawtherapee import VerifiedFiles
    files=VerifiedFiles();path=tmp_path/'pixels';path.write_bytes(b'first')
    calls=[];original=files._hash
    monkeypatch.setattr(files,'_hash',lambda p:(calls.append(p),original(p))[1])
    first=files.digest(path)
    assert files.digest(path)==first and len(calls)==1
    path.write_bytes(b'other')
    assert files.digest(path)!=first and len(calls)==2


def test_foreground_decode_runs_before_waiting_exports_and_slots_release_after_failure():
    from spectral_app.rawtherapee import DecodeGate
    gate=DecodeGate();entered=threading.Event();release=threading.Event();order=[]
    def active():
        with gate.slot('background'):entered.set();release.wait(3)
    def run(name,priority):
        with gate.slot(priority):order.append(name)
    first=threading.Thread(target=active);first.start();assert entered.wait(2)
    background=threading.Thread(target=run,args=('export','background'));background.start()
    foreground=threading.Thread(target=run,args=('viewer','interactive'));foreground.start()
    for _ in range(200):
        if gate.waiting==2:break
        time.sleep(.005)
    assert gate.waiting==2
    release.set()
    for thread in (first,background,foreground):thread.join(3);assert not thread.is_alive()
    assert order==['viewer','export']
    with pytest.raises(RuntimeError):
        with gate.slot('interactive'):raise RuntimeError('decode failed')
    with gate.slot('background'):assert gate.waiting==0


def test_cached_raw_is_mapped_without_starting_decoder_again(tmp_path,monkeypatch):
    from spectral_app.rawtherapee import RawTherapee
    root=Path(__file__).resolve().parents[1]
    source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    cli=root/'local/runtime/RawTherapee.app/Contents/MacOS/rawtherapee-cli'
    if not source.exists() or not cli.exists():pytest.skip('Local RT and test DNG unavailable')
    engine=RawTherapee(root,tmp_path,cli);first=engine.develop(source)
    import spectral_app.rawtherapee as module
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:pytest.fail('cache hit launched RT'))
    again=engine.develop(source,routes=('ap1',),priority='background')
    assert 'srgb' not in again and isinstance(again['ap1'],np.memmap)
    np.testing.assert_array_equal(first['ap1'],again['ap1'])


def test_raw_cache_pruning_preserves_unrecognized_user_files(tmp_path):
    import json
    from spectral_app.rawtherapee import RawTherapee
    engine=RawTherapee(Path.cwd(),tmp_path/'cache')
    old=engine.cache/('a'*64);old.mkdir();(old/'manifest.json').write_text(json.dumps({'files':{}}))
    (old/'ap1.tif').write_bytes(b'cache');(old/'srgb.tif').write_bytes(b'cache');(old/'notes.txt').write_text('preserve')
    current=engine.cache/('b'*64);current.mkdir()
    engine._prune(current,budget=0)
    assert (old/'notes.txt').read_text()=='preserve'
    assert current.exists()


def test_updated_raw_executable_requires_restart_before_any_new_handoff(tmp_path):
    from spectral_app.rawtherapee import RawTherapee
    from experiments.gui_recipe_server import RecipeError
    cli=tmp_path/'raw-cli';cli.write_bytes(b'engine snapshot')
    source=tmp_path/'source.dng';source.write_bytes(b'not processed')
    engine=RawTherapee(Path.cwd(),tmp_path/'cache',cli=cli)
    cli.write_bytes(b'updated engine')
    with pytest.raises(RecipeError) as error:engine.develop(source)
    assert error.value.code=='raw_engine_changed'
