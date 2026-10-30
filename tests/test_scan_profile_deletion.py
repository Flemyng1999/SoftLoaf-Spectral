import copy
import threading
from types import SimpleNamespace
import pytest
from spectral_app.scanning.service import ScanService
from experiments.gui_recipe_server import RecipeError


def service_with_profiles():
    s=ScanService.__new__(ScanService);s.lock=threading.RLock();s.warning=None
    s.storage=SimpleNamespace(validate=lambda:None)
    s.jobs=SimpleNamespace(lock=threading.RLock(),jobs={});s.prepare_jobs=SimpleNamespace(lock=threading.RLock(),jobs={})
    s.index={'profiles':{'a':{'id':'a'},'b':{'id':'b'}},'active_profile':'a',
        'images':['raw'],'assets':{'raw':{'id':'raw'}},'results':{'positive':{'profile':'a'}},'border':{'asset':'raw','roi':[.1,.1,.2,.2]},'geometry':{}}
    s.saved=[];s._save=lambda:s.saved.append(copy.deepcopy(s.index));s.state=lambda:{'ok':True,**copy.deepcopy(s.index)}
    return s


def test_delete_and_undo_preserve_raw_results_border_and_geometry():
    s=service_with_profiles();before=copy.deepcopy(s.index)
    value=s.request({'action':'delete-profile','profile':'a'})
    assert 'a' not in value['profiles'] and value['active_profile'] is None
    for field in ('images','assets','results','border','geometry'):assert value[field]==before[field]
    assert value['deleted_profile_order']==['a']
    value=s.request({'action':'restore-profile','profile':'a'})
    assert value['profiles']==before['profiles'] and value['active_profile']=='a'
    assert value['deleted_profile_order']==[]


def test_deleting_other_profile_does_not_change_selection_and_undo_does_not_steal_it():
    s=service_with_profiles();s.request({'action':'delete-profile','profile':'b'})
    assert s.index['active_profile']=='a'
    s.request({'action':'restore-profile','profile':'b'});assert s.index['active_profile']=='a'
    s.request({'action':'delete-profile','profile':'a'});s.request({'action':'select','profile':'b'})
    s.request({'action':'restore-profile','profile':'a'});assert s.index['active_profile']=='b'


def test_profile_deletion_is_blocked_during_processing_and_unknown_ids_do_not_write():
    s=service_with_profiles();s.jobs.jobs={'j':{'status':'running'}}
    with pytest.raises(RecipeError,match='等待'):s.request({'action':'delete-profile','profile':'b'})
    s.jobs.jobs={}
    with pytest.raises(RecipeError):s.request({'action':'delete-profile','profile':'missing'})
    assert not s.saved


def test_sidebar_preference_survives_state_reload_without_changing_processing():
    s=service_with_profiles();before=copy.deepcopy(s.index)
    s.jobs.jobs={'j':{'status':'running'}}
    value=s.request({'action':'panels','sidebar_collapsed':True})
    assert value['panels']=={'sidebar_collapsed':True}
    assert {k:v for k,v in value.items() if k not in ('ok','panels')}==before
    assert s.saved[-1]['panels']=={'sidebar_collapsed':True}
    s.request({'action':'panels','sidebar_collapsed':False})
    assert s.saved[-1]['panels']=={'sidebar_collapsed':False}
    count=len(s.saved)
    for invalid in ('false',1,None):
        with pytest.raises(RecipeError):s.request({'action':'panels','sidebar_collapsed':invalid})
    assert len(s.saved)==count
