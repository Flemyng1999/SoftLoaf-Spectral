from pathlib import Path
import pytest
from scripts.stage_installer import stage


def test_staging_rejects_a_frozen_runtime_whose_raw_executables_were_lost(tmp_path):
    service=tmp_path/'service';internal=service/'_internal';(internal/'spectral_app').mkdir(parents=True)
    (internal/'spectral_app/model.py').write_text('# fixture')
    for role in ('raw-engine','raw-reference'):
        resource=internal/role/'bin';resource.mkdir(parents=True)
        for name in ('camconst.json','cammatrices.json','dcraw.json','options'):(resource/name).write_bytes(b'fixture')
    for name in ('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll'):(internal/name).write_bytes(b'fixture')
    native=tmp_path/'native.exe';native.write_bytes(b'fixture');notices=tmp_path/'notices';notices.mkdir()
    with pytest.raises(ValueError,match='RAW executable missing'):
        stage('windows',native,service,notices,tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_windows_staging_uses_the_current_release_icon(tmp_path):
    from scripts.stage_installer import ROOT
    service=tmp_path/'service';internal=service/'_internal';(internal/'spectral_app').mkdir(parents=True)
    (internal/'spectral_app/model.py').write_text('# fixture')
    for role in ('raw-engine','raw-reference'):
        resource=internal/role/'bin';resource.mkdir(parents=True)
        for name in ('camconst.json','cammatrices.json','dcraw.json','options','rawtherapee-cli.exe'):(resource/name).write_bytes(b'fixture')
    for name in ('MSVCP140.dll','VCRUNTIME140.dll','VCRUNTIME140_1.dll'):(internal/name).write_bytes(b'fixture')
    native=tmp_path/'native.exe';native.write_bytes(b'fixture');notices=tmp_path/'notices';notices.mkdir()
    stage('windows',native,service,notices,tmp_path/'output')
    assert (tmp_path/'output/App.ico').read_bytes()==(ROOT/'assets/branding/SoftLoafSpectral.ico').read_bytes()
