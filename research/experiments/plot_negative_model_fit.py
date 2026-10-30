"""Show the local 5207 data sheet and the retained effective dye-model fit.

The 2022 sheet illustrates the published quantities. Existing digitized input
provenance remains separate; this does not claim fresh extraction from that PDF.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json

import fitz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np
from PIL import Image,ImageCms


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pdf',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--font',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    doc=fitz.open(a.pdf);assert 'MARCH 2022' in doc[0].get_text()
    font_manager.fontManager.addfont(str(a.font));family=font_manager.FontProperties(fname=str(a.font)).get_name()
    plt.rcParams.update({'font.family':family,'font.size':12,'axes.unicode_minus':False})
    m=np.load(a.model);x=m['camera_stops'];target=m['statusM_fitted_target'];pred=m['statusM_predicted']
    original=m['statusM_original'];coeff=m['dye_amounts_CMY']
    density=coeff@m['dyes_CMY'].T+m['base_density']
    check=-np.log10(10**(-density)@m['response_statusM'])
    np.testing.assert_allclose(check,pred,atol=2e-14,rtol=0)
    assert np.max(np.abs(check-target))<.002
    fig=plt.figure(figsize=(16,10),facecolor='#faf9f5')
    fig.text(.045,.955,'5207：从原厂曲线到有效染料模型',fontsize=28,weight='bold')
    fig.text(.045,.91,'上排为 2022 版手册原图；下排展示本次已有描图数据怎样约束模型',fontsize=16,color='#666660')
    crops=[(3,(58,91,284,321),'感光谱：各波长怎样贡献曝光'),
           (2,(348,500,563,722),'特性曲线：曝光 → Status M 密度'),
           (3,(340,91,537,305),'染料谱：青、品红、黄怎样吸收光')]
    for j,(page,rect,title) in enumerate(crops):
        pix=doc[page].get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(rect),alpha=False)
        image=Image.open(io.BytesIO(pix.tobytes('png')))
        ax=fig.add_axes([.045+j*.32,.53,.27,.30]);ax.imshow(np.array(image));ax.set_axis_off()
        ax.set_title(title,pad=12,fontsize=15)
    fig.text(.5,.465,'已有描图表 → 对齐片基与净密度 → 拟合有效 CMY 系数 → 按 Status M 回算',ha='center',fontsize=19)
    ax=fig.add_axes([.07,.14,.38,.245],facecolor='#faf9f5')
    for i,color in enumerate(['#c54c46','#38885c','#4b6eae']):
        ax.plot(x,original[:,i],ls='--',color=color,alpha=.5,lw=1)
        ax.plot(x,target[:,i],color=color,lw=1.7)
        ax.plot(x[::14],pred[::14,i],ls='none',marker='o',ms=4,markerfacecolor='#faf9f5',color=color)
        ax.text(x[-1]+.12,target[-1,i],'RGB'[i],color=color,fontsize=12,va='center')
    ax.set_xlim(x[0],x[-1]+.8);ax.set_ylim(0,3.1);ax.set_xlabel('曝光位置（档）');ax.set_ylabel('Status M 密度')
    ax.set_title('在测量条件下，回算密度与目标对照',loc='left',fontsize=17,pad=14)
    ax.legend(handles=[Line2D([0],[0],color='#777777',ls='--',label='原始描图'),
              Line2D([0],[0],color='#333333',label='片基对齐后的目标'),
              Line2D([0],[0],color='#333333',ls='none',marker='o',markerfacecolor='#faf9f5',label='模型回算')],
              frameon=False,fontsize=10,loc='upper left')
    ax2=fig.add_axes([.57,.14,.36,.245],facecolor='#faf9f5')
    for i,(label,color) in enumerate(zip('CMY',['#278e9e','#b04c8f','#b69a21'])):
        ax2.plot(x,coeff[:,i],color=color,lw=2,label=label)
    ax2.set_xlabel('曝光位置（档）');ax2.set_ylabel('有效系数');ax2.legend(frameon=False,ncol=3,fontsize=11)
    ax2.set_title('得到随曝光变化的三组有效染料系数',loc='left',fontsize=17,pad=14)
    for axis in [ax,ax2]:
        axis.spines[['top','right']].set_visible(False);axis.grid(axis='y',color='#dedbd4',lw=.7);axis.set_axisbelow(True)
    fig.text(.045,.06,'原厂 R/G/B 密度不是 C/M/Y 染料量。系数要通过染料谱组合与规定测量响应求解；本图没有展示真实化学反应时序。',fontsize=11,color='#666660')
    fig.text(.045,.035,'原图：Eastman Kodak，H-1-5207，Revised 3-22，p.3–4。中性回代用于检查模型构造，彩色准确度仍需实测。',fontsize=11,color='#666660')
    dest=a.output/'5207_document_and_fit.png';fig.savefig(dest,dpi=170,facecolor='#faf9f5');plt.close(fig)
    with Image.open(dest) as im:pixels=im.convert('RGB')
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes();pixels.save(dest,icc_profile=icc)
    name=f'5207_document_and_fit-{sha(dest)[:10]}.png';dest.rename(a.output/name)
    with Image.open(a.output/name) as im:np.testing.assert_array_equal(np.array(im),np.array(pixels));assert im.info['icc_profile']==icc
    report={'image':name,'pdf_sha256':sha(a.pdf),'model_sha256':sha(a.model),
            'pdf_edition':'H-1-5207 Revised 3-22, pages 3–4; reference illustration only, existing digitization provenance is separate.',
            'fit_target':'Spectral base retained; original toe subtracted from each characteristic curve and spectral-base Status M added.',
            'verification':{'recomputed_vs_saved_density_max':float(np.max(np.abs(check-pred))),
              'neutral_fit_target_max_D':float(np.max(np.abs(check-target))),'PNG_and_ICC_readback':True},
            'limits':'Typical curves; effective coefficients are not measured concentrations; no independent colored-film validation.'}
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
