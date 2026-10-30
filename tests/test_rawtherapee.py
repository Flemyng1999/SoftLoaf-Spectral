"""Real CLI handoff tests, plus an independent colorimetric check between branches."""
from pathlib import Path
import io
import hashlib
import numpy as np
import pytest
from PIL import ImageCms
from spectral_app.rawtherapee import RawTherapee,lut_input
from spectral_lut.display import rgb_profile


def test_lut_input_preserves_scene_values_and_uses_acescct_formula():
    values=np.array([[-.02,0,.18],[.0078125,1,4]],dtype=np.float64)
    expected=np.where(values<=.0078125,10.5402377416545*values+.0729055341958355,
        (np.log2(np.maximum(values,1e-300))+9.72)/17.52)
    np.testing.assert_allclose(lut_input(values),expected,atol=1e-14)


def test_linear_ap1_profile_has_linear_trc_and_correct_colorants():
    import colour
    profile=rgb_profile('ACEScg Linear');parsed=ImageCms.ImageCmsProfile(io.BytesIO(profile)).profile
    ap1=colour.RGB_COLOURSPACES['ACEScg'];d50=np.array([.3457,.3585])
    expected=colour.adaptation.matrix_chromatic_adaptation_VonKries(colour.xy_to_XYZ(ap1.whitepoint),colour.xy_to_XYZ(d50),transform='Bradford')@ap1.matrix_RGB_to_XYZ
    actual=np.array([parsed.red_colorant[0],parsed.green_colorant[0],parsed.blue_colorant[0]]).T
    np.testing.assert_allclose(actual,expected,atol=1/65536)
    import struct
    count=struct.unpack_from('>I',profile,128)[0]
    for i in range(count):
        tag,offset,size=struct.unpack_from('>4sII',profile,132+12*i)
        if tag.endswith(b'TRC'):assert struct.unpack_from('>i',profile,offset+12)[0]==65536


@pytest.mark.parametrize('camera',['r5','d850'])
def test_real_rawtherapee_two_outputs_icc_cache_and_independent_srgb_bridge(tmp_path,camera):
    import colour
    cli=Path('local/runtime/RawTherapee.app/Contents/MacOS/rawtherapee-cli')
    source=Path(f'artifacts/hsi-raw-lut/raw/scene43_{camera}_ev+0_SYNTHETIC.dng').resolve()
    if not cli.exists() or not source.exists():pytest.skip('Local official RT runtime and synthetic DNG not supplied.')
    engine=RawTherapee(Path.cwd(),tmp_path,cli.resolve());result=engine.develop(source)
    assert result['ap1'].dtype==np.float32 and result['srgb'].shape==result['ap1'].shape
    assert np.ptp(result['ap1'])>.01
    # Independent colour-science matrix/adaptation + IEC sRGB, not our application processor.
    ap1=colour.RGB_COLOURSPACES['ACEScg'];srgb=colour.RGB_COLOURSPACES['sRGB']
    reference=colour.RGB_to_RGB(result['ap1'].astype(float),ap1,srgb,chromatic_adaptation_transform='Bradford',apply_cctf_encoding=True)
    error=np.abs(np.clip(reference,0,1)-np.clip(result['srgb'],0,1))*255
    assert np.percentile(error,99)<.15
    manifest=next(tmp_path.glob('*/manifest.json'));mtime=manifest.stat().st_mtime_ns
    again=engine.develop(source)
    np.testing.assert_array_equal(again['ap1'],result['ap1']);assert manifest.stat().st_mtime_ns==mtime
    expected=result['ap1'].copy()  # Freeze values before deliberately truncating its mapped file.
    directory=manifest.parent;(directory/'ap1.tif').write_bytes(b'broken')
    # Retained developments cannot be silently decoded again after corruption.
    from experiments.gui_recipe_server import RecipeError
    with pytest.raises(RecipeError) as error:engine.develop(source)
    assert error.value.code=='raw_cache_integrity'


def test_raw_original_stored_without_camera_extension_can_rebuild_an_evicted_cache(tmp_path):
    source=Path('artifacts/hsi-raw-lut/raw/scene43_r5_ev+0_SYNTHETIC.dng')
    cli=Path('local/runtime/RawTherapee.app/Contents/MacOS/rawtherapee-cli')
    if not source.exists() or not cli.exists():pytest.skip('Local RawTherapee and synthetic DNG not supplied.')
    stored=tmp_path/'original.source';stored.write_bytes(source.read_bytes())
    engine=RawTherapee(Path.cwd(),tmp_path/'fresh-cache',cli.resolve())
    developed=engine.develop(stored,source_name=source.name)
    assert developed['ap1'].shape==(490,650,3)
    assert np.ptp(developed['ap1'])>.01


def test_raw_extension_contract_includes_engine_verified_ori_crw_and_foveon():
    from spectral_app.rawtherapee import RAW_EXTENSIONS
    assert {'.ori','.crw','.x3f'}<=RAW_EXTENSIONS


def test_camera_white_balance_fallback_is_recorded_as_fallback_not_as_as_shot():
    from spectral_app.rawtherapee import white_balance_record
    unavailable=white_balance_record(['Processing RAW\nCannot use camera white balance.\n'])
    assert unavailable['white_balance_requested']=='Camera / AsShot'
    assert unavailable['camera_white_balance_unavailable'] is True
    assert 'fallback' in unavailable['white_balance']
    assert white_balance_record(['Processing RAW\n'])['camera_white_balance_unavailable'] is False
