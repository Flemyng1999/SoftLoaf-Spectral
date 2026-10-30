import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from spectral_app.material_plots import load_e100_plot

ROOT=Path(__file__).resolve().parents[1]


def test_e100_vectors_reproduce_reviewed_pdf_and_match_existing_material():
    plot_path=ROOT/'local/materials/e100-plot-v1/sensitivity.json'
    pdf=ROOT/'local/film-color-slides/hyperspectral-demo/data/reversal-E100/Kodak_E100_E4000_2018.pdf'
    if not plot_path.exists() or not pdf.exists():pytest.skip('Local E100 source assets required')
    pytest.importorskip('pymupdf')
    from experiments.extract_e100_plot import extract
    data=json.loads(plot_path.read_text())
    assert data==extract(pdf)
    assert [len(data['channels'][c]['values']) for c in 'RGB']==[381,265,385]
    material=ROOT/'local/film-color-slides/hyperspectral-demo/output/reversal-E100/data/E100_linear_sensitivity_RGB.csv'
    table=np.loadtxt(material,delimiter=',',skiprows=1)
    for j,c in enumerate('RGB'):
        s=data['channels'][c];x=np.array(s['wavelengths_nm']);y=np.array(s['values'])
        assert np.all(np.diff(x)>0)
        assert np.isfinite(y).all() and np.all(y>0)
        # Archived 10 nm samples have small digitization differences. This checks
        # correspondence, not a measured film accuracy or new calibration claim.
        expected=10**np.interp(table[:,0],x,np.log10(y),left=-np.inf,right=-np.inf)
        np.testing.assert_allclose(expected,table[:,j+1],rtol=.005,atol=1e-9)
    before=material.read_bytes()
    sources={'E100_linear_sensitivity_RGB.csv':hashlib.sha256(before).hexdigest()}
    loaded=load_e100_plot(ROOT,sources,10)['E100']['sensitivity']
    assert loaded['calculation_step_nm']==10
    assert load_e100_plot(ROOT,{'E100_linear_sensitivity_RGB.csv':'another material'},10)=={}
    assert material.read_bytes()==before


def test_optional_plot_fails_closed_on_tampering(tmp_path):
    assert load_e100_plot(tmp_path,{},10)=={}
    directory=tmp_path/'local/materials/e100-plot-v1';directory.mkdir(parents=True)
    (directory/'sensitivity.json').write_text('{}')
    (tmp_path/'data').mkdir()
    (tmp_path/'data/e100-plot-reference-manifest.json').write_text(json.dumps({'plot_sha256':'wrong'}))
    with pytest.raises(ValueError,match='identity mismatch'):load_e100_plot(tmp_path,{},10)
