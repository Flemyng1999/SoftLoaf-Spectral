from pathlib import Path
import hashlib

from scripts.install_rt_resources import install


def test_upstream_platform_options_are_installed_as_a_regular_runtime_file(tmp_path):
    source=tmp_path/'source';(source/'options').mkdir(parents=True)
    engine=tmp_path/'rtengine';engine.mkdir();(engine/'camconst.json').write_bytes(b'{"camera":"crop and black levels"}')
    for platform in ('osx','win','lin'):(source/'options'/('options.'+platform)).write_bytes(platform.encode())
    (source/'cammatrices.json').write_bytes(b'{"original":"camera data"}')
    (source/'profiles').mkdir();(source/'profiles/default.pp3').write_bytes(b'upstream parameters')
    original=hashlib.sha256((source/'cammatrices.json').read_bytes()).hexdigest()
    target=tmp_path/'installed';(target/'options').mkdir(parents=True);(target/'options/stale').write_bytes(b'stale source layout')
    install(source,target,'windows')
    assert (target/'options').is_file() and (target/'options').read_bytes()==b'win'
    assert hashlib.sha256((target/'cammatrices.json').read_bytes()).hexdigest()==original
    assert (target/'profiles/default.pp3').read_bytes()==b'upstream parameters'
    assert (target/'camconst.json').read_bytes()==(engine/'camconst.json').read_bytes()
    install(source,target,'macos')
    assert (target/'options').read_bytes()==b'osx'
    assert (source/'options/options.win').read_bytes()==b'win'


def test_macos_rt_resource_relocation_preserves_offsets_and_numeric_bytes(tmp_path):
    from scripts.bundle_macos_raw import relocate_resource_literals
    path=tmp_path/'compatibility-reader'
    original=b'CODE\x01\x02\x03'+b'/Applications/RawTherapee.app/Contents/Resources/share\0'+b'NUMERIC\x04\x05'+b'/Applications/RawTherapee.app/Contents/Resources\0'+b'TAIL'
    path.write_bytes(original);changes=relocate_resource_literals(path);actual=path.read_bytes()
    assert len(actual)==len(original) and len(changes)==2
    assert actual.index(b'NUMERIC')==original.index(b'NUMERIC')
    assert actual.endswith(b'TAIL') and actual.startswith(b'CODE\x01\x02\x03')
    assert b'../Resources/share\0' in actual
    assert not relocate_resource_literals(path)
