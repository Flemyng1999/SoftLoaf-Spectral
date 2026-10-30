"""Measured transmission targets and projective sample geometry; analysis pass."""
import io
from pathlib import Path
import numpy as np
import tifffile
from .flat_assets import FlatCorrection

LABELS=[f'{r}{c}' for r in 'ABCD' for c in range(1,7)]
# Public colour ColorChecker Classic sample keys; names are input identities.
PATCH_KEYS=('dark skin', 'light skin', 'blue sky', 'foliage', 'blue flower', 'bluish green', 'orange', 'purplish blue', 'moderate red', 'purple', 'yellow green', 'orange yellow', 'blue', 'green', 'red', 'yellow', 'magenta', 'cyan', 'white 9.5 (.05 D)', 'neutral 8 (.23 D)', 'neutral 6.5 (.44 D)', 'neutral 5 (.70 D)', 'neutral 3.5 (1.05 D)', 'black 2 (1.5 D)')


PATCH_IDS=tuple(f'CC{i:02d}' for i in range(1,25))


def target_guide(target):
    """Orientation aid only. Numbered files use the familiar ColorChecker layout.
    Legacy files retain measured transmittance under D65, CIE 1931 2°,
    relative XYZ (clear target Y=1) to clipped encoded sRGB. Never used in fitting.
    Integrate at 1 nm over the target/observer shared coverage; no invented tails.
    """
    import colour
    if target.get('numbered'):
        # Familiar chart colours label IDs only. Fits always use target's own
        # measured transmission, never these reflective-chart orientation values.
        card=colour.CCS_COLOURCHECKERS['BabelColor Average']
        encoded=np.clip(colour.XYZ_to_sRGB(colour.xyY_to_XYZ(np.array(list(card.data.values()))),
            illuminant=card.illuminant,chromatic_adaptation_transform='Bradford'),0,1)
        return {'target':target['target'],'colors':np.rint(encoded*255).astype(int).tolist(),
            'observer':'CIE 1931 2°','illuminant':'D65','encoding':'sRGB','purpose':'orientation-only',
            'color_source':'BabelColor Average D50 xyY; Bradford D50 to D65; guide only',
            'numbered':True,'keyed':target.get('keyed',False),'patch_ids':list(PATCH_IDS) if target.get('keyed') else list(range(1,25)),'patch_keys':list(PATCH_IDS),'patch_names':list(card.data)}
    from spectral_lut.reference import quadrature_widths
    source=target['wavelengths'];cmf=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer']
    light=colour.SDS_ILLUMINANTS['D65']
    wave=np.arange(np.ceil(max(source[0],cmf.wavelengths[0],light.wavelengths[0])),
        np.floor(min(source[-1],cmf.wavelengths[-1],light.wavelengths[-1]))+1)
    observer=np.column_stack([np.interp(wave,cmf.wavelengths,cmf.values[:,c]) for c in range(3)])
    kernel=observer*(np.interp(wave,light.wavelengths,light.values)*quadrature_widths(wave))[:,None]
    kernel/=kernel[:,1].sum()
    transmission=np.array([np.interp(wave,source,t) for t in target['transmission']])
    encoded=np.clip(colour.XYZ_to_sRGB(transmission@kernel),0,1)
    return {'target':target['target'],'colors':np.rint(encoded*255).astype(int).tolist(),
        'observer':'CIE 1931 2°','illuminant':'D65','encoding':'sRGB','purpose':'orientation-only','numbered':target.get('numbered',False),'patch_ids':list(range(1,25)) if target.get('numbered') else None}


def load_target(path):
    text=Path(path).read_text(encoding='utf-8-sig');lines=text.splitlines()
    if not lines or lines[0].strip() not in ('# softloaf.transmission-target/1','# softloaf.transmission-target/2','# softloaf.transmission-target/3'):
        raise ValueError('需要实测透射光谱 CSV，首行为 # softloaf.transmission-target/3。')
    keyed=lines[0].strip().endswith('/3');numbered=keyed or lines[0].strip().endswith('/2')
    metadata=dict(line[2:].split('=',1) for line in lines if line.startswith('# ') and '=' in line)
    rows=[line for line in lines if line.strip() and not line.startswith('#')]
    header=[cell.strip() for cell in rows[0].split(',')] if rows else []
    labels=list(PATCH_IDS) if keyed else list(map(str,range(1,25))) if numbered else LABELS
    source_labels=list(PATCH_KEYS) if keyed and set(header[1:])==set(PATCH_KEYS) else labels
    id_scheme='colour' if keyed and source_labels==list(PATCH_KEYS) else 'CC' if keyed else 'legacy'
    if numbered:
        if len(header)!=25 or header[0]!='wavelength_nm' or set(header[1:])!=set(source_labels):
            if keyed:
                supplied=header[1:];missing=[k for k in source_labels if k not in supplied]
                unknown=list(dict.fromkeys(k for k in supplied if k not in source_labels))
                repeated=list(dict.fromkeys(k for k in supplied if supplied.count(k)>1))
                details=[name+' '+', '.join(str(k)[:60] for k in values[:3]) for name,values in
                    [('缺少',missing),('未知',unknown),('重复',repeated)] if values]
                raise ValueError('色块 ID 不匹配（CC01–CC24）：'+('；'.join(details) or '首列必须是 wavelength_nm')+'。请使用 CSV 模板。')
            raise ValueError('旧透射 CSV 表头需包含 wavelength_nm 和不重复的色块编号 1–24。')
        order=[header[1:].index(label) for label in source_labels]
    else:
        if header!=['wavelength_nm',*LABELS]:raise ValueError('旧透射 CSV 表头应为 wavelength_nm,A1,…,D6。新资料请用 CC01–CC24。')
        order=list(range(24))
    try:data=np.loadtxt(io.StringIO('\n'.join(rows[1:])),delimiter=',',ndmin=2)
    except ValueError:raise ValueError('透射 CSV 存在空值或非数值。') from None
    if (data.shape[1]!=25 or not 31<=len(data)<=8192 or not np.isfinite(data).all()
            or np.any(np.diff(data[:,0])<=0) or data[0,0]>400 or data[-1,0]<700
            or data[0,0]<300 or data[-1,0]>1100 or np.min(data[:,1:])<0 or np.max(data[:,1:])>1):
        raise ValueError('需覆盖400–700 nm，波长递增；透射率为0–1比例，不能使用百分数或反射卡。')
    return {'target':metadata.get('target',Path(path).stem)[:120],
        'wavelengths':data[:,0],'transmission':data[:,1:].T[order],'labels':labels,'numbered':numbered,'keyed':keyed,'id_scheme':id_scheme}


