"""The C++ path must agree with the independent NumPy float64 reference."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from spectral_lut.reference import Cube, acescct_decode


@pytest.fixture(scope='module')
def core():
    from spectral_lut.native import NativeCore
    return NativeCore()


def test_native_decode_retains_negative_linear_values_and_breakpoint(core):
    encoded = np.array([[-.25, .155251141552511, .75], [0, .4, .5]])
    np.testing.assert_allclose(core.decode(encoded), acescct_decode(encoded), rtol=2e-14, atol=2e-15)
    assert core.decode(encoded)[0, 0] < 0


def test_native_tetrahedra_match_reference_on_six_orders_and_clamped_edges(core):
    rng = np.random.default_rng(42)
    cube = Cube(rng.random((5, 5, 5, 3)), np.array([-.25, -.1, .2]), np.array([.75, .9, 1.2]))
    points = np.vstack([rng.uniform(-.4, 1.4, (1000, 3)), cube.domain_min, cube.domain_max])
    np.testing.assert_allclose(core.apply_cube(cube, points), cube.apply(points), rtol=2e-14, atol=2e-15)
    np.testing.assert_array_equal(core.apply_cube(cube, cube.domain_min), cube.table[0, 0, 0])


def test_native_rejects_nonfinite_and_malformed_inputs(core):
    with pytest.raises(ValueError):
        core.decode([float('nan'), 0, 0])
    with pytest.raises(ValueError):
        core.decode([0, 0])
    cube = Cube(np.zeros((2, 2, 2, 3)), np.ones(3), np.zeros(3))
    with pytest.raises(ValueError):
        core.apply_cube(cube, [0, 0, 0])


@pytest.mark.parametrize('native',[False,True])
def test_signed_net_dye_basis_requires_nonnegative_summed_density(core,native):
    from spectral_app.model import stage
    spectra=np.ones((1,2));kernel=np.full((2,3),.5)
    axis=np.array([-1.,1.]);amounts=np.array([[0.,0.,0.],[2.,2.,2.]])
    dyes=np.array([[.5,-.1,.2],[.2,.3,-.1]]);base=np.array([.2,.1])
    args=(spectra,kernel,axis,amounts,dyes,base)
    h,a,t=stage(*args,core=core if native else None)
    np.testing.assert_allclose(h,[[1,1,1]],rtol=0,atol=1e-14)
    np.testing.assert_allclose(a,[[1,1,1]],rtol=0,atol=1e-14)
    np.testing.assert_allclose(t,10.**-np.array([[.8,.5]]),rtol=1e-14)
    dyes[0,1]=-2
    with pytest.raises(ValueError,match='density'):
        stage(*args,core=core if native else None)


def test_native_reversal_matches_every_intermediate_and_is_reentrant(core, tmp_path):
    from experiments.gui_recipe_server import E100Model
    archive = Path('local/film-color-slides/hyperspectral-demo')
    opendrt = Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    if not archive.exists() or not opendrt.exists():
        pytest.skip('Optional local reference materials are not supplied.')
    model = E100Model(archive, opendrt, tmp_path)
    rgb = np.vstack([np.random.default_rng(6).uniform(-.03, 2, (400, 3)), [0, 0, 0]])
    for ev, light, gain in [(-4, 'D50', .1), (0, 'D65', 1.8), (4, 'D50', 8)]:
        expected = model.sample(rgb, exposure_ev=ev, viewing_light=light, viewing_gain=gain)
        model.core = core
        actual = model.sample(rgb, exposure_ev=ev, viewing_light=light, viewing_gain=gain)
        model.core = None
        for key in expected:
            np.testing.assert_allclose(actual[key], expected[key], atol=2e-12, rtol=2e-12, err_msg=key)
    model.core = core
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: model.sample(rgb)['XYZ'], range(8)))
    for result in results[1:]:
        np.testing.assert_array_equal(result, results[0])


def test_development_bundle_contains_the_current_core_when_built():
    import hashlib
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    bundled=root/'build/SoftLoaf Spectral.app/Contents/Resources/libsoftloaf_core.dylib'
    built=root/'build/libsoftloaf_core.dylib'
    if not bundled.exists():pytest.skip('macOS development bundle not built.')
    assert hashlib.sha256(bundled.read_bytes()).digest()==hashlib.sha256(built.read_bytes()).digest()


def test_float32_red_fast_cube_uses_float64_interpolation_without_double_table_copy(tmp_path):
    from spectral_lut.native import NativeCore
    from spectral_app.exporting.lut_files import write_cube,read_cube
    from spectral_lut.reference import Cube
    low=np.full(3,-.25);high=np.full(3,.75);path=tmp_path/'mapped.cube'
    nodes=write_cube(path,7,low,high,lambda p:np.sin(p*2),'float32 oracle',[],block=23)
    cube=read_cube(path,tmp_path/'read.nodes',nodes,block=17)
    points=np.random.default_rng(95).uniform(low-.1,high+.1,(257,3))
    result=NativeCore().apply_cube(cube,points)
    expected=Cube(np.array(cube.table,dtype=np.float64),low,high).apply(points)
    np.testing.assert_allclose(result,expected,rtol=0,atol=2e-15)
