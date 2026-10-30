"""Compare collected Kodak curves with original chart pixels and landmarks."""
from pathlib import Path
import argparse
import json

import numpy as np
import pymupdf
from PIL import Image, ImageDraw

from experiments.harvest_kodak_motion import ROOT, SOURCES, ACTIVE_STOCKS

COLORS={'R':'#ef3b38','G':'#00b48b','B':'#2580fa','C':'#00bfe3','M':'#e834ca','Y':'#dbad00','minimum_density':'#e04030','midscale_neutral':'#27bad6'}


def verify(sources,collection,output):
    output.mkdir(parents=True,exist_ok=True);report={}
    for stock in ACTIVE_STOCKS:
        source=SOURCES[stock]
        entry=json.loads((collection/stock/'source-curves.json').read_text())
        stats={}
        with pymupdf.open(sources/source['file']) as doc:
            for role in ['characteristic','sensitivity','density']:
                selected={n:c for n,c in entry['curves'].items() if (n.startswith(role+'_') if role!='density' else n.startswith('dye_') or n in ('minimum_density','midscale_neutral'))}
                first=next(iter(selected.values()));page=doc[first['page']-1]
                if 'image_xref' in first:
                    p=pymupdf.Pixmap(doc,first['image_xref']);im=Image.frombytes('RGB',[p.width,p.height],p.samples);offset=(0,0);scale=1
                else:
                    x0,x1,y0,y1,*_=first['axes'];clip=pymupdf.Rect(x0-35,min(y0,y1)-25,x1+15,max(y0,y1)+30)
                    scale=3;p=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,alpha=False)
                    im=Image.frombytes('RGB',[p.width,p.height],p.samples);offset=(p.x,p.y)
                draw=ImageDraw.Draw(im)
                for name,curve in selected.items():
                    coords=np.array(curve['source_coordinates'])*scale-np.array(offset)
                    color=COLORS.get(name,COLORS.get(name[-1],'#ff0000'))
                    for x,y in coords[::3]:draw.ellipse((x-1.5,y-1.5,x+1.5,y+1.5),fill=color)
                    a=np.array(curve['points']);stats[name]={'points':len(a),'coverage':[float(a[:,0].min()),float(a[:,0].max())],'range':[float(a[:,1].min()),float(a[:,1].max())],'peak_x':float(a[np.argmax(a[:,1]),0]),'largest_source_point_gap':float(np.diff(a[:,0]).max()),'source_page':curve['page']}
                im.save(output/f'{stock}-{role}-source-overlay.png')
        report[stock]={'source_sha256':source['sha256'],'curves':stats,'substitutions':entry['substitutions'],'missing_components':entry['missing_components'],'density_status':entry['characteristic_density_status']}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sources',type=Path,default=ROOT/'local/reference-assets/kodak-motion-user-2026');parser.add_argument('--collection',type=Path,default=ROOT/'local/materials/kodak-motion-survey-v1');parser.add_argument('--output',type=Path,default=ROOT/'artifacts/kodak-motion-harvest');a=parser.parse_args();r=verify(a.sources,a.collection,a.output)
    print(json.dumps({s:{'curves':len(e['curves']),'points':sum(c['points'] for c in e['curves'].values()),'density_status':e['density_status'],'missing':e['missing_components']} for s,e in r.items()},indent=2))


if __name__=='__main__':main()
