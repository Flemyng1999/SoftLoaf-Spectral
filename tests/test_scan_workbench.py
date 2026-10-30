import io
import numpy as np
import pytest

def test_target_guide_uses_its_own_transmission_and_keeps_measurement_order():
    from spectral_app.scanning.targets import target_guide
    wave=np.arange(390,801,10.)
    target={'target':'test','wavelengths':wave,'transmission':np.repeat(np.linspace(.01,1,24)[:,None],len(wave),axis=1)}
    guide=target_guide(target)
    assert guide['target']=='test' and len(guide['colors'])==24
    assert sum(guide['colors'][0])<sum(guide['colors'][-1])
    assert all(len(rgb)==3 and all(0<=v<=255 for v in rgb) for rgb in guide['colors'])
    assert guide['observer']=='CIE 1931 2°' and guide['illuminant']=='D65'


def test_prepared_roll_order_is_admission_order_and_rows_publish_before_render(tmp_path):
    import threading,time
    from spectral_app.scanning.service import ScanService
    from spectral_app.photo_jobs import PhotoJobs
    from experiments.gui_recipe_server import RecipeError
    service=ScanService.__new__(ScanService)
    service.lock=threading.RLock();service.warning=None
    service.storage=type('Storage',(),{'validate':lambda s:None})()
    service.index={'assets':{'a':{'embedded_url':'/a'},'b':{'embedded_url':'/b'}},'images':[],'geometry':{}};service._save=lambda:None
    service.state=lambda:service.index.copy()
    service.jobs=PhotoJobs(service._execute)
    service.prepare_jobs=PhotoJobs(service._execute,workers=2,max_pending=2)
    entered=threading.Barrier(3);release={'a':threading.Event(),'b':threading.Event()}
    def render(i):entered.wait(2);release[i].wait(3)
    service._frame_preview=lambda i,*args:render(i)
    try:
        a=service.request({'action':'prepare','inputs':['a'],'roll':True})
        b=service.request({'action':'prepare','inputs':['b'],'roll':True})
        entered.wait(2);assert service.index['images']==['a','b']
        with pytest.raises(RecipeError,match='等待'):service.request({'action':'new-roll'})
        release['b'].set()
        for _ in range(100):
            if service.request({'action':'job','id':b['id']})['status']=='complete':break
            time.sleep(.01)
        assert service.request({'action':'job','id':b['id']})['status']=='complete'
        assert service.request({'action':'job','id':a['id']})['status']=='running'
        assert service.index['images']==['a','b']
    finally:
        for e in release.values():e.set()
        service.prepare_jobs.worker.shutdown();service.jobs.worker.shutdown()


def test_transmission_csv_requires_explicit_quantity_and_complete_patch_order(tmp_path):
    from spectral_app.scanning.targets import load_target
    path=tmp_path/'card.csv';labels=[f'{r}{c}' for r in 'ABCD' for c in range(1,7)]
    data=np.column_stack([np.arange(390,801,10.),np.full((42,24),.4)])
    header='# softloaf.transmission-target/1\n# target=000003\nwavelength_nm,'+','.join(labels)+'\n'
    with path.open('w') as f:f.write(header);np.savetxt(f,data,delimiter=',')
    value=load_target(path)
    assert value['target']=='000003' and value['transmission'].shape==(24,42)
    path.write_text(path.read_text().replace('transmission-target','reflectance-target'))
    with pytest.raises(ValueError,match='透射'):load_target(path)


def test_projective_patch_centres_honour_orientation_and_reject_crossed_corners():
    from spectral_app.scanning.targets import patch_centres
    corners=np.array([[.8,.8],[.2,.75],[.25,.2],[.85,.25]])
    points=patch_centres(corners)
    np.testing.assert_allclose(points[[0,5,23,18]],corners)
    assert points.shape==(24,2)
    with pytest.raises(ValueError):patch_centres(corners[[0,2,1,3]])


def test_native_full_source_corrects_flat_per_global_region(tmp_path):
    from spectral_app.scanning.imaging import FlatCameraSource
    from spectral_app.imaging.blocks import Region
    import tifffile
    y,x=np.mgrid[-1:1:60j,-1:1:80j];field=np.exp(.1*y+.2*x)
    values=np.uint16(np.rint(field[...,None]*[.1,.2,.3]*65535))
    path=tmp_path/'native.tif';tifffile.imwrite(path,values,photometric='rgb')
    coeff=np.zeros((6,3));coeff[1]=.1;coeff[2]=.2
    source=FlatCameraSource(path,coeff)
    with source.read(Region(23,31,13,17)) as region:
        np.testing.assert_allclose(region,np.broadcast_to([.1,.2,.3],region.shape),atol=2/65535)
    source.close()


