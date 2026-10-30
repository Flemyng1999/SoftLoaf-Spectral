"""Replay local historical experiments with a common no-film white.

Inputs and the external native reference are user-supplied, not distributed
with this project. This program changes channel units and assembles figures;
it does not implement the proprietary inversion or copy its configuration.
"""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import subprocess

import numpy as np
from PIL import Image, ImageCms
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from capture_white import normalize_capture_white

SCENES = (1, 5, 6, 16, 31, 38, 43, 50)
NAMES = dict(zip(SCENES, ('木板门', '石头', '城市', '红黄玫瑰', '涂鸦', '蕨叶', '橙紫花朵', '旧墙')))
PROFILE = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def loadbin(path):
    with path.open('rb') as stream:
        shape = np.fromfile(stream, dtype='<i4', count=3)
        values = np.fromfile(stream, dtype='<f4')
    if len(shape) != 3 or shape[2] != 3 or np.prod(shape) != len(values):
        raise ValueError(f'Invalid RGB tensor: {path}')
    return values.reshape(tuple(shape)).astype(np.float64)


def savebin(path, array):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as stream:
        np.asarray(array.shape, dtype='<i4').tofile(stream)
        np.asarray(array, dtype='<f4').tofile(stream)


def encode(array):
    a = np.clip(array, 0, 1)
    return np.where(a <= .0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - .055)


