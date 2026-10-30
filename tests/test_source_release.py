import json
from pathlib import Path

import pytest

from scripts.source_release import validate_entry

ROOT=Path(__file__).resolve().parents[1]


def policy():
    return json.loads((ROOT/'release/source-policy.json').read_text())


@pytest.mark.parametrize('name',['local/material.json','artifacts/sampling-database/models/a.npz',
    'data/material.npz','tests/capture.ARW','docs/source.pdf','../private.txt','/private.txt',
    'video/manuscript.md','spectral_app/__pycache__/a.pyc','core/build/x.cpp'])
def test_source_payload_rejects_private_data_and_generated_products(name):
    with pytest.raises(ValueError):validate_entry(name,b'not public source',policy())


def test_scientific_csv_is_limited_to_verified_original_cie_files():
    name='assets/science/cie/CIE_illum_D55.csv';data=(ROOT/name).read_bytes()
    validate_entry(name,data,policy())
    with pytest.raises(ValueError):validate_entry(name,data+b'\n',policy())
    with pytest.raises(ValueError):validate_entry('data/film-sensitivity.csv',b'400,1',policy())


def test_identity_manifest_cannot_smuggle_a_sensitivity_table():
    name='data/vision3-materials-manifest.json';raw=(ROOT/name).read_bytes()
    validate_entry(name,raw,policy())
    value=json.loads(raw);value['materials'][0]['fit']['provenance']={'channels':{'R':[1]*33}}
    with pytest.raises(ValueError):validate_entry(name,json.dumps(value).encode(),policy())


def test_credential_and_personal_path_checks_do_not_echo_values():
    for raw in (b'-----BEGIN '+b'PRIVATE KEY-----\n'+b'A'*64,b'/Users/'+b'flemyng/private/file'):
        with pytest.raises(ValueError) as exc:validate_entry('scripts/example.py',raw,policy())
        assert raw.decode() not in str(exc.value)


def test_release_version_and_public_fit_summaries_are_consistent():
    import spectral_app
    assert spectral_app.__version__==(ROOT/'VERSION').read_text().strip()
    assert spectral_app.__version__.startswith('0.1.0-alpha.')
    from spectral_lut.provenance import public_fit_summary
    source={'name':'synthetic','fit_metric':'Status M','fingerprint':'abc','neutral_max_error_D':.001,
            'provenance':{'exposure_reference':{'channels':{'R':[1]*33}}}}
    assert public_fit_summary(source)=={k:source[k] for k in policy()['public_fit_fields']}
    assert 'provenance' in source
