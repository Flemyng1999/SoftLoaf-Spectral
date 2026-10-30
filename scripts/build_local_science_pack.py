"""Prepare local verification inputs, never a public redistributable data pack."""
import argparse
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from spectral_app.runtime_setup import file_digest,validate_science


def build(root,destination):
    from spectral_app.storage import DataStorage
    root=Path(root).resolve();destination=Path(destination).absolute();storage=DataStorage.configured()
    storage.validate()
    if not storage.volume or not destination.resolve().is_relative_to(storage.volume.resolve()):
        raise ValueError('Local science inputs must remain on the configured external volume')
    if destination.exists():raise FileExistsError('Use a new data-pack directory; existing data are never overwritten')
    files=set()
    def add(name):
        if not (root/name).is_file():raise FileNotFoundError(name)
        files.add(name)
    base='local/film-color-slides/hyperspectral-demo/output/reversal-E100/'
    for name in ('E100_characteristic_RGB.csv','E100_linear_sensitivity_RGB.csv','E100_dye_density_CMY.csv'):add(base+'data/'+name)
    add(base+'intermediate/model.npz')
    for name in ('CIE_xyz_official.csv','CIE_std_illum_D50.csv','CIE_std_illum_D65.csv'):add('local/film-color-slides/data/'+name)
    for name in ('report.json','reversal.sqlite','negative.sqlite','models/reversal.npz','models/negative.npz'):add('artifacts/sampling-database/'+name)
    add('local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip')
    manifest=json.loads((root/'data/5207-reference-manifest.json').read_text())
    for name in manifest['sha256']:add('local/materials/5207-v1/'+name)
    add('local/materials/status-m-iso1984/table4.json')
    for name,key,directory,roles in [
        ('film-presets-manifest.json','recipes','film-presets-v1',('file',)),
        ('reversal-presets-manifest.json','materials','reversal-presets-v1',('file','plot_file')),
        ('paper-presets-manifest.json','materials','paper-presets-v1',('file','plot_file')),
        ('vision3-materials-manifest.json','materials','vision3-source-v2',('file','plot_file'))]:
        catalog=json.loads((root/'data'/name).read_text())
        for entry in catalog[key]:
            for role in roles:add('local/materials/'+directory+'/'+entry[role])
    add('local/materials/e100-plot-v1/sensitivity.json')
    optics=json.loads((root/'data/printing-optics-manifest.json').read_text())
    for name in optics['files']:add('local/reference-assets/spektrafilm/printing-optics/'+name)
    add('local/reference-assets/spektrafilm/profile-survey/kodak_ultra_endura.json')
    add('local/reference-assets/spektrafilm/SPEKTRAFILM_LICENSE.txt')
    destination.mkdir(parents=True)
    records=[]
    for name in sorted(files):
        src=root/name;target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,target)
        if file_digest(src)!=file_digest(target):raise RuntimeError('Source changed while copying: '+name)
        records.append({'path':name,'sha256':file_digest(target),'bytes':target.stat().st_size})
    manifest={'schema':'softloaf.runtime-science/1','scope':'local-verification-only',
        'public_distribution_approved':False,'contains_user_raw_or_scan_calibration':False,'files':records}
    (destination/'runtime-science.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    validate_science(destination)
    return {'files':len(records),'bytes':sum(x['bytes'] for x in records),'public_distribution_approved':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.root,args.destination)))
