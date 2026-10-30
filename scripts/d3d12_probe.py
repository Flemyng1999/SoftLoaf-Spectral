"""Real hardware/transport smoke check without film assets or Python science wheels."""
import argparse
import ctypes as ct
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('library',type=Path);parser.add_argument('--scan',type=Path);parser.add_argument('--spectral',type=Path);args=parser.parse_args()
    lib=ct.CDLL(str(args.library.resolve()));F=ct.POINTER(ct.c_float);U=ct.POINTER(ct.c_uint32)
    lib.sl_d3d12_error.restype=ct.c_char_p;lib.sl_d3d12_device_name.restype=ct.c_char_p
    lib.sl_d3d12_create.argtypes=[ct.c_char_p];lib.sl_d3d12_create.restype=ct.c_void_p;lib.sl_d3d12_destroy.argtypes=[ct.c_void_p]
    lib.sl_d3d12_shutdown.argtypes=[];lib.sl_d3d12_shutdown.restype=ct.c_int
    lib.sl_d3d12_run.argtypes=[ct.c_void_p,F,ct.c_uint64,ct.c_uint32,F,ct.c_uint64,U,ct.c_uint64,F,ct.POINTER(ct.c_double)]
    name=lib.sl_d3d12_device_name()
    if not name:raise RuntimeError(lib.sl_d3d12_error().decode())
    source=args.scan.read_bytes() if args.scan else b'''StructuredBuffer<float> input:register(t0,space1);
StructuredBuffer<float> data:register(t1,space1);StructuredBuffer<uint> meta:register(t2,space1);
RWStructuredBuffer<float> output:register(u0,space1);cbuffer Count:register(b0,space1){uint count;};
[numthreads(64,1,1)]void sl_pixels(uint3 id:SV_DispatchThreadID){uint i=id.x;if(i>=count)return;for(uint c=0;c<3;c++)output[i*3+c]=input[i*3+c]*data[0]+float(meta[0]);}'''
    if args.spectral:source=args.spectral.read_bytes().replace(b'/* OCIO_SOURCE */',b'float4 sl_display(float4 value){return value;}')
    handle=lib.sl_d3d12_create(source)
    if not handle:raise RuntimeError(lib.sl_d3d12_error().decode())
    try:
        if args.scan:
            values=[x for y in range(2) for i in range(2) for x in (i,y,0,0,1,1)];channels=6;pixels=4
            expected=[.125,.25,.5,.25,.5,.75,.5,.75,1,.75,1,1.25];data=[0.]*24+expected;meta=[2,2,0,0,2,2,0,24,2,0,0,0]
        elif args.spectral:
            pixels=257;channels=3;values=[i/128 for i in range(pixels*3)];expected=[v*.5 for v in values]
            slots='NS NV NC PC MODE ROUTE PURPOSE BASIS EXPOSURE AXIS AMOUNTS DYES BASE KERNEL ADAPT PAXIS PAMOUNTS PDYES PBASE PEXPOSURE PRINTFACTOR PREFLASH APD DMIN CID EXPACES AP0XYZ REFMATRIX REFKERNEL FANCHOR PANCHOR FILMSCALE INPUTSCALE PRIOR PN PK PRGB PSPECTRA PSCALE PLUMA PRIDGE LUTSIZE LUTTABLE LUTLOW LUTHIGH LUTDISPLAY'.split()
            meta=[0]*len(slots)
            for key,value in {'MODE':0,'ROUTE':3,'PURPOSE':1,'REFMATRIX':1,'INPUTSCALE':10}.items():meta[slots.index(key)]=value
            data=[0,1,0,0,0,1,0,0,0,1,.5]
        else:
            pixels=257;channels=3;values=[i/128 for i in range(pixels*3)];data=[.5];meta=[1];expected=[v*.5+1 for v in values]
        x=(ct.c_float*len(values))(*values);d=(ct.c_float*len(data))(*data);m=(ct.c_uint32*len(meta))(*meta);output=(ct.c_float*(pixels*3))();seconds=ct.c_double()
        result=lib.sl_d3d12_run(handle,x,pixels,channels,d,len(data),m,len(meta),output,ct.byref(seconds))
        if result:raise RuntimeError(lib.sl_d3d12_error().decode())
        error=max(abs(a-b) for a,b in zip(output,expected))
        if error>2e-6:raise RuntimeError('GPU differs from independent hand calculation: '+str(error))
        report={'ok':True,'backend':'D3D12','device':name.decode(),'pixels':pixels,'max_abs_error':error,'gpu_seconds':seconds.value}
    finally:
        lib.sl_d3d12_destroy(handle)
        if lib.sl_d3d12_shutdown():raise RuntimeError(lib.sl_d3d12_error().decode())
    print(json.dumps(report))


if __name__=='__main__':main()
