"""Film reference capture illumination, separate from camera WB and viewing light.

Kelvin values identify the material's declared reference, not a measurement of
an arbitrary photographed scene. Daylight uses a CIE D energy SPD; tungsten uses
the explicitly recorded Planck approximation. Unknown materials are not filled
with another stock's settings.
"""
import copy
import math


def reference_scene(recipe):
    if not isinstance(recipe,dict) or not isinstance(recipe.get('film'),dict):return None
    film=recipe['film'];stock=film.get('stock');custom=film.get('custom_material')
    provenance=custom.get('provenance',{}) if isinstance(custom,dict) else {}
    if not isinstance(provenance,dict):return None
    if provenance.get('stock_id') not in (None,stock):return None
    reference=provenance.get('exposure_reference',{})
    if not isinstance(reference,dict):return None
    kind=reference.get('illuminant');temperature=reference.get('temperature_k')
    if kind is None and provenance.get('process')=='E-6':
        kind='CIE_D';temperature=provenance.get('reference_temperature_k',temperature)
    if temperature is None and stock in ('E100','5207'):
        kind='CIE_D';temperature=5500
    if type(temperature) not in (int,float) or not math.isfinite(temperature):return None
    if kind=='CIE_D' and 4000<=temperature<=10000 or kind=='Planck' and 2500<=temperature<=5000:
        return {'illuminant':kind,'temperature_k':temperature}
    return None


def bind_reference_scene(recipe):
    result=copy.deepcopy(recipe);reference=reference_scene(recipe)
    if reference is not None and result.get('scene')!=reference:
        result['scene']=reference
        result['revision']=result.get('revision',0)+1
    return result
