"""Start the local C++-backed application service; the native shell owns its lifetime."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time


def main():
    from .runtime_paths import resources,state_path,science_root,packaged,SetupRequired
    root = resources()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--opendrt', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--runtime-probe',action='store_true')
    parser.add_argument('--needs-setup',action='store_true')
    parser.add_argument('--configure',action='store_true')
    parser.add_argument('--science-root',type=Path)
    parser.add_argument('--data-root',type=Path)
    parser.add_argument('--volume',type=Path)
    parser.add_argument('--core', type=Path)
    parser.add_argument('--compute',choices=['auto','metal','d3d12','cpu'],default='metal' if sys.platform=='darwin' else 'auto' if sys.platform=='win32' else 'cpu')
    parser.add_argument('--require-gpu',action='store_true',help='Fail verification instead of falling back when the requested GPU is unavailable')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--stop-event',help='Owner-created Windows shutdown event')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.needs_setup:
        from .runtime_paths import settings
        try:
            config=settings()
            return 0 if (Path(config['science_root'])/'runtime-science.json').is_file() and Path(config['volume']).is_mount() else 2
        except SetupRequired:return 2
    if args.runtime_probe:
        from .runtime_probe import probe
        print(json.dumps(probe()),flush=True);return 0
    if args.configure:
        if not all((args.science_root,args.data_root,args.volume)):parser.error('Configuration needs science-root, data-root and volume')
        from .runtime_setup import configure as configure_runtime
        try:configure_runtime(args.science_root,args.data_root,args.volume)
        except (OSError,ValueError,SetupRequired) as error:
            print(json.dumps({'ok':False,'message':str(error)}),flush=True);return 2
        print(json.dumps({'ok':True}),flush=True);return 0
    try:science=science_root()
    except SetupRequired as error:
        print(json.dumps({'ok':False,'missing':[str(error)]}),flush=True);return 2
    args.archive=args.archive or science/'local/film-color-slides/hyperspectral-demo'
    args.opendrt=args.opendrt or science/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip'
    if args.output is None:
        if packaged():
            from .runtime_paths import settings
            args.output=Path(settings()['data_root'])/'data/artifacts/application'
        else:args.output=state_path('artifacts/application')
    from spectral_app.diagnostics import configure,event,install_exception_hooks
    try:configure(state_path('artifacts/application/logs'))
    except OSError:pass
    install_exception_hooks()
    event('service.starting',pid=os.getpid(),requested_backend=args.compute)
    requested=args.compute
    if args.compute=='auto':args.compute='d3d12' if sys.platform=='win32' else 'metal' if sys.platform=='darwin' else 'cpu'
    if args.require_gpu and args.compute=='cpu':parser.error('--require-gpu cannot select CPU processing')
    gpu_backend=None
    # Resolve build/runtime requirements before importing scientific packages.
    missing = []
    try:
        from spectral_app.storage import DataStorage
        storage=DataStorage.configured()
        storage.activate_temporary_directory()
        if sys.platform=='win32' and storage.root is None:
            missing.append('Configure an external RAW/hyperspectral data volume before starting the Windows application.')
    except (OSError,ValueError,RuntimeError) as error:
        print(json.dumps({'ok':False,'missing':[str(error)]},ensure_ascii=False),flush=True)
        return 2
    materials = args.archive/'output/reversal-E100/data'
    assets = [(name, materials/name) for name in ('E100_dye_density_CMY.csv',
        'E100_characteristic_RGB.csv', 'E100_linear_sensitivity_RGB.csv')]
    assets += [('Status A density weights', args.archive/'output/reversal-E100/intermediate/model.npz')]
    assets += [(name, args.archive.parent/'data'/name) for name in (
        'CIE_xyz_official.csv', 'CIE_std_illum_D50.csv', 'CIE_std_illum_D65.csv')]
    assets += [("optimized sampling "+name,science/'artifacts/sampling-database'/name) for name in ('report.json','reversal.sqlite','negative.sqlite','models/reversal.npz','models/negative.npz')]
    assets += [('OpenDRT v1.0.0 mini config', args.opendrt)]
    for name, path in assets:
        if not path.is_file():
            missing.append(name)
    try:
        from spectral_lut.native import NativeCore
        core = NativeCore(args.core)
        from spectral_app.imaging.png_codec import PngLibrary
        PngLibrary(core.path.with_name(('' if sys.platform=='win32' else 'lib')+'softloaf_imageio'+core.path.suffix))
        if args.compute=='metal':
            from spectral_lut.metal import MetalBackend
            MetalBackend(core.path.with_name('libsoftloaf_metal.dylib'))
        elif args.compute=='d3d12':
            from spectral_lut.d3d12 import D3D12Backend
            from spectral_app.compute_policy import choose_backend
            gpu_backend=choose_backend('d3d12',lambda:D3D12Backend(core.path.with_name('softloaf_d3d12.dll')),strict=args.require_gpu)
            if gpu_backend is None:args.compute='cpu'
    except (ImportError, RuntimeError, OSError) as error:
        missing.append(str(error))
    for module in ('colour', 'scipy', 'PIL', 'PyOpenColorIO', 'tifffile'):
        if importlib.util.find_spec(module) is None:
            missing.append('Python dependency: '+module)
    if args.check or missing:
        print(json.dumps({'ok': not missing, 'missing': missing,'backend':args.compute,'reference':'C++23 float64 / ABI 1'}, ensure_ascii=False), flush=True)
        return 0 if not missing else 2
    if args.parent_pid:
        def watch_parent():
            while True:
                try:
                    from spectral_app.processes import process_alive
                    if not process_alive(args.parent_pid):os._exit(0)
                except OSError:os._exit(0)
                time.sleep(1)
        threading.Thread(target=watch_parent, daemon=True).start()
    from experiments.gui_recipe_server import make_server
    from spectral_app.model import SpectralModel
    from spectral_app.application import Application
    model = SpectralModel(args.archive, args.opendrt, args.output, core=core)
    if args.compute=='metal':
        from spectral_app.metal_renderer import MetalRenderer
        model.metal=MetalRenderer(model,core.path.with_name('libsoftloaf_metal.dylib'))
    elif args.compute=='d3d12':
        from spectral_app.metal_renderer import MetalRenderer
        model.metal=MetalRenderer(model,backend=gpu_backend)
    application=Application(model)
    if gpu_backend and not args.require_gpu:
        def fallback(error):
            import hashlib
            model.metal=None
            application.rendition_identity=hashlib.sha256((application.rendition_identity+'/cpu-recovery').encode()).hexdigest()
        gpu_backend.on_failure=fallback
    server = make_server(application, root/'design/gui-v2/index.html',
                         root/'assets/branding/softloaf-spectral.png', args.port)
    ready = {'ok': True, 'url': f'http://127.0.0.1:{server.server_port}/', 'pid': os.getpid(),'backend':args.compute,
             'browser_cache':(storage.root/'browser' if storage.root else args.output/'browser').as_posix()}
    if args.ready_file:
        temporary = args.ready_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(ready,ensure_ascii=False),encoding='utf-8')
        temporary.replace(args.ready_file)
    print(json.dumps(ready), flush=True)
    event('service.ready',pid=os.getpid(),port=server.server_port,backend=args.compute)
    if args.stop_event and sys.platform=='win32':
        def wait_owner():
            import ctypes as ct
            kernel=ct.WinDLL('kernel32',use_last_error=True)
            kernel.OpenEventW.argtypes=[ct.c_uint32,ct.c_int,ct.c_wchar_p];kernel.OpenEventW.restype=ct.c_void_p
            kernel.WaitForSingleObject.argtypes=[ct.c_void_p,ct.c_uint32];kernel.CloseHandle.argtypes=[ct.c_void_p]
            handle=kernel.OpenEventW(0x00100000,False,args.stop_event)
            if not handle:return
            try:kernel.WaitForSingleObject(handle,0xffffffff);server.shutdown()
            finally:kernel.CloseHandle(handle)
        threading.Thread(target=wait_owner,daemon=True).start()
    def stop(*_):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        event('service.stopping',pid=os.getpid())
        server.server_close()
        if args.ready_file:
            args.ready_file.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