def savepng(path, array, linear=False):
    if not np.isfinite(array).all():
        raise ValueError(f'Non-finite output: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = encode(array) if linear else np.clip(array, 0, 1)
    values = np.uint8(np.rint(encoded * 255))
    Image.fromarray(values).save(path, icc_profile=PROFILE)
    with Image.open(path) as image:
        np.testing.assert_array_equal(np.asarray(image), values)
        assert image.info['icc_profile'] == PROFILE


def board(out, scenes, columns, name, title, footer):
    fig, axes = plt.subplots(len(scenes), len(columns), squeeze=False,
                             figsize=(4 * len(columns), 3.35 * len(scenes) + 1.6))
    for row, n in enumerate(scenes):
        for col, (pathfn, label) in enumerate(columns):
            ax = axes[row, col]
            with Image.open(pathfn(n)) as image:
                ax.imshow(np.array(image.convert('RGB')))
            ax.set_axis_off()
            if row == 0:
                ax.set_title(label, fontsize=13, pad=12, linespacing=1.4)
            ax.text(.02, .035, f'{n:02d} {NAMES[n]}', transform=ax.transAxes,
                    color='white', fontsize=11,
                    bbox=dict(facecolor='black', alpha=.6, edgecolor='none', pad=3))
    fig.suptitle(title, fontsize=22, y=.985)
    fig.text(.5, .018, footer, ha='center', va='bottom', fontsize=11, linespacing=1.5)
    fig.subplots_adjust(left=.012, right=.988, top=.85 if len(scenes)==2 else .90,
                        bottom=.105 if len(scenes)==2 else .07, wspace=.025, hspace=.035)
    fig.savefig(out/'figures'/f'{name}.png', dpi=125)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True, help='Historical hyperspectral-demo directory')
    parser.add_argument('--output', type=Path, required=True, help='Separate output; do not use the archive')
    parser.add_argument('--profile-dir', type=Path, required=True, help='User-supplied original CCM files')
    parser.add_argument('--ocio', type=Path, required=True, help='External reference viewing configuration')
    parser.add_argument('--font', type=Path, required=True, help='Chinese TrueType font')
    args = parser.parse_args()
    root, out = args.archive.resolve(), args.output.resolve()
    if out == root or root in out.parents:
        raise ValueError('Output must be outside the immutable historical archive.')
    old = root/'output/5207-light-comparison'
    cc = old/'ccm-trichrome'
    report0 = json.loads((old/'report.json').read_text())
    report = dict(convention='Linear RGB row vectors @ CCM', white='No film: (1,1,1)',
                  units='Dimensionless signal divided by blank illumination signal',
                  formula='normalized_input = old_input / white; normalized_CCM = diag(white) @ old_CCM',
                  scope='Unit change only; no new calibration, base subtraction or grading',
                  scenes=list(SCENES), setups={}, native={}, sources={})
    for folder in ('data', 'linear', 'figures'):
        (out/folder).mkdir(parents=True, exist_ok=True)
    report['sources']['native_reference'] = sha(root/'tools/native_5207_reference')
    report['sources']['ocio'] = sha(args.ocio)
    setups = {}
    for key in ('gh7_rgb', 'gh7_d50', 'cfa_rgb', 'cfa_d50', 'mono_rgb'):
        if key.startswith('gh7_'):
            lamp = key[4:]
            matrix_path = args.profile_dir/('ccm_ipad_0304.npy' if lamp == 'rgb' else 'ccm_wb_white.npy')
            white = np.array(report0['capture'][lamp]['white_input_coordinate'])
            input_dir, prior_on = old/f'native-input/{lamp}', old/f'native-{lamp}'
        else:
            matrix_path = cc/f'data/{key}_CCM.npy'
            white = np.full(3, .8)
            input_dir, prior_on = cc/f'native-input/{key}', cc/f'native-{key}_on'
        matrix = np.load(matrix_path).astype(np.float64)
        _, normalized = normalize_capture_white(np.ones((1,3))*white, matrix, white)
        np.save(out/f'data/{key}_CCM_float64.npy', normalized)
        np.save(out/f'data/{key}_CCM.npy', normalized.astype('<f4'))
        neutral = np.array([0, .02, .09, .18, .5, 1.])[:,None]
        normalized_ramp, _ = normalize_capture_white(neutral*white, matrix, white)
        neutral_error = float(np.max(np.abs(normalized_ramp@normalized-neutral)))
        assert neutral_error < 2e-7
        info = dict(original_matrix_sha256=sha(matrix_path), original_matrix=matrix.tolist(),
                    white_input=white.tolist(), matrix=normalized.tolist(),
                    column_sums=normalized.sum(axis=0).tolist(), neutral_error=neutral_error,
                    equivalence_max_error=0., input_hashes={})
        for n in SCENES:
            name = f'scene{n:02d}'
            source = input_dir/f'{name}.bin'
            raw = loadbin(source)
            raw_n, _ = normalize_capture_white(raw, matrix, white)
            error = float(np.max(np.abs(raw_n@normalized-raw@matrix)))
            assert error < 1e-12
            info['equivalence_max_error'] = max(info['equivalence_max_error'], error)
            info['input_hashes'][name] = sha(source)
            savebin(out/f'input/{key}/{name}.bin', raw_n)
            np.save(out/f'linear/{name}_{key}_raw.npy', raw_n)
            savepng(out/f'figures/{name}_{key}_raw.png', raw_n, linear=True)
            if key == 'mono_rgb':
                for c, label in enumerate('RGB'):
                    savepng(out/f'figures/{name}_mono_{label}.png', np.repeat(raw_n[:,:,c,None],3,axis=2), linear=True)
        report['setups'][key] = info
        setups[key] = prior_on

    def native(route):
        key, state = route
        dest = out/f'native-{key}_{state}'
        command = [str(root/'tools/native_5207_reference'), str(out/f'input/{key}'), str(dest), str(args.ocio)]
        if state == 'on':
            command.append(str(out/f'data/{key}_CCM.npy'))
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        (out/f'{key}_{state}.log').write_bytes(process.stdout)
        if process.returncode:
            raise RuntimeError(process.stdout.decode(errors='replace')[-3000:])
        model = json.loads((dest/'native_model.json').read_text())
        assert model['frame_count'] == 8 and model['response_model_version'] == 5
        drift = dict(post_ccm_max_error=0., final_srgb_max_error=0., final_srgb_rms_error=0.)
        squared = []
        for n in SCENES:
            name = f'scene{n:02d}'
            final = loadbin(dest/f'{name}_srgb.bin')
            savepng(out/f'figures/{name}_{key}_{state}.png', final)
            if state == 'on':
                post = loadbin(dest/f'{name}_post_ccm.bin')
                savepng(out/f'figures/{name}_{key}_ccm.png', post, linear=True)
                raw_n = np.load(out/f'linear/{name}_{key}_raw.npy')
                reference = raw_n@np.array(report['setups'][key]['matrix'])
                assert np.max(np.abs(post-reference)) < 2e-6
                np.save(out/f'linear/{name}_{key}_ccm.npy', post)
                oldpost = loadbin(setups[key]/f'{name}_post_ccm.bin')
                drift['post_ccm_max_error'] = max(drift['post_ccm_max_error'], float(np.max(np.abs(post-oldpost))))
                difference = final-loadbin(setups[key]/f'{name}_srgb.bin')
                drift['final_srgb_max_error'] = max(drift['final_srgb_max_error'], float(np.max(np.abs(difference))))
                squared.append(float(np.mean(difference**2)))
        if squared:
            drift['final_srgb_rms_error'] = float(np.sqrt(np.mean(squared)))
        print(key, state, 'PASS', flush=True)
        return f'{key}_{state}', dict(model=model, unchanged_on_path_drift=drift if state=='on' else None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        for key, value in executor.map(native, [(k,s) for k in setups for s in ('off','on')]):
            report['native'][key] = value
    font_manager.fontManager.addfont(str(args.font))
    font_name = font_manager.FontProperties(fname=str(args.font)).get_name()
    plt.rcParams.update({'font.family':font_name, 'axes.unicode_minus':False,
                         'figure.facecolor':'#f7f7f4', 'savefig.facecolor':'#f7f7f4'})
    def col(key, label):
        return (lambda n: out/f'figures/scene{n:02d}_{key}.png', label)
    def oldcol(base, key, label):
        return (lambda n: base/f'scene{n:02d}_{key}.png', label)
    stages = [oldcol(old/'negative-stages/images','d50_xyz','D50 透射光\nXYZ → sRGB'),
              oldcol(old/'negative-stages/images','sapd_xyz','S_APD 透射光\nXYZ → sRGB'),
              col('gh7_rgb_raw','RGB 光源 · 归一化采集通道\n无片白场 R＝G＝B＝1'),
              col('gh7_rgb_ccm','RGB 光源 · 匹配 CCM 后\n负片通道预览'),
              col('gh7_d50_raw','D50 · 归一化采集通道\n无片白场 R＝G＝B＝1'),
              col('gh7_d50_ccm','D50 · 匹配 CCM 后\n负片通道预览')]
    gh7 = [col(f'gh7_{lamp}_{state}', f'GH7 · {label}\n{mode}')
           for lamp,label in [('rgb','实测 RGB 光源'),('d50','D50')]
           for state,mode in [('off','无 CCM'),('on','有匹配 CCM')]]
    controlled = [col(f'{key}_{state}', f'{label}\n{mode}')
                  for key,label in [('cfa_rgb','彩色 IMX273 · RGB'),('mono_rgb','黑白 IMX273 · 三色分拍')]
                  for state,mode in [('off','无 CCM'),('on','有该配置 CCM')]]
    all_arch = [col(f'cfa_d50_{state}', f'彩色 IMX273 · D50\n{mode}')
                for state,mode in [('off','无 CCM'),('on','有该配置 CCM')]] + controlled
    mono = [col(f'mono_{c}',f'{c} 光单次记录\n空白光源归一化') for c in 'RGB'] + [
        col('mono_rgb_raw','三次记录合并\n归一化采集通道'), col('mono_rgb_ccm','匹配 CCM 后\n负片通道预览'),
        col('mono_rgb_on','整卷 Dmin+Dmax\nBalanced 显示')]
    lights = [oldcol(old/'figures','source','场景颜色参照\n统一降一档显示'),
              oldcol(old/'figures','apd','有限波段 APD 参照\n整卷处理'),
              col('gh7_rgb_on','GH7 · RGB 光源\n匹配 CCM → 整卷处理'),
              col('gh7_d50_on','GH7 · D50\n匹配 CCM → 整卷处理')]
    optical = [lights[0], oldcol(old/'optical-print/figures','paper_ev+0','Ultra Endura 近似彩放\nD50 反射光 → XYZ → sRGB'),
               lights[1], col('mono_rgb_on','黑白三色分拍模型\nCCM → 整卷处理')]
    pairs = [('negative_stages',stages,'模拟负片：透射光与采集信号',
              '无片白场归一化不减去橙色片基。采集列以 sRGB 编码预览通道，不代表已标定的显示颜色。\nCCM 同步转换输入尺度；XYZ 列与原实验相同，保留光源色度。'),
             ('gh7_ccm',gh7,'同一白场基准，再比较 CCM 开关',
              '两侧均先按无片白场归一；CCM 不再承担白平衡差异。各自重新完成同一组 8 张的 V5 整卷定标。\nGH7 通道相对增益缺失，现有矩阵匹配仍待真实测量；本图不验证其标定精度。'),
             ('controlled_ccm',controlled,'相同测量目标，不同采集响应',
              '所有输入均使用 R＝G＝B＝1 的无片白场；开关 CCM 后分别整卷处理。\nIMX273 厂家 QE 图近似；同一染料网格标定方法。三色分拍为理想分色，不包含噪声和位移。'),
             ('all_architectures',all_arch,'三种采集方式：统一白场后的对照',
              '各配置分别标定至有限波段 APD 参照。每组使用相同 8 张负片；不是设备性能排名。'),
             ('mono_stages',mono,'三色分拍：三张黑白记录到彩色结果',
              '每次记录均按对应的无片照明归一化；三通道来自三次曝光，未减去片基。\n负片通道列只是诊断预览；最后一列经过整卷去色罩及显示。'),
             ('optical',optical,'同一负片：近似光学彩放与数字化',
              '相纸和数字化采用不同的成像与显示流程，不作为准确度排名。\n彩放模型与原实验相同；数字采集已统一无片白场并匹配 CCM。')]
    for name,columns,title,footer in pairs:
        board(out,(16,43),columns,f'{name}_examples',title,footer)
        for i,scenes in enumerate((SCENES[:4],SCENES[4:]),1):
            board(out,scenes,columns,f'{name}_{i}',title,footer)
    board(out,SCENES,lights,'two_lights_all_8','同一组 5207 负片，两套翻拍配置',
          '所有采集输入按无片白场归一；CCM 同步转换尺度。两套配置均重新完成 8 张整卷处理。\n光源和指定 CCM 同时变化，不能将差异仅归因于光源带宽；未按照片调色。')
    report['verification'] = dict(status='PASS', white_normalized_setups=5, replayed_rolls=10,
                                  frames_per_roll=8, png_pixels_and_icc_readback=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print(json.dumps(report['verification']),flush=True)


if __name__ == '__main__':
    main()
