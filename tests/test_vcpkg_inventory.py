import json
from pathlib import Path
import pytest


def test_vcpkg_audit_rejects_unreviewed_features_before_copying(tmp_path):
    from scripts.vcpkg_inventory import audit
    provider=tmp_path/'installed/share/libpng';provider.mkdir(parents=True)
    (provider/'vcpkg_abi_info.txt').write_text('features core;apng\n')
    with pytest.raises(ValueError,match='additional vcpkg features'):
        audit(tmp_path/'tools',tmp_path/'installed',tmp_path/'service',tmp_path/'notices',tmp_path/'sources')
    assert not (tmp_path/'notices').exists() and not (tmp_path/'sources').exists()
