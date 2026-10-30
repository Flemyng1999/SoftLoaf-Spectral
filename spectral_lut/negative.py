"""Float64 density operations and ACES v1.2 ADX16 input transform.

ADX constants and algorithm adapted from Academy ACEScsc.Academy.
ADX16_to_ACES.a1.0.3, v1.2 (2019), commit 518c27f577e99cdecfddf2ebcfaa53444b1f9343.
Copyright 2015 Academy of Motion Picture Arts and Sciences. All rights reserved.
See third_party/aces-v1.2/LICENSE.md for conditions and disclaimer.
Matrices here act on row vectors, exactly as CTL mult_f3_f33.
"""
import numpy as np

CDD_TO_CID=np.array([[.75573,.05901,.16134],[.22197,.96928,.07406],[.02230,-.02829,.76460]])
EXP_TO_ACES=np.array([[.72286,.11923,.01427],[.12630,.76418,.08213],[.15084,.11659,.90359]])
TOE=np.array([[-.19,-6],[.01,-2.721718645],[.028,-2.521718645],[.054,-2.321718645],[.095,-2.121718645],[.145,-1.921718645],[.22,-1.721718645],[.30,-1.521718645],[.40,-1.321718645],[.50,-1.121718645],[.60,-.926545676714876]])
REF_PT=(7120-1520)/8000*(100/55)-np.log10(.18)


def integrate_density(transmission,weights):
    t,w=np.asarray(transmission,dtype=np.float64),np.asarray(weights,dtype=np.float64)
    if (t.shape[-1]!=len(w) or w.ndim!=2 or w.shape[1]!=3 or not np.isfinite(t).all() or not np.isfinite(w).all() or np.any(t<0) or np.any(t>1) or np.any(w<0) or np.any(w.sum(0)<=0)):
        raise ValueError('Expected fraction transmittances and nonnegative RGB integration weights.')
    return -np.log10(np.maximum(t@(w/w.sum(0)),np.finfo(float).tiny))


def adx_codes(apd,base,bits=16,quantize=False):
    a,b=np.asarray(apd,dtype=np.float64),np.asarray(base,dtype=np.float64)
    if a.shape[-1]!=3 or b.shape!=(3,) or not np.isfinite(a).all() or not np.isfinite(b).all() or bits not in (10,16):raise ValueError('Invalid APD, Dmin or ADX bit depth.')
    scale,offset=(8000,1520) if bits==16 else (500,95)
    codes=(a-b)*[1,.92,.95]*scale+offset
    return np.floor(np.clip(codes,0,2**bits-1)+.5).astype(np.uint16) if quantize else codes


def adx_to_aces(codes):
    a=np.asarray(codes,dtype=np.float64)
    if a.shape[-1]!=3 or not np.isfinite(a).all():raise ValueError('Expected finite ADX code values, not normalized RGB.')
    cid=((a-1520)/8000)@CDD_TO_CID
    loge=np.where(cid<=.6,np.interp(cid,TOE[:,0],TOE[:,1]),cid*(100/55)-REF_PT)
    return np.power(10.,loge)@EXP_TO_ACES
