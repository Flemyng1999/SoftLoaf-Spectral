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
