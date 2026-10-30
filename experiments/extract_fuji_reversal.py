"""Digitize hash-pinned original Fujifilm curves, with source-ink review.

No E100 or upstream model curves. Guides locate existing raster ink only.
"""
from pathlib import Path
import pymupdf,numpy as np
from scipy.ndimage import binary_opening
ROOT=Path(__file__).resolve().parents[1]
def mask(doc,xref):
 p=pymupdf.Pixmap(doc,xref);return np.frombuffer(p.samples,dtype=np.uint8).reshape(p.height,p.width)>128

def characteristic_centerline(a,cols,guide_y,xp,xv,yp,yv):
 """Global source-ink path; continuity avoids jumps into neighboring dashes.

 Missing grid/dash pixels are omitted from output, never invented samples.
 """
 from scipy.ndimage import distance_transform_edt
 distance=distance_transform_edt(~a);offsets=np.arange(-65,66);back=[];previous=None
 for col,center in zip(cols,np.rint(guide_y).astype(int)):
  rows=np.clip(center+offsets,0,a.shape[0]-1)
  emission=np.minimum(distance[rows,col],12)**2+.001*offsets**2
  if previous is None:cost=emission;back.append(np.zeros(len(offsets),dtype=np.int16));previous=cost;continue
  choices=[]
  for step in range(-7,8):
   shifted=np.full(len(offsets),np.inf)
   if step<0:shifted[:step]=previous[-step:]
   elif step>0:shifted[step:]=previous[:-step]
   else:shifted=previous.copy()
   choices.append(shifted+.7*step*step)
  choices=np.array(choices);which=np.argmin(choices,axis=0);cost=emission+choices[which,np.arange(len(offsets))]
  back.append(np.arange(len(offsets))-(which-7));previous=cost
 path=np.empty(len(cols),dtype=int);path[-1]=np.argmin(previous)
 for j in range(len(cols)-1,0,-1):path[j-1]=back[j][path[j]]
 result=[]
 for col,center,ix in zip(cols,np.rint(guide_y).astype(int),path):
  predicted=center+offsets[ix];ys=np.flatnonzero(a[:,col]);ys=ys[np.abs(ys-predicted)<8]
  groups=np.split(ys,np.flatnonzero(np.diff(ys)>2)+1);centers=[np.median(g) for g in groups if len(g)>=2]
  if centers:
   y=min(centers,key=lambda q:abs(q-predicted));result.append([np.interp(col,xp,xv),np.interp(y,yp,yv)])
 return np.array(result)

def trace(a,xp,xv,yp,yv,guide,radius,max_run=None):
 # Guides locate source ink only; values always read from actual mask pixels.
 a=a.copy()
 if radius>50:a=binary_opening(a,structure=np.ones((7,3)))
 for x in xp:a[:,np.abs(np.arange(a.shape[1])-x)<5]=False
 if radius<=50:
  for y in yp:a[np.abs(np.arange(a.shape[0])-y)<5]=False
 g=np.array(guide);cols=np.arange(int(np.interp(g[0,0],xv,xp)),int(np.interp(g[-1,0],xv,xp))+1)
 if radius<=50:
  guides=np.interp(np.interp(cols,xp,xv),g[:,0],g[:,1]);gy=np.interp(guides,yv[::-1],yp[::-1])
  return characteristic_centerline(a,cols,gy,xp,xv,yp,yv)
 out=[];history=[]
 for col in cols:
  x=np.interp(col,xp,xv);target=float(np.interp(x,g[:,0],g[:,1]));y0=float(np.interp(target,yv[::-1],yp[::-1]));ys=np.flatnonzero(a[:,col]);ys=ys[np.abs(ys-y0)<radius]
  if len(ys):
   groups=np.split(ys,np.flatnonzero(np.diff(ys)>2)+1);centers=[float(np.median(v)) for v in groups if len(v)>=2 and (max_run is None or len(v)<=max_run)]
   if centers:
    y=min(centers,key=lambda q:abs(q-y0))
    history.append([col,y]);out.append([x,float(np.interp(y,yp,yv))])
 return np.array(out)

