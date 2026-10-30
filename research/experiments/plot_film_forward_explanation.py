"""Document-curve readback and a retained 5207 pixel's forward calculation.

Only uses local user-supplied data. The E100 PDF is quoted locally, not bundled.
This draws the historical effective model; it does not identify a new film model.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile

import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle
import numpy as np
from PIL import Image,ImageCms
from scipy.io import loadmat

BG='#faf9f5'
COLORS=['#278e9e','#b04c8f','#b69a21']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(fig,out,name):
    path=out/f'{name}.png';fig.savefig(path,dpi=170,facecolor=BG);plt.close(fig)
    with Image.open(path) as im:pixels=im.convert('RGB')
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    pixels.save(path,icc_profile=icc)
    name=f'{name}-{sha(path)[:10]}.png';dest=out/name;path.rename(dest)
    with Image.open(dest) as im:
        np.testing.assert_array_equal(np.array(im),np.array(pixels));assert im.info['icc_profile']==icc
    return name


def axis_style(ax):
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',color='#dedbd4',lw=.7);ax.set_axisbelow(True)
    ax.tick_params(labelsize=10)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    args=parser.parse_args();root=args.archive;out=args.output;out.mkdir(parents=True,exist_ok=True)
    font_manager.fontManager.addfont(str(args.font))
    family=font_manager.FontProperties(fname=str(args.font)).get_name()
    plt.rcParams.update({'font.family':family,'font.size':13,'axes.unicode_minus':False,'text.color':'#222222'})
    pdf=root/'data/reversal-E100/Kodak_E100_E4000_2018.pdf'
    traces_path=root/'output/reversal-E100/data/E100_original_vector_traces.json'
    traces=json.loads(traces_path.read_text());doc=fitz.open(pdf)
    fig=plt.figure(figsize=(16,9),facecolor=BG)
    fig.text(.045,.95,'先把原厂曲线，变成可计算的数据',fontsize=28,weight='bold')
    fig.text(.045,.90,'以 E100 / E-4000（2018）为例：原厂图与本次提取线叠加',fontsize=16,color='#666660')
    configs=[(3,(40,80,285,315),'感光谱\n横轴：波长','sensitivity_'),
             (2,(322,320,572,579),'特性曲线\n横轴：曝光量的对数','characteristic_'),
             (3,(40,324,285,541),'染料密度谱\n横轴：波长','dye_')]
    endpoint_errors=[]
    for j,(page,rect,title,prefix) in enumerate(configs):
        ax=fig.add_axes([.045+j*.32,.50,.27,.31])
        pix=doc[page].get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(rect),alpha=False)
        original=np.asarray(Image.open(io.BytesIO(pix.tobytes('png'))))
        ax.imshow(original,extent=[rect[0],rect[2],rect[3],rect[1]])
        if prefix=='sensitivity_':
            for key,color,index in zip('RGB',['#c54c46','#38885c','#4b6eae'],[41,39,40]):
                a=np.asarray(traces[prefix+key]);x=74.340+(a[:,0]-250)*(274.886-74.340)/500
                y=106.967+(2-a[:,1])*(258.499-106.967)/4
                raw=doc[page].get_drawings()[index]['items'][0][1]
                endpoint_errors.append(float(np.max(np.abs(np.array([x[0],y[0]])-np.array(raw)))))
                ax.plot(x,y,color=color,lw=1,alpha=.75)
        elif prefix=='characteristic_':
            for key,color in zip('RGB',['#c54c46','#38885c','#4b6eae']):
                a=np.asarray(traces[prefix+key]);x=368.719+(a[:,0]+3)*(553.911-368.719)/4
                y=542.966-a[:,1]*(542.966-358.595)/4;ax.plot(x,y,color=color,lw=1,alpha=.75)
        else:
            for key,color in zip('CMY',COLORS):
                a=np.asarray(traces[prefix+key]);x=70.640+(a[:,0]-400)*(271.101-70.640)/300
                y=501.079-a[:,1]*(501.079-349.656)/1.4;ax.plot(x,y,color=color,lw=1,alpha=.75)
        ax.set_xlim(rect[0],rect[2]);ax.set_ylim(rect[3],rect[1]);ax.set_axis_off()
        ax.set_title(title,fontsize=16,pad=10,linespacing=1.45)
    assert max(endpoint_errors)<1e-10
    fig.text(.5,.435,'读取矢量路径  →  按坐标刻度换算  →  保存数表',ha='center',fontsize=21)
    a=np.asarray(traces['sensitivity_R']);wl=np.array([580.,610.,640.,670.]);logs=np.interp(wl,a[:,0],a[:,1]);linear=10**logs
    ax=fig.add_axes([.07,.13,.37,.215],facecolor=BG)
    ax.plot(a[:,0],a[:,1],color='#b44b43',lw=1.6);ax.scatter(wl,logs,color='#b44b43',s=24,zorder=3)
    ax.set_xlim(560,690);ax.set_ylim(-1.1,1.7);ax.set_xlabel('波长（nm）');ax.set_ylabel('对数感光度')
    ax.set_title('取感红记录的一小段',loc='left',fontsize=17);axis_style(ax)
    ax=fig.add_axes([.54,.12,.40,.23]);ax.set_axis_off()
    rows=[[f'{w:.0f}',f'{v:.3f}',f'{s:.3f}'] for w,v,s in zip(wl,logs,linear)]
    table=ax.table(cellText=rows,colLabels=['波长 / nm','对数感光度','线性感光度'],loc='center',cellLoc='center')
    table.auto_set_font_size(False);table.set_fontsize(14);table.scale(1,1.8)
    for (row,col),cell in table.get_celld().items():
        cell.set_edgecolor('#d6d3cc');cell.set_facecolor('#e8e5dd' if row==0 else BG)
    ax.set_title('按提取曲线插值，再还原为线性响应',fontsize=17,pad=8)
    fig.text(.045,.038,'原图：Kodak Alaris，E-4000 Revised 8-18，p.3–4。彩色细线为提取路径；表格取样不是新增实测。',fontsize=11,color='#666660')
    files={'extraction':save(fig,out,'film-document-to-data')}

    model_path=root/'output/5207-full/intermediate/material_model.npz'
    frame_path=root/'output/5207-light-comparison/intermediate/scene16_film.npz'
    m=np.load(model_path);frame=np.load(frame_path);x,y=140,75
    amounts=frame['amounts_CMY'][y,x].astype(float);stops=frame['effective_layer_stops'][y,x].astype(float)
    fitted=np.array([np.interp(stops[i],m['camera_stops'],m['dye_amounts_CMY'][:,i]) for i in range(3)])
    np.testing.assert_allclose(amounts,fitted,atol=2e-7,rtol=2e-6)
    w=m['wavelength_nm'];components=m['dyes_CMY']*amounts[None,:]
    density=components.sum(axis=1)+m['base_density'];transmission=10**(-density)
    assert np.isfinite(transmission).all() and (transmission>0).all() and (transmission<=1).all()
    apd=-np.log10(transmission@m['response_APD_limited'])
    np.testing.assert_allclose(apd,frame['APD_limited_density'][y,x],atol=3e-7)
    scene_path=root/'data/hsi_16.zip'
    with zipfile.ZipFile(scene_path) as z:hsi=loadmat(io.BytesIO(z.read('hsi_16.mat')))['hsi']
    scene_wl=np.arange(400,721,10);reflectance=hsi[y,x];lamp_path=root/'data/CIE_D55_colour_0.4.6.csv'
    lamp=np.loadtxt(lamp_path,delimiter=',',skiprows=1);light=np.interp(scene_wl,lamp[:,0],lamp[:,1]);incident=light*reflectance
    sensitivity_path=root.parent/'data/sensitivity_5207.csv';sens=np.genfromtxt(sensitivity_path,delimiter=',',names=True)
    responses=[]
    for key in ['cyan','magenta','yellow']:
        good=np.isfinite(sens[key]);responses.append(np.interp(scene_wl,sens['wavelength'][good],10**sens[key][good],left=0,right=0))
    widths=np.full(33,10.);widths[[0,-1]]=5.
    responses=np.column_stack(responses);gray=.18*np.sum(light[:,None]*responses*widths[:,None],axis=0)
    relative_stops=np.log2(np.sum(incident[:,None]*responses*widths[:,None],axis=0)/gray)
    offsets=stops-relative_stops
    assert np.ptp(offsets)<2e-6

    fig=plt.figure(figsize=(16,9),facecolor=BG)
    fig.text(.045,.95,'同一个花瓣像素，怎样变成模拟负片',fontsize=28,weight='bold')
    fig.text(.045,.90,'5207 有效材料模型；读取已有中间结果，沿着计算往下看',fontsize=16,color='#666660')
    boxes=[[.06,.59,.235,.22],[.385,.59,.235,.22],[.715,.59,.235,.22],[.385,.15,.235,.22],[.715,.15,.235,.22]]
    axes=[fig.add_axes(box,facecolor=BG) for box in boxes]
    ax=axes[0];ax.plot(scene_wl,incident/light.max(),color='#5b7589',lw=2)
    ax.set_xlim(400,720);ax.set_xlabel('波长（nm）');ax.set_ylabel('相对光谱强度')
    ax.set_title('① 拍摄照明 × 反射率',loc='left',fontsize=17,pad=13)
    ax=axes[1];ax.bar(['感红','感绿','感蓝'],stops,color=['#c54c46','#38885c','#4b6eae'],width=.45)
    ax.set_ylabel('曝光位置（档）');ax.set_title('② 三层有效曝光',loc='left',fontsize=17,pad=13)
    for i,v in enumerate(stops):ax.text(i,v+.04,f'{v:.2f}',ha='center',fontsize=11)
    ax.set_ylim(min(0,stops.min()-.3),max(0,stops.max()+.6))
    ax=axes[2]
    for i,(label,color) in enumerate(zip('CMY',COLORS)):
        ax.plot(m['camera_stops'],m['dye_amounts_CMY'][:,i],label=label,color=color,lw=1.5)
        ax.plot(stops[i],amounts[i],marker='o',color=color,ms=6)
    ax.set_xlabel('曝光位置（档）');ax.set_ylabel('有效系数');ax.legend(frameon=False,fontsize=10,ncol=3)
    ax.set_title('③ 曝光 → 有效染料系数',loc='left',fontsize=17,pad=13)
    ax=axes[3]
    for i,(label,color) in enumerate(zip('CMY',COLORS)):ax.plot(w,components[:,i],color=color,label=label,lw=1)
    ax.plot(w,m['base_density'],color='#888888',label='片基',ls='--',lw=1.2)
    ax.plot(w,density,color='#222222',label='总密度',lw=2)
    ax.set_xlim(400,790);ax.set_xlabel('波长（nm）');ax.set_ylabel('光谱密度')
    ax.set_title('④ 染料密度谱 + 片基',loc='left',fontsize=17,pad=13)
    ax.legend(frameon=False,fontsize=9,ncol=3)
    ax=axes[4];ax.plot(w,transmission,color='#a56d1a',lw=2)
    ax.set_xlim(400,790);ax.set_ylim(0,1);ax.set_xlabel('波长（nm）');ax.set_ylabel('透过比例')
    ax.set_title('⑤ 换算成光谱透过率',loc='left',fontsize=17,pad=13)
    for ax in axes:axis_style(ax)
    photo_path=root/'output/5207-light-comparison/negative-stages/images/scene16_d50_xyz.png'
    ax=fig.add_axes([.06,.15,.235,.22])
    with Image.open(photo_path) as im:ax.imshow(np.asarray(im.convert('RGB')))
    ax.add_patch(Circle((x,y),8,fill=False,color='white',lw=1.8));ax.set_axis_off()
    ax.set_title('结果：负片透射预览（D50）',loc='left',fontsize=15,pad=13)
    fig.text(.50,.465,'反射光谱 → 有效曝光 → 染料系数 → 光谱密度 → 透过率',ha='center',fontsize=19)
    fig.text(.045,.045,'曝光原点沿用模拟约定；系数由中性 Status M 曲线约束，不是真实染料浓度。层间与掩蔽作用未完整模拟。',fontsize=11,color='#666660')
    fig.text(.045,.017,'场景光谱：Foster、Amano、Nascimento，DOI 10.48420/14877285.v3，CC BY 4.0。',fontsize=9,color='#666660')
    files['forward']=save(fig,out,'film-pixel-forward-process')
    np.savetxt(out/'E100_sensitivity_example.csv',np.column_stack([wl,logs,linear]),delimiter=',',header='wavelength_nm,log_sensitivity,linear_sensitivity',comments='')
    np.savetxt(out/'5207_pixel_density_transmission.csv',np.column_stack([w,*components.T,m['base_density'],density,transmission]),delimiter=',',header='wavelength_nm,C_density,M_density,Y_density,base_density,total_density,transmittance',comments='')
    sources=[pdf,traces_path,model_path,frame_path,scene_path,lamp_path,sensitivity_path,photo_path]
    report={'files':files,'source_hashes':{p.name:sha(p) for p in sources},'pixel_zero_based_xy':[x,y],
            'E100_document':'Kodak Alaris E-4000, Revised 8-18, pages 3–4; Status A and E-6',
            '5207_model':'Existing effective CMY model fitted to neutral Status M curves; ECN-2; independent layer coefficients are an approximation.',
            'source_notice':'PDF crops and input data remain local pending redistribution review. No source archive files modified.',
            'pixel_stops_CMY':stops.tolist(),'pixel_amounts_CMY':amounts.tolist(),
            'exposure_offset_shared':float(offsets.mean()),'negative_preview':'Retained 402–730 nm D50 transmission, CIE 1931 2 degree XYZ to sRGB, no-film white Y=1, gain 1, no adaptation; marked pixel matches x/y used in the plots.',
            'grids':{'scene_nm':[400,720,10],'negative_nm':[402,788,2]},
            'verification':{'PDF_sensitivity_path_endpoint_error_points':max(endpoint_errors),
              'same_layer_exposure_offset_max_difference':float(np.ptp(offsets)),
              'dye_interpolation_max_error':float(np.max(np.abs(amounts-fitted))),
              'APD_saved_intermediate_max_error':float(np.max(np.abs(apd-frame['APD_limited_density'][y,x]))),
              'PNG_pixels_and_ICC_readback':True}}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({'files':files,'verification':report['verification']},ensure_ascii=False))


if __name__=='__main__':main()
