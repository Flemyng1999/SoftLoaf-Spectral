"""Issue #2: primary-table Status M checks and /2 versus /3 pipeline replay.

No private application code is loaded. Manufacturer curves and measured scene
reflectances are source evidence; neither is a measured color-film output.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

import colour
import numpy as np
import pymupdf
from PIL import Image

from experiments.gui_recipe_server import template
from experiments.hsi_raw_lut import SCENES,load_scene,batched
from experiments.validate_5207_colour import legacy_apd_fit
from experiments.validate_pipeline_defaults import diff
from spectral_app.application import Application
from spectral_app.model import SpectralModel
from spectral_lut.native import NativeCore


def primary_table(root):
    """Independent OCR text from the separate ANSI adoption, PDF p17."""
    path=root/'local/reference-assets/ANSI-ISO-5-3-1995.pdf'
    text=pymupdf.open(path)[16].get_text();channels={}
    for c,start,end,first in [('B','2,103','slope = -0,220',410),('G','1,152','slope = -0,120',470),('R','2,109','slope = -O,040',620)]:
        part=text[text.index(start):text.index(end)]
        values=np.array([float(s.replace(',','.')) for s in re.findall(r'\b[0-5],\d{3}\b',part)])
        channels[c]={'x':np.arange(first,first+len(values)*10,10),'y':values}
    slopes=[]
    for raw in re.findall(r'slope = ([^/\n]+)/nm',text):
        slopes.append(float(raw.replace('O','0').replace('Q','0').replace('l','1').replace(',','.')))
    if len(slopes)!=6:raise ValueError('Inspect ANSI Table 4 layout before reading.')
    for i,c in enumerate('BGR'):channels[c]['slopes']=slopes[i*2:i*2+2]
    return channels,{'reference':'ANSI/ISO 5-3:1995 / ANSI/NAPM IT2.18-1996 Table 4, PDF p17',
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def products(table,grid):
    out=[]
    for c in 'RGB':
        d=table[c];x,y=d['x'],d['y'];values=np.interp(grid,x,y)
        values[grid<x[0]]=y[0]+d['slopes'][0]*(grid[grid<x[0]]-x[0])
        values[grid>x[-1]]=y[-1]+d['slopes'][1]*(grid[grid>x[-1]]-x[-1])
        out.append(10.**(values-5))
    return np.array(out).T


def measured_density(transmission,grid,weights):
    return -np.log10(np.trapezoid(np.asarray(transmission)[...,None]*weights,grid,axis=-2)/np.trapezoid(weights,grid,axis=0))


def validate(root,output,exports=False):
    output.mkdir(parents=True,exist_ok=True)
    m=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',output/'runtime',core=NativeCore())
    table,source=primary_table(root);grid=m.negative_wavelengths;w=products(table,grid)
    local=json.loads((root/'local/materials/status-m-iso1984/table4.json').read_text())
    for c in 'RGB':
        np.testing.assert_array_equal(table[c]['x'],local['channels'][c]['wavelengths_nm'])
        np.testing.assert_array_equal(table[c]['y'],local['channels'][c]['log10_products'])
        np.testing.assert_array_equal(table[c]['slopes'],local['channels'][c]['tail_slopes_per_nm'])
    report={'scope':'Primary standard/manufacturer checks, fixed material /2 versus /3 comparison, and measured input scenes. No exposure-paired real-film color accuracy claim.',
        'model':m.negative_refs,'independent_status_m_source':source,'table_comparison':{'values_identical':42,'slopes_identical':6},
        'conditions':{'scene_light':'CIE D55','exposure_ev':0,'viewing_light':'D50','viewing_gain':1.8,'printer':'3200 K Planck model; zero ideal CMY filters, not Kodak CP units','observer':'CIE 1931 2 degree','output':'encoded sRGB / D65'},
        'material':m.negative.metadata,'neutral':{},'scenes':{},'chart':{},'exports':{}}
    n=m.negative;targets=np.array([m.negative_material['characteristic']['channels'][c] for c in 'RGB']).T
    density=n.base+n.amounts@n.dyes.T;neutral_t=10**-density
    back=measured_density(neutral_t,grid,w)
    fine_grid=np.arange(grid[0],grid[-1]+1)
    fine_density=np.stack([np.interp(fine_grid,grid,row) for row in density])
    fine=measured_density(10**-fine_density,fine_grid,products(table,fine_grid))
    report['neutral']['CSV_max_error_D']=float(abs(back-targets).max())
    report['neutral']['CSV_per_channel_max_D']=abs(back-targets).max(0).tolist()
    report['neutral']['one_nm_vs_two_nm_max_D']=float(abs(fine-back).max())
    report['neutral']['original_Kodak_vector_max_error_D']={}
    for i,c in enumerate('RGB'):
        trace=np.asarray(m.calibration['traces']['5207_characteristic_'+c]);exposure=trace[:,0]*np.log10(2)
        inside=(exposure>=n.axis[0])&(exposure<=n.axis[-1]);x=exposure[inside]
        a=np.stack([np.interp(x,n.axis,n.amounts[:,j]) for j in range(3)],-1)
        d=measured_density(10**-(n.base+a@n.dyes.T),grid,w)[:,i]
        report['neutral']['original_Kodak_vector_max_error_D'][c]=float(np.max(abs(d-trace[inside,1])))
    extended=np.arange(300,901,1.)
    report['neutral']['omitted_Status_M_product_area_fraction']= (1-np.trapezoid(products(table,fine_grid),fine_grid,axis=0)/np.trapezoid(products(table,extended),extended,axis=0)).tolist()
    assert report['neutral']['CSV_max_error_D']<.006
    assert max(report['neutral']['original_Kodak_vector_max_error_D'].values())<.006
    assert report['neutral']['one_nm_vs_two_nm_max_D']<.001

    # Replay the prior /2 material and rebuild its frozen paper balance. All
    # viewing, exposure and display settings match /3 in the comparison.
    old=copy.copy(m);old.negative=legacy_apd_fit(old,old.negative_material)
    del old.paper_denominators
    old.paper=old._paper_fit(old.paper_material)
    patches=colour.SDS_COLOURCHECKERS['BabelColor Average']
    spectra=np.stack([np.interp(m.source_wavelengths,s.wavelengths,s.values) for s in patches.values()])
    report['chart']['patches']=list(patches);report['chart']['exposures']={}
    for ev in [-2,0,2]:
        records={}
        for route in ['negative','print']:
            r=m.validate(template(route))['normalized_recipe'];r['film']['exposure_ev']=ev
            direct=m.sample_spectra(spectra,**m.parameters(r));before=old.sample_spectra(spectra,**old.parameters(r))
            approx=m.sample(spectra@m.source_to_ap1,**m.parameters(r))
            records[route]={'new_vs_previous':diff(direct['display_rgb'],before['display_rgb']),
                'RGB_approximation_vs_spectral':diff(direct['display_rgb'],approx['display_rgb']),
                'transmission_range':[float(direct['transmission'].min()),float(direct['transmission'].max())]}
            assert 0<direct['transmission'].min() and direct['transmission'].max()<=1
            if route=='negative':assert 'dmin_apd' in direct
            else:assert 'apd' not in direct and 'dmin_apd' not in direct and 'ACES' not in direct
        report['chart']['exposures'][str(ev)]=records
    panels=[]
    for number in SCENES:
        name=f'scene{number:02d}';scene=load_scene(m.archive,number);rows=scene.reshape(-1,scene.shape[-1]);record={}
        for route in ['negative','print']:
            r=m.validate(template(route))['normalized_recipe']
            current=batched(lambda x:m.sample_spectra(x,**m.parameters(r))['display_rgb'],rows,chunk=2048)
            before=batched(lambda x:old.sample_spectra(x,**old.parameters(r))['display_rgb'],rows,chunk=2048)
            record[route]=diff(current,before)
            if number==43:
                shape=(*scene.shape[:2],3);panels.append((route,before.reshape(shape),current.reshape(shape)))
        report['scenes'][name]=record;print(name,'old/new compared',flush=True)
    app=Application(m)
    if exports:
        for route in ['negative','print']:
            result=app.export({'recipe':m.validate(template(route))['normalized_recipe'],'purpose':'display','grid':65})
            assert result['ok'] and result['verification']['integrity_passed']
            report['exports'][route]=result
            print(route,'65^3 file integrity verified',flush=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(10,7.4))
    for row,(route,before,after) in enumerate(panels):
        for column,(image,label) in enumerate([(before,'Previous: estimated APD fit'),(after,'Current: direct Status M fit')]):
            axes[row,column].imshow(image);axes[row,column].set_title(route+' / '+label,fontsize=10);axes[row,column].axis('off')
            Image.fromarray(np.rint(np.clip(image,0,1)*255).astype('uint8')).save(output/(route+('-before.png' if column==0 else '-after.png')),icc_profile=m.display_profile('sRGB'))
    fig.tight_layout();fig.savefig(output/'comparison.png',dpi=140);plt.close(fig)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--exports',action='store_true');args=p.parse_args()
    report=validate(Path(__file__).resolve().parents[1],args.output.resolve(),args.exports)
    print(json.dumps({'neutral':report['neutral'],'scene43':report['scenes']['scene43']},indent=2))
