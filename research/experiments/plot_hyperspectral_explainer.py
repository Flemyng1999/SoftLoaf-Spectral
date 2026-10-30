"""Illustrate stored RGB channels and spectral reflectance samples.

Reads an existing scene-16 RGB rendering and its matching 33-band MAT source.
No spectrum is reconstructed from RGB; no camera response is inferred.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle
import numpy as np
from PIL import Image, ImageCms
from scipy.io import loadmat

PIXEL_X, PIXEL_Y = 140, 75
WAVELENGTHS = np.arange(400, 721, 10)
BG, INK, MUTED = '#faf9f5', '#222222', '#5b5b56'
COLORS = ['#b9433d', '#43865a', '#4866a0']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_axis(fig, box, pixels, title=None, gray=False, marker=False):
    ax = fig.add_axes(box)
    if gray:
        ax.imshow(pixels, cmap='gray', vmin=0, vmax=1, interpolation='nearest')
    else:
        ax.imshow(pixels, interpolation='nearest')
    ax.set_axis_off()
    if title:
        ax.set_title(title, pad=10, fontsize=15, color=INK)
    if marker:
        for radius, color, width in [(8, 'black', 3), (8, 'white', 1.6)]:
            ax.add_patch(Circle((PIXEL_X, PIXEL_Y), radius, fill=False, edgecolor=color, linewidth=width))
    return ax


def save(fig, out, stem):
    path = out/f'{stem}.png'
    fig.savefig(path, dpi=160, facecolor=BG)
    plt.close(fig)
    # Explicit sRGB display profile. Diagram colors and gray levels are display encodings.
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    with Image.open(path) as source:
        pixels = source.convert('RGB')
    pixels.save(path, icc_profile=profile)
    version = sha(path)[:10]
    versioned = out/f'{stem}-{version}.png'
    path.rename(versioned)
    with Image.open(versioned) as saved:
        np.testing.assert_array_equal(np.array(saved), np.array(pixels))
        assert saved.info['icc_profile'] == profile
    return versioned.name


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True,help='Historical hyperspectral-demo directory')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    font_manager.fontManager.addfont(str(args.font))
    family=font_manager.FontProperties(fname=str(args.font)).get_name()
    plt.rcParams.update({'font.family':family,'font.size':14,'axes.unicode_minus':False,
                         'text.color':INK,'axes.labelcolor':INK,'xtick.color':MUTED,'ytick.color':MUTED})
    source=args.archive/'data/hsi_16.zip'
    rgb_source=args.archive/'output/5207-light-comparison/figures/scene16_source.png'
    with zipfile.ZipFile(source) as archive:
        hsi=loadmat(io.BytesIO(archive.read('hsi_16.mat')))['hsi'].astype(np.float64)
    with Image.open(rgb_source) as image:
        rgb=np.array(image.convert('RGB'))
    assert hsi.shape == (249,329,33) and rgb.shape == (249,329,3)
    assert np.isfinite(hsi).all()
    spectrum=hsi[PIXEL_Y,PIXEL_X].copy()
    rgb_pixel=rgb[PIXEL_Y,PIXEL_X].copy()
    assert np.array_equal(rgb_pixel,[171,154,73])
    assert (spectrum >= 0).all() and (spectrum <= 1).all()
    files={}

    fig=plt.figure(figsize=(16,9),facecolor=BG)
    fig.text(.05,.945,'同一个场景，RGB 和高光谱各记录了什么',fontsize=29,weight='bold')
    fig.text(.05,.87,'普通 RGB 图像',fontsize=23,weight='bold')
    fig.text(.05,.827,'每个像素保存 R、G、B 三个通道值',fontsize=17,color=MUTED)
    fig.text(.55,.87,'这组高光谱图像',fontsize=23,weight='bold')
    fig.text(.55,.827,'每个像素保存 33 个波长位置的反射率值',fontsize=17,color=MUTED)
    image_axis(fig,[.176,.47,.22,.29],rgb,'RGB 合成图')
    for c,label in enumerate('RGB'):
        image_axis(fig,[.05+c*.157,.17,.143,.245],rgb[:,:,c]/255.,f'{label} 通道',gray=True)
    for j,wavelength in enumerate([450,500,550,600,650,700]):
        c,row=j%3,j//3
        band=(wavelength-400)//10
        image_axis(fig,[.55+c*.145,.51-row*.31,.135,.245],hsi[:,:,band],f'{wavelength} nm',gray=True)
    fig.add_artist(plt.Line2D([.518,.518],[.15,.88],transform=fig.transFigure,color='#d4d1c9',lw=1))
    fig.text(.05,.11,'3 张通道图，组成一张 RGB 图像',fontsize=17)
    fig.text(.55,.11,'只展开其中 6 个波段；完整数据为 400–720 nm，每隔 10 nm 一个值',fontsize=13.5)
    fig.text(.05,.043,'RGB 通道按编码值显示为灰阶；三个通道不等于三个单独波长。',fontsize=12,color=MUTED)
    fig.text(.55,.043,'高光谱各图共用 0–1 反射率标尺；仅显示时裁切超出范围的值。',fontsize=12,color=MUTED)
    files['channels']=save(fig,args.output,'rgb-vs-hyperspectral-channels')

    fig=plt.figure(figsize=(16,9),facecolor=BG)
    fig.text(.05,.945,'取同一个花瓣像素，看看里面存了什么',fontsize=29,weight='bold')
    ax=image_axis(fig,[.05,.305,.355,.48],rgb,marker=True)
    ax.annotate('这个花瓣像素',xy=(PIXEL_X,PIXEL_Y),xytext=(215,17),
                color='white',fontsize=17,ha='center',
                arrowprops={'arrowstyle':'->','color':'white','lw':2},
                bbox={'facecolor':'#222222','edgecolor':'none','alpha':.8,'pad':4})
    fig.text(.05,.23,'同一个位置：横向第 141 列，纵向第 76 行',fontsize=14,color=MUTED)
    fig.text(.05,.155,'RGB 预览由这份高光谱数据生成。\n左图用来定位；右图读取同一位置的数值。',fontsize=16,linespacing=1.6)
    ax=fig.add_axes([.51,.62,.43,.21],facecolor=BG)
    ax.plot(range(3),rgb_pixel[::-1],color='#a56d1a',lw=2,zorder=1)
    for x,value,color in zip(range(3),rgb_pixel[::-1],COLORS[::-1]):
        ax.plot(x,value,linestyle='none',marker='o',ms=4,
                markerfacecolor=BG,markeredgecolor=color,markeredgewidth=1.3)
        ax.text(x,value+12,str(int(value)),ha='center',fontsize=19)
    ax.set_xlim(-.2,2.2);ax.set_xticks([0,1,2],['B','G','R'])
    ax.grid(axis='y',color='#dedbd4',lw=.8);ax.set_axisbelow(True)
    ax.set_ylim(0,255);ax.set_yticks([0,128,255]);ax.set_ylabel('RGB 编码值')
    ax.set_title('普通 RGB：3 个通道，3 个数',loc='left',fontsize=20,pad=14)
    ax.spines[['top','right']].set_visible(False)
    ax=fig.add_axes([.51,.205,.43,.275],facecolor=BG)
    ax.plot(WAVELENGTHS,spectrum,color='#a56d1a',lw=2,marker='o',ms=4,
            markerfacecolor=BG,markeredgewidth=1.3)
    ax.set_xlim(395,725);ax.set_ylim(0,1)
    ax.set_xticks([400,450,500,550,600,650,700,720]);ax.set_yticks([0,.25,.5,.75,1])
    ax.set_xlabel('波长（nm）',labelpad=8);ax.set_ylabel('反射率')
    ax.set_title('高光谱：33 个波段，33 个数',loc='left',fontsize=20,pad=14)
    ax.spines[['top','right']].set_visible(False)
    ax.grid(axis='y',color='#dedbd4',lw=.8);ax.set_axisbelow(True)
    fig.text(.51,.09,'这里的曲线表示花瓣怎样反射不同波长的光，\n可供后面另选照明、计算胶片曝光。',fontsize=15,linespacing=1.5)
    fig.text(.05,.035,'上图按 B、G、R 连接通道值，不代表光谱。下图横轴为波长、纵轴为反射率，连线便于阅读。',fontsize=12,color=MUTED)
    files['pixel']=save(fig,args.output,'rgb-vs-hyperspectral-pixel')
    values=np.column_stack([WAVELENGTHS,spectrum])
    np.savetxt(args.output/'selected-pixel.csv',values,delimiter=',',header='wavelength_nm,reflectance',comments='',fmt=['%.0f','%.17g'])
    readback=np.loadtxt(args.output/'selected-pixel.csv',delimiter=',',skiprows=1)
    np.testing.assert_array_equal(readback[:,0],WAVELENGTHS)
    np.testing.assert_allclose(readback[:,1],spectrum,rtol=1e-15,atol=0)
    report={'source':{'title':'Fifty hyperspectral reflectance images of outdoor scenes',
              'authors':['David H. Foster','Kinjiro Amano','Sérgio M. C. Nascimento'],
              'doi':'10.48420/14877285.v3','license':'CC BY 4.0',
              'scene_zip_sha256':sha(source),'rgb_preview_sha256':sha(rgb_source)},
            'hsi_shape':list(hsi.shape),'rgb_shape':list(rgb.shape),
            'pixel_zero_based_xy':[PIXEL_X,PIXEL_Y],'rgb_8bit':rgb_pixel.tolist(),
            'rgb_display_order':['B','G','R'],'rgb_display_values':rgb_pixel[::-1].tolist(),
            'wavelength_nm':WAVELENGTHS.tolist(),'reflectance':spectrum.tolist(),
            'rgb_rendering':'Retained D55 / CIE 1931 2 degree XYZ, finite 400–720 nm 10-nm grid, Bradford to D65, linear RGB gain 0.5, sRGB encoding, clipped for display.',
            'sampling_note':'10 nm sampling interval is not a statement of sensor bandwidth. Original release is spatially downsampled and spectrally smoothed.',
            'display_note':'Grayscale band values share a 0–1 display scale. Out-of-range source samples are retained; only illustrations clip. RGB encoded channel and spectral reflectance axes are not the same units.',
            'files':files,'verification':{'same_spatial_grid':True,'pixel_rgb_readback':True,
             'spectral_csv_readback':True,'png_pixels_and_icc_readback':True}}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps({'files':files,'rgb_pixel':rgb_pixel.tolist(),'verification':report['verification']},ensure_ascii=False))


if __name__=='__main__':
    main()
