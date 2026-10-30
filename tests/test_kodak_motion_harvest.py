from pathlib import Path
import json
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def harvest(tmp_path_factory):
    from experiments.harvest_kodak_motion import harvest_collection
    directory=ROOT/'local/reference-assets/kodak-motion-user-2026'
    if not directory.is_dir():pytest.skip('User-supplied identified manufacturer PDFs required')
    output=tmp_path_factory.mktemp('kodak-motion-harvest')
    return harvest_collection(directory,output),output


def test_collection_keeps_four_vision3_stocks_and_excludes_verita(harvest):
    stocks,output=harvest
    assert set(stocks)=={'5203','5207','5213','5219'}
    for stock,entry in stocks.items():
        assert entry['source']['sha256'] and entry['process']=='ECN-2'
        assert {'characteristic_R','characteristic_G','characteristic_B','sensitivity_R','sensitivity_G','sensitivity_B','minimum_density','midscale_neutral'}.issubset(entry['curves'])
        assert entry['substitutions']==[]
        assert entry['missing_components']==[]
        assert {'dye_C','dye_M','dye_Y'}.issubset(entry['curves'])
        assert (output/stock/'source-curves.json').is_file()
    assert stocks['5219']['characteristic_density_status']=='unconfirmed_source_label'
    assert stocks['5203']['characteristic_density_status']=='not_specified_in_this_document'
    assert not (output/'5206').exists()
    assert '5206' in json.loads((output/'collection.json').read_text())['excluded_stocks']


def test_original_plot_landmarks_signed_density_and_unit_conversion(harvest):
    stocks,_=harvest
    for stock,entry in stocks.items():
        for c,low,high in [('B',380,490),('G',520,580),('R',610,690)]:
            a=np.array(entry['curves']['sensitivity_'+c]['points']);assert low<a[np.argmax(a[:,1]),0]<high,(stock,c)
        if stock!='5206':
            for c,low,high in [('Y',420,480),('M',510,580),('C',630,730)]:
                a=np.array(entry['curves']['dye_'+c]['points']);assert low<a[np.argmax(a[:,1]),0]<high,(stock,c)
                assert .95<a[:,1].max()<1.05
    assert np.array(stocks['5207']['curves']['dye_M']['points'])[:,1].min()<0
    blue=np.array(stocks['5219']['curves']['sensitivity_B']['points'])
    assert blue[:,1].max()>3.1
    assert stocks['5213']['sensitivity_exposure_seconds']==.04
    assert stocks['5213']['characteristic_exposure_seconds']==.02


def test_exports_keep_missing_tails_as_blanks_and_roundtrip_values(harvest):
    stocks,output=harvest
    for stock,entry in stocks.items():
        sensitivity=np.genfromtxt(output/stock/'sensitivity_log10.csv',delimiter=',',names=True)
        linear=np.genfromtxt(output/stock/'sensitivity_linear.csv',delimiter=',',names=True)
        for c in 'RGB':
            mask=np.isfinite(sensitivity[c]);np.testing.assert_allclose(linear[c][mask],10**sensitivity[c][mask],rtol=2e-12)
            assert np.isnan(sensitivity[c]).any() # unmeasured tails are not measured zero
        table=np.genfromtxt(output/stock/'characteristic.csv',delimiter=',',names=True)
        assert np.isfinite(table['R']).all()
        loaded=json.loads((output/stock/'source-curves.json').read_text())
        assert loaded['source']['sha256']==entry['source']['sha256']
        assert '/Users/' not in json.dumps(loaded) and '/Volumes/' not in json.dumps(loaded)

# Independent visual readings of labeled manufacturer plots, rather than a
# comparison with the application's existing materials or our resampled CSVs.
LANDMARKS=[
 ('5203','sensitivity_B',450,1.6,.06),('5203','sensitivity_G',550,1.6,.06),('5203','sensitivity_R',650,1.55,.06),
 ('5203','dye_Y',450,.98,.04),('5203','dye_M',540,1,.04),('5203','dye_C',680,1,.04),
 ('5207','characteristic_R',0,.89,.025),('5207','characteristic_G',0,1.40,.025),('5207','characteristic_B',0,1.64,.025),
 ('5207','sensitivity_B',450,2.37,.05),('5207','sensitivity_G',550,2.40,.05),('5207','sensitivity_R',650,2.38,.05),
 ('5207','dye_M',450,-.02,.025),('5207','dye_M',520,.855,.025),('5207','dye_C',760,.40,.03),
 ('5213','characteristic_R',0,.865,.025),('5213','characteristic_G',0,1.37,.025),('5213','characteristic_B',0,1.61,.025),
 ('5213','sensitivity_B',440,2.85,.05),('5213','sensitivity_G',550,2.48,.05),('5213','sensitivity_R',650,2.17,.05),
 ('5213','dye_M',520,.874,.025),('5213','dye_C',680,.99,.025),('5213','midscale_neutral',760,.42,.025),
 ('5219','sensitivity_B',400,3.20,.05),('5219','sensitivity_G',550,2.79,.05),('5219','sensitivity_R',650,2.44,.05),
 ('5219','dye_M',450,-.035,.025),('5219','dye_M',520,.849,.025),('5219','dye_C',680,1,.025),
]


def test_independent_manufacturer_plot_readings(harvest):
    from experiments.harvest_kodak_motion import interpolate
    stocks,_=harvest
    for stock,name,x,expected,tolerance in LANDMARKS:
        actual=interpolate(stocks[stock]['curves'][name],np.array([x]))[0]
        assert np.isfinite(actual) and abs(actual-expected)<=tolerance,(stock,name,x,actual,expected)


def test_source_identity_and_missing_intervals_are_not_silently_filled(harvest,tmp_path):
    from experiments.harvest_kodak_motion import SOURCES,harvest_collection,interpolate
    stock='5203';(tmp_path/SOURCES[stock]['file']).write_bytes(b'wrong source')
    with pytest.raises(ValueError,match='unexpected PDF hash'):
        harvest_collection(tmp_path,tmp_path/'out')
    # A missing interval must remain missing even when both endpoints exist.
    curve={'points':[[400,1],[410,.5],[430,.3]],'interpolation_gap_limit':8}
    assert np.isnan(interpolate(curve,np.array([405,420]))).all()
    curve={'points':[[400,1],[410,.5],[420,.3]],'interpolation_gap_limit':100,'support_intervals':[[400,410],[419,420]]}
    assert np.isnan(interpolate(curve,np.array([415]))).all()
    assert np.isfinite(interpolate(curve,np.array([405]))).all()
