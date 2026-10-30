"""Extract E-4000 (2018) p4 sensitivity vectors for local display only.

No calibration, CSV material, or numerical grid is changed. Source and resulting
data stay local pending rights review; the repository records only their hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pymupdf

from experiments.extract_5207_materials import runs, mapped

PDF_SHA256='d6e6fa1497c4fc16010997b1a8510d9df3b4692e34c48599c8a4338d5768fab6'
AXES=(74.34001159667969,106.96702575683594,274.8860168457031,258.4990234375)


def extract(pdf):
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=PDF_SHA256:
        raise ValueError('E100 PDF differs from the reviewed 2018 E-4000 source.')
    channels={}
    with pymupdf.open(pdf) as document:
        for channel,index in zip('RGB',[41,39,40]):
            paths=runs(document[3],[index])
            if len(paths)!=1:raise ValueError('Unexpected disconnected sensitivity path.')
            points=mapped(paths[0],AXES,(250,750,-2,2))
            channels[channel]={'wavelengths_nm':points[:,0].tolist(),'values':(10.**points[:,1]).tolist()}
    return {'schema':'softloaf.material-plot/1','quantity':'relative_energy_sensitivity','unit':'relative',
        'source':'Kodak E-4000, Revised 8-18, p4','source_sha256':PDF_SHA256,
        'extraction':{'page':4,'path_indices_RGB':[41,39,40],'axes_pdf_points':list(AXES),
            'axes_values':[250,750,-2,2],'source_encoding':'log10 reciprocal exposure (erg/cm²)',
            'display_encoding':'10**log_sensitivity; linear relative energy sensitivity',
            'bezier_subdivisions':32,'extrapolation':'none'},
        'rights':'Local display only; source and derived curve redistribution review pending',
        'channels':channels}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();data=extract(args.pdf)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
        'samples':{c:len(s['values']) for c,s in data['channels'].items()}}))
