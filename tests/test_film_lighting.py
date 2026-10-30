import copy


def recipe(stock,reference=None,process='ECN-2'):
    result={'route':'slide' if process=='E-6' else 'negative','revision':4,
            'film':{'stock':stock,'exposure_ev':.5},'scene':{'illuminant':'D65'},'viewing':{'illuminant':'D50'}}
    if reference is not None:
        result['film']['custom_material']={'provenance':{'stock_id':stock,'process':process,'exposure_reference':reference}}
    return result


def test_reference_light_uses_material_conditions_without_confusing_daylight_and_tungsten():
    from spectral_app.film_lighting import reference_scene
    assert reference_scene(recipe('5219',{'illuminant':'Planck','temperature_k':3200}))=={'illuminant':'Planck','temperature_k':3200}
    assert reference_scene(recipe('5203',{'illuminant':'CIE_D','temperature_k':5500}))=={'illuminant':'CIE_D','temperature_k':5500}
    assert reference_scene(recipe('E100',process='E-6'))=={'illuminant':'CIE_D','temperature_k':5500}
    assert reference_scene(recipe('5207'))=={'illuminant':'CIE_D','temperature_k':5500}


def test_missing_custom_reference_does_not_borrow_another_film_or_relabel_a_temperature():
    from spectral_app.film_lighting import reference_scene
    assert reference_scene(recipe('unknown')) is None
    assert reference_scene(recipe('5219',{'illuminant':'CIE_D','temperature_k':'3200'})) is None


def test_binding_changes_only_scene_and_revision_and_is_idempotent():
    from spectral_app.film_lighting import bind_reference_scene
    original=recipe('5213',{'illuminant':'Planck','temperature_k':3200});saved=copy.deepcopy(original)
    normalized=bind_reference_scene(original)
    assert original==saved
    assert normalized['scene']=={'illuminant':'Planck','temperature_k':3200}
    assert normalized['revision']==5
    assert normalized['film']==original['film'] and normalized['viewing']==original['viewing']
    assert bind_reference_scene(normalized)==normalized


def application():
    from types import SimpleNamespace
    from spectral_app.application import Application
    app=Application.__new__(Application)
    app.model=SimpleNamespace(validate=lambda value,compute=False:
        {'ok':True,'computable':True,'normalized_recipe':copy.deepcopy(value)})
    return app


def test_application_upgrades_old_recipe_without_mutating_input_or_other_settings():
    app=application()
    old=recipe('5219',{'illuminant':'Planck','temperature_k':3200})
    old.update(id='saved',name='My film',printing={'temperature_k':3400,'filters':[.1,.2,.3]},
               display={'target':'Display P3'},input_model={'id':'frozen'})
    old['scene']={'illuminant':'CIE_D','temperature_k':6500}
    before=copy.deepcopy(old)
    result=app.validate_recipe(old)['normalized_recipe']
    assert old==before
    assert result['scene']=={'illuminant':'Planck','temperature_k':3200}
    assert result['revision']==5
    for field in before.keys()-{'scene','revision'}:assert result[field]==before[field]
    assert app.validate_recipe(result)['normalized_recipe']==result
    # Explicit scientific comparisons are still available below the UI boundary.
    assert app.model.validate(old)['normalized_recipe']['scene']==before['scene']


def test_session_upgrade_covers_baselines_deleted_documents_and_repeated_restore():
    app=application()
    daylight=recipe('E100',process='E-6');daylight['id']='slide'
    tungsten=recipe('5213',{'illuminant':'Planck','temperature_k':3200});tungsten['id']='negative'
    state={'documents':[{'recipe':daylight,'baseline':tungsten}],'active_id':'slide',
           'deleted_documents':[{'id':'deleted','index':1,'document':{'recipe':tungsten,'baseline':daylight}}],
           'photo_workspace':{'order':['raw'],'active_input_id':'raw','exposures':{'raw':.7}}}
    before=copy.deepcopy(state)
    restored=app._validated_session(state)
    assert state==before
    assert restored['documents'][0]['recipe']['scene']=={'illuminant':'CIE_D','temperature_k':5500}
    assert restored['documents'][0]['baseline']['scene']=={'illuminant':'Planck','temperature_k':3200}
    deleted=restored['deleted_documents'][0]['document']
    assert deleted['recipe']['scene']==restored['documents'][0]['baseline']['scene']
    assert deleted['baseline']['scene']==restored['documents'][0]['recipe']['scene']
    assert restored['photo_workspace']==state['photo_workspace']
    assert app._validated_session(restored)==restored


def test_application_does_not_invent_reference_for_unknown_material():
    app=application();old=recipe('unknown')
    assert app.validate_recipe(old)['normalized_recipe']==old


def test_file_import_validation_http_returns_the_upgraded_recipe():
    import json
    from pathlib import Path
    import threading
    from urllib.request import Request,urlopen
    from experiments.gui_recipe_server import make_server
    app=application();server=make_server(app,Path('design/gui-v2/index.html'),None,0)
    worker=threading.Thread(target=server.serve_forever);worker.start()
    try:
        old=recipe('E100',process='E-6')
        request=Request(f'http://127.0.0.1:{server.server_port}/api/validate',
            data=json.dumps({'recipe':old}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request) as response:opened=json.load(response)['normalized_recipe']
        assert opened['scene']=={'illuminant':'CIE_D','temperature_k':5500}
        assert opened['revision']==old['revision']+1
    finally:
        server.shutdown();worker.join();server.server_close()
