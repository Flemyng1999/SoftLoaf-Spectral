import numpy as np
import pytest

from spectral_lut.negative import adx_codes,adx_to_aces,CDD_TO_CID,EXP_TO_ACES,TOE


@pytest.mark.parametrize('density',[[0,0,0],[.3,.5,.7],[1,2,3]])
def test_apd_trace_replays_the_existing_float64_calculation(density):
    from spectral_lut.negative_trace import apd_to_xyz_trace
    base=np.array([.12,.21,.09]);apd=np.array(density)
    ap0=np.array([[.9,.1,-.03],[.2,.7,.1],[0,0,1.02]])
    adapt=np.array([[1.02,.01,-.01],[.005,.99,0],[0,-.01,1.08]])
    trace=apd_to_xyz_trace(apd,base,ap0,adapt)
    expected=adx_to_aces(adx_codes(apd,base))@ap0.T@adapt.T
    np.testing.assert_allclose(trace['output'],expected,rtol=2e-14,atol=1e-14)
    assert trace['pipeline']=='APD_to_XYZ'
    assert trace['encoding']=='relative XYZ D65; CIE 1931 2 degree'
    assert trace['quantized'] is False
    assert len(trace['steps'])==9
    np.testing.assert_allclose(trace['steps'][1]['output'],adx_codes(apd,base))
    np.testing.assert_array_equal(trace['steps'][3]['matrix'],CDD_TO_CID.T)
    np.testing.assert_array_equal(trace['steps'][6]['matrix'],EXP_TO_ACES.T)
    np.testing.assert_array_equal(trace['steps'][4]['table'],TOE)
    previous=trace['input']
    for step in trace['steps']:
        np.testing.assert_array_equal(step['input'],previous)
        if step['kind']=='matrix':
            np.testing.assert_allclose(step['output'],np.array(step['matrix'])@previous+step['offset'],rtol=1e-14,atol=1e-14)
        previous=step['output']
    np.testing.assert_array_equal(trace['output'],previous)


def test_toe_trace_records_table_and_linear_branches_without_quantizing():
    from spectral_lut.negative_trace import apd_to_xyz_trace
    target_cid=np.array([-.3,.3,.8])
    relative=target_cid@np.linalg.inv(CDD_TO_CID)/[1,.92,.95]
    trace=apd_to_xyz_trace(relative,np.zeros(3),np.eye(3),np.eye(3))
    assert trace['steps'][4]['branches']==['趾部查表','趾部查表','直线段']
    assert trace['steps'][4]['output'][0]==-6
    np.testing.assert_allclose(trace['steps'][7]['output'],adx_to_aces(adx_codes(relative,np.zeros(3))),rtol=1e-14)
