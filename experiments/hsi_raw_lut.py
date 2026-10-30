"""Issue #2: compare synthetic camera RAW + LUT with spectral E100 integration.

Run from the repository root with ``python -m experiments.hsi_raw_lut``.
Restricted inputs and all generated images/LUTs stay outside version control.
No historical Python implementation or other application's code is imported.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time
import zipfile

os.environ.setdefault('MPLCONFIGDIR', str(Path('artifacts/.matplotlib').resolve()))
os.environ.setdefault('XDG_CACHE_HOME', str(Path('artifacts/.cache').resolve()))

import colour
import numpy as np
from PIL import Image, ImageCms
import PyOpenColorIO as ocio
from scipy.io import loadmat
from scipy.optimize import brentq
import tifffile

from spectral_lut.camera import dcp_matrix_xyz, hue_sat_map
from spectral_lut.film import ReversalFilm, fit_neutral_amounts
from spectral_lut.metrics import srgb_code_error, summarize_code_errors
from spectral_lut.reference import (Cube, acescct_decode, acescct_encode,
                                   density_transmittance, quadrature_widths,
                                   smooth_reconstruction_basis)

SCENES = (1, 5, 6, 16, 31, 38, 43, 50)
CAMERAS = {'r5': ('Canon_EOS_R5_380_780_5.json', 'Canon EOS R5.dcp', 'Canon', 'EOS R5'),
           'd850': ('Nikon_D850_380_780_5.json', 'NIKON D850.dcp', 'Nikon', 'D850')}
D65 = colour.xy_to_XYZ([0.3127, 0.3290])
D60 = colour.xy_to_XYZ(colour.RGB_COLOURSPACES['ACEScg'].whitepoint)
D50 = colour.xy_to_XYZ([0.3457, 0.3585])
AP1 = colour.RGB_COLOURSPACES['ACEScg']
PROPHOTO = colour.RGB_COLOURSPACES['ProPhoto RGB']
SRGB = colour.RGB_COLOURSPACES['sRGB']
LOW, HIGH = np.full(3, -0.25), np.full(3, 0.75)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cat(source, destination):
    return colour.adaptation.matrix_chromatic_adaptation_VonKries(source, destination, 'Bradford')


def csv(path, skip=0):
    return np.loadtxt(path, delimiter=',', skiprows=skip)


def interpolate(table, wavelengths):
    return np.column_stack([np.interp(wavelengths, table[:, 0], table[:, i])
                            for i in range(1, table.shape[1])])


def load_scene(root, number):
    path = root/'data'/f'hsi_{number}.zip'
    with zipfile.ZipFile(path) as z:
        return np.asarray(loadmat(io.BytesIO(z.read(f'hsi_{number}.mat')))['hsi'], dtype=np.float64)


def color_kernel(wavelengths, illuminant, cmfs):
    k = cmfs * illuminant[:, None] * quadrature_widths(wavelengths)[:, None]
    return k/k[:, 1].sum()


def build_reference(root):
    materials = root/'output/reversal-E100/data'
    characteristic = csv(materials/'E100_characteristic_RGB.csv', 1)
    sensitivity = csv(materials/'E100_linear_sensitivity_RGB.csv', 1)
    dyes = csv(materials/'E100_dye_density_CMY.csv', 1)
    cmfs = csv(root.parent/'data/CIE_xyz_official.csv')
    d65 = csv(root.parent/'data/CIE_std_illum_D65.csv')
    d50 = csv(root.parent/'data/CIE_std_illum_D50.csv')
    wavelength = sensitivity[:, 0]
    light = interpolate(d65, wavelength)[:, 0]
    source_xyz = color_kernel(wavelength, light, interpolate(cmfs, wavelength))
    source_white = source_xyz.sum(axis=0)
    source_to_ap1 = source_xyz @ cat(source_white, D60).T @ AP1.matrix_XYZ_to_RGB.T
    view_grid = dyes[:, 0]
    view_xyz = color_kernel(view_grid, interpolate(d50, view_grid)[:, 0], interpolate(cmfs, view_grid))
    view_to_d65 = view_xyz @ cat(view_xyz.sum(axis=0), D65).T
    # Only the density-measurement weights are read from this archived numeric
    # artifact; dye amounts and the complete film calculation are rebuilt here.
    with np.load(root/'output/reversal-E100/intermediate/model.npz') as old:
        weights = np.asarray(old['StatusA_weights'], dtype=np.float64)
        old_amounts = np.asarray(old['neutral_amounts_CMY'], dtype=np.float64)
    amounts = fit_neutral_amounts(dyes[:, 1:], weights, characteristic[:, 1:])
    predicted = -np.log10(density_transmittance(amounts, dyes[:, 1:]) @ (weights/weights.sum(axis=0)))
    neutral_error = float(np.max(np.abs(predicted-characteristic[:, 1:])))
    if neutral_error > 0.001:
        raise RuntimeError(f'Neutral E100 density check failed: {neutral_error} D')
    def gray_y(log_h):
        a = np.array([np.interp(log_h, characteristic[:, 0], amounts[:, i]) for i in range(3)])
        return float(density_transmittance(a, dyes[:, 1:]) @ view_xyz[:, 1])
    anchor = brentq(lambda x: gray_y(x)-0.1, characteristic[0, 0], characteristic[-1, 0])
    exposure = sensitivity[:, 1:] * light[:, None] * quadrature_widths(wavelength)[:, None]
    exposure /= 0.18*exposure.sum(axis=0)
    film = ReversalFilm(characteristic[:, 0], amounts, exposure, dyes[:, 1:], view_to_d65, anchor)
    return film, source_to_ap1, source_xyz, light, {
        'neutral_StatusA_max_error_D': neutral_error,
        'amounts_max_difference_from_archived_fit': float(np.max(np.abs(amounts-old_amounts))),
        'gray_logH_anchor': anchor,
        'scene_illuminant': 'CIE D65 energy SPD; common for synthetic camera and film exposure',
        'exposure_grid_nm': [400, 720, 10], 'view_grid_nm': [400, 700, 2],
        'view': 'D50, CIE1931 2deg, finite-band Bradford to D65, fixed gain 1.8',
        'density_weights': 'Archived finite-band ISO 5/3:1984 Status A numeric weights; rights pending',
        'base': 'Included in effective dye coefficients; no additional base spectrum',
        'exposure_anchor': 'Each layer aligned on flat 18% gray; not an absolute ISO/shutter calibration',
    }


def read_dcp(path):
    """Read the TIFF-like DCP IFD, including signed-rational matrices."""
    data = Path(path).read_bytes()
    endian = '<' if data[:2] == b'II' else '>'
    offset = struct.unpack_from(endian+'I', data, 4)[0]
    count = struct.unpack_from(endian+'H', data, offset)[0]
    formats = {1: ('B', 1), 2: ('B', 1), 3: ('H', 2), 4: ('I', 4),
               5: ('I', 8), 10: ('i', 8), 11: ('f', 4), 12: ('d', 8)}
    result = {}
    for i in range(count):
        pos = offset+2+i*12
        tag, dtype, n, value_offset = struct.unpack_from(endian+'HHII', data, pos)
        if dtype not in formats:
            continue
        fmt, size = formats[dtype]
        raw = data[pos+8:pos+12] if n*size <= 4 else data[value_offset:value_offset+n*size]
        if dtype == 2:
            result[tag] = raw.rstrip(b'\0').decode('utf-8')
            continue
        values = np.array(struct.unpack_from(endian+str(n*(2 if dtype in (5, 10) else 1))+fmt, raw))
        if dtype in (5, 10):
            values = values[::2]/values[1::2]
        result[tag] = values
    if int(result[50779][0]) != 21 or 50965 not in result:
        raise ValueError('The experiment requires a D65 ForwardMatrix2.')
    dims = result[50937].astype(int)
    if dims[2] != 1 or int(result.get(51107, [0])[0]) != 0:
        raise ValueError('Only linear, value-independent HueSatMap2 is supported.')
    return {'forward': result[50965].reshape(3, 3), 'color': result[50722].reshape(3, 3),
            'table': result[50939].reshape(dims[2], dims[0], dims[1], 3),
            'copyright': result.get(50942, '')}


def camera_kernel(path, light, wavelengths):
    payload = json.loads(Path(path).read_text())
    values = payload['spectral_data']['data']['main']
    table = np.array([[float(k), *v] for k, v in values.items()])
    table = table[np.argsort(table[:, 0])]
    responses = interpolate(table, wavelengths)
    k = responses*light[:, None]*quadrature_widths(wavelengths)[:, None]
    # One shared scale. No independent peak normalization of camera channels.
    k /= k[:, 1].sum()
    return k, payload['header']


def write_synthetic_dng(path, native, white_response, profile, manufacturer, model):
    """One constant 2x2 RGGB patch per HSI pixel, 16-bit quantization, no noise."""
    scale = 4*float(np.max(white_response))
    fraction = native/scale
    clipped = float(np.mean((fraction < 0) | (fraction > 1)))
    codes = np.rint(np.clip(fraction, 0, 1)*65023+512).astype(np.uint16)
    h, w = native.shape[:2]
    mosaic = np.empty((2*h, 2*w), dtype=np.uint16)
    mosaic[::2, ::2], mosaic[::2, 1::2] = codes[..., 0], codes[..., 1]
    mosaic[1::2, ::2], mosaic[1::2, 1::2] = codes[..., 1], codes[..., 2]
    neutral = white_response/np.max(white_response)
    rational = lambda a: tuple(v for x in np.asarray(a).ravel() for v in (int(round(x*1000000)), 1000000))
    tags = [(50706, 'B', 4, (1, 4, 0, 0), False), (50707, 'B', 4, (1, 3, 0, 0), False),
            (50708, 's', 0, manufacturer+' '+model, False), (271, 's', 0, manufacturer, False),
            (272, 's', 0, model, False), (33421, 'H', 2, (2, 2), False),
            (33422, 'B', 4, (0, 1, 1, 2), False), (50710, 'B', 3, (0, 1, 2), False),
            (50711, 'H', 1, 1, False), (50714, '2I', 1, (512, 1), False),
            (50717, 'I', 1, 65535, False), (50721, '2i', 9, rational(profile['color']), False),
            (50728, '2I', 3, rational(neutral), False), (50778, 'H', 1, 21, False),
            (50964, '2i', 9, rational(profile['forward']), False),
            (50937, 'I', 3, (profile['table'].shape[1], profile['table'].shape[2], 1), False),
            (50938, 'f', profile['table'].size, np.asarray(profile['table'], dtype=np.float32).ravel(), False),
            (50940, 'f', 4, (0., 0., 1., 1.), False),
            (50936, 's', 0, 'SYNTHETIC D65 technical profile, matching experiment', False),
            (50942, 's', 0, profile['copyright'], False)]
    tifffile.imwrite(path, mosaic, photometric=32803, metadata=None, extratags=tags,
                     software='SoftLoaf Spectral SYNTHETIC experiment',
                     description='SYNTHETIC from finite-band HSI; 2x2 constant spectral patches; no sensor noise')
    with tifffile.TiffFile(path) as tf:
        readback = tf.asarray()
        np.testing.assert_array_equal(readback, mosaic)
        assert tuple(tf.pages[0].tags[33422].value) == (0, 1, 1, 2)
    reconstructed = np.stack([readback[::2, ::2], (readback[::2, 1::2].astype(float)+readback[1::2, ::2])/2,
                               readback[1::2, 1::2]], axis=-1)
    return (reconstructed.astype(float)-512)/65023, neutral, clipped


def dcp_to_ap1(raw_fraction, neutral, profile, brightness=4.0, use_table=True):
    xyz = dcp_matrix_xyz(raw_fraction, neutral, profile['forward'])
    prophoto = xyz @ PROPHOTO.matrix_XYZ_to_RGB.T
    negative_fraction = float(np.mean(prophoto < 0))
    if use_table:
        prophoto = hue_sat_map(prophoto, profile['table'])
    xyz = prophoto @ PROPHOTO.matrix_RGB_to_XYZ.T * brightness
    return xyz @ cat(D50, D60).T @ AP1.matrix_XYZ_to_RGB.T, negative_fraction


def apply_ocio(processor, array):
    values = np.array(array, dtype=np.float32, order='C', copy=True)
    processor.applyRGB(values)
    return values.astype(np.float64)


def display_processor(archive, directory):
    if sha(archive) != 'c1a60bb4bd77bc2ae9c897143f9036229d816a9009aed58cfd4c5933fe9f6cc1':
        raise ValueError('Unexpected OpenDRT archive revision.')
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            if Path(member).is_absolute() or '..' in Path(member).parts:
                raise ValueError('Unsafe archive path.')
        z.extractall(directory)
    config_path = directory/'OpenDRT_v1.0.0_mini-config_v2/OpenDRT_v1.0.0_mini-config.ocio'
    config = ocio.Config.CreateFromFile(str(config_path.resolve()))
    config.validate()
    bridge = AP1.matrix_XYZ_to_RGB @ cat(D65, D60)
    matrix = np.eye(4)
    matrix[:3, :3] = bridge
    group = ocio.GroupTransform()
    group.appendTransform(ocio.MatrixTransform(matrix=matrix.ravel().tolist()))
    group.appendTransform(ocio.DisplayViewTransform(src='ACEScg', display='sRGB Display',
                                                     view='OpenDRT v1.0.0 Default'))
    group.appendTransform(ocio.ColorSpaceTransform(src='sRGB Display', dst='Rec.709 - Linear'))
    # The supplied eocf table ENcodes linear values (0.18 -> 0.461356). The
    # upstream sRGB Encoding colorspace instead models a nonstandard display
    # EOTF; it is not a standard file encoder. Use the table forward here.
    encoding_table = config_path.parent/'transfer_functions/eocf_srgb_to_linear.spi1d'
    group.appendTransform(ocio.FileTransform(src=str(encoding_table.resolve()),
                                             interpolation=ocio.INTERP_LINEAR))
    return config.getProcessor(group).getDefaultCPUProcessor(), config_path


def batched(function, values, chunk=8192):
    shape = values.shape[:-1]
    flat = values.reshape(-1, values.shape[-1])
    return np.concatenate([function(flat[i:i+chunk]) for i in range(0, len(flat), chunk)]).reshape(*shape, 3)


def error_summary(a, b, encoded=False):
    if encoded:
        a = colour.cctf_decoding(np.clip(a, 0, 1), function='sRGB') @ SRGB.matrix_RGB_to_XYZ.T
        b = colour.cctf_decoding(np.clip(b, 0, 1), function='sRGB') @ SRGB.matrix_RGB_to_XYZ.T
    lab_a = colour.XYZ_to_Lab(a, illuminant=[0.3127, 0.3290])
    lab_b = colour.XYZ_to_Lab(b, illuminant=[0.3127, 0.3290])
    de = colour.delta_E(lab_a, lab_b, method='CIE 2000')
    return {'mean': float(np.mean(de)), 'median': float(np.median(de)),
            'p95': float(np.percentile(de, 95)), 'max': float(np.max(de))}, de


def save_png(path, encoded):
    pixels = np.rint(np.clip(encoded, 0, 1)*255).astype(np.uint8)
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    Image.fromarray(pixels).save(path, icc_profile=icc)
    np.testing.assert_array_equal(np.asarray(Image.open(path)), pixels)


def bake_cube(film_rgb, size, path):
    axis = np.linspace(LOW[0], HIGH[0], size)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), axis=-1)
    table = batched(lambda x: film_rgb(acescct_decode(x)), grid)
    cube = Cube(table, LOW, HIGH)
    cube.write(path)
    reloaded = Cube.read(path)
    np.testing.assert_array_equal(reloaded.table, table)
    processor = ocio.Config.CreateRaw().getProcessor(ocio.FileTransform(
        src=str(path.resolve()), interpolation=ocio.INTERP_TETRAHEDRAL)).getDefaultCPUProcessor()
    return reloaded, processor


def figures(out, examples, report):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for name, images in examples.items():
        fig, axes = plt.subplots(1, 4, figsize=(15, 4.2), layout='constrained')
        labels = ['Spectral E100 reference', 'Ideal RGB + spectral-prior LUT',
                  'Synthetic RAW + DCP + LUT', 'Display difference, delta E00']
        for ax, title, image in zip(axes, labels, images):
            if image.ndim == 2:
                im = ax.imshow(image, cmap='magma', vmin=0, vmax=15)
                fig.colorbar(im, ax=ax, shrink=0.7)
            else:
                ax.imshow(np.clip(image, 0, 1))
            ax.set_title(title, fontsize=10)
            ax.axis('off')
        fig.suptitle(name+' / EV 0 / D65 capture / D50 slide viewing / OpenDRT v1.0.0')
        fig.savefig(out/(name+'_comparison.png'), dpi=150)
        plt.close(fig)
    sizes = report['grid_sizes']
    medians = [np.median([v['lut_vs_continuous_display']['p95'] for v in report['frames']
                         if v['grid'] == size]) for size in sizes]
    fig, ax = plt.subplots(figsize=(7, 4), layout='constrained')
    ax.plot(sizes, medians, marker='o')
    ax.set(xlabel='LUT edge size', ylabel='Median per-frame 95th-percentile display delta E00',
           title='LUT interpolation error, separate from spectral approximation')
    ax.grid(alpha=0.2)
    fig.savefig(out/'lut_interpolation.png', dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('local/film-color-slides/hyperspectral-demo'))
    parser.add_argument('--opendrt', type=Path, default=Path('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/hsi-raw-lut'))
    parser.add_argument('--grids', nargs='+', type=int, default=[33, 65, 129])
    parser.add_argument('--scenes', nargs='+', type=int, default=list(SCENES))
    args = parser.parse_args()
    started = time.time()
    root, out = args.archive, args.output
    out.mkdir(parents=True, exist_ok=True)
    (out/'raw').mkdir(exist_ok=True)
    film, source_kernel, source_xyz_kernel, light, settings = build_reference(root)
    basis = smooth_reconstruction_basis(source_kernel)
    def film_rgb(rgb):
        # Declared minimum-first-difference prior followed by nonnegative
        # projection. No upper reflectance cap; measured factors >1 are retained.
        reflectance = np.maximum(rgb @ basis, 0)
        return film.evaluate(reflectance)
    display, display_path = display_processor(args.opendrt, out/'opendrt')
    cubes = {}
    for size in args.grids:
        print(f'Generating and reading back {size}^3 LUT', flush=True)
        cubes[size] = bake_cube(film_rgb, size, out/f'e100_acescct_to_xyz_d65_{size}.cube')
    camera_data = {}
    for key, (sensor_name, profile_name, make, model) in CAMERAS.items():
        kernel, header = camera_kernel(root/'data'/sensor_name, light, np.arange(400, 721, 10))
        camera_data[key] = (kernel, read_dcp(root/'profiles'/profile_name), make, model, header)
    sources = [root/'data'/CAMERAS[k][0] for k in CAMERAS]
    sources += [root/'profiles'/CAMERAS[k][1] for k in CAMERAS]
    sources += [root/'output/reversal-E100/data'/n for n in
                ['E100_characteristic_RGB.csv', 'E100_linear_sensitivity_RGB.csv', 'E100_dye_density_CMY.csv']]
    sources += [root/'output/reversal-E100/intermediate/model.npz', args.opendrt]
    sources += [root.parent/'data'/n for n in ['CIE_xyz_official.csv', 'CIE_std_illum_D50.csv', 'CIE_std_illum_D65.csv']]
    sources += [root/'data'/f'hsi_{n}.zip' for n in args.scenes]
    report = {'issue': 2, 'recipe': settings, 'grid_sizes': args.grids, 'scenes': args.scenes,
              'sources': [{'name': p.name, 'sha256': sha(p)} for p in sources],
              'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                           'colour': colour.__version__, 'ocio': ocio.__version__},
              'LUT': {'input': 'ACEScct AP1/D60', 'output': 'relative viewed XYZ D65, before OpenDRT',
                      'domain_min': LOW.tolist(), 'domain_max': HIGH.tolist(),
                      'interpolation': 'tetrahedral; own float64 and independent OCIO CPU float32'},
              'prior': 'Minimum first-difference energy with 1e-8 L2 regularization, exact color constraints before nonnegative projection; no photo fitting',
              'camera': {k: {'sensor_header': v[4], 'profile_copyright': v[1]['copyright']}
                         for k, v in camera_data.items()},
              'camera_processing': 'D65 ForwardMatrix2 + linear value-independent HueSatMap2; no tone/look/baseline exposure; synthetic AB and CameraCalibration identity; neutral from same finite-band light',
              'RAW': '16-bit RGGB DNG, black=512, white=65535, fixed two-stop headroom, no noise; statistics recover co-located channels from 2x2 constant patches, not a general demosaicer',
              'display': 'OpenDRT v1.0.0 Default, sRGB Display -> Rec.709 Linear -> forward eocf table for piecewise sRGB',
              'display_adapter': 'Official package retained unchanged. Its sRGB Encoding colorspace models a nonstandard display EOTF, not standard file encoding. This adapter decodes sRGB Display and uses the eocf table forward, regression checked against independent IEC sRGB math.',
              'limitations': ['Development scenes previously used in historical work; not an independent final benchmark',
                              'Not a real-camera or real-E100 accuracy measurement',
                              'Camera response and DCP are separate data sources; native gain compatibility not established on hardware',
                              'Finite 400-720 nm scene coverage; viewing 400-700 nm; no omitted-band reconstruction',
                              'Film neutral fit is a construction check, not color validation',
                              'Experimental model/LUT rights are pending; generated files are local only',
                              'DCP support is this specific D65 subset, not a complete general RAW/DCP implementation'],
              'acceptance': {'space': 'bounded standard-encoded sRGB after the shared display transform',
                             'limit': 'at least 99% of pixels have abs difference <= 2/255 in all three channels',
                             'required_fraction': 0.99,
                             'PNG_check': 'round both outputs to 8-bit as in save_png; abs code difference <=2',
                             'pass': 'both continuous-code and actual quantized-code checks reach 99%; evaluated per frame and for pooled samples; maxima retained as diagnostics'},
              'frames': []}
    examples = {}
    camera_summary = []
    pooled = {(size, camera): {'total_display': [], 'lut_vs_continuous_display': [],
                               'total_pre_display': []}
              for size in args.grids for camera in camera_data}
    code_pooled = {(size, camera): {'total_float': [], 'total_u8': [], 'lut_float': [], 'lut_u8': []}
                   for size in args.grids for camera in camera_data}
    for number in args.scenes:
        hsi = load_scene(root, number)
        print(f'Scene {number}: {hsi.shape}', flush=True)
        for ev in [-1, 0, 1]:
            stimulus = hsi*2.0**ev
            ideal_rgb = stimulus @ source_kernel
            truth = batched(film.evaluate, stimulus)
            ideal_continuous = batched(film_rgb, ideal_rgb)
            truth_display = apply_ocio(display, truth)
            ideal_display = apply_ocio(display, ideal_continuous)
            for camera, (kernel, profile, make, model, header) in camera_data.items():
                native = stimulus @ kernel
                white = kernel.sum(axis=0)
                dng = out/'raw'/f'scene{number:02d}_{camera}_ev{ev:+d}_SYNTHETIC.dng'
                raw, neutral, clipping = write_synthetic_dng(dng, native, white, profile, make, model)
                camera_rgb, negative = dcp_to_ap1(raw, neutral, profile)
                continuous = batched(film_rgb, camera_rgb)
                continuous_display = apply_ocio(display, continuous)
                prior_only, _ = error_summary(ideal_display, truth_display, encoded=True)
                camera_continuous_error, _ = error_summary(continuous_display, truth_display, encoded=True)
                profile_propagation, _ = error_summary(continuous_display, ideal_display, encoded=True)
                encoded = acescct_encode(camera_rgb)
                outside = np.any((encoded < LOW) | (encoded > HIGH), axis=-1)
                input_xyz_d65 = camera_rgb @ AP1.matrix_RGB_to_XYZ.T @ cat(D60, D65).T
                true_source_xyz = stimulus @ source_xyz_kernel
                true_source_xyz = true_source_xyz @ cat(source_xyz_kernel.sum(axis=0), D65).T
                input_error, _ = error_summary(input_xyz_d65, true_source_xyz)
                camera_summary.append({'scene': number, 'camera': camera, 'ev': ev,
                                       'input_DCP_deltaE00': input_error,
                                       'RAW_clipped_channel_fraction': clipping})
                for size, (cube, processor) in cubes.items():
                    xyz = cube.apply(encoded)
                    independent = apply_ocio(processor, encoded)
                    serialization = float(np.max(np.abs(xyz-independent)))
                    lut_display = apply_ocio(display, xyz)
                    total_codes, total_float, total_u8 = srgb_code_error(lut_display, truth_display)
                    lut_codes, lut_float, lut_u8 = srgb_code_error(lut_display, continuous_display)
                    for key, values in [('total_float', total_float), ('total_u8', total_u8),
                                        ('lut_float', lut_float), ('lut_u8', lut_u8)]:
                        code_pooled[size, camera][key].append(values.ravel())
                    total, difference = error_summary(lut_display, truth_display, encoded=True)
                    interpolation, interpolation_values = error_summary(lut_display, continuous_display, encoded=True)
                    total_pre, pre_values = error_summary(xyz, truth)
                    for key, values in [('total_display', difference),
                                        ('lut_vs_continuous_display', interpolation_values),
                                        ('total_pre_display', pre_values)]:
                        pooled[size, camera][key].append(values.astype(np.float32).ravel())
                    item = {'scene': number, 'camera': camera, 'ev': ev, 'grid': size,
                            'total_display': total, 'total_pre_display': total_pre,
                            'total_srgb_codes': total_codes,
                            'lut_vs_continuous_srgb_codes': lut_codes,
                            'lut_vs_continuous_display': interpolation,
                            'ideal_RGB_prior_vs_spectral_display': prior_only,
                            'camera_continuous_vs_spectral_display': camera_continuous_error,
                            'camera_input_propagation_vs_ideal_RGB_display': profile_propagation,
                            'LUT_outside_domain_pixel_fraction': float(np.mean(outside)),
                            'ocio_vs_float64_LUT_max_abs_XYZ': serialization,
                            'DCP_negative_ProPhoto_channel_fraction_before_HSM': negative,
                            'display_clipped_channel_fraction': float(np.mean((lut_display<0)|(lut_display>1)))}
                    report['frames'].append(item)
                    if ev == 0 and number in (16, 43) and size == max(args.grids):
                        ideal_lut = apply_ocio(display, cube.apply(acescct_encode(ideal_rgb)))
                        name = f'scene{number:02d}_{camera}'
                        examples[name] = (truth_display, ideal_lut, lut_display, difference)
                        for suffix, image in [('spectral', truth_display), ('ideal_lut', ideal_lut), ('raw_lut', lut_display)]:
                            save_png(out/(name+'_'+suffix+'.png'), image)
                        np.savez_compressed(out/(name+'_values.npz'), spectral_XYZ=truth,
                                            ideal_continuous_XYZ=ideal_continuous,
                                            camera_continuous_XYZ=continuous,
                                            LUT_XYZ=xyz, camera_AP1_linear=camera_rgb,
                                            native_sensor_relative=native)
        # An interrupted run retains complete metrics for finished scenes.
        report['camera_input'] = camera_summary
        report['elapsed_seconds'] = time.time()-started
        (out/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    report['pooled'] = []
    for (size, camera), metrics in pooled.items():
        row = {'grid': size, 'camera': camera}
        for key, arrays in metrics.items():
            values = np.concatenate(arrays)
            row[key] = {'mean': float(np.mean(values, dtype=np.float64)),
                        'median': float(np.median(values)), 'p95': float(np.percentile(values, 95)),
                        'max': float(np.max(values)), 'pixels': int(values.size)}
        code_arrays = code_pooled[size, camera]
        row['total_srgb_codes'] = summarize_code_errors(np.concatenate(code_arrays['total_float']),
                                                        np.concatenate(code_arrays['total_u8']))
        row['lut_vs_continuous_srgb_codes'] = summarize_code_errors(np.concatenate(code_arrays['lut_float']),
                                                                    np.concatenate(code_arrays['lut_u8']))
        report['pooled'].append(row)
    report['elapsed_seconds'] = time.time()-started
    (out/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    figures(out, examples, report)
    freeze = subprocess.run([sys.executable, '-m', 'pip', '--disable-pip-version-check',
                             '--no-cache-dir', 'freeze'], check=True, capture_output=True, text=True)
    (out/'environment.txt').write_text(freeze.stdout)
    print(f'Complete: {len(report["frames"])} comparisons, {report["elapsed_seconds"]:.1f} seconds', flush=True)


if __name__ == '__main__':
    main()
