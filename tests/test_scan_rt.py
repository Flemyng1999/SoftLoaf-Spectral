import json
from pathlib import Path
import numpy as np


def test_rt_scan_develops_native_and_srgb_once_and_retains_both(tmp_path,monkeypatch):
    import subprocess,tifffile
    from spectral_app.scanning.raw import RTScanRaw
    from spectral_app.rawtherapee import find_cli
    from experiments.hsi_raw_lut import write_synthetic_dng
    p={'color':np.eye(3),'forward':np.eye(3),'copyright':'synthetic test',
       'table':np.broadcast_to([0,1,1],(1,2,2,3)).copy()}
    p['table'][...,0]=35 # display characterization must not leak into measurement
    values=np.full((100,150,3),[.12,.18,.24]);values[20:60,20:60]=[.06,.09,.12]
    source=tmp_path/'chart.dng';write_synthetic_dng(source,values,np.array([.8,1,.6]),p,'Test','Bayer')
    engine=RTScanRaw(find_cli(Path.cwd()),tmp_path/'retained');calls=[];run=subprocess.run
    def tracked(command,**kwargs):
        if command[0]==str(engine.executable) and '-c' in command:calls.append(command)
        return run(command,**kwargs)
    monkeypatch.setattr(subprocess,'run',tracked)
    half=engine.develop(source,stage='half');a=tifffile.imread(half/'camera.tif');b=tifffile.imread(half/'srgb.tif')
    assert a.dtype==np.uint16 and b.dtype==np.float32 and a.shape==b.shape
    assert np.isfinite(b).all() and a.shape[0]<200
    np.testing.assert_allclose(a[30,30]/a[75,75].astype(float),.5,atol=.002)
    np.testing.assert_allclose(a[75,75]/a[75,75,1],[2/3,1,4/3],atol=.003)
    metadata=json.loads((half/'manifest.json').read_text())
    assert metadata['engine']['raw_decode_count']==1 and metadata['encoding'].startswith('linear native')
    assert metadata['engine']['display_encoding']=='sRGB D65' and metadata['engine']['native_white_balance']=='off'
    assert len(calls)==1
    engine=RTScanRaw(find_cli(Path.cwd()),tmp_path/'retained')
    assert engine.develop(source,stage='half')==half and len(calls)==1
    full=engine.develop(source,stage='full');assert tifffile.imread(full/'camera.tif').shape[0]>a.shape[0]
    assert engine.develop(source,stage='full')==full and len(calls)==2
    # Independent unmodified RT 5.12 executable, on a synthetic RAW only.
    # Adding a native measurement handoff must not alter RT display colours.
    import os
    official=Path('local/runtime/RawTherapee.app/Contents/MacOS/rawtherapee-cli').resolve()
    env={**os.environ,'RT_SETTINGS':str(tmp_path/'official-settings'),'OMP_NUM_THREADS':'2'}
    for k in ('SOFTLOAF_RT_NATIVE_OUTPUT','SOFTLOAF_RT_SUPERPIXEL','SOFTLOAF_RT_SECONDARY_PROFILE','SOFTLOAF_RT_SECONDARY_OUTPUT'):env.pop(k,None)
    oracle=tmp_path/'official.tif'
    result=run([str(official),'-q','-Y','-p',str(full/'settings.pp3'),'-o',str(oracle),'-t','-b32','-c',str(source)],env=env,capture_output=True,timeout=120)
    assert result.returncode==0,result.stdout[-1000:]
    np.testing.assert_allclose(tifffile.imread(full/'srgb.tif'),tifffile.imread(oracle),atol=2e-5,rtol=0)
