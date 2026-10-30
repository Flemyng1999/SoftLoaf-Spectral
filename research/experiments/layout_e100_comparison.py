"""Lay out retained E100 scene-reference and gain-1.8 viewing images.

Only panel selection and labels change. No film or display calculation runs.
"""
from pathlib import Path
import argparse
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from PIL import Image, ImageCms


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    font_manager.fontManager.addfont(str(args.font))
    family=font_manager.FontProperties(fname=str(args.font)).get_name()
    plt.rcParams.update({'font.family':family,'axes.unicode_minus':False})
    fig,axes=plt.subplots(2,2,figsize=(8.8,8.5),squeeze=False,facecolor='#f7f7f4')
    columns=[('reference','场景光谱参照\nD55 → XYZ → sRGB'),
             ('view_ev+0','E100 模型 · D50 透射观察\n统一观察亮度 ×1.8')]
    sources={}
    for row,(scene,label) in enumerate([(16,'红黄玫瑰'),(43,'橙紫花朵')]):
        for col,(key,title) in enumerate(columns):
            path=args.source/f'scene{scene:02d}_{key}.png'
            sources[path.name]=sha(path)
            with Image.open(path) as source:
                pixels=np.array(source.convert('RGB'))
            assert pixels.shape==(249,329,3)
            ax=axes[row,col];ax.imshow(pixels);ax.set_axis_off()
            if row==0:ax.set_title(title,pad=10,fontsize=13,linespacing=1.5)
            ax.text(.02,.04,f'{scene:02d} {label}',transform=ax.transAxes,color='white',fontsize=11,
                    bbox={'facecolor':'black','alpha':.6,'pad':3,'edgecolor':'none'})
    fig.suptitle('从场景光谱模拟 E100 反转片拍摄',y=.985,fontsize=21)
    footer='场景 D55 照明 → E100 感光 → E-6 染料模型 → D50 透射观察 → sRGB。\n右列统一观察亮度 ×1.8，未逐张提亮；近似模拟尚未用真实 E100 色卡验证。'
    fig.text(.5,.015,footer,ha='center',va='bottom',fontsize=10,linespacing=1.5)
    fig.subplots_adjust(left=.01,right=.99,top=.85,bottom=.10,hspace=.035,wspace=.02)
    path=args.output/'E100_examples_two_columns.png'
    fig.savefig(path,dpi=160,facecolor='#f7f7f4');plt.close(fig)
    with Image.open(path) as source:rendered=source.convert('RGB')
    rendered.save(path,icc_profile=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    name=f'E100_examples_two_columns-{sha(path)[:10]}.png';destination=args.output/name
    path.rename(destination)
    with Image.open(destination) as saved:
        np.testing.assert_array_equal(np.array(saved),np.array(rendered));assert 'icc_profile' in saved.info
    for name0,digest in sources.items():assert sha(args.source/name0)==digest
    report={'columns':['reference','view_ev+0'],'scenes':[16,43],'viewing_gain':1.8,
            'source_hashes':sources,'image':name,'verification':'Two columns; original image sources unchanged; saved PNG pixels and ICC read back.'}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