def velvia():
 d=pymupdf.open(ROOT/'local/reference-assets/film-stock-survey/fuji_velvia50.pdf')
 cs=mask(d,68);ss=mask(d,69);ds=mask(d,67)
 charaxes=([226,408,593,774,961,1143,1328,1513,1695,1879],[-3,-2.5,-2,-1.5,-1,-.5,0,.5,1,1.5],[38,221,404,587,772,956,1142,1327,1512],[4,3.5,3,2.5,2,1.5,1,.5,0])
 # Individual printed line styles: R solid, G dash-dot, B short dash.
 xs=[-2.84,-2.6,-2.3,-2.1,-2,-1.9,-1.8,-1.7,-1.6,-1.5,-1.4,-1.3,-1.2,-1.1,-1,-.9,-.8,-.7,-.6,-.5,-.4,-.3,-.2,-.1,0,.2,.4,.6,.8,1.1]
 r=[3.34,3.335,3.324,3.309,3.294,3.268,3.219,3.15,2.996,2.77,2.50,2.272,2.02,1.78,1.57,1.38,1.22,1.07,.92,.79,.66,.54,.44,.36,.295,.21,.165,.165,.17,.18]
 g=[3.8,3.79,3.757,3.695,3.62,3.54,3.421,3.246,2.97,2.73,2.47,2.165,1.967,1.73,1.51,1.35,1.19,1.04,.9,.76,.64,.53,.43,.35,.28,.2,.155,.15,.15,.16]
 b=[3.7,3.69,3.654,3.592,3.52,3.44,3.324,3.19,2.908,2.68,2.43,2.108,1.871,1.68,1.45,1.31,1.15,1.0,.86,.73,.61,.50,.40,.32,.26,.19,.15,.14,.14,.15]
 char={c:trace(cs,*charaxes,list(zip(xs,v)),50) for c,v in zip('RGB',[r,g,b])}
 saxes=([195,285,768,1255,1733,1818],[381.3,400,500,600,700,717.8],[47,525,1007,1487],[2,1,0,-1])
 sensguides={'B':[(387,-.28),(395,.25),(405,.55),(420,.57),(435,.51),(450,.56),(455,.59),(460,.53),(470,.27),(480,.02),(487,-.26),(493,-.62)],'G':[(483,-.73),(495,-.43),(510,-.1),(525,.23),(540,.55),(547,.53),(555,.44),(563,.44),(575,.46),(580,.35),(583,-.03),(587,-.44),(590,-.71)],'R':[(578,-.8),(585,-.43),(592,-.23),(605,-.16),(620,-.03),(628,.18),(637,.47),(645,.56),(650,.5),(655,.52),(660,.34),(665,.06),(670,-.10),(680,-.32),(691,-.62)]}
 sens={c:trace(ss,*saxes,g,100) for c,g in sensguides.items()}
 daxes=([191,287,766,1248,1729,1822],[380,400,500,600,700,719.3],[19,259,740,1219],[1.25,1,.5,0])
 dyeguides={'M':[(383,.32),(390,.14),(400,.11),(412,.12),(430,.18),(445,.195),(460,.19),(475,.24),(490,.4),(505,.65),(520,.88),(535,.99),(545,1),(555,.98),(565,.90),(575,.78),(585,.62),(595,.44),(605,.30),(615,.205),(630,.12),(650,.06),(680,.015),(715,.01)],'Y':[(383,.54),(390,.45),(400,.51),(415,.76),(430,.96),(445,1),(455,.96),(465,.88),(475,.74),(485,.56),(495,.39),(505,.25),(515,.17),(530,.10),(550,.05),(580,.025),(600,.005)],'C':[(383,.35),(390,.24),(405,.16),(430,.1),(460,.055),(480,.05),(500,.065),(520,.10),(540,.19),(560,.29),(580,.44),(600,.62),(620,.81),(640,.96),(660,1),(680,.96),(700,.8),(719,.61)]}
 dyes={c:trace(ds,*daxes,g,100,max_run=100) for c,g in dyeguides.items()}
 return d,{'characteristic':char,'sensitivity':sens,'dyes':dyes},{'characteristic':(68,charaxes),'sensitivity':(69,saxes),'dyes':(67,daxes)}



from experiments.extract_5207_materials import runs

