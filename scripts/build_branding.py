"""Package the selected owner-supplied logo without a visual redesign."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

SIZES=(16,20,24,32,40,48,64,96,128,256)


def build(source, output):
    source,output=Path(source),Path(output)
    with Image.open(source) as loaded:
        loaded.load()
        if loaded.width!=loaded.height or loaded.width<1024:
            raise ValueError('The selected square logo must be at least 1024 pixels')
        master=loaded.convert('RGBA')
    output.mkdir(parents=True,exist_ok=True)
    frames={size:master.resize((size,size),Image.Resampling.LANCZOS)
            for size in {*SIZES,512,1024}}
    frames[1024].save(output/'softloaf-spectral.png',compress_level=9)
    frames[256].save(output/'SoftLoafSpectral.ico',sizes=[(n,n) for n in SIZES],
                     append_images=[frames[n] for n in SIZES if n!=256])
    frames[1024].save(output/'SoftLoafSpectral.icns',
                      append_images=[frames[n] for n in (32,64,128,256,512)])
    files={name:hashlib.sha256((output/name).read_bytes()).hexdigest()
           for name in ('softloaf-spectral.png','SoftLoafSpectral.ico','SoftLoafSpectral.icns')}
    with Image.open(output/'SoftLoafSpectral.ico') as ico:
        if ico.info['sizes']!={(n,n) for n in SIZES}:raise ValueError('ICO frame set changed')
        for size in SIZES:
            frame=ico.ico.getimage((size,size));frame.load()
            if frame.convert('RGBA').tobytes()!=frames[size].tobytes():
                raise ValueError('ICO pixel readback differs')
    with Image.open(output/'SoftLoafSpectral.icns') as icns:
        icns.load()
        if icns.size!=(1024,1024):raise ValueError('ICNS master size differs')
        if icns.convert('RGBA').tobytes()!=frames[1024].tobytes():raise ValueError('ICNS pixel readback differs')
    manifest={'schema':1,'application':{'en':'SoftLoaf Spectral','zh-CN':'面包光谱'},
              'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'selection':'Colorful background, original bread-cat, no mohawk',
              'operation':'Lanczos size conversion and PNG/ICO/ICNS packaging only',
              'ico_sizes':list(SIZES),'master_size':1024,'files':files}
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('assets/branding/softloaf-spectral-source.png'))
    parser.add_argument('--output',type=Path,default=Path('assets/branding'))
    args=parser.parse_args();print(json.dumps(build(args.source,args.output),ensure_ascii=False))
