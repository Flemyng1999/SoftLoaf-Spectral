"""Collect the four selected VISION3 stocks from identified Kodak PDFs.

This creates a source survey, not runtime materials. No substituted curves,
material fitting, tail extrapolation, density clipping or recipe changes.
Original PDFs and extracted curves remain local pending rights review.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pymupdf
from scipy.ndimage import distance_transform_edt

from experiments.extract_5207_materials import runs

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    '5203': {'file': 'Kodak_VISION3_50D_5203_7203_Technical_Data.pdf', 'sha256': 'f697ae60b74872b402e2ded8752fb1b326e4a392eece2bb3e3f9dd24b517271c', 'name': 'Kodak VISION3 50D 5203 / 7203', 'revision': 'K-1165.25.09.30.EN.02; copyright 2025', 'temperature_k': 5500, 'status': 'not_specified_in_this_document', 'char_seconds': None, 'sens_seconds': None},
    '5206': {'file': 'Kodak_VERITA_200D_5206_7206_Technical_Data_2026.pdf', 'sha256': 'aa5bfd899003cf4a0ae5a86a33325e0eac2ed16b9fca61c8894532de1458bae2', 'name': 'Kodak VERITA 200D 5206 / 7206', 'revision': 'H-1-5206; 2026', 'temperature_k': 5500, 'status': 'Status M', 'char_seconds': .02, 'sens_seconds': .02},
    '5207': {'file': 'Kodak_VISION3_250D_5207_7207_Technical_Data.pdf', 'sha256': '0a4f1c4fc454a4498162853a62f0989436d18233b7153cb7038f4dcb68f14f18', 'name': 'Kodak VISION3 250D 5207 / 7207', 'revision': 'H-1-5207; revised 3-22', 'temperature_k': 5500, 'status': 'Status M', 'char_seconds': .02, 'sens_seconds': .02},
    '5213': {'file': 'Kodak_VISION3_200T_5213_7213_Technical_Data_H-1-5213_2026.pdf', 'sha256': '6208b3938416434bb74fc628d102b59cd60cb1704510202496b46197796ec624', 'name': 'Kodak VISION3 200T 5213 / 7213', 'revision': 'H-1-5213; revised 3-26', 'temperature_k': 3200, 'status': 'Status M', 'char_seconds': .02, 'sens_seconds': .04},
    '5219': {'file': 'Kodak_VISION3_500T_5219_7219_Technical_Data.pdf', 'sha256': 'bcf82ca05b991505ea5cdd198875128e724195eabed43976e0ccf7aec3b083c8', 'name': 'Kodak VISION3 500T 5219 / 7219', 'revision': 'H-1-5219; revised 3-22', 'temperature_k': 3200, 'status': 'unconfirmed_source_label', 'char_seconds': .02, 'sens_seconds': .04},
}


ACTIVE_STOCKS = ('5203', '5207', '5213', '5219')
EXCLUSIONS = {'5206': 'Excluded by user: separate CMY dye spectra unavailable; archival source record only.'}

def clean(points):
    a = np.asarray(points, dtype=np.float64)
    a = a[np.argsort(a[:, 0], kind='stable')]
    x, inv = np.unique(a[:, 0], return_inverse=True)
    return np.column_stack([x, np.bincount(inv, weights=a[:, 1]) / np.bincount(inv)])


def map_points(points, axes):
    """Unclamped affine mapping; first y locator is the lower plot edge."""
    x0, x1, y0, y1, a, b, c, d = axes
    p = np.asarray(points)
    return np.column_stack([a + (p[:, 0]-x0)/(x1-x0)*(b-a), c + (p[:, 1]-y0)/(y1-y0)*(d-c)])


def outline_centers(contours):
    """Read center of a filled stroke outline, keeping disconnected dash gaps."""
    points = []
    for contour in contours:
        v = np.vstack([contour, contour[0]])
        x = np.arange(v[:, 0].min()+.015, v[:, 0].max(), .10)
        p, q = v[:-1], v[1:]
        for col in x:
            hit = (np.minimum(p[:, 0], q[:, 0]) <= col) & (np.maximum(p[:, 0], q[:, 0]) > col)
            if not hit.any(): continue
            s, t = p[hit], q[hit]
            yy = s[:, 1]+(col-s[:, 0])/(t[:, 0]-s[:, 0])*(t[:, 1]-s[:, 1])
            points.append([col, (yy.min()+yy.max())/2])
    return clean(points)


def vector_curve(doc, page_number, index, axes, filled=False):
    contours = runs(doc[page_number-1], index if isinstance(index, list) else [index])
    pixels = outline_centers(contours) if filled else np.vstack(contours)
    values = map_points(pixels, axes)
    # Preserve full native geometry separately. Output only the printed viewport.
    a, b, c, d = axes[4:]
    for bound in (a,b):
        values[np.abs(values[:,0]-bound)<.01,0]=bound
    keep = (values[:, 0] >= a) & (values[:, 0] <= b) & (values[:, 1] >= min(c,d)) & (values[:, 1] <= max(c,d))
    support=[]
    if not filled:
        indices=np.flatnonzero(keep)
        for group in np.split(indices,np.flatnonzero(np.diff(indices)>1)+1):
            if len(group)>1:support.append([float(values[group,0].min()),float(values[group,0].max())])
    return {'support_intervals': support, 'points': clean(values[keep]).tolist(), 'source_coordinates': pixels[keep].tolist(), 'source_geometry': [r.tolist() for r in contours], 'page': page_number, 'drawing_index': index, 'axes': list(axes), 'method': 'filled_vector_outline_center' if filled else 'native_vector_path_32_subdivisions_per_Bezier', 'interpolation_gap_limit': (1e6 if not filled else (.10 if axes[4] == -8 else 8.0))}


def raster_curve(doc, page_number, xref, axes, guide, grid=False):
    """Find actual dark source strokes near manually reviewed locator guides.

    Guides are never exported as measurements. A global path follows the ink;
    columns without a nearby stroke are omitted. Dash/grid gaps remain explicit.
    """
    pix = pymupdf.Pixmap(doc, xref)
    raster = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    ink = raster[:, :, :3].min(axis=2) < 150
    x0,x1,y0,y1,a,b,c,d = axes
    yy,xx = np.indices(ink.shape)
    ink &= (xx>x0+2)&(xx<x1-2)&(yy>min(y0,y1)+2)&(yy<max(y0,y1)-2)
    if grid:
        for wavelength in np.arange(250,751,50):
            pos=x0+(wavelength-a)/(b-a)*(x1-x0);ink[:,abs(np.arange(pix.width)-pos)<1.6]=False
        for log_value in np.arange(0,5):
            pos=y0+(log_value-c)/(d-c)*(y1-y0);ink[abs(np.arange(pix.height)-pos)<1.6,:]=False
    g=np.array(guide,dtype=float)
    cols=np.arange(max(int(np.ceil(x0+3)),int(np.ceil(x0+(g[0,0]-a)/(b-a)*(x1-x0)))),min(int(x1-2),int(np.floor(x0+(g[-1,0]-a)/(b-a)*(x1-x0))))+1)
    data_x=a+(cols-x0)/(x1-x0)*(b-a)
    centers=np.rint(y0+(np.interp(data_x,g[:,0],g[:,1])-c)/(d-c)*(y1-y0)).astype(int)
    distance=distance_transform_edt(~ink)
    offsets=np.arange(-12,13);back=[];previous=None
    for col,center in zip(cols,centers):
        rows=np.clip(center+offsets,0,pix.height-1)
        emission=np.minimum(distance[rows,col],8)**2+.035*offsets**2
        if previous is None: previous=emission;back.append(np.zeros(len(offsets),dtype=int));continue
        choices=[]
        for step in range(-4,5):
            shifted=np.full(len(offsets),np.inf)
            if step<0:shifted[:step]=previous[-step:]
            elif step>0:shifted[step:]=previous[:-step]
            else:shifted=previous.copy()
            choices.append(shifted+.45*step**2)
        choices=np.array(choices);which=np.argmin(choices,axis=0)
        previous=emission+choices[which,np.arange(len(offsets))]
        back.append(np.arange(len(offsets))-(which-4))
    indices=np.empty(len(cols),dtype=int);indices[-1]=np.argmin(previous)
    for i in range(len(cols)-1,0,-1):indices[i-1]=back[i][indices[i]]
    points=[];missing=[]
    for col,center,ix in zip(cols,centers,indices):
        target=center+offsets[ix]
        rows=np.flatnonzero(ink[:,col]);rows=rows[abs(rows-target)<=4]
        if not len(rows):missing.append(int(col));continue
        groups=np.split(rows,np.flatnonzero(np.diff(rows)>1)+1)
        nearest=min(groups,key=lambda group:abs(np.median(group)-target))
        # Median of the actual connected source ink, never the locator value.
        row=float(np.median(nearest));points.append([float(col),row])
    if len(points)<20:raise ValueError(f'Unresolved source curve xref={xref}')
    values=map_points(points,axes)
    return {'points':clean(values).tolist(),'source_coordinates':points,'page':page_number,'image_xref':xref,'image_size':[pix.width,pix.height], 'axes':list(axes),'locator_guide':guide,'omitted_source_columns':missing,'method':'reviewed_guide_located_raster_ink_centerline','interpolation_gap_limit':.12 if a==-8 else 8.0,'pixel_size_in_data_units':[abs((b-a)/(x1-x0)),abs((d-c)/(y1-y0))],'source_ink_threshold':150,'grid_removed':grid}


# Manual locators identify the corresponding strokes in the original embedded
# raster. They are not numerical input to the film model or measured curve data.
SENS_GUIDES={
 '5207':{
  'B':[(360,1.52),(380,1.95),(400,2.38),(420,2.38),(440,2.42),(450,2.37),(468,2.51),(480,2.2),(490,1.55),(500,1.0),(510,.6),(520,.08)],
  'G':[(400,.63),(420,.48),(440,.34),(450,.4),(460,.53),(470,.59),(480,.95),(490,1.54),(500,1.85),(520,2.1),(540,2.32),(550,2.41),(570,2.2),(580,2.02),(590,1.3),(600,.34)],
  'R':[(530,.03),(540,.02),(550,.1),(560,.3),(570,.52),(580,1.17),(590,1.64),(600,1.9),(620,2.2),(640,2.31),(650,2.39),(660,2.38),(670,2.07),(680,1.62),(690,1.22),(700,.16)]},
 '5213':{
  'B':[(380,2.34),(400,2.68),(410,2.68),(430,2.82),(440,2.85),(450,2.76),(468,2.83),(478,2.55),(490,1.6),(500,1.2),(510,.95),(520,.46)],
  'G':[(480,.97),(490,1.57),(500,1.9),(520,2.15),(530,2.25),(550,2.48),(560,2.38),(570,2.27),(580,2.1),(590,1.3),(600,.28)],
  'R':[(560,.35),(570,.56),(580,1.19),(590,1.67),(610,1.98),(620,2.08),(640,2.16),(650,2.17),(660,2.05),(665,1.81),(670,1.49),(675,1.0),(680,.54)]},
 '5219':{
  'B':[(370,2.53),(385,3.01),(400,3.19),(420,3.17),(440,3.08),(460,3.06),(470,3.04),(485,2.75),(500,2.24),(510,1.8),(520,1.25),(529,.69)],
  'G':[(450,1.05),(470,1.23),(480,1.57),(490,1.98),(500,2.28),(520,2.47),(535,2.64),(550,2.79),(560,2.71),(575,2.55),(582,2.33),(590,1.75),(600,.76)],
  'R':[(510,.62),(520,.71),(530,.75),(540,.69),(550,.61),(560,.78),(570,1.15),(575,1.34),(580,1.54),(585,1.76),(590,1.98),(600,2.14),(610,2.17),(620,2.3),(630,2.42),(645,2.37),(650,2.43),(660,2.42),(665,2.23),(670,2.09),(675,1.89),(680,1.7)]}
}
# Independent stock-specific readings of the published five density strokes.
DYE_GUIDES={
 '5207':{
  'dye_Y':[(402,.52),(420,.84),(440,1),(450,.99),(470,.81),(480,.61),(490,.4),(500,.25),(520,.12),(540,.07),(560,.03),(580,.01),(610,0),(680,-.007),(750,0),(790,0)],
  'dye_C':[(402,.20),(420,.11),(440,.05),(460,.02),(480,.02),(500,.055),(520,.08),(540,.11)],
  'dye_M':[(402,-.01),(420,-.015),(430,0),(440,-.01),(450,-.03),(460,-.025),(470,.12),(480,.233),(490,.395),(500,.554),(510,.722),(520,.855),(540,.99),(550,.96),(560,.82),(580,.42),(600,.19),(620,.1),(650,.06),(690,.045),(740,.02),(790,0)],
  'minimum_density':[(402,.67),(420,.82),(440,.9),(460,.86),(480,.81),(500,.68),(510,.69),(520,.66),(530,.58),(540,.54),(560,.53),(575,.53),(590,.373),(600,.3),(610,.23),(630,.21),(650,.20),(690,.20),(720,.19),(750,.15),(790,.10)],
  'midscale_neutral':[(402,1.14),(420,1.41),(440,1.57),(450,1.55),(470,1.44),(480,1.39),(490,1.26),(500,1.25),(510,1.30),(530,1.26),(540,1.26),(550,1.24),(560,1.16),(580,.92),(600,.67),(610,.66),(620,.70),(640,.74),(660,.8),(680,.83),(700,.81),(720,.73),(740,.55),(760,.37),(780,.24),(798,.17)]},
 '5213':{
  'dye_Y':[(402,.54),(420,.83),(440,.98),(450,.99),(470,.83),(480,.64),(490,.44),(500,.28),(520,.12),(540,.06),(560,.02),(580,0),(650,-.005),(730,-.004),(790,0)],
  'dye_C':[(402,.21),(420,.13),(440,.07),(460,.035),(480,.03),(500,.04),(520,.05),(540,.12)],
  'dye_M':[(402,0),(420,.01),(430,.03),(440,.02),(450,.01),(460,.04),(470,.154),(480,.267),(490,.431),(500,.587),(510,.742),(520,.874),(540,.99),(550,.96),(560,.82),(580,.43),(600,.20),(620,.10),(640,.06),(680,.03),(730,.02),(790,0)],
  'minimum_density':[(402,.60),(420,.75),(440,.84),(460,.8),(475,.78),(485,.73),(495,.68),(500,.67),(510,.69),(520,.63),(530,.57),(540,.55),(560,.54),(570,.54),(580,.49),(590,.359),(600,.29),(610,.25),(620,.22),(630,.22),(640,.20),(650,.18),(680,.17),(720,.16),(750,.14),(790,.1)],
  'midscale_neutral':[(402,1.12),(420,1.4),(440,1.58),(450,1.56),(470,1.46),(480,1.41),(490,1.31),(500,1.30),(510,1.36),(530,1.36),(540,1.36),(550,1.32),(560,1.23),(580,1.0),(600,.74),(610,.69),(620,.71),(630,.75),(640,.77),(650,.78),(670,.86),(690,.88),(710,.85),(730,.70),(740,.599),(750,.50),(760,.42),(770,.34),(780,.28),(798,.21)]},
 '5219':{
  'dye_Y':[(402,.51),(420,.82),(440,1),(450,.99),(470,.84),(480,.66),(490,.46),(500,.3),(520,.16),(540,.11),(560,.06),(580,.03),(600,.01),(650,0),(730,0),(790,0)],
  'dye_C':[(402,.18),(420,.10),(440,.04),(460,.015),(480,.01),(500,.025),(520,.04),(540,.075)],
  'dye_M':[(402,-.02),(420,-.025),(430,-.02),(440,-.04),(450,-.04),(460,-.01),(470,.098),(480,.214),(490,.368),(500,.546),(510,.708),(520,.849),(540,1),(550,.96),(560,.83),(580,.46),(600,.24),(620,.15),(640,.10),(680,.07),(730,.05),(790,.015)],
  'minimum_density':[(402,.62),(420,.78),(440,.87),(460,.83),(480,.79),(490,.75),(500,.72),(510,.72),(520,.64),(530,.557),(540,.54),(550,.54),(560,.53),(575,.53),(580,.49),(590,.38),(600,.30),(610,.26),(620,.25),(630,.23),(640,.19),(650,.16),(680,.14),(720,.12),(750,.105),(790,.08)],
  'midscale_neutral':[(402,1.14),(420,1.46),(440,1.64),(450,1.63),(470,1.51),(490,1.38),(500,1.38),(510,1.43),(520,1.41),(530,1.41),(540,1.41),(550,1.37),(560,1.28),(580,1.05),(600,.79),(610,.76),(620,.80),(630,.81),(640,.82),(660,.88),(680,.92),(700,.91),(720,.84),(740,.68),(760,.49),(780,.32),(798,.2)]}
}
# Each guide is independent of the numerical data; output values are source ink.
CYAN_TAIL_LOCATORS={
 '5207':[(560,.16),(580,.24),(600,.4),(620,.60),(640,.78),(660,.93),(680,1),(700,.98),(720,.88),(740,.611),(750,.491),(760,.401),(770,.30),(780,.23),(790,.17),(798,.12)],
 '5213':[(560,.19),(580,.29),(600,.47),(620,.65),(640,.8),(660,.94),(680,.99),(700,.94),(720,.82),(740,.599),(750,.498),(760,.408),(770,.303),(780,.24),(798,.15)],
 '5219':[(560,.16),(580,.24),(600,.4),(620,.60),(640,.78),(660,.93),(680,1),(700,.98),(720,.88),(740,.629),(750,.534),(760,.44),(770,.33),(780,.25),(790,.18),(798,.14)],
}
for _stock,_locators in CYAN_TAIL_LOCATORS.items():DYE_GUIDES[_stock]['dye_C'] += _locators

RASTER_AXES={
 '5207':{'characteristic':(90,631,640,99,-8,8,0,3),'sensitivity':(105,693,603,158,250,750,0,4),'dyes':(105,646,670,129,400,800,-.2,1.8),'xref':(9,15,17)},
 '5213':{'characteristic':(108,675,664,97,-8,8,0,3),'sensitivity':(106,721,518,54,250,750,0,4),'dyes':(118,684,633,66,400,800,-.2,1.8),'xref':(9,17,16)},
 '5219':{'characteristic':(85,652,668,102,-8,8,0,3),'sensitivity':(110,751,560,76,250,750,0,4),'dyes':(96,662,646,79,400,800,-.2,1.8),'xref':(9,15,17)},
}
CHAR_GUIDES={
 '5207':{'R':[.18,.21,.34,.61,.89,1.18,1.46,1.70,1.83,1.84],'G':[.58,.61,.77,1.08,1.42,1.75,2.08,2.36,2.51,2.55],'B':[.85,.88,1.02,1.34,1.66,1.98,2.29,2.56,2.70,2.74]},
 '5213':{'R':[.18,.20,.30,.58,.87,1.15,1.43,1.68,1.81,1.83],'G':[.58,.60,.75,1.06,1.39,1.72,2.04,2.32,2.49,2.54],'B':[.85,.87,1.01,1.32,1.64,1.97,2.28,2.57,2.75,2.79]},
 '5219':{'R':[.19,.22,.35,.60,.88,1.16,1.43,1.67,1.83,1.86],'G':[.59,.62,.78,1.1,1.43,1.76,2.08,2.36,2.53,2.56],'B':[.85,.88,1.04,1.36,1.69,2.02,2.35,2.63,2.73,2.75]},
}


def extract_stock(doc,stock):
    curves={}
    if stock=='5206':
        for c,i in zip('RGB',[18,19,20]):curves['characteristic_'+c]=vector_curve(doc,4,i,(78.439,243.034,258.095,109.521,-8,8,0,(258.095-109.521)/(258.095-120.994)*3))
        for c,i in zip('RGB',[32,31,30]):curves['sensitivity_'+c]=vector_curve(doc,4,i,(63.059,219.198,549.549,409.320,250,750,0,4))
        for name,i in [('minimum_density',7),('midscale_neutral',8)]:curves[name]=vector_curve(doc,4,i,(360.604,528.758,270.789,111.359,400,700,0,1.6))
    elif stock=='5203':
        for c,i in zip('RGB',[list(range(3,20)),20,21]):curves['characteristic_'+c]=vector_curve(doc,2,i,(56.0635,176.5985,614.7901,495.0651,-8,8,0,3),True)
        for c,i in zip('RGB',[45,44,46]):curves['sensitivity_'+c]=vector_curve(doc,3,i,(59.264,178.097,607.277,488.480,250,750,0,4),True)
        for name,i in [('dye_C',83),('dye_M',84),('dye_Y',85),('minimum_density',86),('midscale_neutral',87)]:curves[name]=vector_curve(doc,3,i,(244.1338,362.9888,607.7306,488.9136,400,800,-.2,1.8),True)
    else:
        specs=RASTER_AXES[stock];charxref,sensxref,dyexref=specs['xref']
        for c,g in CHAR_GUIDES[stock].items():
            curves['characteristic_'+c]=raster_curve(doc,3,charxref,specs['characteristic'],list(zip([-8,-6,-4,-2,0,2,4,6,7.9,8],g)))
        for c,g in SENS_GUIDES[stock].items():curves['sensitivity_'+c]=raster_curve(doc,4,sensxref,specs['sensitivity'],g,True)
        for name,g in DYE_GUIDES[stock].items():curves[name]=raster_curve(doc,4,dyexref,specs['dyes'],g)
    return curves


def interpolate(curve,grid):
    a=np.array(curve['points']);out=np.interp(grid,*a.T,left=np.nan,right=np.nan)
    # Native discontinuities and long unresolved raster gaps remain blank.
    if curve.get('support_intervals'):
        supported=np.zeros(len(grid),dtype=bool)
        for low,high in curve['support_intervals']:supported |= (grid>=low)&(grid<=high)
        out[~supported]=np.nan
    for left,right in zip(a[:-1,0],a[1:,0]):
        if right-left>curve['interpolation_gap_limit']:out[(grid>left)&(grid<right)]=np.nan
    return out


def csv(path,axis,columns,header):
    arrays=np.column_stack([axis,*columns]);lines=[header]
    lines.extend(','.join('' if not np.isfinite(v) else f'{v:.15g}' for v in row) for row in arrays)
    path.write_text('\n'.join(lines)+'\n')


def harvest_collection(source_directory,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);result={}
    for stock in ACTIVE_STOCKS:
        source=SOURCES[stock]
        pdf=Path(source_directory)/source['file']
        if hashlib.sha256(pdf.read_bytes()).hexdigest()!=source['sha256']:raise ValueError(f'{stock}: unexpected PDF hash')
        with pymupdf.open(pdf) as doc:curves=extract_stock(doc,stock)
        for name,curve in curves.items():
            curve['abscissa_unit']='camera stop' if name.startswith('characteristic_') else 'nm'
            curve['ordinate_unit']='log10(cm^2/erg)' if name.startswith('sensitivity_') and stock!='5203' else ('log10 sensitivity; unit unconfirmed' if name.startswith('sensitivity_') else 'D')
            curve['observer']='not applicable; not a colorimetric integration'
            if name.startswith('sensitivity_'):curve['layer']={'R':'cyan-forming','G':'magenta-forming','B':'yellow-forming'}[name[-1]]
        entry={'schema':'softloaf.kodak-source-survey/1','stock':stock,'name':source['name'],'source':{**{k:source[k] for k in ('file','sha256','revision')},'author':'Eastman Kodak Company','access':'user-supplied local PDF','printed_identity_used':True},'process':'ECN-2','characteristic_density_status':source['status'],'characteristic_exposure_seconds':source['char_seconds'],'sensitivity_exposure_seconds':source['sens_seconds'],'characteristic_illuminant':{'description':'daylight' if source['temperature_k']==5500 else 'tungsten','temperature_k':source['temperature_k'],'exact_SPD':'not supplied'},'sensitivity':{'ordinate':'log10 sensitivity','linear_unit':'proportional; original unit not specified' if stock=='5203' else 'cm^2/erg','criterion':None if stock=='5203' else '0.2 density above D-min; Status M','energy_response':True if stock!='5203' else 'unconfirmed'},'substitutions':[],'missing_components':['separate_CMY_dye_density_spectra'] if stock=='5206' else [],'curves':curves,'limits':['Source collection only: not a fitted material or a validated color reproduction.','No APD conversion: published characteristic densities retain their original measurement definition.','No extrapolation, negative-density clipping, sensitivity channel normalization or borrowed curves.','Minimum Density is processed film D-min, including support/fog/mask; not a separately measured bare support.','The source density plot states D-mins subtracted; labels and signed dye increments are retained as published.','Digitized sample spacing does not increase the original chart information content.','Raster crossings / merged strokes cannot establish independent values below the original image resolution.'],'rights':'manufacturer PDF, extracted tables and derived material/LUT redistribution review pending; local source reference only'}
        entry['collection_credit']='SoftLoaf Spectral; Yangming Feng and contributors'
        entry['sensitivity']['criterion_original_label']=None if stock=='5203' else 'Density: 0.2>D-min'
        if stock=='5203':entry['limits'].append('This 2025 simplified sheet does not explicitly identify density status, sensitivity energy units/criterion, or curve exposure times. Nominal 5500 K daylight comes from general stock instructions, not an explicit characteristic-chart condition. Do not copy conditions from another revision.')
        if stock=='5219':entry['limits'].append('Characteristic chart prints Densitometry: ECN-2; ECN-2 names processing, not density weighting. Status M is explicit only on the sensitivity chart. Independent confirmation required.')
        anchors={'5203':[[-8,-3.03],[0,-.515],[8,2.006]],'5206':[[-8,-2.915],[0,-.515],[8,1.885]],'5207':[[-8,-3.7],[0,-1.3],[8,1.1]],'5213':[[-8,-3.684],[0,-1.284],[8,1.116]]}
        entry['characteristic_axis']={'primary':'camera_stops','relative_log_exposure':'camera_stops * log10(2); relative origin, not ISO calibration','printed_log_lux_seconds_anchors':anchors.get(stock),'printed_axis_warning':'Printed absolute axis and physical stops may differ; both retained separately. No inferred exposure anchor is used.'}
        if stock=='5219':entry['characteristic_axis']['printed_log_lux_seconds_pixel_anchors']=[[85,-4],[198,-3],[306,-2],[418,-1],[542,0],[652,1]]
        folder=output/stock;folder.mkdir(parents=True,exist_ok=True)
        (folder/'source-curves.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        wavelengths=np.arange(250.,751.,2.)
        log_values=[interpolate(curves['sensitivity_'+c],wavelengths) for c in 'RGB']
        csv(folder/'sensitivity_log10.csv',wavelengths,log_values,'wavelength_nm,R,G,B')
        csv(folder/'sensitivity_linear.csv',wavelengths,[10**v for v in log_values],'wavelength_nm,R,G,B')
        low=max(curves['characteristic_'+c]['points'][0][0] for c in 'RGB');high=min(curves['characteristic_'+c]['points'][-1][0] for c in 'RGB')
        stops=np.linspace(low,high,321);densities=[interpolate(curves['characteristic_'+c],stops) for c in 'RGB']
        csv(folder/'characteristic.csv',stops*np.log10(2),densities,'relative_log_exposure,R,G,B')
        absolute=np.interp(stops,*np.array(anchors[stock]).T) if stock in anchors else np.interp(85+(stops+8)/16*567,*np.array(entry['characteristic_axis']['printed_log_lux_seconds_pixel_anchors']).T)
        csv(folder/'characteristic_axes.csv',stops,[stops*np.log10(2),absolute],'camera_stops,relative_log_exposure,printed_log_lux_seconds')
        names=([f'dye_{c}' for c in 'CMY'] if stock!='5206' else [])+['minimum_density','midscale_neutral']
        axis=np.arange(400.,801.,2.)
        csv(folder/'density_spectra.csv',axis,[interpolate(curves[n],axis) for n in names],'wavelength_nm,'+','.join(names))
        result[stock]=entry
    (output/'collection.json').write_text(json.dumps({'schema':'softloaf.kodak-source-survey-index/1','excluded_stocks':EXCLUSIONS,'stocks':[{k:e[k] for k in ('stock','name','source','missing_components','characteristic_density_status')} for e in result.values()]},ensure_ascii=False,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,default=ROOT/'local/reference-assets/kodak-motion-user-2026')
    parser.add_argument('--output',type=Path,default=ROOT/'local/materials/kodak-motion-survey-v1')
    args=parser.parse_args();stocks=harvest_collection(args.sources,args.output)
    print('Collected '+', '.join(stocks)+'; source tables only, no runtime materials changed.')


if __name__=='__main__':main()