def provia():
 d=pymupdf.open(ROOT/'local/reference-assets/film-stock-survey/fuji_provia100f.pdf');page=d[-1]
 # Masks are separated by PDF drawing color: Im59 G, Im60 R, Im61 B.
 # Only the red curve is drawn after green/blue merge into it in the source.
 # Graph axes calibrated on Im58 (the grid), converted via image transforms.
 info={im['xref']:im for im in page.get_image_info(xrefs=True)}
 def to_page(v,ix):
  im=info[ix];x0,y0,x1,y1=im['bbox'];return np.column_stack([x0+v[:,0]*(x1-x0)/im['width'],y0+v[:,1]*(y1-y0)/im['height']])
 def img_trace(ix,xmin,xmax,ymin,ymax):
  a=mask(d,ix);points=[]
  for x in range(xmin,xmax+1):
   y=np.flatnonzero(a[ymin:ymax,x])+ymin
   if len(y):points.append([x,float(np.median(np.split(y,np.flatnonzero(np.diff(y)>2)+1)[0]))])
  return np.array(points)
 grid=info[50];bx=grid['bbox'];px=lambda v:bx[0]+np.array(v)*(bx[2]-bx[0])/grid['width'];py=lambda v:bx[1]+np.array(v)*(bx[3]-bx[1])/grid['height']
 ca=(px([127,220,313,406,500,592,687,781,874,967]),[-3.5,-3,-2.5,-2,-1.5,-1,-.5,0,.5,1],py([37,131,223,317,409,503,595,689,781]),[4,3.5,3,2.5,2,1.5,1,.5,0])
 def data(v,axes):return np.column_stack([np.interp(v[:,0],axes[0],axes[1]),np.interp(v[:,1],axes[2],axes[3])])
 red=to_page(img_trace(52,148,937,100,800),52)
 char={'R':data(red,ca)}
 for c,ix,xmax,ymax in [('G',51,501,500),('B',53,378,450)]:
  own=to_page(img_trace(ix,145,xmax,100,ymax),ix)
  # Exact same-stock shared source line after the separate stencil ends.
  merged=np.vstack([own,red[red[:,0]>own[-1,0]]]);char[c]=data(merged,ca)
 sa=([337.7482,349.63,409.039,468.45,527.861,539.7432],[380,400,500,600,700,720],[172,201.744,261.132,320.52,348.915],[(261.132-172)/59.388,1,0,-1,(261.132-348.915)/59.388])
 sens={c:data(runs(page,[ix])[0],sa) for c,ix in [('R',23),('G',24),('B',25)]}
 # Im63 grid locators: lambda400=163,500=414,600=656,700=903; D1=127,D.5=381,D0=628
 def dye_data(v,ix):
  im=info[ix];grid=info[55];v=to_page(v,ix);bbox=grid['bbox'];xx=(v[:,0]-bbox[0])*grid['width']/(bbox[2]-bbox[0]);yy=(v[:,1]-bbox[1])*grid['height']/(bbox[3]-bbox[1]);return np.column_stack([np.interp(xx,[112.8,163,414,656,903,952.4],[380,400,500,600,700,720]),np.interp(yy,[127,381,628],[1,.5,0])])
 dyes={c:dye_data(img_trace(ix,136,948,100,660),ix) for c,ix in [('Y',56),('M',57),('C',58)]}
 return d,{'characteristic':char,'sensitivity':sens,'dyes':dyes},(ca,sa)

SOURCES={
 'velvia50':{'file':'fuji_velvia50.pdf','sha256':'bebfb4305fd3edc5e3505a9a0f4a0a1078da1db7672aacb4aa1bac1de3d64cfd','name':'Fujifilm Velvia 50','document':'AF3-0221E2 (KAMIQ-07.3-FP), p8','url':'https://asset.fujifilm.com/www/us/files/2020-03/742f83fe2440fce58fbcc08f7370a7e6/AF3-0221E2Velvia50PIB.pdf','exposure':'Daylight; exact SPD not supplied','method':'1-bit original raster masks 68/69/67; calibrated grid; source-ink centerlines; published R solid, G dash-dot, B short-dash; unresolved/overlapping strokes limited by chart resolution','uncertainty_D':.025},
 'provia100f':{'file':'fuji_provia100f.pdf','sha256':'e28d54e76e8fcdf44c8ffacc930b5b8f2ea54a7cdaeedfcc91790e68eb599de8','name':'Fujifilm Provia 100F','document':'AF3-036E (EIGI-00.10-HB), p6','url':'https://asset.fujifilm.com/www/in/files/2020-07/0b154ed25442c231feccf22032620306/films_provia-100f_datasheet_01.pdf','exposure':'Daylight, 1/50 second; exact SPD not supplied','method':'Original RGB characteristic stencil masks 51/52/53 and CMY dye masks 56/57/58; published common R segment after G/B merge; native sensitivity vector paths 23/24/25, 32 Bezier subdivisions','uncertainty_D':.015},
}

