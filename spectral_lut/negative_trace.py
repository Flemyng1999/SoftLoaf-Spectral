"""Inspection of the pinned float64 APD/ADX-to-ACES calculation.

Matrices in the trace act on column vectors. CTL matrices imported from
negative.py act on row vectors and are transposed for this presentation.
"""
import numpy as np

from .negative import CDD_TO_CID,EXP_TO_ACES,TOE,REF_PT,adx_codes,adx_to_aces


def apd_to_xyz_trace(apd,base,ap0_to_xyz_d60,d60_to_d65):
    apd,base=np.asarray(apd,dtype=np.float64),np.asarray(base,dtype=np.float64)
    ap0,adapt=np.asarray(ap0_to_xyz_d60,dtype=np.float64),np.asarray(d60_to_d65,dtype=np.float64)
    if (apd.shape!=(3,) or base.shape!=(3,) or ap0.shape!=(3,3) or adapt.shape!=(3,3)
            or not all(np.isfinite(a).all() for a in [apd,base,ap0,adapt])):
        raise ValueError('Expected one finite APD/Dmin triplet and two 3×3 matrices.')
    value=apd.copy();steps=[]
    def step(title,output,**details):
        nonlocal value
        output=np.asarray(output,dtype=np.float64)
        steps.append({'title':title,'kind':'formula','input':value.tolist(),'output':output.tolist(),**details})
        value=output
    def matrix(title,m):
        step(title,m@value,kind='matrix',matrix=m.tolist(),offset=[0,0,0])

    step('扣除片基 APD',value-base,formula='D相对 = APD − Dmin',parameters={'Dmin':base.tolist()},unit='D')
    step('编码 ADX16 浮点码值',adx_codes(apd,base),formula='CV = 1520 + 8000 × D相对 × g',
        parameters={'g':[1,.92,.95]},note='保留浮点码值，不取整、不裁切。',unit='float code value')
    step('还原相机打印密度 CDD',(value-1520)/8000,formula='CDD = (CV − 1520) / 8000',unit='D')
    matrix('CDD → CID',CDD_TO_CID.T)
    cid=value.copy()
    loge=np.where(cid<=.6,np.interp(cid,TOE[:,0],TOE[:,1]),cid*(100/55)-REF_PT)
    step('CID → 对数曝光',loge,
        formula=f'CID ≤ 0.6：趾部表线性插值\nCID > 0.6：log₁₀ E = CID × (100 / 55) − {REF_PT:.12g}',
        table=TOE.tolist(),table_labels=['CID','log₁₀ E'],branches=['趾部查表' if x<=.6 else '直线段' for x in cid],
        note='低于表首端点时，沿用表首值。',unit='log10 relative exposure')
    step('还原线性曝光',10.**value,formula='E = 10^(log₁₀ E)',unit='relative exposure')
    matrix('曝光 → ACES2065-1 · AP0 / D60',EXP_TO_ACES.T)
    matrix('AP0 / D60 → XYZ D60',ap0)
    matrix('Bradford 白点适应 · D60 → D65',adapt)
    expected=adx_to_aces(adx_codes(apd,base))@ap0.T@adapt.T
    if not np.allclose(value,expected,rtol=2e-14,atol=1e-14):
        raise ValueError('APD trace differs from the float64 reference.')
    return {'pipeline':'APD_to_XYZ','label':'APD → ADX16 → ACES2065-1 → XYZ D65',
        'input':apd.tolist(),'input_label':'APD · 绝对密度 D','output':value.tolist(),'output_label':'XYZ · D65 · 相对 Y',
        'encoding':'relative XYZ D65; CIE 1931 2 degree','quantized':False,'steps':steps,
        'reference':'ACES v1.2 (2019) · ADX16_to_ACES a1.0.3',
        'reference_commit':'518c27f577e99cdecfddf2ebcfaa53444b1f9343'}
