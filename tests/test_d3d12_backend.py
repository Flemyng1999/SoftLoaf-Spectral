"""Mandatory hardware gate on Windows; synthetic hand and external OCIO oracles."""
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows D3D12 hardware gate')


@pytest.fixture
def backend(request):
    from spectral_lut.d3d12 import D3D12Backend
    value=D3D12Backend();request.node.user_properties.extend([('gpu',value.device_name),('library_sha256',value.sha256)])
    yield value;value.close()


def plan(route,purpose=1,*,counts=None,tables=None):
    from spectral_app.metal_renderer import _Pack
    b=_Pack()
    for k,v in {'NS':3,'NV':3,'NC':2,'PC':2,'MODE':1,'ROUTE':route,'PURPOSE':purpose,**(counts or {})}.items():b.count(k,v)
    for k,v in {'EXPOSURE':np.eye(3),'AXIS':[-4,2],'AMOUNTS':[[3,3,3],[0,0,0]] if route==0 else [[0,0,0],[3,3,3]],
        'DYES':np.eye(3),'BASE':np.zeros(3),'KERNEL':np.eye(3),'ADAPT':np.eye(3),'INPUTSCALE':1,'FILMSCALE':1,'FANCHOR':0,
        'APD':np.eye(3),'PRINTFACTOR':np.ones(3),'PREFLASH':np.zeros(3),'PEXPOSURE':np.eye(3),
        'PAXIS':[-4,2],'PAMOUNTS':[[0,0,0],[3,3,3]],'PDYES':np.eye(3),'PBASE':np.zeros(3),'PANCHOR':0,**(tables or {})}.items():b.add(k,v)
    return b.finish()


@pytest.mark.parametrize('route',[0,1,2])
def test_three_material_routes_match_independent_closed_forms_on_hardware(backend,route):
    from spectral_lut.shaders import shader_path
    source=shader_path(backend,'spectral').read_text().replace('/* OCIO_SOURCE */','float4 sl_display(float4 value){return value;}')
    p=backend.program(source);x=np.random.default_rng(67).uniform(.02,1,(129,3)).astype(np.float32)
    data,meta=plan(route,2 if route==1 else 1);actual,_=p.run(x,data,meta)
    expected=.1*np.sqrt(x.astype(float)) if route==0 else (np.log10(x.astype(float))+4)/2 if route==1 else .1*x.astype(float)**.25
    np.testing.assert_allclose(actual,expected,rtol=0,atol=3e-6)


def test_apd_adx_to_xyz_matches_float64_academy_reference(backend):
    import colour
    from spectral_lut.negative import adx_codes,adx_to_aces,CDD_TO_CID,EXP_TO_ACES
    from spectral_lut.shaders import shader_path
    from experiments.hsi_raw_lut import cat,D60,D65
    matrix=cat(D60,D65)@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ
    data,meta=plan(1,tables={'DMIN':np.zeros(3),'CID':CDD_TO_CID.T,'EXPACES':EXP_TO_ACES.T,'AP0XYZ':matrix})
    p=backend.program(shader_path(backend,'spectral').read_text().replace('/* OCIO_SOURCE */','float4 sl_display(float4 value){return value;}'))
    x=np.random.default_rng(19).uniform(.02,1,(257,3)).astype(np.float32)
    actual,_=p.run(x,data,meta);apd=(np.log10(x.astype(float))+4)/2
    expected=adx_to_aces(adx_codes(apd,np.zeros(3)))@matrix.T
    np.testing.assert_allclose(actual,expected,rtol=3e-5,atol=3e-6)


@pytest.mark.parametrize('kind',['local','root'])
def test_rgb_spectral_priors_match_independent_float64_reconstruction(backend,kind):
    from spectral_lut.reconstruction import LocalSpectralPrior,RootPolynomialPrior
    from spectral_lut.shaders import shader_path
    rng=np.random.default_rng(61);spectra=rng.uniform(.02,1,(96,5));kernel=rng.uniform(.1,1,(5,3));kernel/=kernel.sum(0)
    prior=LocalSpectralPrior(spectra,kernel,[.2,.7,.1],neighbors=12) if kind=='local' else RootPolynomialPrior(spectra,kernel)
    counts={'NS':5,'MODE':0,'PRIOR':1 if kind=='local' else 2}
    tables={'BASIS':prior.base,'EXPOSURE':kernel}
    if kind=='local':
        counts.update(PN=len(prior.normalized_rgb),PK=prior.neighbors)
        tables.update(PRGB=prior.normalized_rgb,PSPECTRA=prior.normalized_spectra,PSCALE=prior.scale,PLUMA=prior.luminance,PRIDGE=prior.ridge)
    else:counts['PN']=len(prior.scale);tables.update(PSPECTRA=prior.coefficients,PSCALE=prior.scale)
    data,meta=plan(0,counts=counts,tables=tables);x=rng.uniform(.05,.8,(129,3)).astype(np.float32)
    p=backend.program(shader_path(backend,'spectral').read_text().replace('/* OCIO_SOURCE */','float4 sl_display(float4 value){return value;}'))
    actual,_=p.run(x,data,meta);expected=.1*np.sqrt(prior.reconstruct(x.astype(float))@kernel)
    # Local ridge solves have the same 3e-4 complete-route float32 budget as
    # test_metal_pipeline.py. Primitive curves and root reconstruction retain
    # their tighter 3e-6 gate. LDL replaces the unstable determinant inverse.
    np.testing.assert_allclose(actual,expected,rtol=0,atol=3e-4 if kind=='local' else 3e-6)


