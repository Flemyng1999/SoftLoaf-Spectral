"""Issue #2 local recipe workbench, using the float64 E100 reference.

Run ``python -m experiments.gui_recipe_server`` from the repository root.
The historical source data and generated files remain local experiments.
"""

import argparse
import base64
from collections import OrderedDict
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid
import zipfile

os.environ.setdefault('MPLCONFIGDIR', str(Path('artifacts/.matplotlib').resolve()))
os.environ.setdefault('XDG_CACHE_HOME', str(Path('artifacts/.cache').resolve()))

import colour
import numpy as np
from PIL import Image, ImageCms
import PyOpenColorIO as ocio
from scipy.optimize import brentq

from experiments.hsi_raw_lut import (AP1, D60, D65, SRGB, HIGH, LOW, apply_ocio,
    batched, build_reference, cat, color_kernel, csv, display_processor,
    interpolate, load_scene, sha)
from spectral_lut.metrics import srgb_code_error
from spectral_lut.export_metadata import lut_metadata
from spectral_lut.film import ReversalFilm, fit_neutral_amounts
from spectral_lut.display import (DisplayManager, VIEWS, TARGETS, migrate_display_defaults,
    ROUTE_DEFAULT_VIEWS, COLORIMETRIC_VIEW, DISPLAY_DEFAULTS_VERSION)
from spectral_lut.reference import (Cube, acescct_decode, acescct_encode,
    density_transmittance, quadrature_widths, smooth_reconstruction_basis)


class RecipeError(ValueError):
    def __init__(self, code, message, issues=None):
        super().__init__(message)
        self.code, self.issues = code, issues or []


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('utf-8')


def fingerprint(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def version(recipe):
    return {'recipe_id': recipe['id'], 'revision': recipe['revision'],
            'fingerprint': fingerprint(recipe)}


def negative_output_draft():
    """A declaration of missing standard inputs, never synthetic APD numbers."""
    return {'metric': 'APD', 'apd_standard': 'SMPTE ST 2065-2:2012',
            'adx_standard': 'SMPTE ST 2065-3:2012', 'value_type': 'float_density',
            'spectral_weights': None, 'spectral_coverage_nm': None,
            'normalization': None, 'base_density': None, 'channel_gains': None,
            'standard_conversion': {'name': 'APD/ADX-to-ACES',
                'reference': 'aces-core v1.2 (2019)', 'version': None,
                'status': 'unimplemented'}}


def template(route='slide'):
    stock = 'E100' if route == 'slide' else '5207'
    recipe = {'schema': 'softloaf.recipe/1', 'id': f'{route}-default',
            'name': f'{stock} · ' + {'slide': 'D50', 'negative': 'APD 草案', 'print': '光学放大草案'}[route],
            'revision': 1, 'route': route,
            'film': {'stock': stock, 'exposure_ev': 0},
            'scene': {'illuminant': 'D65'} if route=='slide' else {'illuminant':'CIE_D','temperature_k':5500},
            'viewing': {'illuminant': 'D50', 'gain': 1.8},
            'display': {'view': ROUTE_DEFAULT_VIEWS[route], 'defaults_version': DISPLAY_DEFAULTS_VERSION},
            'digitization': {'light': 'unconfigured', 'sensor': 'unconfigured', 'calibration': None},
            'printing': {'light': 'unconfigured', 'paper': 'Ultra Endura'}, 'asset_refs': {}}
    if route == 'negative':
        recipe['negative_output'] = negative_output_draft()
    return recipe


def material_issues(material,allow_signed_dyes=False):
    """Check declared quantities and axes before any spectral resampling."""
    issues = []
    def issue(field, message):
        issues.append({'field': 'film.custom_material.'+field, 'message': message})
    if not isinstance(material, dict) or material.get('schema') != 'softloaf.material/1':
        issue('schema', '材料需要 softloaf.material/1 完整格式。')
        return issues
    for key in ('name', 'source'):
        if not isinstance(material.get(key), str) or not material[key].strip():
            issue(key, '材料名称和来源不可为空。')
    specs = [('sensitivity', 'wavelengths_nm', ('R', 'G', 'B'), 'relative_energy_sensitivity', 'relative', (400, 720), 8192),
             ('characteristic', 'log_exposure', ('R', 'G', 'B'), 'status_a_density', 'D', None, 1024),
             ('dyes', 'wavelengths_nm', ('C', 'M', 'Y'), 'spectral_density', 'D', (400, 700), 8192)]
    for key, axis, labels, quantity, unit, coverage, maximum in specs:
        curve = material.get(key)
        if not isinstance(curve, dict) or curve.get('quantity') != quantity or curve.get('unit') != unit:
            issue(key, f'{key} 的量或单位不匹配：需要 {quantity} / {unit}。')
            continue
        try:
            samples = curve.get(axis)
            if not isinstance(samples, list) or not 2 <= len(samples) <= maximum or any(type(v) not in (int, float) for v in samples):
                raise ValueError()
            x = np.asarray(samples, dtype=np.float64)
            if not np.isfinite(x).all() or np.any(np.diff(x) <= 0):
                raise ValueError()
            if coverage and (x[0] > coverage[0] or x[-1] < coverage[1]):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            issue(key+'.'+axis, f'{axis} 必须是有限、严格递增的数字数组，样本数 2–{maximum}'+(f'，完整覆盖 {coverage[0]}–{coverage[1]} nm。' if coverage else '；此轴为 log10 相对曝光，不是波长。'))
            continue
        values = curve.get('channels')
        if not isinstance(values, dict) or set(values) != set(labels):
            issue(key+'.channels', '需要完整且仅有 '+' / '.join(labels)+' 三通道。')
            continue
        for channel in labels:
            raw = values[channel]
            try:
                if not isinstance(raw, list) or len(raw) != len(x) or any(type(v) not in (int, float) for v in raw):
                    raise ValueError()
                y = np.asarray(raw, dtype=np.float64)
                if not np.isfinite(y).all() or (not (allow_signed_dyes and key=='dyes') and np.any(y < 0)):
                    raise ValueError()
                if key == 'characteristic' and np.any(np.diff(y) > 1e-12):
                    issue(key+'.channels.'+channel, '反转片的 Status A 密度须随 log10 曝光递减或持平。')
                if key == 'sensitivity' and not np.any(np.interp(np.arange(400, 721, 10), x, y) > 0):
                    issue(key+'.channels.'+channel, '感光通道在 400–720 nm 内不能全为零。')
            except (ValueError, TypeError, OverflowError):
                issue(key+'.channels.'+channel, '通道需要与横轴等长的有限非负数字数组。')
    return issues


def validate_recipe(recipe, source_refs=None):
    """Validate without silently substituting unknown materials or sources."""
    issues = []
    if not isinstance(recipe, dict):
        return {'ok': False, 'normalized_recipe': None, 'computable': False,
                'issues': [{'field': 'recipe', 'message': '配方必须是 JSON 对象。'}]}
    result = migrate_display_defaults(recipe)
    def issue(field, message):
        issues.append({'field': field, 'message': message})
    def number(value, low, high):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value) and low <= value <= high
    if result.get('schema') != 'softloaf.recipe/1':
        issue('schema', '不支持的配方版本。')
    for field in ('id', 'name'):
        if not isinstance(result.get(field), str) or not result[field].strip() or len(result[field]) > 200:
            issue(field, '需要非空名称，最多 200 个字符。')
    if type(result.get('revision')) is not int or result['revision'] < 1:
        issue('revision', '版本号必须是正整数。')
    route = result.get('route')
    if route not in ('slide', 'negative', 'print'):
        issue('route', '未知的固定流程。')
    for field in ('film', 'scene', 'viewing', 'display', 'digitization', 'printing', 'asset_refs'):
        if not isinstance(result.get(field), dict):
            issue(field, '需要完整的节点设置。')
            result[field] = {}
    film, viewing = result['film'], result['viewing']
    if route == 'negative':
        # Old capture settings describe another model. Retain the original file
        # and require an explicit new APD draft rather than pretending to replay it.
        if result['digitization'] != {'light': 'unconfigured', 'sensor': 'unconfigured', 'calibration': None}:
            issues.append({'field': 'digitization', 'code': 'legacy_digitization',
                'message': '此旧草案含已配置的翻拍设备或定标，不能作为 APD 配方复现。请保留原文件，明确另建 APD 草案。'})
        if 'negative_output' not in result:
            result['negative_output'] = negative_output_draft()
        if result['negative_output'] != negative_output_draft():
            issue('negative_output', '当前仅保存 APD 标准输出草案，标准权重、归一化、Dmin、通道增益与转换版本待补。自定义权重不能仍称标准 APD。')
    if film.get('stock') != ('E100' if route == 'slide' else '5207'):
        issue('film.stock', '胶片与流程不匹配，不能替换为默认胶片。')
    if not number(film.get('exposure_ev'), -4, 4):
        issue('film.exposure_ev', '胶片曝光范围为 −4 到 +4 EV。')
    if film.get('custom_material') is not None:
        issues.extend(material_issues(film['custom_material']))
        if route != 'slide':
            issue('film.custom_material', '自定义材料当前仅适用于 E100 参考流程。')
    scene = result['scene']
    if scene.get('illuminant') not in ('D65', 'CIE_D'):
        issue('scene.illuminant', '拍摄照明支持 D65 或 CIE 标准日光。')
    elif scene['illuminant'] == 'CIE_D' and not number(scene.get('temperature_k'), 4000, 10000):
        issue('scene.temperature_k', '标准日光色温范围为 4000–10000 K。')
    elif scene['illuminant'] == 'D65' and 'temperature_k' in scene:
        issue('scene.temperature_k', '请明确选择标准日光色温或固定 D65。')
    if not number(viewing.get('gain'), 0.1, 8):
        issue('viewing.gain', '观看增益范围为 0.1 到 8。')
    illuminant = viewing.get('illuminant')
    if illuminant not in ('D50', 'D65', 'custom'):
        issue('viewing.illuminant', '当前支持 D50、D65 或完整自定义 SPD。')
    custom = viewing.get('custom_spd')
    if illuminant == 'custom':
        valid = isinstance(custom, dict)
        if valid:
            valid = custom.get('quantity') == 'relative_energy_spd' and custom.get('unit') in ('relative', 'a.u.')
            valid = valid and all(isinstance(custom.get(k), str) and bool(custom[k].strip()) for k in ('name', 'source'))
            try:
                valid = valid and all(isinstance(custom.get(k), list) and all(type(v) in (int, float) for v in custom[k]) for k in ('wavelengths_nm', 'values'))
                x = np.asarray(custom.get('wavelengths_nm'), dtype=np.float64)
                y = np.asarray(custom.get('values'), dtype=np.float64)
                valid = valid and x.ndim == y.ndim == 1 and x.shape == y.shape and len(x) >= 2
                valid = valid and np.isfinite(x).all() and np.isfinite(y).all() and np.all(np.diff(x) > 0)
                valid = valid and x[0] <= 400 and x[-1] >= 700 and np.all(y >= 0) and np.any(np.interp(np.arange(400, 701, 2), x, y) > 0)
            except (TypeError, ValueError, IndexError):
                valid = False
        if not valid:
            issue('viewing.custom_spd', '需要来源、相对能量 SPD、严格递增且完整覆盖 400–700 nm 的非负样本。')
    elif custom is not None:
        issue('viewing.custom_spd', '内置光源与自定义 SPD 冲突；请明确选用哪一个。')
    if result['display'].get('view') not in VIEWS:
        issue('display.view', '请选择可用的 OCIO 显示外观。')
    if type(result['display'].get('defaults_version')) is not int or result['display']['defaults_version']!=DISPLAY_DEFAULTS_VERSION:
        issue('display.defaults_version', '不支持的显示管线版本。')
    if result['display'].get('target', 'sRGB') not in TARGETS:
        issue('display.target', '请选择 sRGB、Display P3 或 Rec.709 / Rec.1886。')
    if source_refs is not None and route == 'slide':
        if result['asset_refs'] and result['asset_refs'] != source_refs:
            issue('asset_refs', '配方的材料或变换来源与当前模型不匹配。')
        elif not result['asset_refs']:
            result['asset_refs'] = copy.deepcopy(source_refs)
    if issues:
        return {'ok': False, 'normalized_recipe': result, 'computable': False, 'issues': issues}
    computable = route == 'slide'
    if not computable:
        issue('route', '5207 材料与 APD 标准密度／标准输出转换尚未实现；可保存草案，不能计算或导出 LUT。' if route == 'negative' else
              '5207 材料、光学放大与相纸模型尚未实现；可保存草案，不能计算或导出 LUT。')
    return {'ok': True, 'normalized_recipe': result, 'computable': computable, 'issues': issues}


