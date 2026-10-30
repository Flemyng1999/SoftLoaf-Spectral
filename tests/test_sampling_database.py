from contextlib import closing
import sqlite3

import numpy as np
import pytest

from spectral_lut.sampling_db import SamplingDatabase, SpectrumRecord


def record(identifier='one', group='scene1', split='fit', values=None):
    return SpectrumRecord(identifier, 'source', group, split, 'measured',
                          np.array([400., 410., 420.]),
                          np.array([.1, .2, .3]) if values is None else np.asarray(values))


def test_family_is_checked_when_opening_a_database(tmp_path):
    path = tmp_path/'reversal.sqlite'
    with SamplingDatabase.create(path, 'reversal', {'stock': 'E100'}) as db:
        db.add_spectrum(record())
    with pytest.raises(ValueError, match='family'):
        SamplingDatabase.open(path, 'negative')
    with SamplingDatabase.open(path, 'reversal') as db:
        np.testing.assert_array_equal(db.spectrum('one').values, [.1, .2, .3])


def test_source_group_cannot_cross_data_splits(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'negative', {}) as db:
        db.add_spectrum(record())
        with pytest.raises(ValueError, match='split'):
            db.add_spectrum(record('two', split='audit'))


def test_out_of_bound_factors_are_retained_and_excluded_from_bounded_fit(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'negative', {}) as db:
        db.add_spectrum(record(values=[.1, 1.2, .3]))
        stored = db.spectrum('one')
        assert stored.values[1] == 1.2
        assert not db.eligible_ids('fit')
        with pytest.raises(ValueError, match='eligible'):
            db.set_selection('main', ['one'], {})


def test_audit_records_cannot_enter_a_fit_selection(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'reversal', {}) as db:
        db.add_spectrum(record(split='audit'))
        with pytest.raises(ValueError, match='fit'):
            db.set_selection('main', ['one'], {})


def test_negative_database_rejects_reversal_outputs(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'negative', {}) as db:
        db.add_spectrum(record())
        with pytest.raises(ValueError, match='family'):
            db.add_output('one', 'reversal', 'XYZ_D65', [.1, .2, .3], {})
        assert db.counts()['outputs'] == 0


def test_cannot_overwrite_an_existing_database(tmp_path):
    path = tmp_path/'db.sqlite'
    with SamplingDatabase.create(path, 'reversal', {}) as db:
        db.add_spectrum(record())
    with pytest.raises(FileExistsError):
        SamplingDatabase.create(path, 'reversal', {})


def test_corrupt_spectral_blob_fails_readback(tmp_path):
    path = tmp_path/'db.sqlite'
    with SamplingDatabase.create(path, 'reversal', {}) as db:
        db.add_spectrum(record())
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('UPDATE spectra SET values_blob=?', (b'broken',))
    with SamplingDatabase.open(path, 'reversal') as db:
        with pytest.raises(ValueError, match='corrupt'):
            db.spectrum('one')


def test_unimplemented_negative_output_cannot_gain_fabricated_APD_labels(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'negative', {'output_status': 'APD_output_unimplemented'}) as db:
        db.add_spectrum(record())
        with pytest.raises(ValueError, match='unimplemented'):
            db.add_output('one', 'negative', 'APD', [.1, .2, .3], {})


def test_native_grid_cannot_be_extrapolated_for_missing_bands():
    with pytest.raises(ValueError, match='coverage'):
        record().on_grid([390., 400., 410.])


def test_family_tagged_samples_cannot_be_inserted_in_another_family(tmp_path):
    with SamplingDatabase.create(tmp_path/'db.sqlite', 'negative', {}) as db:
        with pytest.raises(ValueError, match='family'):
            db.add_spectrum(record('reversal/one'))


def test_readback_audit_rechecks_quality_flags(tmp_path):
    path = tmp_path/'db.sqlite'
    with SamplingDatabase.create(path, 'reversal', {}) as db:
        db.add_source('source', {})
        db.add_spectrum(record(values=[.1, 1.2, .3]))
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('UPDATE spectra SET eligible=1')
    with SamplingDatabase.open(path, 'reversal') as db:
        with pytest.raises(ValueError, match='quality'):
            db.audit()


def test_family_conditions_do_not_borrow_reversal_viewing_for_negative():
    from experiments.build_sampling_database import family_conditions
    reference = {'view': 'E100 D50 viewing', 'view_gain': 1.8}
    negative = family_conditions('negative', {'grid_nm': [400, 720, 10]}, reference)
    assert negative['stock'] == '5207'
    assert negative['output_conditions']['status'] == 'unimplemented'
    assert negative['output_conditions'].get('view_gain') is None
    assert negative['output_conditions'].get('view') is None
    reversal = family_conditions('reversal', {'grid_nm': [400, 720, 10]}, reference)
    assert reversal['output_conditions']['view_gain'] == 1.8
