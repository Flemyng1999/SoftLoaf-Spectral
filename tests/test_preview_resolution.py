import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image
import pytest


def test_preview_policy_uses_2048_short_edge_and_never_upscales():
    from spectral_app.preview_policy import preview_size,PREVIEW_SHORT_EDGE
    assert PREVIEW_SHORT_EDGE==2048
    assert preview_size(6000,4000)==(3072,2048)
    assert preview_size(4000,6000)==(2048,3072)
    assert preview_size(329,249)==(329,249)


def test_rgb_and_float_preview_preserve_requested_detail():
    from spectral_app.application import Application
    x=np.linspace(0,1,3000,dtype=np.float32)[None,:,None]*np.ones((40,1,3),dtype=np.float32)
    y=Application._resize_float(x)
    assert y.shape==(40,3000,3)
    assert np.unique(y[...,0]).size>2000


def test_registered_preview_and_schema_are_2048(app):
    image=Image.new('RGB',(3000,2000),(100,120,140));stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue()
    item=app.import_image({'name':'resolution-test.png','data_base64':base64.b64encode(data).decode()})['input']
    assert app.model.inputs[item['id']].shape==(2000,3000,3)
    import json
    metadata=json.loads((app.import_directory/(item['id']+'.json')).read_text())
    assert metadata['preview_schema']==3 and metadata['preview_short_edge']==2048
    assert app._restore_preview({**metadata,'preview_schema':1}) is False


def test_old_low_resolution_cache_is_upgraded_lazily_from_immutable_source(app,monkeypatch):
    import json,hashlib
    from spectral_app.application import Application
    image=Image.new('RGB',(2400,1600),(30,60,90));stream=io.BytesIO();image.save(stream,format='PNG');data=stream.getvalue()
    item=app.import_image({'name':'legacy-resolution.png','data_base64':base64.b64encode(data).decode()})['input'];identifier=item['id']
    preview=app.model.output/'preview-cache'/(identifier+'.npy');np.save(preview,np.zeros((256,384,3)),allow_pickle=False)
    path=app.import_directory/(identifier+'.json');record=json.loads(path.read_text());record.update(preview_schema=1,preview_sha256=hashlib.sha256(preview.read_bytes()).hexdigest());record.pop('preview_short_edge',None);path.write_text(json.dumps(record))
    calls=[];original=Application._decode
    def track(self,*args):calls.append(True);return original(self,*args)
    monkeypatch.setattr(Application,'_decode',track)
    restored=Application(app.model)
    assert not calls and identifier in restored.pending_preview_upgrades
    restored._ensure_preview(identifier)
    assert calls and identifier not in restored.pending_preview_upgrades
    assert restored.model.inputs[identifier].shape==(1600,2400,3)
    assert (restored.import_directory/(identifier+'.source')).read_bytes()==data


@pytest.fixture
def app(tmp_path):
    from spectral_app.model import SpectralModel
    from spectral_app.application import Application
    root=Path(__file__).resolve().parents[1]
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',tmp_path)
    return Application(model)
