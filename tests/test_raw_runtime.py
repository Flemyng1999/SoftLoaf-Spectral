"""Platform runtime discovery and actual Windows handoff file ownership."""
import json
from pathlib import Path
import pytest


def test_windows_runtime_configuration_resolves_three_roles(tmp_path):
    from spectral_app.raw_runtime import RawRuntime
    root=tmp_path/'source';(root/'local').mkdir(parents=True)
    engine=tmp_path/'engine/rawtherapee-cli.exe';reference=tmp_path/'official/rawtherapee-cli.exe'
    for p in (engine,reference):p.parent.mkdir();p.write_bytes(b'executable')
    (root/'local/raw-runtime.json').write_text(json.dumps({'schema':1,'integrated':str(engine),'reference':str(reference),'dll_directory':str(tmp_path/'dlls')}))
    runtime=RawRuntime(root,platform='win32')
    assert runtime.cli==engine and runtime.preview==engine and runtime.integrated==engine and runtime.reference==reference
    assert runtime.resources==engine.parent
    env=runtime.environment(reference,{'PATH':'original'})
    assert env['PATH'].split(__import__('os').pathsep)==[str(reference.parent),str(tmp_path/'dlls'),'original']


def test_explicit_official_reader_does_not_masquerade_as_integrated(tmp_path):
    from spectral_app.raw_runtime import RawRuntime
    root=tmp_path/'source';official=tmp_path/'official/rawtherapee-cli.exe';official.parent.mkdir();official.write_bytes(b'official')
    runtime=RawRuntime(root,cli=official,platform='win32')
    assert runtime.cli==official and runtime.integrated!=official
    assert runtime.resources==official.parent


def test_macos_layout_and_reference_override_are_preserved(tmp_path,monkeypatch):
    from spectral_app.raw_runtime import RawRuntime
    root=tmp_path;exe=root/'local/runtime/RawTherapeeEngine.app/Contents/MacOS/rawtherapee-cli';exe.parent.mkdir(parents=True);exe.write_bytes(b'engine')
    resources=exe.parent.parent/'Resources/share';resources.mkdir(parents=True)
    reference=root/'official';reference.write_bytes(b'official')
    monkeypatch.setenv('SOFTLOAF_RAWTHERAPEE_REFERENCE',str(reference))
    runtime=RawRuntime(root,platform='darwin')
    assert runtime.cli==exe and runtime.preview==exe and runtime.resources==resources and runtime.reference==reference


def test_lcms_windows_named_dll_is_resolved_without_system_install(tmp_path,monkeypatch):
    from spectral_app.raw_runtime import find_lcms2
    lib=tmp_path/'liblcms2-2.dll';lib.write_bytes(b'library')
    monkeypatch.setenv('SOFTLOAF_LCMS2_LIBRARY',str(lib))
    assert find_lcms2()==str(lib)


def test_malformed_runtime_config_fails_instead_of_silent_fallback(tmp_path):
    from spectral_app.raw_runtime import RawRuntime
    (tmp_path/'local').mkdir();(tmp_path/'local/raw-runtime.json').write_text('{"schema":9}')
    with pytest.raises(ValueError,match='runtime'):RawRuntime(tmp_path)


def test_windows_symlink_privilege_failure_copies_exact_typed_source(tmp_path,monkeypatch):
    import hashlib
    from spectral_app.rawtherapee import typed_raw_source
    source=tmp_path/'original.source';source.write_bytes(b'RAW source bytes');target=tmp_path/'original.CR3'
    def denied(*a,**kw):
        error=OSError(22,'symbolic link privilege unavailable');error.winerror=1314;raise error
    monkeypatch.setattr(Path,'symlink_to',denied)
    typed_raw_source(source,target,hashlib.sha256(source.read_bytes()).hexdigest())
    assert not target.is_symlink() and target.read_bytes()==source.read_bytes()


def test_typed_copy_does_not_hide_other_filesystem_errors(tmp_path,monkeypatch):
    from spectral_app.rawtherapee import typed_raw_source
    def denied(*a,**kw):raise OSError(22,'other invalid parameter')
    monkeypatch.setattr(Path,'symlink_to',denied)
    with pytest.raises(OSError):typed_raw_source(tmp_path/'original',tmp_path/'original.CR3','0'*64)
