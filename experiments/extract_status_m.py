"""Extract ISO 5/3:1984 Table 4 from the identified local PDF.

Only extraction code and hashes belong in Git. The standard and numeric table
remain local pending rights review. No other application's tables are imported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import pymupdf


def extract(pdf,output):
    page=pymupdf.open(pdf)[6];words=page.get_text('words');channels={}
    for c,left,right,start,count in [('B',230,285,410,11),('G',330,380,470,15),('R',425,475,620,16)]:
        selected=sorted((w for w in words if left<w[0]<right and 160<w[1]<575 and re.fullmatch(r'[0-5][,.]\d{3}',w[4])),key=lambda w:w[1])
        values=[float(w[4].replace(',','.')) for w in selected]
        slopes=[float(w[4].split('/')[0].replace('O','0').replace(',','.')) for w in words if left<w[0]<right and '/nm' in w[4]]
        if len(values)!=count or max(values)!=5 or len(slopes)!=2 or not slopes[0]>0>slopes[1]:
            raise ValueError('Unexpected Table 4 layout; inspect the source page before extraction.')
        channels[c]={'wavelengths_nm':list(range(start,start+count*10,10)),
                     'log10_products':values,'tail_slopes_per_nm':slopes}
    record={'schema':'softloaf.status-m-source/1','reference':'ISO 5/3:1984 Table 4, printed p5 / PDF p7',
        'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'channels':channels,
        'quantity':'log10_spectral_product','peak_log10':5.,
        'rights':'Local reference only; permission for redistribution pending.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
    return record


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf',type=Path,default=Path('local/film-color-slides/hyperspectral-demo/data/ISO-5-3-1984-preview.pdf'))
    p.add_argument('--output',type=Path,default=Path('local/materials/status-m-iso1984/table4.json'))
    args=p.parse_args();record=extract(args.pdf,args.output)
    print(json.dumps({'pdf_sha256':record['pdf_sha256'],'table_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}))
