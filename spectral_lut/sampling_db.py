"""Local, family-specific spectral sample databases with explicit source splits."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote

import numpy as np


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


@dataclass
class SpectrumRecord:
    identifier: str
    source_id: str
    group: str
    split: str
    kind: str
    wavelengths: np.ndarray
    values: np.ndarray

    def validate(self):
        x, y = np.asarray(self.wavelengths, dtype=np.float64), np.asarray(self.values, dtype=np.float64)
        if (x.ndim != 1 or y.shape != x.shape or len(x) < 2 or
                not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x) <= 0)):
            raise ValueError('Invalid spectral grid or values')
        if self.split not in ('fit', 'dev', 'audit', 'probe') or self.kind not in ('measured', 'synthetic'):
            raise ValueError('Unknown split or spectral kind')
        if not all(isinstance(v, str) and v for v in (self.identifier, self.source_id, self.group)):
            raise ValueError('Source and sample identities are required')
        return x, y

    def on_grid(self, grid):
        x, y = self.validate()
        grid = np.asarray(grid, dtype=np.float64)
        if (grid.ndim != 1 or not len(grid) or not np.isfinite(grid).all() or
                np.any(np.diff(grid) <= 0) or grid[0] < x[0] or grid[-1] > x[-1]):
            raise ValueError('Missing spectral coverage; extrapolation is not permitted')
        return np.interp(grid, x, y)


class SamplingDatabase:
    def __init__(self, path, connection):
        self.path, self.connection = Path(path), connection

    @classmethod
    def create(cls, path, family, metadata):
        if family not in ('reversal', 'negative'):
            raise ValueError('Unknown family')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        connection = sqlite3.connect(path)
        connection.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sources(id TEXT PRIMARY KEY, description TEXT NOT NULL);
            CREATE TABLE spectra(
                id TEXT PRIMARY KEY, source_id TEXT NOT NULL, group_id TEXT NOT NULL,
                split TEXT NOT NULL, kind TEXT NOT NULL, bands INTEGER NOT NULL,
                wavelengths_blob BLOB NOT NULL, values_blob BLOB NOT NULL,
                eligible INTEGER NOT NULL, quality TEXT NOT NULL);
            CREATE INDEX spectra_split ON spectra(split, eligible);
            CREATE INDEX spectra_group ON spectra(group_id);
            CREATE TABLE selections(name TEXT PRIMARY KEY, policy TEXT NOT NULL);
            CREATE TABLE selection_members(
                selection TEXT NOT NULL REFERENCES selections(name), rank INTEGER NOT NULL,
                spectrum_id TEXT NOT NULL REFERENCES spectra(id), weight REAL NOT NULL,
                PRIMARY KEY(selection, rank), UNIQUE(selection, spectrum_id));
            CREATE TABLE outputs(
                spectrum_id TEXT NOT NULL REFERENCES spectra(id), family TEXT NOT NULL,
                quantity TEXT NOT NULL, vector TEXT NOT NULL, conditions TEXT NOT NULL);
            CREATE TABLE probes(id TEXT PRIMARY KEY, kind TEXT NOT NULL, coordinates TEXT NOT NULL,
                                status TEXT NOT NULL, details TEXT NOT NULL);
        ''')
        result = cls(path, connection)
        result.set_metadata('schema', 'softloaf.spectral-samples/1')
        result.set_metadata('family', family)
        result.set_metadata('conditions', metadata)
        connection.commit()
        return result

    @classmethod
    def open(cls, path, family):
        path = Path(path)
        connection = sqlite3.connect('file:' + quote(str(path.resolve())) + '?mode=ro', uri=True)
        result = cls(path, connection)
        if result.metadata('family') != family or result.metadata('schema') != 'softloaf.spectral-samples/1':
            connection.close()
            raise ValueError('Database family or schema mismatch')
        return result

    def __enter__(self):
        return self

    def __exit__(self, kind, value, trace):
        if kind:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()

    def metadata(self, key):
        row = self.connection.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        if not row:
            raise ValueError('Missing database metadata: ' + key)
        return json.loads(row[0])

    def set_metadata(self, key, value):
        self.connection.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, encoded(value)))

    def add_source(self, identifier, description):
        self.connection.execute('INSERT INTO sources VALUES(?,?)', (identifier, encoded(description)))

    def add_spectrum(self, record):
        x, y = record.validate()
        tag = record.identifier.split('/', 1)[0]
        if tag in ('reversal', 'negative') and tag != self.metadata('family'):
            raise ValueError('Spectrum family mismatch')
        split = self.connection.execute('SELECT split FROM spectra WHERE group_id=? LIMIT 1', (record.group,)).fetchone()
        if split and split[0] != record.split:
            raise ValueError('A source group cannot cross a data split')
        quality = {'negative': bool(np.any(y < 0)), 'above_one': bool(np.any(y > 1)),
                   'quantity': 'spectral_reflectance_factor', 'unit': '1'}
        eligible = not quality['negative'] and not quality['above_one']
        self.connection.execute('INSERT INTO spectra VALUES(?,?,?,?,?,?,?,?,?,?)',
            (record.identifier, record.source_id, record.group, record.split, record.kind, len(x),
             x.astype('<f8').tobytes(), y.astype('<f8').tobytes(), int(eligible), encoded(quality)))

    def spectrum(self, identifier):
        row = self.connection.execute('SELECT id,source_id,group_id,split,kind,bands,wavelengths_blob,values_blob FROM spectra WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise KeyError(identifier)
        try:
            x, y = np.frombuffer(row[6], dtype='<f8').copy(), np.frombuffer(row[7], dtype='<f8').copy()
            if len(x) != row[5] or len(y) != row[5]:
                raise ValueError('Wrong spectral size')
            result = SpectrumRecord(*row[:5], x, y)
            result.validate()
        except (ValueError, TypeError) as error:
            raise ValueError('corrupt spectral record: ' + identifier) from error
        return result

    def eligible_ids(self, split):
        return [row[0] for row in self.connection.execute(
            "SELECT id FROM spectra WHERE split=? AND eligible=1 AND kind='measured' ORDER BY id", (split,))]

    def set_selection(self, name, identifiers, policy, weights=None):
        if len(set(identifiers)) != len(identifiers) or not identifiers:
            raise ValueError('A selection needs unique samples')
        for identifier in identifiers:
            row = self.connection.execute('SELECT split,eligible FROM spectra WHERE id=?', (identifier,)).fetchone()
            if not row or row[0] != 'fit':
                raise ValueError('Only fit samples can enter a fitted selection')
            if not row[1]:
                raise ValueError('Sample is not eligible for bounded-reflectance fitting')
        weights = np.ones(len(identifiers)) if weights is None else np.asarray(weights, dtype=np.float64)
        if weights.shape != (len(identifiers),) or not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError('Invalid sampling weights')
        self.connection.execute('INSERT INTO selections VALUES(?,?)', (name, encoded(policy)))
        self.connection.executemany('INSERT INTO selection_members VALUES(?,?,?,?)',
            [(name, i, identifier, float(weight)) for i, (identifier, weight) in enumerate(zip(identifiers, weights))])

    def add_output(self, identifier, family, quantity, vector, conditions):
        if family != self.metadata('family'):
            raise ValueError('Output family mismatch')
        if family == 'negative' and self.metadata('conditions').get('output_status') == 'APD_output_unimplemented':
            raise ValueError('Negative material output is unimplemented')
        vector = np.asarray(vector, dtype=np.float64)
        if vector.shape != (3,) or not np.isfinite(vector).all():
            raise ValueError('Invalid output quantity')
        self.connection.execute('INSERT INTO outputs VALUES(?,?,?,?,?)',
            (identifier, family, quantity, encoded(vector.tolist()), encoded(conditions)))

    def add_probe(self, identifier, kind, coordinates, status, details):
        self.connection.execute('INSERT INTO probes VALUES(?,?,?,?,?)',
            (identifier, kind, encoded(coordinates), status, encoded(details)))

    def counts(self):
        return {name: self.connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                for name in ('sources', 'spectra', 'outputs', 'selections', 'probes')}

    def audit(self):
        if self.connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        missing = self.connection.execute('SELECT DISTINCT source_id FROM spectra WHERE source_id NOT IN (SELECT id FROM sources)').fetchall()
        if missing:
            raise ValueError('Missing source records')
        leaking = self.connection.execute('SELECT group_id FROM spectra GROUP BY group_id HAVING COUNT(DISTINCT split)>1').fetchall()
        if leaking:
            raise ValueError('Data split leakage')
        for identifier, eligible in self.connection.execute('SELECT id,eligible FROM spectra'):
            record = self.spectrum(identifier)
            expected = bool(np.all((record.values >= 0) & (record.values <= 1)))
            if bool(eligible) != expected:
                raise ValueError('Corrupt spectral quality flag')
        family = self.metadata('family')
        if self.connection.execute('SELECT COUNT(*) FROM outputs WHERE family<>?', (family,)).fetchone()[0]:
            raise ValueError('Output family mismatch')
        if family == 'negative' and self.metadata('conditions').get('output_status') == 'APD_output_unimplemented' and self.counts()['outputs']:
            raise ValueError('Negative material output is unimplemented')
        return self.counts()