def test_scan_service_import_calibrate_positive_full_export_restart_without_redecode(tmp_path,monkeypatch):
    import json,time,subprocess
    from pathlib import Path
    from PIL import Image
    from spectral_app.model import SpectralModel
    from spectral_app.scanning.service import ScanService
    from spectral_app.scanning import assets
    from spectral_app.storage import DataStorage
    from spectral_app.rendition_cache import RenditionCache
    from spectral_lut.native import NativeCore
    from experiments.hsi_raw_lut import write_synthetic_dng
    capture={'Model':'Test Bayer','LensModel':'test','ISO':100,'ExposureTime':.0125,'FNumber':5.6}
    monkeypatch.setattr(assets,'read_metadata',lambda p:capture.copy())
    configured=DataStorage.configured();storage=DataStorage(tmp_path/'data',configured.volume)
    root=Path.cwd();model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path/'model',core=NativeCore())
    cache=RenditionCache(tmp_path/'renditions');service=ScanService(model,storage,cache)
    assert service.materials['5207'] is None # retain the previously validated scan reference
    calls=[];run=subprocess.run
    def track(*args,**kwargs):
        if args[0][0]==str(service.raw.executable) and '-c' in args[0]:calls.append('half' if kwargs['env'].get('SOFTLOAF_RT_SUPERPIXEL') else 'full')
        return run(*args,**kwargs)
    monkeypatch.setattr(subprocess,'run',track)
    def wait(body):
        result=service.request(body);deadline=time.monotonic()+120
        while result['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.02);result=service.request({'action':'job','id':result['id']})
        assert result['status']=='complete',result
        return result['result']
    wave=np.arange(390,801,10.);rng=np.random.default_rng(789)
    dyes=np.array([np.exp(-.5*((wave-c)/35)**2) for c in [420,480,550,620,690]])
    transmission=np.exp(-rng.uniform(.05,1.5,(24,5))@dyes)
    kernel=np.column_stack([np.exp(-.5*((wave-c)/35)**2) for c in [620,540,450]]);kernel/=kernel.sum(0)
    camera=transmission@kernel
    target=tmp_path/'reference.csv'
    with target.open('w') as f:
        f.write('# softloaf.transmission-target/1\n# target=synthetic\nwavelength_nm,'+','.join(f'{r}{c}' for r in 'ABCD' for c in range(1,7))+'\n')
        np.savetxt(f,np.column_stack([wave,transmission.T]),delimiter=',')
    reference=service.upload(io.BytesIO(target.read_bytes()),target.stat().st_size,'target.csv','reference')['asset']['id']
    profile={'color':np.eye(3),'forward':np.eye(3),'copyright':'test','table':np.broadcast_to([0,1,1],(1,2,2,3)).copy()}
    def raw(name,pixels):
        path=tmp_path/name;write_synthetic_dng(path,pixels,np.ones(3),profile,'Test','Bayer')
        return service.upload(io.BytesIO(path.read_bytes()),path.stat().st_size,name,'raw')['asset']['id']
    card=np.zeros((960,1440,3))
    for i in range(24):card[(i//6)*240:(i//6+1)*240,(i%6)*240:(i%6+1)*240]=camera[i]*.6
    chart=raw('chart.dng',card);flat=raw('flat.dng',np.full(card.shape,.6))
    corners=[[1/12,1/8],[11/12,1/8],[11/12,7/8],[1/12,7/8]]
    fitted=wait({'action':'calibrate','chart':chart,'flat':flat,'reference':reference,'corners':corners,'name':'Test capture'})
    assert fitted['profile']['RMS_D']<.04
    # RT displays retained camera pixels in matching geometry; it never unpacks
    # the original again, and its encoded sRGB never replaces fit samples.
    # Explicit numeric IDs preserve the same measured data and fit. Legacy
    # layouts are offered only after comparing the entire measured spectra.
    numbered=target.read_text().replace('transmission-target/1','transmission-target/2').replace(','.join(f'{r}{c}' for r in 'ABCD' for c in range(1,7)),','.join(map(str,range(1,25))))
    numeric=service.upload(io.BytesIO(numbered.encode()),len(numbered.encode()),'numbered.csv','reference')['asset']['id']
    guide=service.request({'action':'target-guide','reference':reference,'chart':chart})
    assert guide['reference']==numeric and guide['numbered']
    np.testing.assert_allclose(guide['known_corners'],corners,atol=1e-12)
    numeric_fit=wait({'action':'calibrate','chart':chart,'flat':flat,'reference':numeric,'corners':corners,'name':'Numbered'})
    with np.load(service.root/'profiles'/fitted['profile']['id']/'calibration.npz') as a,np.load(service.root/'profiles'/numeric_fit['profile']['id']/'calibration.npz') as b:
        np.testing.assert_array_equal(a['weights'],b['weights'])
        np.testing.assert_array_equal(a['camera'],b['camera'])
    service.request({'action':'select','profile':fitted['profile']['id']})
    retained=service._native(chart).read_bytes()
    wait({'action':'prepare','inputs':[chart],'chart':True})
    assert service._native(chart).read_bytes()==retained and calls==['half','half']
    assert service.state()['assets'][chart]['chart_preview_url'].startswith('/previews/')
    renamed=wait({'action':'calibrate','chart':chart,'flat':flat,'reference':reference,'corners':corners,'name':'Renamed capture'})
    assert renamed['profile']['id']==fitted['profile']['id'] and renamed['profile']['name']=='Renamed capture'
    negative=np.full(card.shape,[.17,.12,.08]);negative[:100]=[.35,.28,.2]
    frame=raw('negative.dng',negative);wait({'action':'prepare','inputs':[frame],'roll':True})
    from PIL import Image
    import io as image_io
    thumb=service.state()['assets'][frame]['thumbnail_url']
    with Image.open(image_io.BytesIO(cache.asset(thumb))) as image:assert min(image.size)==80 and max(image.size)<=160
    request={'inputs':[frame],'profile':fitted['profile']['id'],'border':{'asset':frame,'roi':[.2,.02,.8,.08]},'size':9,'view_ev':2,'stock':'5207'}
    from spectral_app.scanning.inverse import MaterialInverse
    solve=MaterialInverse.solve;inversions=[]
    def track_inverse(self,values,**kwargs):inversions.append(len(values));return solve(self,values,**kwargs)
    monkeypatch.setattr(MaterialInverse,'solve',track_inverse)
    positive=wait({'action':'positive',**request});assert positive['outputs'][frame]['report']['readback_exact']
    with Image.open(image_io.BytesIO(cache.asset(positive['outputs'][frame]['thumbnail_url']))) as image:assert min(image.size)==80
    assert calls==['half','half','half']
    # The synthetic writer expands each RGB sample into a 2x2 CFA tile.
    full=wait({'action':'export',**request});assert full['outputs'][frame]['report']['width']==2872
    png=next(f for f in full['files'] if f['name'].endswith('.png'))
    path,kind,download=service.resource(png['url'])
    with Image.open(path) as image:assert image.size==(2872,1912) and image.info['icc_profile']
    assert calls==['half','half','half','full']
    service=ScanService(model,storage,cache)
    wait({'action':'export',**request});cache.clear();wait({'action':'prepare','inputs':[frame]});wait({'action':'positive',**request})
    assert calls==['half','half','half','full']
    assert len(list(service.raw.cache.glob('*/manifest.json')))==4
    assert service.state()['results'][positive['id']]['border']==request['border']
    # A second immutable frame exercises batch publication and per-source stages.
    second=raw('negative-2.dng',negative*.98)
    wait({'action':'prepare','inputs':[second],'roll':True})
    batch=wait({'action':'export',**{**request,'inputs':[frame,second]}})
    import zipfile
    bundle=next(f for f in batch['files'] if f['name']=='positives.zip')
    with zipfile.ZipFile(service.resource(bundle['url'])[0]) as archive:
        assert archive.testzip() is None and len(archive.namelist())==3
    assert calls==['half','half','half','full','half','full']
    inversion_grids=inversions.count(9**3)
    linear_tables=len(list((service.root/'transforms').glob('*/table.json')))
    wait({'action':'positive',**{**request,'view_ev':1}})
    assert inversions.count(9**3)==inversion_grids==1
    assert len(list((service.root/'transforms').glob('*/table.json')))==linear_tables==1
    # Geometry is spatial, never baked into a 3D color LUT, and never decodes RAW.
    before={i:service.state()['assets'][i].copy() for i in [frame,second]}
    configured=wait({'action':'geometry','asset':frame,'settings':{'mode':'manual','strength':.025,
        'rotation':1,'crop':[.1,.15,.9,.85],'auto_crop':True}})['geometry']
    for i in [frame,second]:
        after=service.state()['assets'][i]
        assert after['preview_context']==service.state()['preview_context']
        assert after['preview_url']!=before[i]['preview_url']
        assert after['thumbnail_url']!=before[i]['thumbnail_url']
        assert after['chart_preview_url']==before[i]['chart_preview_url']
    geometric=wait({'action':'positive',**request,'geometry':configured})
    assert geometric['lut_id']==positive['lut_id'] and geometric['id']!=positive['id']
    report=geometric['outputs'][frame]['report'];assert report['width']==765 and report['height']==1005
    sample=service.request({'action':'geometry-preview','asset':frame,'settings':configured,'result':geometric['id']})
    assert sample['report']['readback_exact'] and not sample['technical']
    full_geometry=wait({'action':'export',**request,'geometry':configured})
    assert full_geometry['outputs'][frame]['report']['width']==1530
    assert calls==['half','half','half','full','half','full']
    assert inversions.count(9**3)==1
    # Spatial flat normalization keeps channel acquisition scales in the fit.
    spatial=wait({'action':'flat','inputs':[flat]})['flat']
    assert spatial['supported_fraction']==1
    refit=wait({'action':'refit-flat','profile':fitted['profile']['id'],'flat_asset':spatial['id']})['profile']
    assert refit['flat_mode']=='spatial' and refit['RMS_D']<.04
    with np.load(service.root/'profiles'/refit['id']/'calibration.npz') as a:
        import tifffile
        native=tifffile.memmap(service._native(flat),mode='r')
        try:level=np.asarray(native[native.shape[0]//2,native.shape[1]//2],float)/65535
        finally:native._mmap.close()
        np.testing.assert_allclose(a['weights'].sum(0),level,atol=.01)
    disabled=wait({'action':'refit-flat','profile':refit['id'],'flat_asset':None})['profile']
    assert disabled['flat_mode']=='off' and disabled['RMS_D']<.04
    assert calls==['half','half','half','full','half','full']
    # Metadata incompatibility is rejected before either stage can be decoded.
    service.index['assets'][second]['metadata']['ISO']=200
    rejected=service.request({'action':'positive',**{**request,'inputs':[second]}})
    while rejected['status'] in ('queued','running'):
        time.sleep(.02);rejected=service.jobs.get(rejected['id'])
    assert rejected['status']=='failed' and 'ISO' in rejected['error']
    assert calls==['half','half','half','full','half','full']
    cleared=service.request({'action':'new-roll'})
    assert cleared['images']==[] and cleared['border'] is None and len(cleared['profiles'])==4
    assert frame in cleared['assets'] and len(list(service.raw.cache.glob('*/manifest.json')))==6


def test_scan_http_upload_origin_size_and_resource_allowlist(tmp_path):
    import json,threading
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    from experiments.gui_recipe_server import make_server
    from spectral_app.scanning.assets import ScanAssets
    class App:
        downloads={}
        def __init__(self):self.assets=ScanAssets(tmp_path/'assets');self.scans=self
        def scan_upload(self,stream,length,name,kind):return {'ok':True,'asset':self.assets.import_stream(stream,length,name,kind)}
        def state(self):return {'ok':True}
        def resource(self,url):raise FileNotFoundError()
    ui=tmp_path/'index.html';ui.write_text('<title>scan</title>')
    server=make_server(App(),ui,None,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    header='# softloaf.transmission-target/1\n# target=test\nwavelength_nm,'+','.join(f'{r}{c}' for r in 'ABCD' for c in range(1,7))+'\n'
    text=header+'\n'.join(str(w)+','+','.join(['.3']*24) for w in range(390,801,10))
    headers={'Content-Type':'application/octet-stream','X-File-Name':'target.csv','X-Scan-Kind':'reference','Origin':base}
    try:
        value=json.load(urlopen(Request(base+'/api/scan-upload',data=text.encode(),headers=headers)))
        assert value['ok'] and value['asset']['metadata']['target']=='test'
        with pytest.raises(HTTPError) as error:urlopen(Request(base+'/api/scan-upload',data=text.encode(),headers={**headers,'Origin':'https://other.example'}))
        assert error.value.code==403
        for path in ('/scan-files/private.csv','/scan-files/../index.json'):
            with pytest.raises(HTTPError) as error:urlopen(base+path)
            assert error.value.code==404
        with pytest.raises(HTTPError) as error:urlopen(Request(base+'/api/scan-upload',data=b'',headers=headers))
        assert error.value.code==400
        assert len(list((tmp_path/'assets').glob('a*.csv')))==1
    finally:server.shutdown();server.server_close();thread.join(2)


def test_numbered_transmission_columns_are_ids_not_file_positions(tmp_path):
    from spectral_app.scanning.targets import load_target
    path=tmp_path/'numbered.csv';ids=np.roll(np.arange(1,25),7)
    data=np.column_stack([np.arange(390,801,10.),np.broadcast_to(ids/30,(42,24))])
    with path.open('w') as f:
        f.write('# softloaf.transmission-target/2\n# target=card\nwavelength_nm,'+','.join(map(str,ids))+'\n');np.savetxt(f,data,delimiter=',')
    target=load_target(path)
    assert target['numbered'] and target['labels']==list(map(str,range(1,25)))
    np.testing.assert_allclose(target['transmission'][:,0],np.arange(1,25)/30)
    path.write_text(path.read_text().replace('wavelength_nm,','wavelength_nm,1,',1))
    with pytest.raises(ValueError,match='1–24'):load_target(path)


def test_known_layout_requires_exact_patch_spectra_and_projective_grid():
    from spectral_app.scanning.targets import equivalent_layout,patch_centres
    wave=np.arange(400,701,10.);values=np.broadcast_to(np.arange(1,25)[:,None]/25,(24,len(wave))).copy()
    a={'wavelengths':wave,'transmission':values};b={'wavelengths':wave,'transmission':values[::-1]}
    corners=np.array([[.2,.3],[.8,.3],[.8,.7],[.2,.7]])
    remapped=equivalent_layout(a,b,corners)
    np.testing.assert_allclose(patch_centres(remapped),patch_centres(corners)[::-1],atol=1e-12)
    b['transmission']=b['transmission'].copy();b['transmission'][0,0]+=.000001
    assert equivalent_layout(a,b,corners) is None


def test_numbered_chart_guide_uses_familiar_order_without_replacing_measured_spectra():
    from spectral_app.scanning.targets import target_guide
    data=np.broadcast_to(np.linspace(.01,.9,24)[:,None],(24,31)).copy()
    target={'target':'numbered','wavelengths':np.arange(400,701,10.),'transmission':data,'numbered':True}
    guide=target_guide(target)
    assert guide['patch_ids']==list(range(1,25))
    assert guide['patch_names'][0]=='dark skin' and guide['patch_names'][-1].startswith('black')
    assert guide['purpose']=='orientation-only' and 'guide only' in guide['color_source']
    np.testing.assert_array_equal(target['transmission'],data)
    assert guide['colors'][0][0]>guide['colors'][0][1]>guide['colors'][0][2]
    assert sum(guide['colors'][18])>sum(guide['colors'][23])


@pytest.mark.parametrize('bad_key',['0','light skin','Dark Skin'])
def test_colour_patch_keys_are_stable_and_column_order_is_irrelevant(tmp_path,bad_key):
    from spectral_app.scanning.targets import load_target,PATCH_KEYS
    import colour
    assert tuple(PATCH_KEYS)==tuple(colour.CCS_COLOURCHECKERS['BabelColor Average'].data)
    data=np.column_stack([np.arange(390,801,10.),np.broadcast_to(np.arange(24,0,-1)/30,(42,24))])
    path=tmp_path/'keyed.csv'
    with path.open('w') as f:
        f.write('# softloaf.transmission-target/3\n# target=keyed\nwavelength_nm,'+','.join(PATCH_KEYS[::-1])+'\n');np.savetxt(f,data,delimiter=',')
    t=load_target(path)
    assert t['keyed'] and t['labels']==[f'CC{i:02d}' for i in range(1,25)]
    np.testing.assert_allclose(t['transmission'][:,0],np.arange(1,25)/30)
    path.write_text(path.read_text().replace('dark skin',bad_key))
    with pytest.raises(ValueError,match='色块 ID'):load_target(path)


@pytest.mark.parametrize('bad_id',['CC00','CC1','CC02'])
def test_cc_ids_are_explicit_unique_and_independent_of_column_order(tmp_path,bad_id):
    from spectral_app.scanning.targets import PATCH_IDS,load_target
    labels=PATCH_IDS[::-1];path=tmp_path/'cc.csv'
    data=np.column_stack([np.arange(390,801,10.),np.broadcast_to(np.arange(24,0,-1)/30,(42,24))])
    with path.open('w') as f:
        f.write('# softloaf.transmission-target/3\n# target=test\nwavelength_nm,'+','.join(labels)+'\n');np.savetxt(f,data,delimiter=',')
    target=load_target(path)
    assert target['id_scheme']=='CC' and target['labels']==list(PATCH_IDS)
    np.testing.assert_allclose(target['transmission'][:,0],np.arange(1,25)/30)
    path.write_text(path.read_text().replace('CC01',bad_id))
    with pytest.raises(ValueError,match='色块 ID'):load_target(path)