class E100Model:
    def __init__(self, archive, opendrt, output, core=None,preview_long_edge=192,preview_short_edge=None):
        self.core = core
        self.metal = None
        self.archive, self.output = Path(archive), Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        materials = self.archive/'output/reversal-E100/data'
        source_paths = {name: materials/name for name in ('E100_characteristic_RGB.csv', 'E100_linear_sensitivity_RGB.csv', 'E100_dye_density_CMY.csv')}
        source_paths.update({name: self.archive.parent/'data'/name for name in ('CIE_xyz_official.csv', 'CIE_std_illum_D50.csv', 'CIE_std_illum_D65.csv')})
        source_paths['StatusA_model.npz'] = self.archive/'output/reversal-E100/intermediate/model.npz'
        source_paths['OpenDRT_v1.0.0_mini-config_v2.zip'] = Path(opendrt)
        self.sources = {name: sha(path) for name, path in source_paths.items()}
        self.film, self.source_to_ap1, _, self.source_light, self.reference_settings = build_reference(self.archive)
        self.basis = smooth_reconstruction_basis(self.source_to_ap1)
        self.source_wavelengths = csv(materials/'E100_linear_sensitivity_RGB.csv', 1)[:, 0]
        self._scene_lights, self._scene_light_lock = {}, threading.Lock()
        self.view_wavelengths = csv(materials/'E100_dye_density_CMY.csv', 1)[:, 0]
        sensitivity = csv(materials/'E100_linear_sensitivity_RGB.csv', 1)
        characteristic = csv(materials/'E100_characteristic_RGB.csv', 1)
        dyes = csv(materials/'E100_dye_density_CMY.csv', 1)
        def curve(table, axis, labels, quantity, unit):
            return {axis: table[:, 0].tolist(), 'channels': {label: table[:, i+1].tolist() for i, label in enumerate(labels)},
                    'quantity': quantity, 'unit': unit}
        self.original_material = {'schema': 'softloaf.material/1', 'name': 'E100 本地参考',
            'source': 'Local archived E100_characteristic_RGB.csv, E100_linear_sensitivity_RGB.csv, E100_dye_density_CMY.csv; permissions pending',
            'sensitivity': curve(sensitivity, 'wavelengths_nm', 'RGB', 'relative_energy_sensitivity', 'relative'),
            'characteristic': curve(characteristic, 'log_exposure', 'RGB', 'status_a_density', 'D'),
            'dyes': curve(dyes, 'wavelengths_nm', 'CMY', 'spectral_density', 'D')}
        self.exposure_normalization = .18*np.sum(sensitivity[:, 1:]*self.source_light[:, None]*quadrature_widths(self.source_wavelengths)[:, None], axis=0)
        with np.load(self.archive/'output/reversal-E100/intermediate/model.npz') as archived:
            self.status_a_weights = np.array(archived['StatusA_weights'], dtype=np.float64)
        self.material_cache, self.material_lock = OrderedDict(), threading.Lock()
        self.cmfs = interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'), self.view_wavelengths)
        self.lights = {name: interpolate(csv(self.archive.parent/f'data/CIE_std_illum_{name}.csv'), self.view_wavelengths)[:, 0] for name in ('D50', 'D65')}
        self.original_lights = {}
        for name in ('D50', 'D65'):
            data = csv(self.archive.parent/f'data/CIE_std_illum_{name}.csv')
            self.original_lights[name] = {'name': name, 'source': f'CIE_std_illum_{name}.csv',
                'wavelengths_nm': data[:, 0].tolist(), 'values': data[:, 1].tolist(),
                'quantity': 'relative_energy_spd', 'unit': 'relative'}
        d50_kernel = color_kernel(self.view_wavelengths, self.lights['D50'], self.cmfs)
        self.fixed_adaptation = cat(d50_kernel.sum(axis=0), D65)
        default, config_path = display_processor(Path(opendrt), self.output/'opendrt')
        config = ocio.Config.CreateFromFile(str(config_path.resolve()))
        self.display_manager = DisplayManager(config, config_path)
        self.config = self.display_manager.config
        self.displays = {view: self.display_manager.processors['sRGB', view] for view in VIEWS}
        self.display_groups = {view: self.display_group(view) for view in VIEWS}
        with zipfile.ZipFile(opendrt) as package:
            self.opendrt_license = package.read('OpenDRT_v1.0.0_mini-config_v2/LICENSE.md')
        if self.sources != {name: sha(path) for name, path in source_paths.items()}:
            raise RuntimeError('Source files changed while the model was being loaded.')
        self.source_refs = {'model': 'E100-reference/1', 'sha256': self.sources}
        self.original_material_metadata = {'custom': False, 'name': 'E100 本地参考',
            'fingerprint': fingerprint(self.original_material),
            'neutral_StatusA_max_error_D': self.reference_settings['neutral_StatusA_max_error_D'],
            'gray_logH_anchor': float(self.film.gray_log_h),
            'sensitivity_normalization': 'fixed original E100 per-channel 18% gray exposure denominators; custom amplitude retained',
            'sensitivity_denominators': self.exposure_normalization.tolist(),
            'calibration': 'local neutral-density fit only; not full measured film color calibration'}
        self.samples = [
            {'id': 'gray18', 'name': '18% 灰', 'input_srgb': [float(colour.cctf_encoding(.18, function='sRGB'))]*3},
            {'id': 'skin', 'name': '暖色', 'input_srgb': [.72, .47, .34]},
            {'id': 'red', 'name': '红色', 'input_srgb': [.8, .16, .12]},
            {'id': 'green', 'name': '绿色', 'input_srgb': [.18, .58, .25]},
            {'id': 'blue', 'name': '蓝色', 'input_srgb': [.16, .35, .78]},
            {'id': 'white', 'name': '亮灰', 'input_srgb': [.88]*3}]
        patches = np.array([sample['input_srgb'] for sample in self.samples]).reshape(2, 3, 3)
        chart = np.repeat(np.repeat(patches, 64, axis=0), 64, axis=1)
        self.inputs = {'chart': self.srgb_to_ap1(chart)}
        self.original_scene_xyz = {}
        self.measured_inputs = {}
        self.verification_input_sources = {'chart': 'six representative encoded sRGB patches, not measured ColorChecker data'}
        self.input_info = [{'id': 'chart', 'name': '代表性色块', 'kind': 'rgb_chart', 'width': 192, 'height': 128}]
        if (self.archive/'data/hsi_43.zip').exists():
            hsi = load_scene(self.archive, 43)
            h, w = hsi.shape[:2]
            scale=min(1.,preview_short_edge/min(h,w) if preview_short_edge else preview_long_edge/max(h,w));pw,ph=max(1,round(w*scale)),max(1,round(h*scale))
            yy = np.minimum((np.arange(ph)*h/ph).astype(int), h-1)
            xx = np.minimum((np.arange(pw)*w/pw).astype(int), w-1)
            sampled = hsi[yy[:, None], xx[None, :]]
            self.measured_inputs['scene43_rgb'] = sampled
            self.inputs['scene43_rgb'] = sampled @ self.source_to_ap1
            source_xyz = color_kernel(self.source_wavelengths, self.source_light,
                interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'), self.source_wavelengths))
            self.original_scene_xyz['scene43_rgb'] = sampled @ source_xyz @ cat(source_xyz.sum(axis=0), D65).T
            self.verification_input_sources['scene43_rgb'] = {'source': 'hsi_43.zip', 'sha256': sha(self.archive/'data/hsi_43.zip'),
                'conversion': 'finite-band D65 XYZ→Bradford D60→AP1; source-limited nearest-neighbour sampling',
                'native_size':[w,h],'preview_size':[pw,ph],'preview_long_edge':preview_long_edge if preview_short_edge is None else None,'preview_short_edge':preview_short_edge}
            self.input_info.append({'id': 'scene43_rgb', 'name': '内置 RGB 照片', 'kind': 'rgb_photo', 'width': pw, 'height': ph})

    @staticmethod
    def srgb_to_ap1(srgb):
        linear = colour.cctf_decoding(np.asarray(srgb), function='sRGB')
        return linear @ SRGB.matrix_RGB_to_XYZ.T @ cat(D65, D60).T @ AP1.matrix_XYZ_to_RGB.T

    def light(self, illuminant):
        if isinstance(illuminant, dict):
            return np.interp(self.view_wavelengths, illuminant['wavelengths_nm'], illuminant['values'])
        return self.lights[illuminant]

    def scene_light(self, temperature_k=None):
        if temperature_k is None or temperature_k == 6500:
            return self.source_light
        if type(temperature_k) not in (int, float) or not np.isfinite(temperature_k) or not 4000 <= temperature_k <= 10000:
            raise RecipeError('invalid_daylight', '日光色温范围为 4000–10000 K。')
        with self._scene_light_lock:
            if temperature_k not in self._scene_lights:
                xy = colour.temperature.CCT_to_xy_CIE_D(temperature_k*1.4388/1.4380)
                sd = colour.sd_CIE_illuminant_D_series(xy)
                light = np.interp(self.source_wavelengths, sd.wavelengths, sd.values)
                cmf = interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'), self.source_wavelengths)
                weights = cmf[:, 1]*quadrature_widths(self.source_wavelengths)
                light *= (self.source_light@weights)/(light@weights)
                light.setflags(write=False)
                if len(self._scene_lights) >= 64:
                    self._scene_lights.pop(next(iter(self._scene_lights)))
                self._scene_lights[temperature_k] = light
            return self._scene_lights[temperature_k]

    def render(self, xyz, display, target='sRGB'):
        return np.clip(apply_ocio(self.display_manager.processors[target, display], xyz), 0, 1)

    def display_result(self, xyz, view, target='sRGB'):
        rgb = self.render(xyz, view, target)
        return {'display_rgb': rgb, **({'sRGB': rgb} if target == 'sRGB' else {})}

    def display_group(self, view, target='sRGB'):
        return self.display_manager.groups[target, view]

    def display_profile(self, target='sRGB'):
        return self.display_manager.profiles[target]

    def material(self, custom=None):
        if custom is None:
            return self.film, self.original_material_metadata
        key = fingerprint(custom)
        # Fit once per complete material snapshot. Serializing fits also avoids
        # duplicate work from overlapping preview/validation/export requests.
        with self.material_lock:
            if key in self.material_cache:
                value = self.material_cache.pop(key)
                self.material_cache[key] = value
            else:
                try:
                    value = self.fit_material(custom, key)
                except RecipeError as error:
                    value = (error.code, str(error), error.issues)
                self.material_cache[key] = value
                while len(self.material_cache) > 16:
                    self.material_cache.popitem(last=False)
            if len(value) == 3:
                raise RecipeError(value[0], value[1], value[2])
            return value

    def material_fit_tolerance(self, custom):
        return .001

    def fit_material(self, custom, key):
        problems = material_issues(custom)
        if problems:
            raise RecipeError('invalid_material', problems[0]['message'], problems)
        def table(name, axis, labels, grid):
            curve = custom[name]
            return np.column_stack([np.interp(grid, curve[axis], curve['channels'][label]) for label in labels])
        sensitivity = table('sensitivity', 'wavelengths_nm', 'RGB', self.source_wavelengths)
        dyes = table('dyes', 'wavelengths_nm', 'CMY', self.view_wavelengths)
        target = np.column_stack([custom['characteristic']['channels'][label] for label in 'RGB'])
        logs = np.asarray(custom['characteristic']['log_exposure'], dtype=np.float64)
        tolerance=self.material_fit_tolerance(custom)
        try:
            if not np.any(dyes > 0):
                raise ValueError('zero dyes')
            amounts = fit_neutral_amounts(dyes, self.status_a_weights, target)
            weights = self.status_a_weights/self.status_a_weights.sum(axis=0)
            predicted = -np.log10(density_transmittance(amounts, dyes) @ weights)
            error = float(np.max(np.abs(predicted-target)))
            if not np.isfinite(error) or error > tolerance:
                raise ValueError('incompatible density')
        except (RuntimeError, ValueError, FloatingPointError, np.linalg.LinAlgError):
            raise RecipeError('incompatible_material', f'染料与特性曲线无法完成 ≤{tolerance:g} D 的中性密度拟合；未替换原材料。',
                [{'field': 'film.custom_material', 'message': '请检查染料、Status A 密度和三通道的相容性。'}]) from None
        d50 = color_kernel(self.view_wavelengths, self.lights['D50'], self.cmfs)
        def gray_y(log_h):
            a = np.array([np.interp(log_h, logs, amounts[:, i]) for i in range(3)])
            return float(density_transmittance(a, dyes) @ d50[:, 1])
        try:
            anchor = brentq(lambda x: gray_y(x)-.1, logs[0], logs[-1])
        except ValueError:
            raise RecipeError('incompatible_material', '材料特性范围无法解出固定 D50、Y=0.1 的中性曝光锚点；未替换原材料。',
                [{'field': 'film.custom_material.characteristic', 'message': '需要覆盖固定材料灰锚点的曝光和密度范围。'}]) from None
        exposure = sensitivity*self.source_light[:, None]*quadrature_widths(self.source_wavelengths)[:, None]/self.exposure_normalization
        if not np.isfinite(exposure).all() or np.any(exposure.sum(axis=0) <= 0):
            raise RecipeError('invalid_material', '自定义感光曲线没有有限、非零的 D65 曝光响应。')
        film = ReversalFilm(logs, amounts, exposure, dyes, self.film.view_kernel, anchor)
        for array in (logs, amounts, exposure, dyes):
            array.setflags(write=False)
        metadata = {**self.original_material_metadata, 'custom': True, 'name': custom['name'],
            'label': '自定义（基于 E100）', 'source': custom['source'], 'fingerprint': key,
            'neutral_StatusA_max_error_D': error, 'neutral_fit_limit_D':tolerance, 'gray_logH_anchor': float(anchor),
            'anchor_policy': 'refit from custom dyes/characteristic at fixed D50 Y=0.1; sensitivity amplitude does not alter normalization or this anchor'}
        return film, metadata

    def sample(self, rgb, exposure_ev=0, viewing_light='D50', viewing_gain=1.8, display=COLORIMETRIC_VIEW, custom_material=None, scene_temperature_k=None, display_target='sRGB'):
        film, _ = self.material(custom_material)
        exposure_kernel = film.exposure_kernel if scene_temperature_k is None or scene_temperature_k == 6500 else film.exposure_kernel*(self.scene_light(scene_temperature_k)/self.source_light)[:, None]
        rgb = np.asarray(rgb, dtype=np.float64)
        if self.core is not None:
            light = self.light(viewing_light)
            divisor = np.sum(light*self.cmfs[:, 1]*quadrature_widths(self.view_wavelengths))
            if divisor <= 0:
                raise RecipeError('invalid_spd', '观看光在可见波段没有有效亮度。')
            result = self.core.reversal(rgb, film, self.basis,
                color_kernel(self.view_wavelengths, light, self.cmfs), light/divisor,
                self.fixed_adaptation, exposure_ev, viewing_gain, exposure_kernel=exposure_kernel)
            result.update(self.display_result(result['XYZ'], display, display_target))
            return result
        reflectance = np.maximum(rgb @ self.basis, 0)
        h = reflectance @ exposure_kernel * np.exp2(exposure_ev)
        logs = film.gray_log_h + np.log10(np.maximum(h, 1e-30))
        amounts = np.stack([np.interp(logs[..., i], film.log_h, film.amounts[:, i]) for i in range(3)], axis=-1)
        transmission = density_transmittance(amounts, film.dyes)
        light = self.light(viewing_light)
        divisor = np.sum(light*self.cmfs[:, 1]*quadrature_widths(self.view_wavelengths))
        if divisor <= 0:
            raise RecipeError('invalid_spd', '观看光在可见波段没有有效亮度。')
        viewed = transmission*light/divisor*viewing_gain
        xyz_raw = transmission @ color_kernel(self.view_wavelengths, light, self.cmfs)*viewing_gain
        xyz = xyz_raw @ self.fixed_adaptation.T
        return {'reflectance': reflectance, 'exposure': h, 'dye_amounts': amounts,
                'transmission': transmission, 'viewed_spectrum': viewed, 'XYZ_view': xyz_raw,
                'XYZ': xyz, **self.display_result(xyz, display, display_target)}

    def parameters(self, recipe):
        view = recipe['viewing']
        return {'exposure_ev': recipe['film']['exposure_ev'],
                'viewing_light': view['custom_spd'] if view['illuminant'] == 'custom' else view['illuminant'],
                'viewing_gain': view['gain'], 'display': recipe['display']['view'],
                'display_target': recipe['display'].get('target', 'sRGB'),
                'custom_material': recipe['film'].get('custom_material'),
                'scene_temperature_k': recipe['scene'].get('temperature_k')}

    def validate(self, recipe, compute=False):
        result = validate_recipe(recipe, self.source_refs)
        if not result['ok'] or (compute and not result['computable']):
            code = 'unsupported' if result['ok'] else result['issues'][0].get('code', 'invalid_recipe')
            raise RecipeError(code, result['issues'][0]['message'], result['issues'])
        if result['computable']:
            self.material(result['normalized_recipe']['film'].get('custom_material'))
        return result


def spectrum(quantity, unit, wavelengths, **series):
    return {'kind': 'spectrum', 'quantity': quantity, 'unit': unit,
            'wavelengths_nm': np.asarray(wavelengths).tolist(),
            'series': [{'name': name, 'values': np.asarray(value).tolist()} for name, value in series.items()]}


def channels(quantity, unit, labels, values):
    return {'kind': 'channels', 'quantity': quantity, 'unit': unit,
            'labels': list(labels), 'values': np.asarray(values).tolist()}


def png_preview(encoded, icc_profile=None):
    pixels = np.rint(np.clip(encoded, 0, 1)*255).astype(np.uint8)
    output = io.BytesIO()
    icc = icc_profile if icc_profile is not None else ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    from spectral_app.preview_codec import interactive
    Image.fromarray(pixels).save(output, format='PNG', icc_profile=icc, compress_level=1 if interactive() else 6)
    if not interactive():np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(output.getvalue()))), pixels)
    return {'kind': 'image', 'width': pixels.shape[1], 'height': pixels.shape[0],
            'data_url': 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode('ascii')}


