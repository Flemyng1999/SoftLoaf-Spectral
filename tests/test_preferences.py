import json
import pytest
from spectral_app.preferences import Preferences


def test_preferences_roundtrip_and_invalid_values_do_not_overwrite(tmp_path):
    path=tmp_path/'ui.json';p=Preferences(path)
    assert p.state()['language']=='system'
    p.update({'language':'en'});assert Preferences(path).state()['language']=='en'
    before=path.read_bytes()
    for value in ('EN',True,None,{},['en']):
        with pytest.raises(ValueError):p.update({'language':value})
    assert path.read_bytes()==before


def test_corrupt_preferences_are_preserved_and_block_overwriting(tmp_path):
    path=tmp_path/'ui.json';path.write_text('{broken')
    p=Preferences(path);assert p.state()['warning']
    with pytest.raises(ValueError):p.update({'language':'zh-CN'})
    assert path.read_text()=='{broken'
