"""Compare validated full-quality RAW derivatives from two engine builds."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import tifffile


def full_entries(directory,engine=None):
    entries={}
    for manifest in directory.glob('*/manifest.json'):
        metadata=json.loads(manifest.read_text())
        if metadata.get('processing_mode','full-quality')!='full-quality':continue
        if engine and metadata['engine_sha256']!=engine:continue
        for route in ('ap1','srgb'):
            with (manifest.parent/(route+'.tif')).open('rb') as stream:
                assert hashlib.file_digest(stream,'sha256').hexdigest()==metadata['files'][route]
        source=metadata['source_sha256'];previous=entries.get(source)
        if not previous or manifest.stat().st_mtime_ns>(previous[0]/'manifest.json').stat().st_mtime_ns:
            entries[source]=(manifest.parent,metadata)
    return entries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-cache',type=Path,required=True)
    parser.add_argument('--candidate-cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate-engine-sha256')
    parser.add_argument('--reference-engine-sha256')
    args=parser.parse_args();old=full_entries(args.reference_cache,args.reference_engine_sha256);new=full_entries(args.candidate_cache,args.candidate_engine_sha256);records=[]
    for source in old.keys()&new.keys():
        first,a=old[source];second,b=new[source]
        record={'source_sha256':source,'reference_engine':a['engine_sha256'],'candidate_engine':b['engine_sha256'],
            'same_camera_database':a['camera_database_sha256']==b['camera_database_sha256'],'channels':{}}
        for route in ('ap1','srgb'):
            x=tifffile.memmap(first/(route+'.tif'),mode='r');y=tifffile.memmap(second/(route+'.tif'),mode='r')
            assert x.shape==y.shape and x.dtype==y.dtype==np.float32
            x=x.reshape(-1,3);y=y.reshape(-1,3);maximum=0.;squared=0.
            for i in range(0,len(x),65536):
                delta=x[i:i+65536].astype(float)-y[i:i+65536];maximum=max(maximum,float(np.abs(delta).max()));squared+=float(np.square(delta).sum())
            record['channels'][route]={'max_abs':maximum,'RMS':(squared/x.size)**.5}
            print(source,route,maximum,(squared/x.size)**.5,flush=True)
        records.append(record)
    assert records,'No common full-quality sources'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    accepted=all(v['max_abs']<=1e-5 for r in records for v in r['channels'].values())
    args.output.write_text(json.dumps({'accepted':accepted,'records':records,'spaces':{'ap1':'linear ACEScg AP1/D60 float32','srgb':'encoded sRGB/D65 float32'},'scope':'Same source files, dimensions, technical PP3, WB and camera profile selection; independent engine builds'},indent=2))
    assert accepted,'Engine output differs: inspect spatial boundaries, WB, profiles and thread counts.'
    print(json.dumps({'sources':len(records),'maximum_abs':max(v['max_abs'] for r in records for v in r['channels'].values())}))


if __name__=='__main__':main()
