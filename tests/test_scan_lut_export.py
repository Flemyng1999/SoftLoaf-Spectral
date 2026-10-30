from pathlib import Path
import numpy as np
import pytest
import PyOpenColorIO as ocio


def test_scan_cube_and_linear_clf_declare_domains_and_match_analytic_transfer(tmp_path):
    from spectral_app.scanning.export import export_scan_lut
    # A camera-density ramp has a known continuous mathematical output.
    metadata={'status':'estimated-joint-response','calibration_sha256':'a'*64,'camera':'ILCE-7RM5',
              'material':'Kodak 5207 / ECN-2 / Status M fitted','display':'sRGB / ACES 2.0','view_exposure_ev':0}
    result=export_scan_lut(tmp_path/'scan',lambda density:density/4,metadata,size=5)
    cube=Path(result['cube']);text=cube.read_text()
    assert 'LUT_3D_SIZE 5' in text and 'DOMAIN_MAX 4 4 4' in text
    assert 'Yangming Feng' in text and 'estimated-joint-response' in text
    assert 'not an independently measured camera SSF' in text
    assert '/Users/' not in text and '/Volumes/' not in text
    values=np.array([[1,.1,.01],[.001,.0001,.5]],np.float32)
    processor=ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=result['clf'],interpolation=ocio.INTERP_TETRAHEDRAL)).getDefaultCPUProcessor()
    processor.applyRGB(values)
    np.testing.assert_allclose(values,[[0,.25,.5],[.75,1,-np.log10(.5)/4]],atol=2e-6)
    assert result['all_nodes_readback_exact']
    assert result['interpolation']['max_codes']<1e-10
    assert result['interpolation']['samples']==1024


def test_non_linear_scan_clf_separates_lossless_and_default_math_error(tmp_path):
    from spectral_app.scanning.export import export_scan_lut
    result=export_scan_lut(tmp_path/'nonlinear',lambda d:np.sin(d*8)**2,
        {'status':'estimated-joint-response'},size=9)
    assert result['independent_clf_lossless_max_abs']<3e-5
    assert result['independent_clf_default_max_abs']<.1/255
    assert result['interpolation']['max_codes']>1


def test_measured_scan_label_requires_actual_camera_and_illumination_sources(tmp_path):
    from spectral_app.scanning.export import export_scan_lut
    with pytest.raises(ValueError,match='measured'):
        export_scan_lut(tmp_path/'false-measurement',lambda x:x,
            {'status':'independently-measured','calibration_sha256':'a'*64},size=5)


def test_asymmetric_density_domain_is_preserved_in_cube_and_linear_clf(tmp_path):
    from spectral_app.scanning.export import export_scan_lut
    low=np.array([.2,.6,.8]);high=np.array([2.3,2.8,3.])
    result=export_scan_lut(tmp_path/'domain',lambda d:(d-low)/(high-low),
        {'status':'estimated-joint-response'},size=5,domain_min=low,domain_max=high)
    density=np.array([low,high,(low+high)/2]);values=np.asarray(10**-density,np.float32)
    ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=result['clf'],interpolation=ocio.INTERP_TETRAHEDRAL)).getOptimizedCPUProcessor(ocio.OPTIMIZATION_LOSSLESS).applyRGB(values)
    np.testing.assert_allclose(values,[[0,0,0],[1,1,1],[.5,.5,.5]],atol=2e-6)
    np.testing.assert_array_equal(result['density_domain'],[low,high])


def test_material_density_domain_contains_physical_states_and_has_known_extrema():
    from spectral_app.scanning.export import material_density_domain
    from spectral_app.scanning.inverse import MaterialInverse
    # Diagonal transmission integrals have exact density extrema, including gain.
    inverse=MaterialInverse(np.eye(3),np.array([.1,.3,.5]),np.diag([.8,.9,1.]),
        np.zeros(3),np.array([1.,2.,3.]))
    low,high=material_density_domain(inverse,margin=.05)
    expected_low=inverse.base-np.log10(np.diag(inverse.weights))
    expected_high=expected_low+inverse.high
    assert np.all(low<=expected_low-.04999) and np.all(high>=expected_high+.04999)
    assert np.all(expected_low-low<.061) and np.all(high-expected_high<.061)
