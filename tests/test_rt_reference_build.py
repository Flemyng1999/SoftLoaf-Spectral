from pathlib import Path
import json
import pytest


def test_reference_builder_rejects_unidentified_source_before_creating_build_outputs(tmp_path):
    from scripts.build_windows_rt_reference import build
    source=tmp_path/'source';output=tmp_path/'build';archive=tmp_path/'source.tar.xz'
    archive.write_bytes(b'not the pinned upstream source')
    with pytest.raises(ValueError,match='source archive'):
        build(archive,tmp_path/'toolchain',source,output)
    assert not source.exists() and not output.exists()


def test_integrated_builder_rejects_a_changed_declared_source_before_compiling(tmp_path):
    from scripts.build_windows_rt_reference import build_integrated
    source=tmp_path/'source';source.mkdir();(source/'CMakeLists.txt').write_text('changed')
    (source/'softloaf-source.json').write_text(json.dumps({'local_changes':{'CMakeLists.txt':'0'*64}}))
    with pytest.raises(ValueError,match='source identity differs'):
        build_integrated(source,tmp_path/'toolchain',tmp_path/'output')
    assert not (tmp_path/'output').exists()
