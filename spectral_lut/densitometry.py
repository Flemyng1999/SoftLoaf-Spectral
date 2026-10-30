"""Source-pinned Status M spectral products, separate from APD output weights."""
import hashlib
import json

import numpy as np


def load_status_m(root,grid,*,data_root=None):
    manifest=json.loads((root/'data/status-m-reference-manifest.json').read_text())
    path=(data_root or root)/'local/materials/status-m-iso1984/table4.json'
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['table_sha256']:
        raise ValueError('Status M source identity mismatch; extract the reviewed standard table.')
    data=json.loads(path.read_text());x=np.asarray(grid,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all() or np.any(np.diff(x)<=0):
        raise ValueError('Status M requires a finite increasing wavelength grid.')
    products=[]
    for c in 'RGB':
        channel=data['channels'][c];knots=np.asarray(channel['wavelengths_nm']);values=np.asarray(channel['log10_products'])
        low,high=channel['tail_slopes_per_nm']
        v=np.interp(x,knots,values)
        v[x<knots[0]]=values[0]+low*(x[x<knots[0]]-knots[0])
        v[x>knots[-1]]=values[-1]+high*(x[x>knots[-1]]-knots[-1])
        products.append(10.**(v-data['peak_log10']))
    return np.column_stack(products),{'metric':'Status M','reference':data['reference'],
        'pdf_sha256':data['pdf_sha256'],'table_sha256':manifest['table_sha256'],
        'interpolation':'linear in log10 spectral product',
        'tail_extrapolation':'printed channel-specific log10 slopes; finite-band normalized integration',
        'normative_conformance':False}