class Workbench:
    def __init__(self, model):
        self.model = model
        self.downloads = {}
        self.export_lock = threading.Lock()

    def bootstrap(self):
        templates = []
        for route, label in [('slide', '反转片 · 透射观看'), ('negative', '负片 · APD 输出'), ('print', '负片 · 光学放大')]:
            result = validate_recipe(template(route), self.model.source_refs)
            templates.append({'id': route, 'name': label,
                'description': '光谱计算参考' if route == 'slide' else '材料与 APD 标准密度／标准输出尚未实现，可保存配方草案' if route == 'negative' else '材料与光学放大、相纸模型尚未实现，可保存配方草案',
                'available': result['computable'], 'recipe': result['normalized_recipe']})
        return {'ok': True, 'default_recipe': templates[0]['recipe'], 'templates': templates,
            'inputs': self.model.input_info, 'samples': self.model.samples,
            'spectral_assets': {'E100': copy.deepcopy(self.model.original_material),
                                'xyz_observer': spectrum('cie1931_xyz_matching_functions', 'relative',
                                    self.model.view_wavelengths, X=self.model.cmfs[:, 0],
                                    Y=self.model.cmfs[:, 1], Z=self.model.cmfs[:, 2]),
                                'viewing_lights': copy.deepcopy(self.model.original_lights)},
            'capabilities': {'routes': [{'id': t['id'], 'label': t['name'], 'computable': t['available'],
                **({'density_metric': 'APD', 'capture_model': False, 'standard_conversion_implemented': False} if t['id'] == 'negative' else {})} for t in templates],
                'viewing_lights': [{'id': key, 'label': key} for key in ('D50', 'D65', 'custom')],
                'display_views': [{'id': key, 'label': VIEWS[key]} for key in self.model.displays],
                'display_defaults': dict(ROUTE_DEFAULT_VIEWS),
                'ocio_config': dict(self.model.display_manager.config_metadata),
                'display_targets': [{'id': key, 'label': value['label']} for key, value in TARGETS.items()],
                'raw_supported': False, 'source': 'E100 local float64 neutral-fitted reference; spectral prior estimated from ordinary AP1 RGB',
                'compute_backend': 'C++23 float64 / ABI 1' if self.model.core is not None else 'Python NumPy float64 reference',
                'encoding': 'linear ACEScg/AP1 D60 input; LUT input ACEScct AP1 D60',
                'film_exposure_ev': {'min': -4, 'max': 4}, 'viewing_gain': {'min': .1, 'max': 8},
                'scene_daylight': {'min_k': 4000, 'max_k': 10000, 'step_k': 100, 'default_k': 6500},
                'custom_spd': True, 'custom_material': True, 'material_schema': 'softloaf.material/1',
                'material_limits': {'spectral_samples_max': 8192, 'characteristic_samples_max': 1024},
                'lut_grid': 65, 'lut_grid_options': [17, 33, 65, 129],
                'lut_grid_range': {'min': 2, 'max': 129}, 'interpolation': 'tetrahedral',
                'export_purposes': ['pipeline', 'internal', 'display'], 'pipeline_format': 'CTF',
                'pipeline_format_note': 'CLF cannot encode the packaged InverseLUT1D operation; CTF preserves it without another approximation'}}

    def conditions(self, recipe):
        view = recipe['viewing']
        _, material_metadata = self.model.material(recipe['film'].get('custom_material'))
        light = view['custom_spd'] if view['illuminant'] == 'custom' else {
            'name': view['illuminant'], 'source': f'CIE_std_illum_{view["illuminant"]}.csv',
            'sha256': self.model.sources[f'CIE_std_illum_{view["illuminant"]}.csv']}
        return {'observer': 'CIE 1931 2 degree', 'input': 'scene-linear ACEScg/AP1 D60; no RAW decoding or camera SSF assumed',
            'compute_backend': 'C++23 float64 / ABI 1' if self.model.core is not None else 'Python NumPy float64 reference',
            'compute_kernel_sha256': self.model.core.sha256 if self.model.core is not None else None,
            'spectral_prior': 'float64 minimum-first-difference, regularization 1e-8; nonnegative projection; no upper reflectance cap',
            'scene_illuminant': 'CIE D65 energy SPD' if recipe['scene']['illuminant'] == 'D65' else 'CIE D-series simulated daylight energy SPD',
            'scene_temperature_k': recipe['scene'].get('temperature_k', 6500),
            'scene_light_spectrum': spectrum('relative_energy_spd', 'relative', self.model.source_wavelengths,
                SPD=self.model.scene_light(recipe['scene'].get('temperature_k'))),
            'daylight_model': {'method': 'CIE D series; nominal K × 1.4388/1.4380; M1/M2 rounded to 3 places; 6500 K uses frozen original D65',
                'colour_version': colour.__version__},
            'scene_light_normalization': 'same finite-band photopic Y as original D65; original per-layer exposure denominators and gray anchor frozen',
            'input_reference_illuminant': 'fixed D65; unchanged by simulated scene daylight',
            'exposure_wavelengths_nm': self.model.source_wavelengths.tolist(),
            'view_wavelengths_nm': self.model.view_wavelengths.tolist(), 'viewing_light': light,
            'viewing_normalization': 'per-light perfect-transmitter Y=1 over 400–700 nm before viewing gain',
            'adaptation': 'fixed finite-band D50 white to D65 Bradford for all lights; no automatic adaptation to replacement light',
            'viewing_gain': view['gain'], 'film_exposure_ev': recipe['film']['exposure_ev'],
            'material_gray_logH_anchor': material_metadata['gray_logH_anchor'],
            'material': copy.deepcopy(material_metadata),
            'exposure_anchor': 'layerwise flat 18% gray; frozen material fit; not absolute ISO or shutter exposure',
            'density': 'effective CMY optical density, base included; archived finite-band Status A neutral fit, not full film calibration',
            'output_domain': 'observed XYZ under the declared transmission viewing conditions; not original scene radiance',
            'display': self.model.display_manager.metadata(recipe['display']['view'], recipe['display'].get('target','sRGB')),
            'sources': self.model.source_refs, 'rights': 'local experimental inputs; source redistribution permissions pending'}

    def evaluate_one(self, recipe, image, point, spectra=None, spectral_point=None,input_ev=0):
        params = self.model.parameters(recipe)
        compute = self.model.sample if spectra is None else self.model.sample_spectra
        gpu=getattr(self.model,'metal',None)
        streaming=getattr(self,'image_previews',None)
        preview=streaming.render(image if spectra is None else spectra,recipe,spectral=spectra is not None,input_ev=input_ev) if streaming else None
        output = None if streaming else gpu.render(image if spectra is None else spectra,recipe,spectral=spectra is not None,input_ev=input_ev) if gpu else batched(lambda x: compute(x, **params)['display_rgb'], image if spectra is None else spectra, chunk=2048)
        sample = compute(point if spectra is None else spectral_point, **params)
        _, material_metadata = self.model.material(params['custom_material'])
        material_curves = params['custom_material'] or self.model.original_material
        source = self.model.source_wavelengths
        viewed = self.model.view_wavelengths
        input_ap1 = channels('linear_AP1_D60', 'relative', ['R', 'G', 'B'], point)
        reflectance = spectrum('estimated_spectral_reflectance_factor', 'relative', source, R=sample['reflectance'])
        incident = spectrum('relative_spectral_exposure', 'relative', source,
            H=sample['reflectance']*self.model.scene_light(params['scene_temperature_k'])*np.exp2(recipe['film']['exposure_ev']))
        transmission = spectrum('spectral_transmittance', 'fraction', viewed, T=sample['transmission'])
        radiance = spectrum('relative_viewed_spectral_radiance', 'relative per nm', viewed, L=sample['viewed_spectrum'])
        xyz_view = channels('observed_XYZ_fixed_band', 'relative Y', ['X', 'Y', 'Z'], sample['XYZ_view'])
        xyz = channels('adapted_XYZ_D65', 'relative Y', ['X', 'Y', 'Z'], sample['XYZ'])
        srgb = channels('encoded_'+recipe['display'].get('target','sRGB'), '0–1', ['R', 'G', 'B'], sample['display_rgb'])
        nodes = {
            'estimate': {'name': 'RGB 光谱估计', 'input': input_ap1, 'output': reflectance,
                'details': {'method': 'minimum-first-difference prior + nonnegative projection; estimated, not measured'}},
            'light': {'name': '拍摄日光', 'input': spectrum('relative_energy_spd', 'relative', source, SPD=self.model.scene_light(params['scene_temperature_k'])), 'output': incident,
                'details': {'illuminant': recipe['scene']['illuminant'], 'temperature_k': recipe['scene'].get('temperature_k', 6500), 'estimated_reflectance': reflectance, 'exposure_ev': recipe['film']['exposure_ev'],
                    'layer_exposures': channels('normalized_layer_exposure', 'relative', ['R', 'G', 'B'], sample['exposure'])}},
            'film': {'name': 'E100 冲洗后胶片', 'input': incident, 'output': transmission,
                'details': {'material': copy.deepcopy(material_metadata),
                    'material_curves': copy.deepcopy(material_curves),
                    'dye_amounts': channels('effective_CMY_amount', 'relative', ['C', 'M', 'Y'], sample['dye_amounts']),
                    'density': spectrum('optical_density', 'D', viewed, D=-np.log10(sample['transmission']))}},
            'view': {'name': '透射观看', 'input': transmission, 'output': radiance,
                'details': {'light': spectrum('relative_energy_spd', 'relative', viewed, SPD=self.model.light(params['viewing_light'])), 'gain': recipe['viewing']['gain']}},
            'interface': {'name': '观察者与白点', 'input': radiance, 'output': xyz,
                'details': {'observed_xyz': xyz_view, 'adaptation': 'fixed D50 reference white Bradford to D65'}},
            'display': {'name': '显示输出', 'input': xyz, 'output': srgb,
                'details': {**self.model.display_manager.metadata(recipe['display']['view'],recipe['display'].get('target','sRGB')),
                    'process': self.model.display_manager.trace(sample['XYZ'],recipe['display']['view'],recipe['display'].get('target','sRGB'))}}}
        return {'preview': preview or png_preview(output, self.model.display_profile(recipe['display'].get('target','sRGB'))), 'nodes': nodes,
                'sample': {'input_ap1': np.asarray(point).tolist(), 'xyz_d65': sample['XYZ'].tolist(), 'display_rgb': sample['display_rgb'].tolist(), 'display_target': recipe['display'].get('target','sRGB'), **({'srgb':sample['display_rgb'].tolist()} if recipe['display'].get('target','sRGB')=='sRGB' else {})}}

    def validate_recipe(self,recipe,compute=False):
        return self.model.validate(recipe,compute=compute)

    def evaluate(self, request):
        recipe = self.validate_recipe(request.get('recipe'), compute=True)['normalized_recipe']
        baseline = request.get('baseline')
        if baseline is not None:
            baseline = self.validate_recipe(baseline, compute=True)['normalized_recipe']
        input_spec = request.get('input') or {'id': 'scene43_rgb' if 'scene43_rgb' in self.model.inputs else 'chart', 'exposure_ev': 0}
        selection = request.get('selection') or {'x': .5, 'y': .5, 'sample_id': self.model.samples[0]['id']}
        if not isinstance(input_spec, dict) or input_spec.get('id') not in self.model.inputs:
            raise RecipeError('invalid_input', '请选择已提供的 RGB 试片；当前不读取 RAW。')
        exposure = input_spec.get('exposure_ev', 0)
        if isinstance(exposure, bool) or not isinstance(exposure, (int, float)) or not np.isfinite(exposure) or not -4 <= exposure <= 4:
            raise RecipeError('invalid_input', '输入曝光范围为 −4 到 +4 EV。')
        if not isinstance(selection, dict):
            raise RecipeError('invalid_selection', '请选择图像上的一点。')
        gpu=getattr(self.model,'metal',None)
        image = self.model.inputs[input_spec['id']]
        streamed=bool(getattr(self,'image_previews',None))
        if not gpu and not streamed:image=image*np.exp2(exposure)
        if input_spec['id'] == 'chart':
            patch = next((s for s in self.model.samples if s['id'] == selection.get('sample_id', self.model.samples[0]['id'])), None)
            if patch is None:
                raise RecipeError('invalid_selection', '未知的代表性色块。')
            point = (np.asarray(patch['input_ap1']) if 'input_ap1' in patch else self.model.srgb_to_ap1(patch['input_srgb']))*np.exp2(exposure)
            selection = {'sample_id': patch['id']}
        else:
            x, y = selection.get('x', .5), selection.get('y', .5)
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not np.isfinite(v) or not 0 <= v <= 1 for v in (x, y)):
                raise RecipeError('invalid_selection', '选点坐标必须在 0 到 1 之间。')
            point = image[min(int(y*image.shape[0]), image.shape[0]-1), min(int(x*image.shape[1]), image.shape[1]-1)]*(np.exp2(exposure) if gpu or streamed else 1)
            selection = {'x': x, 'y': y}
        spectra = self.model.measured_inputs.get(input_spec['id']) if getattr(self.model, 'direct_spectral_preview', False) else None
        spectral_point = None
        if spectra is not None:
            if not gpu and not streamed:spectra = spectra*np.exp2(exposure)
            if input_spec['id'] == 'chart':
                index = next(i for i,s in enumerate(self.model.samples) if s['id'] == selection['sample_id'])
                columns = getattr(self.model, 'chart_columns', 3)
                spectral_point = spectra[(index//columns)*64+32, (index%columns)*64+32]
            else:
                spectral_point = spectra[min(int(selection['y']*spectra.shape[0]),spectra.shape[0]-1),min(int(selection['x']*spectra.shape[1]),spectra.shape[1]-1)]
            if gpu or streamed:spectral_point=spectral_point*np.exp2(exposure)
        return {'ok': True, 'version': version(recipe), 'baseline_version': version(baseline) if baseline else None,
            'input': {'id': input_spec['id'], 'exposure_ev': exposure}, 'selection': selection,
            'current': self.evaluate_one(recipe, image, point, spectra, spectral_point,input_ev=exposure if gpu or streamed else 0),
            'baseline': self.evaluate_one(baseline, image, point,input_ev=exposure if gpu or streamed else 0) if baseline else None,
            'conditions': self.conditions(recipe),
            'warnings': ['光谱由普通 RGB 估计；同色异谱信息无法由 DCP 或 RGB 还原。',
                         'E100 当前是局部中性密度拟合参考，不代表整款胶片的实测色彩精度。',
                         '预览使用与 LUT 相同的 RGB 光谱估计，不显示 HSI 直接积分真值。']}

    def export(self, request):
        if set(request)-{'recipe', 'purpose', 'request_id', 'grid'}:
            raise RecipeError('invalid_export', '导出只接受固定配方、用途、网格和请求编号；输入曝光不参与 LUT。')
        grid = request.get('grid', 65)
        if type(grid) is not int or not 2 <= grid <= 129:
            raise RecipeError('invalid_grid', 'LUT 边长需要是 2 到 129 的整数。')
        recipe = self.validate_recipe(request.get('recipe'), compute=True)['normalized_recipe']
        purpose = request.get('purpose')
        if purpose not in ('internal', 'display', 'pipeline'):
            raise RecipeError('invalid_export', '请选择完整 OCIO/CTF 效果包、内部 XYZ 或显示 LUT。')
        with self.export_lock:
            return self._export(recipe, purpose, grid)

    def _export(self, recipe, purpose, size=65):
        from spectral_app import __version__
        frozen = version(recipe)
        conditions = self.conditions(recipe)
        metadata = lut_metadata(recipe, frozen, purpose, conditions, __version__,
            datetime.now(timezone.utc).isoformat(timespec='seconds'))
        export_id = uuid.uuid4().hex
        directory = self.model.output/'exports'/export_id
        directory.mkdir(parents=True)
        parameters = self.model.parameters(recipe)
        decode = self.model.core.decode if self.model.core is not None else acescct_decode
        def continuous(rgb):
            result = self.model.sample(rgb, **parameters)
            return result['display_rgb' if purpose == 'display' else 'XYZ']
        axis = np.linspace(LOW[0], HIGH[0], size)
        grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1)
        gpu=getattr(self.model,'metal',None)
        table = gpu.render(grid,recipe,acescct=True,purpose='display' if purpose=='display' else 'XYZ').astype(np.float64) if gpu else batched(lambda x: continuous(decode(x)), grid, chunk=2048)
        cube_path = directory/'recipe.cube'
        Cube(table, LOW, HIGH).write(cube_path, title=metadata['title'], comments=metadata['comments'])
        cube = Cube.read(cube_path)
        np.testing.assert_array_equal(cube.table, table)
        processor = ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=str(cube_path.resolve()), interpolation=ocio.INTERP_TETRAHEDRAL)).getDefaultCPUProcessor()
        pipeline_processor = None
        if purpose == 'pipeline':
            pipeline = ocio.GroupTransform()
            pipeline.appendTransform(ocio.FileTransform(src=str(cube_path.resolve()), interpolation=ocio.INTERP_TETRAHEDRAL))
            pipeline.appendTransform(self.model.display_group(recipe['display']['view'], recipe['display'].get('target','sRGB')))
            # The preview's final code values are bounded. Encode this operation
            # explicitly in the portable graph rather than silently relying on
            # an application's framebuffer clamp.
            pipeline.appendTransform(ocio.RangeTransform(minInValue=0, minOutValue=0, maxInValue=1, maxOutValue=1))
            resolved = self.model.config.getProcessor(pipeline).createGroupTransform()
            # CLF explicitly rejects the actual package's InverseLUT1D op.
            # OCIO's native CTF preserves that operation instead of baking a
            # second approximation merely to advertise a different container.
            pipeline_path = directory/'recipe.ctf'
            resolved.getFormatMetadata().setName(metadata['title'])
            ctf_metadata=lut_metadata(recipe,frozen,'display',conditions,__version__,metadata['created_utc'])
            resolved.getFormatMetadata().addChildElement('Description',
                'Container: CTF complete material and display graph\n'+'\n'.join(ctf_metadata['comments']))
            resolved.write('Color Transform Format', str(pipeline_path.resolve()))
            pipeline_processor = ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(src=str(pipeline_path.resolve()))).getDefaultCPUProcessor()
        # Fixed independent ordinary-RGB build check; no fitting against these
        # points. Record this scope instead of claiming entire-domain accuracy.
        rng = np.random.default_rng(20261026)
        rgb = self.model.srgb_to_ap1(rng.random((8192, 3)))
        gray = np.repeat(np.linspace(0, 1, 2049)[:, None], 3, axis=1)
        points = np.vstack([acescct_encode(rgb), acescct_encode(gray),
            acescct_encode(self.model.inputs.get('scene43_rgb', self.model.inputs['chart']).reshape(-1, 3))])
        in_domain = np.all((points >= LOW) & (points <= HIGH), axis=-1)
        points = points[in_domain]
        truth = batched(lambda x: continuous(decode(x)), points, chunk=2048)
        python_interpolation = cube.apply(points, interpolation='tetrahedral')
        own = self.model.core.apply_cube(cube, points) if self.model.core is not None else python_interpolation
        native_difference = float(np.max(np.abs(own-python_interpolation)))
        external = apply_ocio(processor, points)
        if purpose in ('internal', 'pipeline'):
            reference_display = self.model.render(truth, recipe['display']['view'],recipe['display'].get('target','sRGB'))
            own_display = self.model.render(own, recipe['display']['view'],recipe['display'].get('target','sRGB'))
            external_display = self.model.render(external, recipe['display']['view'],recipe['display'].get('target','sRGB'))
        else:
            reference_display, own_display, external_display = truth, own, external
        pipeline_difference = None
        if pipeline_processor is not None:
            pipeline_output = apply_ocio(pipeline_processor, points)
            pipeline_difference = float(np.max(np.abs(pipeline_output-external_display)))
            external_display = pipeline_output
        own_check = srgb_code_error(reference_display, own_display)[0]
        external_check = srgb_code_error(reference_display, external_display)[0]
        independent_difference = float(np.max(np.abs(own-external)))
        integrity_passed = native_difference <= 2e-12 and independent_difference <= 2e-5 and (pipeline_difference is None or pipeline_difference <= 2e-5)
        verification = {'accepted': own_check['accepted'] and external_check['accepted'],
            'integrity_passed': integrity_passed,
            'quality_policy': '99% within 2/255 is a reference line; quality does not block download',
            'float64_cube': own_check, 'independent_ocio': external_check,
            'ocio_vs_float64_max_abs_output': independent_difference,
            'native_vs_python_max_abs_output': native_difference if self.model.core is not None else None,
            'readback_exact': True, 'grid': size, 'interpolation': 'tetrahedral',
            'sample_set': 'seed 20261026: 8192 uniform encoded-sRGB samples converted to AP1; 2049 linear neutral samples; current built-in RGB photo pixels; in-domain only',
            'excluded_outside_domain': int(np.count_nonzero(~in_domain)),
            'input_sources': self.model.verification_input_sources,
            'scope': 'independent build samples only; not whole-domain or real-film accuracy'}
        if pipeline_difference is not None:
            verification['pipeline_vs_material_display_max_abs'] = pipeline_difference
        if hasattr(self.model, 'spectral_verification'):
            verification['spectral_reference'] = self.model.spectral_verification(recipe, cube, purpose)
        manifest = {'schema': 'softloaf.lut-manifest/1', 'export_id': export_id, 'frozen': frozen,
            'application': metadata['application'], 'created_utc': metadata['created_utc'],
            'purpose': purpose, 'input': {'space': 'ACEScct', 'primaries': 'AP1', 'white': 'D60', 'domain_min': LOW.tolist(), 'domain_max': HIGH.tolist(),
                'requirements': 'develop/profile camera RAW to scene-linear AP1 D60, then ACEScct; no mosaic RAW input; DCP is not sensor spectral sensitivity'},
            'output': {'space': 'relative XYZ D65' if purpose == 'internal' else recipe['display'].get('target','sRGB')+' encoded RGB D65', 'includes_display': purpose in ('display', 'pipeline'),
                'format': f'CTF operation graph with embedded {size}³ material LUT and resolved display operations' if purpose == 'pipeline' else 'CUBE',
                'format_reason': 'CTF preserves the selected material and display operation graph without rebaking its display operators' if purpose == 'pipeline' else None,
                'cube_role': 'material ACEScct→relative XYZ D65; use recipe.ctf for the complete effect' if purpose == 'pipeline' else purpose},
            'conditions': conditions, 'verification': verification,
            'versions': {'python': platform.python_version(), 'numpy': np.__version__, 'colour': colour.__version__, 'ocio': ocio.__version__},
            'cube_sha256': sha(cube_path)}
        if recipe['route'] == 'negative':
            academy_license = Path(__file__).resolve().parents[1]/'third_party/aces-v1.2/LICENSE.md'
            (directory/'ACES-LICENSE.md').write_bytes(academy_license.read_bytes())
        if purpose == 'pipeline' and recipe['display']['view'] in ('Default','Colorful','Umbra'):
            (directory/'OpenDRT-LICENSE.md').write_bytes(self.model.opendrt_license)
            manifest['opendrt'] = {'source': 'https://github.com/jedypod/open-display-transform',
                'package': 'OpenDRT_v1.0.0_mini-config_v2.zip',
                'package_sha256': self.model.sources['OpenDRT_v1.0.0_mini-config_v2.zip'],
                'license': 'MIT; exact packaged LICENSE.md included as OpenDRT-LICENSE.md',
                'license_sha256': sha(directory/'OpenDRT-LICENSE.md')}
        if purpose == 'pipeline':manifest['ctf_sha256'] = sha(directory/'recipe.ctf')
        upstream_data=bool(conditions.get('optical_sources')) or bool(conditions.get('material',{}).get('provenance',{}).get('sources',{}).get('processed_sensitivity'))
        if upstream_data:
            source_license=Path(__file__).resolve().parents[1]/'local/reference-assets/spektrafilm/SPEKTRAFILM_LICENSE.txt'
            if not source_license.is_file():raise RecipeError('missing_license','缺少上游资料的原始许可文件。')
            (directory/'SPEKTRAFILM_LICENSE.txt').write_bytes(source_license.read_bytes())
            (directory/'CHANGELOG.txt').write_text('SoftLoaf Spectral derived local export\nAuthor: Yangming Feng and contributors\nOriginal profile author: Andrea Volpato / spektrafilm\nChanges and sources:\n'+'\n'.join(metadata['comments'])+'\n',encoding='utf-8')
            manifest['spektrafilm']={'author':'Andrea Volpato','repository':'https://github.com/andreavolpato/spektrafilm','profile_license':'CC BY-SA 4.0','license_sha256':sha(source_license),'changes':'CHANGELOG.txt','scope':'Used profile fields and derivatives; independent manufacturer filter rights remain separately pending'}
        (directory/'recipe.json').write_bytes(json_bytes(recipe))
        (directory/'manifest.json').write_bytes(json_bytes(manifest))
        if not integrity_passed:
            return {'ok': False, 'error': {'code': 'integrity_failed', 'message': '文件读回与独立执行结果不一致，请检查实现后重新生成。'},
                    'export_id': export_id, 'frozen': frozen, 'verification': verification, 'files': []}
        names = ['recipe.cube', 'recipe.json', 'manifest.json']
        if upstream_data:names.extend(['SPEKTRAFILM_LICENSE.txt','CHANGELOG.txt'])
        if recipe['route']=='negative':names.append('ACES-LICENSE.md')
        if purpose == 'pipeline':
            names.append('recipe.ctf')
            if recipe['display']['view'] in ('Default','Colorful','Umbra'):names.append('OpenDRT-LICENSE.md')
        with zipfile.ZipFile(directory/'recipe.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
            for name in names:
                bundle.write(directory/name, name)
        files = []
        for name in names+['recipe.zip']:
            path = directory/name
            url = f'/downloads/{export_id}/{name}'
            self.downloads[url] = (path.resolve(), sha(path))
            files.append({'name': name, 'url': url, 'sha256': sha(path), 'size': path.stat().st_size})
        warnings = [] if verification['accepted'] else [{'code': 'quality_reference_missed',
            'message': '本次抽样误差超过 99% / 2 码参考线，仍可下载。请结合误差和文件大小选择。'}]
        return {'ok': True, 'export_id': export_id, 'frozen': frozen, 'verification': verification, 'warnings': warnings, 'files': files}


def make_server(workbench, ui, logo, port=8772):
    """Exact route allowlist: never expose a working directory or arbitrary path."""
    static = {'/': (Path(ui).resolve(), 'text/html; charset=utf-8'),
              '/assets/spectral-csv.js': ((Path(ui).parent/'spectral-csv.js').resolve(), 'text/javascript; charset=utf-8'),
              '/assets/spectral-editor.js': ((Path(ui).parent/'spectral-editor.js').resolve(), 'text/javascript; charset=utf-8'),
              '/assets/diagnostic-samples.js': ((Path(ui).parent/'diagnostic-samples.js').resolve(), 'text/javascript; charset=utf-8')}
    static['/assets/photo-queue.js']=((Path(ui).parent/'photo-queue.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/paper-presets.js']=((Path(ui).parent/'paper-presets.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/cache-settings.js']=((Path(ui).parent/'cache-settings.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/rendition-cache.js']=((Path(ui).parent/'rendition-cache.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/preview-requests.js']=((Path(ui).parent/'preview-requests.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/scan-calibration.js']=((Path(ui).parent/'scan-calibration.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/scanning.js']=((Path(ui).parent/'scanning.js').resolve(),'text/javascript; charset=utf-8')
    static['/assets/scanning.css']=((Path(ui).parent/'scanning.css').resolve(),'text/css; charset=utf-8')
    for name in ('i18n','i18n-en'):static['/assets/'+name+'.js']=((Path(ui).parent/(name+'.js')).resolve(),'text/javascript; charset=utf-8')
    if logo is not None and Path(logo).is_file():
        static['/assets/softloaf-cat.png'] = (Path(logo).resolve(), 'image/png')

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SoftLoafRecipe/1'

        def handle(self):
            try:super().handle()
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                # Navigating to another frame can close an image response early.
                # This is a disconnected viewer, not a processing failure.
                pass

        def log_message(self, fmt, *args):
            # Request paths and user-controlled metadata need not enter logs.
            pass

        def send(self, status, payload, kind='application/json; charset=utf-8', download=None,cache_control='no-store'):
            content = json_bytes(payload) if isinstance(payload, dict) else payload
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', cache_control)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(content)

        def error(self, status, code, message, issues=None):
            from spectral_app.diagnostics import event
            import sys
            event('request.failed' if status>=500 else 'request.rejected',code=code,status=status,error=sys.exc_info()[1])
            body = {'ok': False, 'error': {'code': code, 'message': message}}
            if issues:
                body['issues'] = issues
            if code == 'unsupported':
                body['computable'] = False
            self.send(status, body)

        def safe_request(self):
            expected = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in expected:
                self.error(403, 'invalid_host', '仅接受本机工作台地址。')
                return False
            # No query aliases, URL decoding, traversal or reverse-proxy routing.
            if urlsplit(self.path).query or '%' in self.path or '\\' in self.path or '..' in self.path:
                self.error(404, 'not_found', '没有此资源。')
                return False
            return True

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self.safe_request():
                return
            if self.path=='/api/preferences' and hasattr(workbench,'preferences'):
                self.send(200,workbench.preferences.state())
            elif self.path == '/api/cache-settings' and hasattr(workbench,'cache_settings'):
                self.send(200,workbench.cache_settings.state())
            elif self.path == '/api/bootstrap':
                self.send(200, workbench.bootstrap())
            elif self.path=='/api/scan' and getattr(workbench,'scans',None):
                self.send(200,workbench.scans.state())
            elif self.path.startswith('/scan-files/') and getattr(workbench,'scans',None):
                try:path,kind,download=workbench.scans.resource(self.path)
                except (OSError,ValueError):self.error(404,'scan_file','扫描文件不存在或已变化。');return
                with path.open('rb') as stream:
                    self.send_response(200);self.send_header('Content-Type',kind)
                    self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff')
                    if download:
                        from urllib.parse import quote
                        self.send_header('Content-Disposition',f'attachment; filename="{path.name}"; filename*=UTF-8\'\''+quote(download,safe=''))
                    self.end_headers()
                    if self.command!='HEAD':
                        for block in iter(lambda:stream.read(1024*1024),b''):self.wfile.write(block)
            elif self.path.startswith('/previews/') and hasattr(workbench,'renditions'):
                try:self.send(200,workbench.renditions.asset(self.path),'image/png',cache_control='private, max-age=86400, immutable')
                except FileNotFoundError:self.error(404,'preview_missing','预览缓存已过期，请重新选择照片。')
            elif self.path in static:
                path, kind = static[self.path]
                if path.is_file():
                    self.send(200, path.read_bytes(), kind)
                else:
                    self.error(404, 'not_found', '界面文件尚未就绪。')
            elif self.path in workbench.downloads:
                path, expected_hash = workbench.downloads[self.path]
                root = (workbench.model.output/'exports').resolve()
                if not path.is_relative_to(root) or not path.is_file() or sha(path) != expected_hash:
                    self.error(409, 'changed_export', '导出文件已变化，请重新生成。')
                    return
                kind = 'application/zip' if path.suffix == '.zip' else 'application/json' if path.suffix == '.json' else 'application/octet-stream'
                with path.open('rb') as stream:
                    self.send_response(200);self.send_header('Content-Type',kind)
                    self.send_header('Content-Length',str(path.stat().st_size))
                    self.send_header('Content-Disposition',f'attachment; filename="{path.name}"')
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
                    if self.command!='HEAD':
                        for block in iter(lambda:stream.read(1024*1024),b''):self.wfile.write(block)
            else:
                self.error(404, 'not_found', '没有此资源。')

        def do_POST(self):
            if not self.safe_request():
                return
            allowed_origins = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if self.headers.get('Origin') is not None and self.headers['Origin'] not in allowed_origins:
                self.error(403, 'invalid_origin', '请求来自其他网页，未接受更改。')
                return
            if self.path=='/api/scan-upload' and hasattr(workbench,'scan_upload'):
                from urllib.parse import unquote
                try:
                    result=workbench.scan_upload(self.rfile,int(self.headers.get('Content-Length','-1')),
                        unquote(self.headers.get('X-File-Name','')),self.headers.get('X-Scan-Kind',''))
                    self.send(200,result)
                except RecipeError as error:self.error(422,error.code,str(error))
                except (ValueError,TypeError):self.error(400,'scan_import','上传格式不正确。')
                except Exception:self.error(500,'scan_import','扫描原件未能保存，请检查外置数据卷。')
                return
            extra = {'/api/import-image': 'import_image', '/api/export-image': 'export_image', '/api/export-images':'export_images',
                     '/api/export-images-start':'start_photo_export','/api/photo-job':'photo_job',
                     '/api/cache-settings':'update_cache_settings','/api/cache-maintenance':'cache_maintenance',
                     '/api/scan':'scan_action','/api/preferences':'update_preferences',
                     '/api/session': 'save_session'}
            if self.path not in ('/api/validate', '/api/evaluate', '/api/export') and not (
                    self.path in extra and hasattr(workbench, extra[self.path])):
                self.error(404, 'not_found', '没有此接口。')
                return
            if self.headers.get_content_type() != 'application/json':
                self.error(415, 'invalid_content_type', '请发送 JSON 配方。')
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                limit = 343*1024*1024 if self.path == '/api/import-image' else 4*1024*1024 if self.path == '/api/session' else 512*1024
                if not 0 < length <= limit:
                    self.error(413, 'invalid_size', '请求数据超过大小限制。')
                    return
                body = json.loads(self.rfile.read(length), parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                if not isinstance(body, dict):
                    raise RecipeError('invalid_request', '请求必须是 JSON 对象。')
                if self.path == '/api/validate':
                    result = workbench.validate_recipe(body.get('recipe'))
                elif self.path == '/api/evaluate':
                    result = workbench.evaluate(body)
                elif self.path in extra:
                    result = getattr(workbench, extra[self.path])(body)
                else:
                    result = workbench.export(body)
                self.send(200 if result['ok'] else 422, result)
            except RecipeError as error:
                self.error(422, error.code, str(error), error.issues)
            except (ValueError, TypeError, UnicodeDecodeError) as error:
                self.error(400, 'invalid_request', '请求数据不完整或格式错误。')
            except Exception:
                # Avoid exposing local source paths or tracebacks to a webpage.
                self.error(500, 'computation_failed', '计算没有完成；配方未被替换，请保留上一可用版本。')

    class LocalServer(ThreadingHTTPServer):
        def handle_error(self,request,client_address):
            from spectral_app.diagnostics import event
            import sys
            event('request.transport_failed',error=sys.exc_info()[1])
    server = LocalServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/gui-workbench'))
    parser.add_argument('--ui', type=Path, default=Path('design/gui-v2/index.html'))
    parser.add_argument('--port', type=int, default=8772)
    args = parser.parse_args()
    model = E100Model(args.archive, args.opendrt, args.output)
    app = Workbench(model)
    server = make_server(app, args.ui, Path('artifacts/branding/softloaf-cat.png'), args.port)
    print(f'Recipe workbench: http://127.0.0.1:{server.server_port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
