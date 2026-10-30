import hashlib,io,tarfile
from pathlib import Path
import pytest


def test_package_fields_keep_multi_license_and_multiline_file_names():
    from scripts.msys2_inventory import parse_fields
    fields=parse_fields('%NAME%\nmingw-w64-ucrt-x86_64-demo\n\n%LICENSE%\nLGPL-2.1-or-later\nMIT\n\n%FILES%\nucrt64/bin/demo.dll\nucrt64/share/licenses/demo/LICENSE\n')
    assert fields['LICENSE']==['LGPL-2.1-or-later','MIT']
    assert fields['FILES'][0]=='ucrt64/bin/demo.dll'


def test_native_provider_requires_bytes_to_match_the_original_binary_package(tmp_path):
    from scripts.msys2_inventory import verify_member
    package=tmp_path/'public-package.tar';member='ucrt64/bin/demo.dll';binary=tmp_path/'demo.dll';binary.write_bytes(b'reviewed code')
    with tarfile.open(package,'w') as archive:
        info=tarfile.TarInfo(member);info.size=len(binary.read_bytes());archive.addfile(info,io.BytesIO(binary.read_bytes()))
    assert verify_member(binary,package,member)==hashlib.sha256(binary.read_bytes()).hexdigest()
    binary.write_bytes(b'different code')
    with pytest.raises(ValueError,match='differs from its binary package'):verify_member(binary,package,member)


def test_source_archive_requires_the_recipe_used_for_the_binary_build(tmp_path):
    from scripts.msys2_inventory import verify_source_recipe
    archive=tmp_path/'source.tar';recipe=b'pkgname=demo\npkgver=1.0\n'
    with tarfile.open(archive,'w') as tar:
        info=tarfile.TarInfo('mingw-w64-demo/PKGBUILD');info.size=len(recipe);tar.addfile(info,io.BytesIO(recipe))
    expected=hashlib.sha256(recipe).hexdigest()
    assert verify_source_recipe(archive,'mingw-w64-demo',expected)==expected
    with pytest.raises(ValueError,match='source recipe differs'):
        verify_source_recipe(archive,'mingw-w64-demo','0'*64)


def test_source_notices_include_nested_upstream_license_without_path_traversal(tmp_path):
    from scripts.msys2_inventory import source_notices
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode='w:gz') as nested:
        for name in ('demo/COPYING','../../escape/COPYING','C:/escape/COPYING','..\\escape\\COPYING'):
            info=tarfile.TarInfo(name);info.size=7;nested.addfile(info,io.BytesIO(b'License'))
    archive=tmp_path/'source.tar'
    with tarfile.open(archive,'w') as outer:
        info=tarfile.TarInfo('package/upstream.tar.gz');info.size=len(data.getvalue());outer.addfile(info,io.BytesIO(data.getvalue()))
    assert source_notices(archive,tmp_path/'notices')==1
    assert (tmp_path/'notices/upstream.tar.gz/demo/COPYING').read_bytes()==b'License'
    assert not (tmp_path/'escape').exists()
