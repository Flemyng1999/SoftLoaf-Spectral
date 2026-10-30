import hashlib
import json
from pathlib import Path

import pytest

from spectral_app.presets import load_recipe_presets


def test_catalog_rejects_changed_file_but_negative_method_is_independent(tmp_path):
    directory=tmp_path/'local/materials/film-presets-v1';directory.mkdir(parents=True)
    manifest=tmp_path/'data/film-presets-manifest.json';manifest.parent.mkdir()
    recipe={'route':'print','film':{'stock':'portra','custom_material':{
        'provenance':{'stock_id':'portra','process':'C-41','density_metric':'Status M'}}}}
    path=directory/'portra.json';path.write_text(json.dumps(recipe))
    entry={'id':'portra-print','route':'print','process':'C-41','file':path.name,
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest.write_text(json.dumps({'schema':'softloaf.experimental-presets/1','recipes':[entry]}))
    assert load_recipe_presets(tmp_path)[0]['recipe']==recipe
    path.write_text('{}')
    with pytest.raises(ValueError,match='identity'):load_recipe_presets(tmp_path)
    recipe['route']='negative';path.write_text(json.dumps(recipe));entry.update(route='negative',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest.write_text(json.dumps({'schema':'softloaf.experimental-presets/1','recipes':[entry]}))
    assert load_recipe_presets(tmp_path)[0]['recipe']==recipe
    recipe['film']['custom_material']['provenance']['process']='E-6'
    path.write_text(json.dumps(recipe));entry.update(process='E-6',sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest.write_text(json.dumps({'schema':'softloaf.experimental-presets/1','recipes':[entry]}))
    with pytest.raises(ValueError,match='process or density'):load_recipe_presets(tmp_path)


def test_missing_optional_catalog_does_not_remove_original_templates(tmp_path):
    assert load_recipe_presets(tmp_path)==[]


def test_visible_negative_choices_are_vision3_only_and_do_not_delete_archive():
    from spectral_app.presets import visible_negative_presets
    entries=[{'recipe':{'film':{'stock':stock,'custom_material':{'provenance':{'process':process}}}}}
             for stock,process in [('5203','ECN-2'),('5213','ECN-2'),('5219','ECN-2'),('portra400','C-41'),('gold200','C-41'),('5207','C-41')]]
    visible=visible_negative_presets(entries)
    assert [e['recipe']['film']['stock'] for e in visible]==['5203','5213','5219']
    assert len(entries)==6