def patch_centres(corners):
    corners=np.asarray(corners,float)
    if corners.shape!=(4,2) or not np.isfinite(corners).all() or np.any(corners<0) or np.any(corners>1):
        raise ValueError('色卡角点无效，请重新定位。')
    edges=np.roll(corners,-1,axis=0)-corners
    cross=edges[:,0]*np.roll(edges,-1,axis=0)[:,1]-edges[:,1]*np.roll(edges,-1,axis=0)[:,0]
    if not (np.all(cross>1e-5) or np.all(cross<-1e-5)):
        raise ValueError('色卡角点交叉或过近，请重新定位。')
    matrix=[];target=[]
    for (u,v),(x,y) in zip([(0,0),(1,0),(1,1),(0,1)],corners):
        matrix.extend([[u,v,1,0,0,0,-x*u,-x*v],[0,0,0,u,v,1,-y*u,-y*v]]);target.extend([x,y])
    h=np.r_[np.linalg.solve(np.array(matrix),target),1].reshape(3,3)
    points=np.array([[c/5,r/3,1] for r in range(4) for c in range(6)])@h.T
    points=points[:,:2]/points[:,2,None]
    if not np.isfinite(points).all() or np.any(points<0) or np.any(points>1):raise ValueError('色卡投影超出画面。')
    return points


def equivalent_layout(source,target,corners):
    """Transfer a saved grid only across an exact, unambiguous row permutation.

    Neither card names nor approximate display colours establish equivalence.
    The entire remapped grid must still be represented by its corner homography.
    """
    if not np.array_equal(source['wavelengths'],target['wavelengths']):return None
    a=source['transmission'];b=target['transmission']
    equal=np.all(a[:,None,:]==b[None,:,:],axis=-1)
    if not np.all(equal.sum(0)==1) or not np.all(equal.sum(1)==1):return None
    order=np.argmax(equal,axis=0)
    if corners is None:return order.tolist()
    points=patch_centres(corners)[order];outer=points[[0,5,23,18]]
    try:valid=np.allclose(patch_centres(outer),points,rtol=0,atol=1e-10)
    except ValueError:return None
    return outer.tolist() if valid else None


def extract_patches(path,corners,coefficients):
    a=tifffile.memmap(path,mode='r');h,w=a.shape[:2];points=patch_centres(corners)
    locations=points*np.array([w-1,h-1]);distances=np.linalg.norm(locations[:,None]-locations[None,:],axis=-1)
    distances+=np.eye(24)*1e12;radius=max(2,int(distances.min()*.15));values=[]
    try:
        for x,y in np.rint(locations).astype(int):
            x0,x1=x-radius,x+radius+1;y0,y1=y-radius,y+radius+1
            if min(x0,y0)<0 or x1>w or y1>h:raise ValueError('取样区越过画面边界。')
            raw=np.asarray(a[y0:y1,x0:x1],float)/65535
            if np.max(np.mean(raw>=1,axis=(0,1)))>.001:raise ValueError('色卡取样有通道饱和，请降低扫描曝光后重新拍摄。')
            gain=FlatCorrection.of(coefficients).evaluate(h,w,y0,y1,x0,x1)
            values.append(np.median(raw*gain,axis=(0,1)))
    finally:a._mmap.close()
    values=np.array(values)
    if np.min(values)<=1/65535:raise ValueError('色卡有取样接近黑电平，请检查定位与曝光。')
    return values,{'centres':points.tolist(),'radius_half_pixels':radius}


def border_reading(path,roi,coefficients):
    roi=np.asarray(roi,float)
    if roi.shape!=(4,) or not np.isfinite(roi).all() or np.any(roi<0) or np.any(roi>1) or roi[2]-roi[0]<.002 or roi[3]-roi[1]<.002:
        raise ValueError('请在已显影、未曝光的片边拖出一个片基区域。')
    a=tifffile.memmap(path,mode='r');h,w=a.shape[:2]
    x0,y0,x1,y1=np.rint(roi*[w,h,w,h]).astype(int);x1=min(w,x1);y1=min(h,y1)
    try:
        raw=np.asarray(a[y0:y1,x0:x1],float)/65535
        if raw.size==0 or np.max(np.mean(raw>=1,axis=(0,1)))>.001:raise ValueError('片基取样区为空或有通道饱和。')
        gain=FlatCorrection.of(coefficients).evaluate(h,w,y0,y1,x0,x1)
        result=np.median(raw*gain,axis=(0,1))
        if np.any(result<=1/65535):raise ValueError('片基取样接近黑电平。')
        return result
    finally:a._mmap.close()