@pytest.mark.parametrize('target',['sRGB','Display P3'])
def test_aces_20_display_graph_matches_official_cpu_processor(backend,target):
    import PyOpenColorIO as ocio
    from spectral_app.metal_renderer import MetalRenderer,_Pack
    from spectral_lut.display import ACES_CONFIG,TARGETS
    config=ocio.Config.CreateFromBuiltinConfig(ACES_CONFIG);graph=ocio.GroupTransform()
    graph.appendTransform(ocio.BuiltinTransform(style='UTILITY - ACES-AP0_to_CIE-XYZ-D65_BFD',direction=ocio.TRANSFORM_DIR_INVERSE))
    graph.appendTransform(ocio.DisplayViewTransform(src='ACES2065-1',display=TARGETS[target]['aces_display'],view=TARGETS[target]['aces_view']))
    processor=config.getProcessor(graph);transform=processor.createGroupTransform()
    renderer=MetalRenderer(SimpleNamespace(display_group=lambda view,target:transform),backend=backend)
    p=_Pack();p.count('MODE',0);p.count('ROUTE',3);p.count('PURPOSE',0);p.add('INPUTSCALE',1);p.add('REFMATRIX',np.eye(3))
    x=np.random.default_rng(24).uniform(-.01,2,(513,3)).astype(np.float32);expected=x.copy()
    processor.getDefaultCPUProcessor().applyRGB(expected)
    np.testing.assert_allclose(renderer._run(x,p.finish(),'ACES 2.0',target),np.clip(expected,0,1),rtol=0,atol=3e-4)


@pytest.mark.parametrize('kind',['3d','1d','2d'])
def test_original_ocio_texture_matches_official_cpu_processor(backend,kind):
    import PyOpenColorIO as ocio
    from spectral_app.metal_renderer import MetalRenderer,_Pack
    if kind=='3d':
        transform=ocio.Lut3DTransform(gridSize=3)
        for r in range(3):
            for g in range(3):
                for b in range(3):transform.setValue(r,g,b,(r/2)**2,(g/2)**.5,b/2)
    else:
        length=17 if kind=='1d' else 8193;transform=ocio.Lut1DTransform(length=length)
        for i in range(length):
            v=i/(length-1);transform.setValue(i,v*v,v**.5,v)
    model=SimpleNamespace(display_group=lambda view,target:transform)
    renderer=MetalRenderer(model,backend=backend);p=_Pack()
    for k,v in {'MODE':0,'ROUTE':3,'PURPOSE':0}.items():p.count(k,v)
    p.add('INPUTSCALE',1);p.add('REFMATRIX',np.eye(3))
    x=np.random.default_rng(91).random((257,3),dtype=np.float32)
    actual=renderer._run(x,p.finish(),'test','sRGB');expected=x.copy()
    ocio.Config.CreateRaw().getProcessor(transform).getDefaultCPUProcessor().applyRGB(expected)
    np.testing.assert_allclose(actual,expected,rtol=0,atol=3e-6)


def test_compile_failure_disables_gpu_and_retries_frozen_operation_on_cpu(backend):
    from spectral_app.compute_policy import retry_cpu
    selected={'gpu':True};backend.on_failure=lambda error:selected.update(gpu=False)
    calls=[];values=np.array([[.1,.2,.3]])
    @retry_cpu
    def render():
        calls.append(selected['gpu'])
        if selected['gpu']:backend.program('invalid shader')
        return values*2
    np.testing.assert_array_equal(render(),values*2)
    assert calls==[True,False] and backend.disabled


def test_dispatch_failure_retries_same_pixels_on_cpu(backend,monkeypatch):
    from spectral_app.compute_policy import retry_cpu
    from spectral_lut.shaders import shader_path
    selected={'gpu':True};backend.on_failure=lambda error:selected.update(gpu=False)
    program=backend.program(shader_path(backend,'spectral').read_text().replace('/* OCIO_SOURCE */','float4 sl_display(float4 value){return value;}'))
    data,meta=plan(0);x=np.array([[.02,.18,.9]],np.float32);calls=[]
    monkeypatch.setattr(backend.lib,'sl_metal_run',lambda *args:1)
    monkeypatch.setattr(backend.lib,'sl_metal_error',lambda:b'D3D12 device removed HRESULT=2289696773')
    @retry_cpu
    def render():
        calls.append(selected['gpu'])
        return program.run(x,data,meta)[0] if selected['gpu'] else .1*np.sqrt(x.astype(float))
    np.testing.assert_allclose(render(),.1*np.sqrt(x.astype(float)),atol=0,rtol=0)
    assert calls==[True,False] and backend.disabled
