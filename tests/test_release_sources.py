import copy
import csv
import hashlib
import json
from pathlib import Path

from scripts.check_release_sources import check


def approved(tmp_path):
    (tmp_path/'table.csv').write_text('400,0.5\n')
    (tmp_path/'notice.txt').write_text('Attribution and original licence record')
    return {'schema':1,'roots':['table'],'assets':[{
        'id':'table','status':'approved','source_kind':'original',
        'source':'https://example.org/original/table.csv',
        'path':'table.csv','sha256':hashlib.sha256((tmp_path/'table.csv').read_bytes()).hexdigest(),
        'license_record':'notice.txt','dependencies':[]}]}


def test_original_bytes_and_notices_are_required(tmp_path):
    review=approved(tmp_path)
    assert check(review,tmp_path)==[]
    (tmp_path/'table.csv').write_text('400,0.6\n')
    assert any('SHA-256' in x for x in check(review,tmp_path))
    (tmp_path/'notice.txt').unlink()
    assert any('license_record' in x for x in check(review,tmp_path))


def test_model_cannot_hide_pending_or_missing_training_input(tmp_path):
    review=approved(tmp_path)
    review['assets'].append({'id':'training','status':'pending'})
    review['assets'][0]['dependencies']=['training','unknown']
    errors=check(review,tmp_path)
    assert any('training: pending' in x for x in errors)
    assert any('unknown: missing' in x for x in errors)


def test_repository_curves_need_documented_unavoidable_exception(tmp_path):
    review=approved(tmp_path);item=review['assets'][0]
    item.update(source_kind='upstream_repository',source='https://github.com/example/curves')
    assert any('fallback' in x for x in check(review,tmp_path))
    item['fallback']={'original_unavailable':True,'reason':'Search did not locate original numeric data',
                      'limitations':'Digitized estimate; measurement conditions unknown',
                      'search_record':'notice.txt'}
    assert check(review,tmp_path)==[]
    item['fallback']['original_unavailable']=False
    assert any('fallback' in x for x in check(review,tmp_path))


def test_source_and_payload_paths_cannot_escape_candidate(tmp_path):
    review=approved(tmp_path)
    review['assets'][0]['path']='../private.csv'
    assert any('outside' in x for x in check(review,tmp_path))
    review['assets'][0]['path']='/Users/private/raw.csv'
    assert any('outside' in x for x in check(review,tmp_path))


def test_cycles_duplicate_ids_and_unlisted_assets_are_rejected(tmp_path):
    review=approved(tmp_path);review['assets'][0]['dependencies']=['table']
    assert any('cycle' in x for x in check(review,tmp_path))
    review=approved(tmp_path);review['assets'].append(copy.deepcopy(review['assets'][0]))
    assert any('duplicate' in x for x in check(review,tmp_path))
    review=approved(tmp_path);review['assets'].append({'id':'unlisted','status':'pending'})
    assert any('unlisted' in x for x in check(review,tmp_path))


def test_repository_review_has_no_hidden_integrity_or_dependency_failures():
    root=Path(__file__).resolve().parents[1]
    review=json.loads((root/'release/scientific-sources.json').read_text())
    errors=check(review,root)
    pending={f'{item["id"]}: pending distribution' for item in review['assets']
             if item['status']=='pending'}
    assert set(errors)==pending


def test_cie_originals_match_official_hashes_and_actual_grids():
    root=Path(__file__).resolve().parents[1]/'assets/science/cie'
    manifest=json.loads((root/'sources.json').read_text())
    expected={
        'CIE_xyz_1931_2deg.csv':(471,360,830,1,4),
        'CIE_std_illum_D50.csv':(531,300,830,1,2),
        'CIE_std_illum_D65.csv':(531,300,830,1,2),
        'CIE_illum_D55.csv':(97,300,780,5,2),
        'CIE_illum_Dxx_comp.csv':(107,300,830,5,4)}
    assert {x['id'] for x in manifest['files']}==set(expected)
    for item in manifest['files']:
        raw=(root/item['id']).read_bytes();meta_raw=(root/item['metadata']).read_bytes()
        assert hashlib.sha256(meta_raw).hexdigest()==item['metadata_sha256']
        meta=json.loads(meta_raw)
        official=next(c['checksum'] for c in meta['checksums'] if c['hashMethod']=='sha256')
        assert hashlib.sha256(raw).hexdigest()==official==item['sha256']
        rows=list(csv.reader(raw.decode().splitlines()))
        count,start,end,step,columns=expected[item['id']]
        assert len(rows)==count and all(len(r)==columns for r in rows)
        assert [float(r[0]) for r in rows]==list(range(start,end+1,step))
        sample=next([float(v) for v in r[1:]] for r in rows if r[0]=='560')
        assert sample==([.5945,.995,.0039] if 'xyz' in item['id'] else
                        [100,0,0] if 'comp' in item['id'] else [100])
