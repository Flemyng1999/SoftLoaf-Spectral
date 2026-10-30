"""Generate the owned Metal-kernel subset's HLSL spelling; no algorithm changes.

This is deliberately not a general shader transpiler. Generated files are checked
in, hash their source, and must pass independent float64 tests on hardware.
"""
import argparse
import hashlib
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
HEADER='''StructuredBuffer<float> input : register(t0, space1);
StructuredBuffer<float> d : register(t1, space1);
StructuredBuffer<uint> m : register(t2, space1);
RWStructuredBuffer<float> output : register(u0, space1);
cbuffer DispatchCount : register(b0, space1) { uint count; };
#define NAN asfloat(0x7fc00000u)
float3 sl_select(float3 a,float3 b,bool3 condition) { return float3(condition.x?b.x:a.x,condition.y?b.y:a.y,condition.z?b.z:a.z); }
uint3 sl_axis(uint axis) { return uint3(axis==0?1:0,axis==1?1:0,axis==2?1:0); }
'''


def vector_casts(text):
    pattern=re.compile(r'\b(float[234]|uint[234]|int[234])\(');position=0
    while match:=pattern.search(text,position):
        start=match.end();depth=1;end=start;commas=False
        while depth:
            c=text[end];depth+=(c=='(')-(c==')')
            if c==',' and depth==1:commas=True
            end+=1
        if not commas:
            value='('+match[1]+')('+text[start:end-1]+')'
            text=text[:match.start()]+value+text[end:];position=match.start()+len(match[1])+3
        else:position=match.end()
    return text


def convert(source):
    text=source.replace('#include <metal_stdlib>','').replace('using namespace metal;','')
    text=re.sub(r'enum Slot\s*\{([^}]+)\};',lambda match:'\n'.join('static const uint '+name.strip()+'='+str(i)+';' for i,name in enumerate(match[1].split(','))),text)
    text=text.replace('device const float *','StructuredBuffer<float> ').replace('device const uint *','StructuredBuffer<uint> ')
    for name,n in [('keys',512),('weights',512),('features',13)]:text=text.replace('thread float *'+name,('out' if name=='features' else 'inout')+' float '+name+'['+str(n)+']')
    text=text.replace('thread float3 &coefficient','out float3 coefficient').replace('thread float &penalty','out float penalty')
    text=text.replace('constant float','static const float').replace('sl_toe_x[]','sl_toe_x[11]').replace('sl_toe_y[]','sl_toe_y[11]')
    text=text.replace('mix(','lerp(').replace('select(','sl_select(')
    text=re.sub(r'\bpoint\(', 'scan_point(',text)
    text=re.sub(r'\blinear\b','sl_linear',text)
    text=text.replace('a[o[2]]--;c[o[0]]++;','a-=sl_axis(o[2]);c+=sl_axis(o[0]);')
    text=text.replace('a[order[0]]++;b[order[2]]--;','a+=sl_axis(order[0]);b-=sl_axis(order[2]);')
    # Keep loop bounds dynamic; never ask FXC to unroll the local 512-sample prior.
    text=text.replace('for(', '[loop] for(').replace('while(', '[loop] while(')
    entry=text.index('kernel void sl_pixels(');body=re.search(r'\)\s*\{',text[entry:]).end()+entry
    # The scan kernel and spectral kernel use different names for the thread id.
    variable='pixel' if 'uint pixel [[thread_position_in_grid]]' in text[entry:body] else 'i'
    text=text[:entry]+'[numthreads(64,1,1)]\nvoid sl_pixels(uint3 dispatch_id : SV_DispatchThreadID) {\n    uint '+variable+'=dispatch_id.x;'+text[body:]
    text=text.replace('/* OCIO_ARGUMENTS */ ','')
    return '// Generated from owned kernel SHA256 '+hashlib.sha256(source.encode()).hexdigest()+'\n'+HEADER+vector_casts(text)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    for name in ('scan','spectral'):
        source=(ROOT/'core/metal'/f'{name}.metal').read_text();path=ROOT/'core/d3d12'/f'{name}.hlsl';generated=convert(source)
        if args.check:
            if not path.exists() or path.read_text()!=generated:raise SystemExit('HLSL source drift: '+name)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(generated)


if __name__=='__main__':main()
