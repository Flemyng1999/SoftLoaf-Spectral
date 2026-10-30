from pathlib import Path
import numpy as np
import pytest


def test_one_raw_decode_per_stage_and_reuse_across_restart(tmp_path,monkeypatch):
    from spectral_app.rawtherapee import RawTherapee
    import spectral_app.rawtherapee as module
    root=Path.cwd();source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local synthetic DNG not supplied')
    events=[];monkeypatch.setattr(module,'event',lambda name,**fields:events.append((name,fields)))
    calls=[];original=module.subprocess.run
    def run(command,*args,**kwargs):
        result=original(command,*args,**kwargs)
        if '-c' in command:calls.append(result.stdout.decode(errors='replace'))
        return result
    monkeypatch.setattr(module.subprocess,'run',run)
    engine=RawTherapee(root,tmp_path/'raw')
    preview=engine.develop(source,preview=True)
    assert len(calls)==1,'Both color outputs must share one RAW development'
    assert preview['metadata']['raw_decode_count']==1
    assert calls[-1].count('SOFTLOAF_RAW_DECODE 1')==1
    expected=preview['ap1'].copy()
    for _ in range(2):engine.develop(source,preview=True)
    full=engine.develop(source)
    assert len(calls)==2 and full['metadata']['raw_decode_count']==1
    engine._prune(Path('never-current'),budget=0)
    restarted=RawTherapee(root,tmp_path/'raw')
    np.testing.assert_array_equal(restarted.develop(source,preview=True)['ap1'],expected)
    restarted.develop(source,routes=('ap1',))
    assert len(calls)==2,'Switches, eviction and restart must not reopen RAW'
    started=[v for name,v in events if name=='raw.development.started']
    assert [v['stage'] for v in started]==['half','full']
    assert len([v for name,v in events if name=='raw.development.finished'])==2


def test_committed_raw_cache_corruption_does_not_silently_decode_again(tmp_path,monkeypatch):
    from spectral_app.rawtherapee import RawTherapee
    from experiments.gui_recipe_server import RecipeError
    root=Path.cwd();source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local synthetic DNG not supplied')
    engine=RawTherapee(root,tmp_path/'raw');result=engine.develop(source,preview=True)
    folder=next(engine.cache.glob('*/manifest.json')).parent
    del result
    (folder/'ap1.tif').write_bytes(b'broken')
    with pytest.raises(RecipeError) as error:engine.develop(source,preview=True)
    assert error.value.code=='raw_cache_integrity'


def test_upgrade_adopts_verified_legacy_full_data_without_decoding_again(tmp_path,monkeypatch):
    import json,hashlib
    from spectral_app.rawtherapee import RawTherapee,BASE_PP3
    import spectral_app.rawtherapee as module
    root=Path.cwd();source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local synthetic DNG not supplied')
    engine=RawTherapee(root,tmp_path/'raw');original=engine.develop(source);expected=original['ap1'].copy();del original
    path=next(engine.cache.glob('*/manifest.json'));metadata=json.loads(path.read_text())
    legacy=hashlib.sha256((BASE_PP3+'raw-handoff/2; typed originals; WB availability').encode()+b''.join(engine.profiles.values())+engine.identity.encode()+json.dumps(engine.resource_hashes,sort_keys=True).encode()).hexdigest()
    metadata['settings_sha256']=legacy;path.write_text(json.dumps(metadata))
    for record in (engine.cache/'ledger').glob('*.json'):
        if not record.name.startswith('._'):record.unlink()
    real_run=module.subprocess.run
    def run(command,*a,**k):
        assert '-c' not in command,'An executable upgrade must reuse the existing full data'
        return real_run(command,*a,**k)
    monkeypatch.setattr(module.subprocess,'run',run)
    np.testing.assert_array_equal(RawTherapee(root,engine.cache).develop(source)['ap1'],expected)


def test_application_import_edit_export_and_restart_have_two_raw_decodes(tmp_path,monkeypatch):
    import base64,json
    from spectral_app.application import Application
    from spectral_app.model import SpectralModel
    from spectral_app.metal_renderer import MetalRenderer
    from spectral_lut.native import NativeCore
    import spectral_app.rawtherapee as module
    root=Path.cwd();source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local synthetic DNG not supplied')
    core=NativeCore()
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path,core=core)
    model.metal=MetalRenderer(model,core.path.with_name('libsoftloaf_metal.dylib'))
    calls=[];original=module.subprocess.run
    def run(command,*a,**k):
        result=original(command,*a,**k)
        if '-c' in command:calls.append(result.stdout.decode(errors='replace').count('SOFTLOAF_RAW_DECODE 1'))
        return result
    monkeypatch.setattr(module.subprocess,'run',run)
    app=Application(model);item=app.import_image({'name':'sample.dng','data_base64':base64.b64encode(source.read_bytes()).decode()})['input']
    assert calls==[1]
    recipe=app.bootstrap()['default_recipe'];request={'recipe':recipe,'input':{'id':item['id'],'exposure_ev':0},'preview_transport':'url'}
    for _ in range(2):app.evaluate(request)
    recipe['film']['exposure_ev']=.2;app.evaluate(request)
    assert calls==[1]
    for _ in range(2):
        exported=app.export_image(request)
        assert [exported['verification']['width'],exported['verification']['height']]==[650,490]
    assert calls==[1,1]
    restored=Application(model);restored.evaluate(request);restored.export_image(request)
    assert calls==[1,1]
    stages=[json.loads(p.read_text())['stage'] for p in (app.raw_engine.cache/'ledger').glob('*.json') if not p.name.startswith('._')]
    assert sorted(stages)==['full','half']


def test_parallel_readers_share_the_same_preview_development(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from spectral_app.rawtherapee import RawTherapee
    import spectral_app.rawtherapee as module
    root=Path.cwd();source=root/'artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng'
    if not source.exists():pytest.skip('Local synthetic DNG not supplied')
    engines=[RawTherapee(root,tmp_path/'shared') for _ in range(2)];calls=[];original=module.subprocess.run
    def run(command,*a,**k):
        if '-c' in command:calls.append(1)
        return original(command,*a,**k)
    monkeypatch.setattr(module.subprocess,'run',run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(lambda engine:engine.develop(source,preview=True),engines))
    assert calls==[1]
    np.testing.assert_array_equal(values[0]['ap1'],values[1]['ap1'])
