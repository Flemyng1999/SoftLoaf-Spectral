"""Independent direct-sample audit and local visual report for the scan study."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from spectral_app.storage import DataStorage
from spectral_app.model import SpectralModel
from spectral_app.scanning.inverse import MaterialInverse
from spectral_app.scanning.rendering import amounts_to_display
from spectral_app.scanning.sensitivity import display_difference
from spectral_app.imaging.sources import ArraySource
from spectral_app.imaging.pipeline import write_image
from experiments.export_scan_lut import array_digest,retained_records


LABELS={'joint_current':'当前色卡拟合','joint_cropped':'当前拟合 · 裁至400–700',
    'v_refit':'A7R V 预测 · 重标定','iv_refit':'A7R IV · 重标定','iii_refit':'A7R III · 重标定',
    'ii_refit':'A7R II · 重标定','iv_wide':'A7R IV · 391–730',
    'iv_fixed':'A7R IV · 同光谱','iii_fixed':'A7R III · 同光谱','ii_fixed':'A7R II · 同光谱'}
PRIMARY=['joint_current','v_refit','iv_refit','iii_refit','ii_refit']
FIXED=['joint_current','v_refit','iv_fixed','iii_fixed','ii_fixed']
COVERAGE=['joint_current','joint_cropped','v_refit','iv_refit','iv_wide']


def direct_audit(out,directory):
    metadata=json.loads((out/'calibration-summary.json').read_text());keys=list(metadata['cases'])
    fingerprint=hashlib.sha256((out/'calibration-summary.json').read_bytes()).hexdigest()
    if (out/'direct-audit.json').exists():
        existing=json.loads((out/'direct-audit.json').read_text())
        if existing['analysis_sha256']!=fingerprint:raise ValueError('Direct audit is stale')
        return
    storage=DataStorage.configured();retained=storage.root/'scanning/retained-raw';before=retained_records(retained)
    root=Path(__file__).resolve().parents[1]
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',
        root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'audit-runtime')
    material=model.negative;a=np.load(directory/'calibration.npz');wave=a['wave']
    frozen=json.loads((directory/'calibration.json').read_text())
    for name,value in [('dyes',material.dyes),('base',material.base),('apd_weights',model.apd_weights)]:
        if array_digest(value)!=frozen['material_arrays_sha256'][name]:raise ValueError('Material changed during audit')
    dyes=np.column_stack([np.interp(wave,model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
    base=np.interp(wave,model.negative_wavelengths,material.base);inverses={}
    for key in keys:
        weights=np.load(out/(key+'-calibration.npz'))['aligned_weights']
        if array_digest(weights)!=metadata['cases'][key]['aligned_weights_sha256']:raise ValueError('Response weights changed')
        inverses[key]=MaterialInverse(dyes,base,weights,material.amounts.min(0),material.amounts.max(0))
    values={key:[] for key in keys};values0={key:[] for key in keys};valids={key:[] for key in keys};indices=[]
    for path in sorted(p for p in directory.glob('*-camera.npy') if not p.name.startswith('._')):
        pixels=np.load(path,mmap_mode='r');h,w=pixels.shape[:2]
        camera=np.array(pixels[int(.18*h):int(.84*h):max(1,int(.66*h)//16),
            int(.17*w):int(.82*w):max(1,int(.65*w)//24)]).reshape(-1,3).astype(float)
        pixels._mmap.close();number=int(path.stem.split('-camera')[0].rsplit('_',1)[1]);indices.extend([number]*len(camera))
        for key,inverse in inverses.items():
            solved=inverse.solve(camera);valids[key].append(solved['valid'])
            values[key].append(amounts_to_display(model,material,solved['amounts'],exposure_ev=2))
            values0[key].append(amounts_to_display(model,material,solved['amounts'],exposure_ev=0))
    rgb={key:np.concatenate(value) for key,value in values.items()}
    rgb0={key:np.concatenate(value) for key,value in values0.items()}
    valid={key:np.concatenate(value) for key,value in valids.items()};indices=np.array(indices)
    pairs=[(key,'joint_current') for key in keys if key!='joint_current']
    pairs += [(key+'_fixed','v_refit') for key in ('iv','iii','ii')]
    pairs += [('iv_refit','v_refit'),('iii_refit','iv_refit'),('ii_refit','iv_refit'),('iv_wide','iv_refit')]
    records={}
    for actual,reference in pairs:
        mask=valid[actual]&valid[reference]
        records[actual+'__'+reference]={'reference':reference,'actual':actual,
            'plus2':display_difference(rgb[reference],rgb[actual],valid=mask),
            'zero':display_difference(rgb0[reference],rgb0[actual],valid=mask),
            'frames':{str(i):display_difference(rgb[reference][indices==i],rgb[actual][indices==i],valid=mask[indices==i]) for i in range(1,38)}}
    if retained_records(retained)!=before:raise ValueError('RAW records changed during direct audit')
    np.savez(out/'direct-samples.npz',frame=indices,**{key:rgb[key] for key in keys},
        **{key+'_0':rgb0[key] for key in keys},**{key+'_valid':valid[key] for key in keys})
    (out/'direct-audit.json').write_text(json.dumps({'analysis_sha256':fingerprint,'samples':len(indices),
        'pairs':records,'RAW_records_unchanged':True,'new_RAW_developments':0,
        'scope':'independent direct float64 evaluation without LUT; display sensitivity, not ground truth'},indent=2)+'\n')


def plots(out):
    os.environ.setdefault('MPLCONFIGDIR',str(out/'plot-cache'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data=np.load(out/'response-and-light.npz');wave=data['common_wave']
    fig,axes=plt.subplots(2,2,figsize=(12,7),sharex=True,sharey=True,layout='constrained')
    for ax,key,title in zip(axes.flat,['v','iv','iii','ii'],['A7R V prediction / source grid 10 nm','A7R IV Weta / source grid 5 nm','A7R III Weta / source grid 5 nm','A7R II Weta / source grid 5 nm']):
        for c,color in enumerate(['#ca4b47','#2d8e69','#436cc6']):ax.plot(wave,data[key+'_response'][:,c],color=color,label='RGB'[c])
        ax.set_title(title);ax.grid(alpha=.18);ax.set_xlim(400,700);ax.set_ylim(0,1.05);ax.legend(loc='upper right')
        ax.set_xlabel('Wavelength / nm');ax.set_ylabel('Each channel peak normalized')
    fig.suptitle('Provided response shapes / linear interpolation inside source support only')
    fig.savefig(out/'response-curves.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,4.8),layout='constrained')
    for key,label in [('v','A7R V prediction'),('iv','A7R IV'),('iii','A7R III'),('ii','A7R II'),('iv_wide','A7R IV / wide band')]:
        light=data[key+'_light'];x=wave if len(light)==len(wave) else np.load(out/'iv_wide-calibration.npz')['wave']
        ax.plot(x,light/light.max(),label=label)
    ax.set(xlabel='Wavelength / nm',ylabel='Relative energy / peak 1',title='Estimated effective light AND optics / not a measured scanning lamp')
    ax.grid(alpha=.2);ax.legend();fig.savefig(out/'effective-light-estimates.png',dpi=160);plt.close(fig)
    audit=json.loads((out/'direct-audit.json').read_text())
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
    for ax,keys,reference,title in [(axes[0],PRIMARY[1:],'joint_current','Individual light refit / difference from current joint fit'),
        (axes[1],['iv_fixed','iii_fixed','ii_fixed'],'v_refit','Same estimated light / camera shape sensitivity relative to A7R V prediction')]:
        for key in keys:
            rows=audit['pairs'][key+'__'+reference]['frames']
            ax.plot(range(1,38),[rows[str(i)]['all']['deltaE00']['P95'] for i in range(1,38)],label=key,marker='.',linewidth=1)
        ax.set(ylabel='Display deltaE00 / frame P95',title=title);ax.grid(alpha=.2);ax.legend(ncol=2)
    axes[1].set_xlabel('Frame');fig.savefig(out/'display-sensitivity-by-frame.png',dpi=160);plt.close(fig)


def reviews(out):
    profile=None
    for case in LABELS:
        for path in sorted((out/'images'/case).glob('*.png')):
            if path.name.startswith('._'):continue
            target=out/'review'/case/path.name;target.parent.mkdir(parents=True,exist_ok=True)
            with Image.open(path) as image:
                w,h=image.size;profile=image.info.get('icc_profile');crop=image.crop((int(.17*w),int(.18*h),int(.82*w),int(.84*h))).rotate(180)
                crop.thumbnail((1000,700));crop.save(target,icc_profile=profile)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',20)
    small=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',17)
    def sheet(keys,frames,name,title):
        cw,ch=380,284;canvas=Image.new('RGB',(len(keys)*cw,len(frames)*ch+98),'#222426');draw=ImageDraw.Draw(canvas)
        draw.text((12,9),title,font=font,fill='white')
        draw.text((12,39),'全卷固定 +2 EV 观看；同一片边对齐；未逐张调色。固定画面裁切并旋转180°供比较。',font=small,fill='#c4c7c9')
        for col,key in enumerate(keys):draw.text((col*cw+12,70),LABELS[key],font=small,fill='white')
        for row,number in enumerate(frames):
            for col,key in enumerate(keys):
                with Image.open(out/'review'/key/f'{number:02d}.png') as image:
                    tile=image.copy();tile.thumbnail((cw-14,ch-30));x=col*cw+7;y=row*ch+98
                    draw.text((x,y),f'{number:02d}',font=small,fill='#c4c7c9');canvas.paste(tile,(x,y+27))
        canvas.save(out/name,icc_profile=profile)
    sheet(PRIMARY,[1,8,17,24],'selected-comparison.png','5207 翻拍 · 更换相机响应并分别重拟合有效光谱')
    sheet(FIXED,[1,8,17,24],'fixed-light-comparison.png','5207 翻拍 · 固定 A7R V 推算的同一个有效光谱')
    sheet(COVERAGE,[1,8,17,24],'coverage-comparison.png','5207 翻拍 · 波段与重标定对照')
    for start,end in [(1,19),(20,37)]:sheet(PRIMARY,list(range(start,end+1)),f'roll-comparison-{start:02d}-{end:02d}.png','5207 全卷 · 相机响应敏感度')


def gallery(out):
    modes=[{'label':'各曲线分别重标定','keys':PRIMARY,'frames':list(range(1,38))},
        {'label':'固定同一有效光谱','keys':FIXED,'frames':[1,8,17,24]},
        {'label':'波段对照','keys':COVERAGE,'frames':list(range(1,38))}]
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>5207 相机响应比较</title>
<style>body{margin:0;background:#222426;color:#e6e8e9;font:15px system-ui,sans-serif}header{padding:20px 24px;border-bottom:1px solid #444}h1{font-size:21px;margin:0 0 10px}p{color:#babfc2;line-height:1.6;max-width:1200px;margin:6px 0}nav{display:flex;align-items:center;gap:15px;margin-top:18px}select,button{background:#363a3d;color:white;border:1px solid #5b6064;border-radius:6px;padding:8px;font:inherit}input{width:250px}main{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;padding:20px;overflow:auto}figure{margin:0}figcaption{margin-bottom:12px;font-weight:600}img{width:100%;height:auto;display:block}a{color:#8cbcff}small{display:block;margin-top:8px;color:#adb4b8}.note{padding:0 24px 24px}</style>
<header><h1>5207 翻拍 · 相机感光曲线敏感度</h1><p>所有版本使用同一份 RAW 交接、平场、5207 材料、片边读数和 ACES 2.0。全卷固定 +2 EV 观看，无逐图自动曝光／白平衡。相机曲线和扫描光谱仍有假设，这里比较差异，不判定真实颜色。</p><nav><select id="mode"></select><button id="prev">←</button><input id="frame" type="range" min="0"><button id="next">→</button><span id="number"></span></nav></header><main id="grid"></main>
<div class="note"><p>页面使用固定画面裁切／旋转的检查图。点击图像可打开完整 3074×2048 输出。固定同光谱组提供四帧整图，直接光谱抽样比较涵盖全部37帧。</p><a href="direct-audit.json">直接计算对照</a> · <a href="frames.json">逐帧与文件检查</a> · <a href="calibration-summary.json">曲线及标定来源</a></div>
<script>const modes=MODES,labels=LABELS;const mode=document.getElementById('mode'),slider=document.getElementById('frame');modes.forEach((m,i)=>mode.add(new Option(m.label,i)));function draw(){const m=modes[+mode.value],n=m.frames[+slider.value],s=String(n).padStart(2,'0');document.getElementById('number').textContent='第 '+s+' 帧';const grid=document.getElementById('grid');grid.replaceChildren();m.keys.forEach(k=>{const f=document.createElement('figure'),c=document.createElement('figcaption'),a=document.createElement('a'),img=document.createElement('img'),t=document.createElement('small');c.textContent=labels[k];a.href='images/'+k+'/'+s+'.png';a.target='_blank';img.src='review/'+k+'/'+s+'.png';img.alt=labels[k]+' / '+s;t.textContent=k==='joint_current'?'当前结果作比较基准':'差异见直接计算报告';a.append(img);f.append(c,a,t);grid.append(f)})}function reset(){slider.max=modes[+mode.value].frames.length-1;slider.value=0;draw()}mode.onchange=reset;slider.oninput=draw;document.getElementById('prev').onclick=()=>{slider.value=Math.max(0,+slider.value-1);draw()};document.getElementById('next').onclick=()=>{slider.value=Math.min(+slider.max,+slider.value+1);draw()};reset();slider.value=16;draw();</script></html>'''
    (out/'index.html').write_text(html.replace('MODES',json.dumps(modes,ensure_ascii=False)).replace('LABELS',json.dumps(LABELS,ensure_ascii=False)))


def direct_reference_panel(out,directory,number=17):
    """Small per-pixel float64 reference panel; no CUBE interpolation."""
    root=Path(__file__).resolve().parents[1]
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',
        root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',out/'audit-runtime')
    material=model.negative;wave=np.load(directory/'calibration.npz')['wave']
    dyes=np.column_stack([np.interp(wave,model.negative_wavelengths,material.dyes[:,c]) for c in range(3)])
    base=np.interp(wave,model.negative_wavelengths,material.base)
    path=next(p for p in directory.glob('*-camera.npy') if not p.name.startswith('._') and p.stem.endswith(f'_{number:02d}-camera'))
    pixels=np.load(path,mmap_mode='r');h,w=pixels.shape[:2];step=max(1,round(.65*w/400))
    small=np.array(pixels[int(.18*h):int(.84*h):step,int(.17*w):int(.82*w):step])[::-1,::-1].copy()
    pixels._mmap.close();records={};tiles=[]
    for key in PRIMARY:
        weights=np.load(out/(key+'-calibration.npz'))['aligned_weights']
        inverse=MaterialInverse(dyes,base,weights,material.amounts.min(0),material.amounts.max(0))
        def render(values):
            solved=inverse.solve(values.reshape(-1,3).astype(float))
            return amounts_to_display(model,material,solved['amounts'],exposure_ev=2).reshape(values.shape)
        target=out/'direct-review'/key/f'{number:02d}.png';target.parent.mkdir(parents=True,exist_ok=True)
        records[key]=write_image(target,ArraySource(small),render,model.display_profile('sRGB'),
            fingerprint='camera-sensitivity-direct-reference-'+key,budget=16*1024**2,max_tile_pixels=1024)
        with Image.open(target) as image:tiles.append(image.copy())
        print('Direct reference pixels completed:',key,flush=True)
    cw=small.shape[1]+12;ch=small.shape[0]+100;canvas=Image.new('RGB',(cw*len(PRIMARY),ch),'#222426');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',18)
    draw.text((8,7),f'第{number:02d}帧 · 逐像素 float64 光谱反演 · 未经过 LUT · 固定 +2 EV 观看',font=font,fill='white')
    for i,(key,tile) in enumerate(zip(PRIMARY,tiles)):
        draw.text((i*cw+6,41),LABELS[key],font=font,fill='white');canvas.paste(tile,(i*cw+6,78))
    canvas.save(out/'direct-reference-comparison.png',icc_profile=model.display_profile('sRGB'))
    (out/'direct-reference-pixels.json').write_text(json.dumps({'frame':number,'input_sampling_stride':step,
        'each_pixel_direct_float64':True,'LUT_used':False,'pixel_shape':list(small.shape),
        'image_readback':records,'scope':'low-resolution visual reference, no additional RAW decoding'},indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--calibration-dir',type=Path,required=True);parser.add_argument('--audit-only',action='store_true')
    args=parser.parse_args();storage=DataStorage.configured();storage.validate();storage.activate_temporary_directory()
    if not args.output.resolve().is_relative_to(storage.volume.resolve()):raise ValueError('External outputs required')
    direct_audit(args.output,args.calibration_dir);plots(args.output)
    if not args.audit_only:
        reviews(args.output);gallery(args.output);direct_reference_panel(args.output,args.calibration_dir)
    print('Report ready:',args.output,flush=True)


if __name__=='__main__':main()
