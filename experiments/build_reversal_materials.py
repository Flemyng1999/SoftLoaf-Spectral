"""Build local reversal material from hash-identified original manufacturer vectors.

Data and plots remain local pending redistribution review. E-6 only.
"""
from pathlib import Path
import json,numpy as np,pymupdf
from experiments.extract_5207_materials import runs
from spectral_lut.reference import decreasing_projection
root=Path(__file__).resolve().parents[1]
pdf=root/'local/reference-assets/film-stock-survey/fuji_velvia100.pdf'
import hashlib
if hashlib.sha256(pdf.read_bytes()).hexdigest()!='4c57a27b978311ca2ef819f2bf2d74c757639d27f9f0bd94e5f49c4b1c3d5902':raise ValueError('Velvia 100 manufacturer source changed')
page=pymupdf.open(pdf)[7]
def remap(a,xp,xv,yp,yv):return np.column_stack([np.interp(a[:,0],xp,xv),np.interp(a[:,1],yp,yv)])
original={"characteristic":{},"sensitivity":{},"dyes":{}}
char={};axis=np.linspace(-3.4,1.01,256)
for c,ix in zip('RGB',[143,142,144]):
 a=runs(page,[ix])[0];a=remap(a,[86.036,107.572,129.463,151.632,172.944,194.832,216.433,238.319,259.919,281.796,282.3],[-3.5,-3,-2.5,-2,-1.5,-1,-.5,0,.5,1,1.01],[174.218,195.659,217.74,239.574,261.127,282.747,304.588,326.293,347.493],[4,3.5,3,2.5,2,1.5,1,.5,0]);original['characteristic'][c]=a.tolist();char[c]=decreasing_projection(np.interp(axis,a[:,0],a[:,1])).tolist()
grid=np.arange(400,721,10);sens={}
for c,a in zip('BGR',runs(page,[292])):
 a=remap(a,[335.475,347.05,405.683,463.756,521.804,533.822],[380,400,500,600,700,720],[174.937,205.127,262.762,320.395,345.051],[1.525,1,0,-1,-1.428]);original['sensitivity'][c]=a.tolist();x,y=a.T;v=np.interp(grid,x,y)
 # Extend only in log response, with the outward source tangent; retain floor.
 left=max((y[8]-y[0])/(x[8]-x[0]),.02);right=min((y[-1]-y[-9])/(x[-1]-x[-9]),-.02)
 v=np.where(grid<x[0],y[0]+(grid-x[0])*left,v);v=np.where(grid>x[-1],y[-1]+(grid-x[-1])*right,v)
 sens[c]=(10**np.maximum(v,-10)).tolist()
dyes={}
for a in runs(page,[22]):
 a=remap(a,[333.231,344.97,404.43,463.323,522.19,534.377],[380,400,500,600,700,720],[449.381,477.733,537.275,596.814],[1.24,1,.5,0]);c='Y' if a[np.argmax(a[:,1]),0]<500 else 'M' if a[np.argmax(a[:,1]),0]<600 else 'C';original['dyes'][c]=a.tolist();dyes[c]=np.maximum(np.interp(grid,a[:,0],a[:,1]),0).tolist()
