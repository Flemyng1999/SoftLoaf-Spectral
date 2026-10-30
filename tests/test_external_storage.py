from pathlib import Path
import uuid
import pytest


@pytest.fixture(autouse=True)
def simulate_mounted_test_volume(monkeypatch):
    from spectral_app.storage import DataStorage
    monkeypatch.setattr(DataStorage,'mounted',lambda self:True)


def test_data_directory_is_on_external_volume_and_workspace_stays_in_project(tmp_path):
    from spectral_app.storage import DataStorage
    root=Path(__file__).resolve().parents[1]
    base=root/'artifacts'/('storage-policy-test-'+uuid.uuid4().hex)
    base.mkdir();workspace=base/'workspace.json';workspace.write_text('{"recipe":"preserve"}')
    storage=DataStorage(root=tmp_path/'external-data',volume=tmp_path,project=root)
    try:
        data=storage.directory(base/'raw-cache')
        assert data.is_relative_to(tmp_path/'external-data')
        (data/'probe').write_bytes(b'test')
        assert (base/'raw-cache').is_symlink()
        assert workspace.read_text()=='{"recipe":"preserve"}' and not workspace.is_symlink()
    finally:
        (base/'raw-cache').unlink(missing_ok=True);workspace.unlink();base.rmdir()


def test_storage_never_migrates_or_overwrites_existing_unreviewed_data(tmp_path):
    from spectral_app.storage import DataStorage
    root=Path(__file__).resolve().parents[1];base=root/'artifacts'/('storage-policy-test-'+uuid.uuid4().hex);base.mkdir()
    old=base/'raw-cache';old.mkdir();metadata=old/'manifest.json';metadata.write_text('{"keep":true}')
    storage=DataStorage(root=tmp_path/'external-data',volume=tmp_path,project=root)
    try:
        with pytest.raises(RuntimeError,match='迁移'):storage.directory(old)
        assert metadata.read_text()=='{"keep":true}' and not old.is_symlink()
    finally:metadata.unlink();old.rmdir();base.rmdir()


def test_missing_external_volume_does_not_create_internal_fallback(tmp_path,monkeypatch):
    from spectral_app.storage import DataStorage
    root=tmp_path/'not-created'
    storage=DataStorage(root=root,volume=tmp_path,project=Path.cwd())
    monkeypatch.setattr(storage,'mounted',lambda:False)
    with pytest.raises(RuntimeError,match='连接'):storage.directory(Path.cwd()/'artifacts'/'must-not-create')
    assert not root.exists() and not (Path.cwd()/'artifacts'/'must-not-create').exists()


def test_raw_original_file_and_temporary_directory_use_external_storage(tmp_path):
    from spectral_app.storage import DataStorage
    root=Path(__file__).resolve().parents[1]
    storage=DataStorage(root=tmp_path/'external-data',volume=tmp_path,project=root)
    relative=Path('artifacts')/('storage-policy-test-'+uuid.uuid4().hex)/'inputs/user_abc.source'
    source=storage.file(root/relative)
    assert source==tmp_path/'external-data/data'/relative
    (root/relative).unlink();(root/relative).parent.rmdir();(root/relative).parent.parent.rmdir()
    temporary=storage.temporary_directory()
    assert temporary.is_relative_to(tmp_path/'external-data')
