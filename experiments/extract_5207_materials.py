"""Extract published vector plots, not historical product code.

Inputs remain local. Run from the repository root after acquiring the two
identified manufacturer PDFs and the user's TB-2014-005 reference.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import pymupdf
from spectral_lut.reference import decreasing_projection


def runs(page, indices):
    result=[]
    for idx in indices:
        current=[]
        for item in page.get_drawings()[idx]['items']:
            if item[0] not in ('l','c'): continue
            if current and np.linalg.norm(np.array(current[-1])-np.array(item[1]))>.01:
                result.append(np.array(current)); current=[]
            if not current: current=[tuple(item[1])]
            if item[0]=='l': current.append(tuple(item[2]))
            else:
                p=np.array([tuple(x) for x in item[1:]])
                for t in np.linspace(0,1,33)[1:]: current.append((1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3])
        if current: result.append(np.array(current))
    return result


def mapped(points, axes, limits):
    x0,y0,x1,y1=axes; a,b,c,d=limits
    p=np.asarray(points)
    x=a+(p[:,0]-x0)/(x1-x0)*(b-a)
    y=c+(y1-p[:,1])/(y1-y0)*(d-c)
    if np.any(np.diff(x)<-1e-5): raise ValueError('Non-monotonic path: check selected plot.')
    keep=np.r_[True,np.diff(x)>1e-9]
    return np.column_stack([x[keep],y[keep]])


def extract(film_pdf, paper_pdf, bulletin, output):
    output.mkdir(parents=True,exist_ok=True)
    f,p=pymupdf.open(film_pdf),pymupdf.open(paper_pdf)
    traces={}
    def curve(name, points, axes, limits):
        traces[name]=mapped(points,axes,limits).tolist(); return np.array(traces[name])
    def sampled(name,grid,columns,header,log=False,zero_tails=False):
        values=[]
        for label,t in columns:
            v=np.interp(grid,t[:,0],t[:,1])
            if log:
                v=10**v
                if zero_tails: v[(grid<t[0,0])|(grid>t[-1,0])]=0
            else:
                v=np.maximum(v,0)
                if 'characteristic' in name:v=-decreasing_projection(-v)
            values.append(v)
        np.savetxt(output/name,np.column_stack([grid,*values]),delimiter=',',header=header,comments='',fmt='%.15g')
    a=(357.070,125.230,541.594,309.721)
    char=[curve('5207_characteristic_'+c,runs(f[3],[i])[0],a,(-8,8,0,3)) for c,i in zip('RGB',[74,72,73])]
    sampled('5207_characteristic.csv',np.linspace(-8,7.95,321)*np.log10(2),list(zip('RGB',[np.column_stack([v[:,0]*np.log10(2),v[:,1]]) for v in char])),'log_exposure,R,G,B')
    s=[curve('5207_sensitivity_'+c,runs(f[3],[i])[0],(352.696,517.997,553.222,669.696),(250,750,0,4)) for c,i in zip('RGB',[91,90,89])]
    sampled('5207_sensitivity.csv',np.arange(400,721,10),list(zip('RGB',s)),'wavelength_nm,R,G,B',True,True)
    dyes=[curve('5207_dye_'+c,runs(f[4],[i])[0],(78.261,170.581,262.655,354.807),(400,800,-.2,1.8)) for c,i in zip('CMY',[26,25,24])]
    base=curve('5207_base',runs(f[4],[28])[0],(78.261,170.581,262.655,354.807),(400,800,-.2,1.8))
    sampled('5207_dyes.csv',np.arange(360,731,2),list(zip('CMY',dyes))+[('base',base)],'wavelength_nm,C,M,Y,base')
    # Paper plots contain disconnected strokes; select connected curve runs,
    # joining only path boundaries whose coordinates coincide.
    rr=runs(p[6],[3,4]); curves=[r for r in rr if len(r)>30 and np.diff(r[:,0]).min()>0]
    R=next(r for r in curves if r[0,0]<100 and r[-1,1]<105)
    rest=[r for r in curves if r is not R]
    G=np.vstack([rest[0],rest[1][1:]])
    B=rest[2]
    pc=[curve('paper_characteristic_'+c,r,(97.982,84.013,282.987,267.926),(-3,0,0,3)) for c,r in zip('RGB',[R,G,B])]
    sampled('paper_characteristic.csv',np.linspace(-2.99,-.16,257),list(zip('RGB',pc)),'log_exposure,R,G,B')
    rr=runs(p[6],[46,47,48,49]); rr=[r for r in rr if len(r)>20]
    ps=[np.vstack([rr[3],rr[4][1:]]),np.vstack([rr[1],rr[2][1:]]),rr[0]]
    ps=[curve('paper_sensitivity_'+c,r,(362.668,53.014,563.196,204.487),(250,750,-2,2)) for c,r in zip('RGB',ps)]
    sampled('paper_sensitivity.csv',np.arange(360,731,2),list(zip('RGB',ps)),'wavelength_nm,R,G,B',True,True)
    pd=[curve('paper_dye_'+c,[r for r in runs(p[6],[i]) if len(r)>50][-1],(95.808,339.586,279.466,523.074),(350,700,0,2.5)) for c,i in zip('CMY',[21,8,6])]
    sampled('paper_dyes.csv',np.arange(360,731,2),list(zip('CMY',pd)),'wavelength_nm,C,M,Y')
    # Published APD products already include the standard influx spectrum.
    text='\n'.join(pymupdf.open(bulletin)[i].get_text(sort=True) for i in [23,24,25])
    values=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts) in (4,8):
            for j in range(0,len(parts),4):
                if re.fullmatch(r'\d{3}',parts[j]) and all(re.fullmatch(r'\d\.\d{4}',v) for v in parts[j+1:j+4]):values.append([float(v) for v in parts[j:j+4]])
    values=sorted(values)
    if len(values)!=186 or not np.array_equal(np.array(values)[:,0],np.arange(360,731,2)): raise ValueError(f'Incomplete APD table: {len(values)}')
    np.savetxt(output/'apd_weights.csv',values,delimiter=',',header='wavelength_nm,R,G,B',comments='',fmt='%.8g')
    metadata={'schema':'softloaf.extracted-materials/1','sources':{name:{'file':Path(file).name,'sha256':hashlib.sha256(Path(file).read_bytes()).hexdigest()} for name,file in [('5207',film_pdf),('paper',paper_pdf),('APD',bulletin)]},'traces':traces,'assumptions':['Published log sensitivities converted with 10**logS; channel labels R=cyan-forming, G=magenta-forming, B=yellow-forming.','Sensitivity outside each drawn trace is zero: unmeasured model tail assumption, not a measured zero.','CMY and base densities below 400 nm and paper dyes outside drawn ranges use nearest endpoint; negative digitization excursions clipped to zero.','5207 neutral exposure origin: camera stops 0; not absolute ISO calibration.','Paper reflection density model has no scattering/fluorescence/interimage calibration.'],'rights':'local reference only; redistribution review pending'}
    metadata['assumptions'].append('Characteristic densities use increasing isotonic projection of small vector-digitization reversals; original mapped traces are preserved here.')
    metadata['status_m_to_apd']={'source':'TB-2014-005 PDF p31 / S-2008-002 v1.1 p25, Eastman Kodak 5207','matrix':[[1.087370,-.008372,.001454],[-.010327,1.022765,.017075],[-.007220,.028536,.955400]],'offset':[-.015931,-.032591,.012734],'reported_max_error_D':[.016,.053,.010],'reported_mean_abs_error_D':[.004,.010,.002],'scope':'published stock-specific fit; not a new calibration or exact mapping'}
    (output/'provenance.json').write_text(json.dumps(metadata,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bulletin',type=Path,required=True);args=parser.parse_args()
    extract(Path('local/reference-assets/Kodak_5207_2015.pdf'),Path('local/film-color-slides/hyperspectral-demo/data/paper-reflectance/Kodak_Ultra_Endura_E4020_2003.pdf'),args.bulletin,Path('local/materials/5207-v1'))