material={'schema':'softloaf.material/1','name':'Fujifilm Velvia 100','source':'Fujifilm AF3-202E, February 2005, p8; original Status A curves, independent vector extraction',
'sensitivity':{'quantity':'relative_energy_sensitivity','unit':'relative','wavelengths_nm':grid.tolist(),'channels':sens},
'characteristic':{'quantity':'status_a_density','unit':'D','log_exposure':axis.tolist(),'channels':char},
'dyes':{'quantity':'spectral_density','unit':'D','wavelengths_nm':grid.tolist(),'channels':dyes},
'provenance':{'stock_id':'velvia100','process':'E-6','density_metric':'Status A','reference_temperature_k':5500,'experimental':True,'summary':'Original manufacturer curve extraction; relative D55 neutral calibration; declared unmeasured curve-tail extrapolation; not a full-color measurement'}}
material['provenance'].update(
    source_pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
    manufacturer_url='https://asset.fujifilm.com/www/in/files/2020-07/053a4dd52b58d6f75cd3ad35dd03998c/films_velvia-100_datasheet_01.pdf',
    manufacturer_document='AF3-202E, February 2005, p8',
    manufacturer_conditions={'exposure':'Daylight; exact SPD not supplied','process':'E-6 / CR-56','density':'Status A','sensitivity_density':'1.0 D above Dmin','sensitivity_quantity':'reciprocal energy exposure J/cm2; relative response used'},
    modeling={'normalization':'per-stock frozen 18% flat reflector under model D55; not ISO speed calibration',
              'sensitivity_tails':'log-linear outward tangent, minimum slope magnitude .02 per nm and floor -10 log response; unmeasured beyond each plotted curve',
              'dye_tails':'endpoint hold beyond published plotted vertices; tiny negative digitization undershoot clamped to zero',
              'characteristic':'256 log-exposure points; monotone projection; actual original Status A, no processed upstream density curves'},
    exposure_reference={'quantity':'relative_energy_sensitivity','unit':'relative','wavelengths_nm':grid.tolist(),'channels':sens,'temperature_k':5500,'reflectance':.18},
    extraction={'page':8,'characteristic_paths_RGB':[143,142,144],'sensitivity_path_BGR':292,'dye_path':22,'bezier_subdivisions':32,'axes':'Original graph grid intersections; calibrated piecewise in PDF coordinates; axis constants retained in extractor'},
    sources={'manufacturer':{'url':'https://asset.fujifilm.com/www/in/files/2020-07/053a4dd52b58d6f75cd3ad35dd03998c/films_velvia-100_datasheet_01.pdf','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'document':'AF3-202E, February 2005, p8'}},
    rights='Manufacturer original and derived material/LUT redistribution pending review')
material['provenance']['summary']='原厂 Status A／感光／染料曲线；E-6；D55 相对曝光标定；图外尾部为假设，非实拍校准。'
out=root/'local/materials/reversal-presets-v1';out.mkdir(parents=True,exist_ok=True)
(out/'velvia100-source-points.json').write_text(json.dumps(original)+'\n')
path=out/'velvia100.json';path.write_text(json.dumps(material,ensure_ascii=False,indent=2)+'\n')
# Original sensitivity vertices belong only to the unchanged built-in curve.
channels={}
for c,a in zip('BGR',runs(page,[292])):
    a=remap(a,[335.475,347.05,405.683,463.756,521.804,533.822],[380,400,500,600,700,720],[174.937,205.127,262.762,320.395,345.051],[1.525,1,0,-1,-1.428])
    channels[c]={'wavelengths_nm':a[:,0].tolist(),'values':(10**a[:,1]).tolist()}
plot={'channels':channels,'calculation_step_nm':10,'source':'Fujifilm AF3-202E, p8; original plotted sensitivity, no extrapolation in this plot','provenance_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
plot_path=out/'velvia100-plot.json';plot_path.write_text(json.dumps(plot,ensure_ascii=False)+'\n')
manifest={'schema':'softloaf.reversal-presets/1','recorded_on':'2026-10-28','materials':[{'id':'velvia100','name':'Fujifilm Velvia 100','process':'E-6','density_metric':'Status A','source':material['provenance']['sources']['manufacturer'],'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'plot_file':plot_path.name,'plot_sha256':hashlib.sha256(plot_path.read_bytes()).hexdigest()}]}
manifest_path=root/'data/reversal-presets-manifest.json'
if manifest_path.exists():manifest['materials']+= [e for e in json.loads(manifest_path.read_text())['materials'] if e['id']!='velvia100']
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print('Built Velvia 100 from manufacturer vectors, no E100 or processed upstream curve substitution')
