import hashlib
import json
from pathlib import Path

import pytest
from spectral_app import runtime_setup as setup
from spectral_app.runtime_paths import SetupRequired


def inventory(root,names):
    root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name in names:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test input')
        rows.append({'path':name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest={'schema':'softloaf.runtime-science/1','files':rows}
    (root/'runtime-science.json').write_text(json.dumps(manifest))
    return manifest


def test_missing_inventory_cannot_silently_load_developer_assets(tmp_path):
    with pytest.raises(SetupRequired,match='prepared scientific-data'):setup.validate_science(tmp_path)


@pytest.mark.parametrize('name',['../private','/absolute','bad\\path','duplicate'])
def test_inventory_rejects_escaping_paths_and_duplicates(tmp_path,name):
    manifest=inventory(tmp_path,['duplicate'])
    manifest['files'].append({'path':name,'sha256':'0'*64})
    (tmp_path/'runtime-science.json').write_text(json.dumps(manifest))
    with pytest.raises(SetupRequired,match='inventory path'):setup.validate_science(tmp_path)


def test_changed_input_and_resolved_escape_are_not_accepted(tmp_path,monkeypatch):
    science=tmp_path/'science';inventory(science,['table.csv'])
    (science/'table.csv').write_text('changed')
    with pytest.raises(SetupRequired,match='differs'):setup.validate_science(science)
    external=tmp_path/'private';external.write_bytes(b'test input')
    (science/'table.csv').write_bytes(b'test input')
    resolve=Path.resolve
    monkeypatch.setattr(Path,'resolve',lambda p,*a,**k:external if p==science/'table.csv' else resolve(p,*a,**k))
    with pytest.raises(SetupRequired,match='differs'):setup.validate_science(science)


def test_incomplete_science_inventory_fails_closed(tmp_path):
    inventory(tmp_path,['table.csv'])
    with pytest.raises(SetupRequired,match='lacks required'):setup.validate_science(tmp_path)


def test_failed_configuration_keeps_previous_record_and_no_pixel_directory(tmp_path,monkeypatch):
    science=tmp_path/'science';science.mkdir();state=tmp_path/'state';state.mkdir()
    previous=b'{"previous":"preserved"}';(state/'runtime.json').write_bytes(previous)
    monkeypatch.setattr(Path,'is_mount',lambda p:p==tmp_path)
    monkeypatch.setattr(setup.sys,'platform','linux')
    with pytest.raises(SetupRequired):setup.configure(science,tmp_path/'pixels',tmp_path,state=state)
    assert (state/'runtime.json').read_bytes()==previous
    assert not (tmp_path/'pixels').exists()
    assert not (state/'runtime.working.json').exists()


def test_configuration_cannot_place_science_on_system_volume(tmp_path,monkeypatch):
    volume=tmp_path/'volume';volume.mkdir();science=tmp_path/'science';science.mkdir()
    monkeypatch.setattr(Path,'is_mount',lambda p:p==volume)
    monkeypatch.setattr(setup.sys,'platform','linux')
    with pytest.raises(SetupRequired,match='scientific-data directory'):setup.configure(science,volume/'pixels',volume,state=tmp_path/'state')