def clean(points):
    a=np.asarray(points);a=a[np.argsort(a[:,0],kind='stable')]
    x,inv=np.unique(a[:,0],return_inverse=True);y=np.bincount(inv,weights=a[:,1])/np.bincount(inv)
    return np.column_stack([x,y])


def reliable_characteristic(points):
    # Partial dash caps / grid intersections can be ink but not the curve's
    # center. Compare against a local quadratic source contour, without any
    # film-fit information. Keep rejected candidates separately for inspection.
    a=clean(points);keep=np.ones(len(a),dtype=bool)
    for i,(x,y) in enumerate(a):
        neighbors=(np.abs(a[:,0]-x)<.045)&(np.arange(len(a))!=i)
        if neighbors.sum()<8:continue
        local=a[neighbors];prediction=np.polyval(np.polyfit(local[:,0]-x,local[:,1],2),0)
        if abs(y-prediction)>.01:keep[i]=False
    return a[keep],a[~keep]


def build(stock,traces,output):
    import hashlib,json
    from spectral_lut.reference import decreasing_projection
    source=SOURCES[stock];grid=np.arange(400,721,10,dtype=float)
    original={k:{c:clean(v) for c,v in values.items()} for k,values in traces.items()}
    candidates={c:a.copy() for c,a in original['characteristic'].items()};rejected={}
    for c,a in candidates.items():original['characteristic'][c],rejected[c]=reliable_characteristic(a)
    # Five-pixel grid removal and printed dash gaps are interpolated, never a
    # missing tens-of-nm spectral segment. Characteristic end holding is explicit.
    for role,channels in original.items():
        for c,a in channels.items():
            limit=.09 if role=='characteristic' else 6
            if np.max(np.diff(a[:,0]))>limit:raise ValueError(f'{stock} {role} {c}: unresolved source-ink gap')
    low=min(a[0,0] for a in original['characteristic'].values());high=max(a[-1,0] for a in original['characteristic'].values())
    axis=np.linspace(low,high,256);char={};sens={};dyes={}
    for c,a in original['characteristic'].items():char[c]=decreasing_projection(np.interp(axis,*a.T)).tolist()
    for c,a in original['sensitivity'].items():
        x,y=a.T;v=np.interp(grid,x,y)
        # Source outward secants cover at least ~2 nm, avoiding single-pixel noise.
        j=min(np.searchsorted(x,x[0]+2),len(x)-1);k=max(np.searchsorted(x,x[-1]-2),0)
        left=max((y[j]-y[0])/(x[j]-x[0]),.02);right=min((y[-1]-y[k])/(x[-1]-x[k]),-.02)
        v=np.where(grid<x[0],y[0]+(grid-x[0])*left,v);v=np.where(grid>x[-1],y[-1]+(grid-x[-1])*right,v)
        sens[c]=(10**np.maximum(v,-10)).tolist()
    dye_grid=np.arange(400,721,2,dtype=float)
    for c,a in original['dyes'].items():dyes[c]=np.maximum(np.interp(dye_grid,*a.T),0).tolist()
    calibration={'quantity':'relative_energy_sensitivity','unit':'relative','wavelengths_nm':grid.tolist(),'channels':sens,'temperature_k':5500,'reflectance':.18}
    credit={k:source[k] for k in ('url','sha256','document')}
    material={'schema':'softloaf.material/1','name':source['name'],'source':'Fujifilm '+source['document']+'; independently digitized original manufacturer curves',
        'sensitivity':{k:v for k,v in calibration.items() if k not in ('temperature_k','reflectance')},
        'characteristic':{'quantity':'status_a_density','unit':'D','log_exposure':axis.tolist(),'channels':char},
        'dyes':{'quantity':'spectral_density','unit':'D','wavelengths_nm':dye_grid.tolist(),'channels':dyes},
        'provenance':{'stock_id':stock,'process':'E-6','density_metric':'Status A','reference_temperature_k':5500,'experimental':True,
            'summary':'原厂感光／Status A／染料曲线；E-6；D55 相对标定，非实拍校准。',
            'source_pdf_sha256':source['sha256'],'manufacturer_url':source['url'],'manufacturer_document':source['document'],
            'manufacturer_conditions':{'exposure':source['exposure'],'process':'E-6 / CR-56','density':'Status A; Fuji FAD-30S' if stock=='provia100f' else 'Status A','sensitivity_density':'1.0 D above Dmin','sensitivity_quantity':'reciprocal exposure J/cm2; relative response used'},
            'extraction':{'method':source['method'],'estimated_chart_reading_uncertainty_D':source['uncertainty_D'],'uncertainty_scope':'declared chart-reading allowance, not instrument measurement or calibrated statistical confidence','characteristic_center_filter':'local quadratic source contour within ±.045 logH; omit partial-cap / grid points displaced >.01 D; candidates and rejected points retained','rejected_source_ink_count':{c:len(a) for c,a in rejected.items()}},
            'modeling':{'normalization':'per-stock frozen 18% D55 relative exposure, not ISO speed; fixed D50 Y=.1 viewing anchor',
                'sensitivity_tails':'unmeasured log-linear outward secants, minimum .02/nm, log floor -10',
                'dye_tails':'same-stock published endpoint hold beyond plotted coverage; not measured',
                'characteristic':'256 samples, monotone projection, source endpoint hold; raw traces retained; shared/merged source strokes do not establish independent layer measurements'},
            'exposure_reference':calibration,'sources':{'manufacturer':credit},'rights':'Manufacturer and derived material/LUT redistribution pending review'}}
    material['provenance']['fit_reference_components']={k:hashlib.sha256(json.dumps(material[k],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() for k in ('characteristic','dyes')}
    def write(name,value):
        path=output/name;path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');return path,hashlib.sha256(path.read_bytes()).hexdigest()
    write(stock+'-characteristic-ink-candidates.json',{'candidates':{c:a.tolist() for c,a in candidates.items()},'rejected':{c:a.tolist() for c,a in rejected.items()},'reason':'partial dash caps / grid ink inconsistent with local quadratic source contour by more than .01 D; no film-model information used'})
    write(stock+'-source-points.json',{k:{c:a.tolist() for c,a in cs.items()} for k,cs in original.items()})
    path,mhash=write(stock+'.json',material)
    plot={'channels':{c:{'wavelengths_nm':a[:,0].tolist(),'values':(10**a[:,1]).tolist()} for c,a in original['sensitivity'].items()},'calculation_step_nm':10,'source':'Fujifilm '+source['document']+'; digitized original chart samples; no plotted extrapolation','provenance_sha256':source['sha256'],'sampling_kind':'manufacturer_chart_digitization' if stock=='velvia50' else 'manufacturer_vector'}
    plot_path,phash=write(stock+'-plot.json',plot)
    return {'id':stock,'name':source['name'],'process':'E-6','density_metric':'Status A','source':credit,'file':path.name,'sha256':mhash,'plot_file':plot_path.name,'plot_sha256':phash}


def main():
    import hashlib,json
    output=ROOT/'local/materials/reversal-presets-v1';output.mkdir(parents=True,exist_ok=True)
    manifest_path=ROOT/'data/reversal-presets-manifest.json';catalog=json.loads(manifest_path.read_text())
    for stock,extract in [('velvia50',velvia),('provia100f',provia)]:
        source=SOURCES[stock];pdf=ROOT/'local/reference-assets/film-stock-survey'/source['file']
        if hashlib.sha256(pdf.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Manufacturer PDF identity changed')
        doc,traces,axes=extract();entry=build(stock,traces,output)
        catalog['materials']=[e for e in catalog['materials'] if e['id']!=stock]+[entry]
        doc.close();print('Built',stock,'from its own manufacturer curves')
    manifest_path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
