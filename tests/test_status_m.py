"""Status M uses the retained standard spectral products, not film sensitivity."""
from pathlib import Path
import shutil
import numpy as np
import pytest


def test_source_log_values_and_tail_slopes_are_preserved():
    from spectral_lut.densitometry import load_status_m
    grid=np.arange(360.,801.)
    products,meta=load_status_m(Path.cwd(),grid)
    # Selected printed table entries and slopes, independently read from
    # ISO 5/3:1984 Table 4 and ANSI/ISO 5-3:1995 Table 4.
    for c,peak in enumerate([640,540,450]):assert products[int(peak-360),c]==pytest.approx(1)
    assert products[620-360,0]==pytest.approx(10**(2.109-5))
    assert products[550-360,1]==pytest.approx(10**(4.995-5))
    assert products[420-360,2]==pytest.approx(10**(4.111-5))
    assert products[610-360,0]/products[620-360,0]==pytest.approx(10**-2.6)
    assert products[780-360,0]/products[770-360,0]==pytest.approx(10**-.4)
    assert products[460-360,1]/products[470-360,1]==pytest.approx(10**-1.06)
    assert products[620-360,1]/products[610-360,1]==pytest.approx(10**-1.2)
    assert products[400-360,2]/products[410-360,2]==pytest.approx(10**-2.5)
    assert products[520-360,2]/products[510-360,2]==pytest.approx(10**-2.2)
    assert meta['metric']=='Status M' and meta['interpolation']=='linear in log10 spectral product'


def test_source_table_identity_is_required(tmp_path):
    from spectral_lut.densitometry import load_status_m
    root=Path.cwd();(tmp_path/'data').mkdir()
    shutil.copy(root/'data/status-m-reference-manifest.json',tmp_path/'data')
    folder=tmp_path/'local/materials/status-m-iso1984';folder.mkdir(parents=True)
    source=root/'local/materials/status-m-iso1984/table4.json'
    (folder/'table4.json').write_bytes(source.read_bytes()+b' ')
    with pytest.raises(ValueError,match='Status M'):load_status_m(tmp_path,np.arange(360,731,2))
