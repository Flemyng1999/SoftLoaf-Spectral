import json
from pathlib import Path
import sys

import pytest

from spectral_app import runtime_paths as paths


def frozen(monkeypatch,tmp_path):
    bundle=tmp_path/'readonly-install';bundle.mkdir()
    state=tmp_path/'user-state'
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'_MEIPASS',str(bundle),raising=False)
    monkeypatch.setenv('SOFTLOAF_STATE_HOME',str(state))
    return bundle,state


def test_development_paths_remain_explicit_and_unchanged(tmp_path):
    assert not paths.packaged()
    assert paths.science_root(tmp_path)==tmp_path
    assert paths.state_root()==Path(__file__).resolve().parents[1]


def test_frozen_settings_and_science_never_resolve_under_installation(monkeypatch,tmp_path):
    bundle,state=frozen(monkeypatch,tmp_path)
    library=tmp_path/'external-science';library.mkdir()
    state.mkdir();(state/'runtime.json').write_text(json.dumps({'schema':1,'science_root':str(library),
        'data_root':str(tmp_path/'volume/cache'),'volume':str(tmp_path/'volume')}),encoding='utf-8')
    assert paths.resources()==bundle
    assert paths.state_root()==state
    assert paths.science_root()==library
    assert paths.science_root(bundle)==library
    assert paths.state_path('local/ui-settings.json')==state/'local/ui-settings.json'
    assert not list(bundle.iterdir())


def test_missing_or_corrupt_frozen_configuration_does_not_use_developer_data(monkeypatch,tmp_path):
    bundle,state=frozen(monkeypatch,tmp_path)
    with pytest.raises(paths.SetupRequired):paths.science_root()
    state.mkdir();(state/'runtime.json').write_text('{broken',encoding='utf-8')
    with pytest.raises(paths.SetupRequired):paths.settings()
    assert not list(bundle.iterdir())


def test_explicit_test_or_import_roots_are_not_redirected(monkeypatch,tmp_path):
    bundle,state=frozen(monkeypatch,tmp_path)
    other=tmp_path/'explicit-fixture'
    assert paths.science_root(other)==other


def test_frozen_storage_reads_user_configuration_and_preserves_state_owner(monkeypatch,tmp_path):
    from spectral_app.storage import DataStorage
    bundle,state=frozen(monkeypatch,tmp_path)
    volume=tmp_path/'volume';state.mkdir()
    (state/'runtime.json').write_text(json.dumps({'schema':1,'science_root':str(volume/'science'),
        'data_root':str(volume/'pixels'),'volume':str(volume)}),encoding='utf-8')
    storage=DataStorage.configured()
    assert storage.root==volume/'pixels' and storage.volume==volume and storage.project==state
    assert not list(bundle.iterdir())
