"""Immutable density -> linear ACES nodes, independent of viewing exposure.

This is a frozen numerical transform, not an image or a RAW development stage.
The caller supplies its physical identity; all files use the external workbench.
"""
import json
from pathlib import Path
import uuid
import numpy as np
from .raw import digest
from ..exporting.lut_files import grid_blocks


class LinearScanTable:
    @classmethod
    def create(cls,root,key,size,low,high,render):
        low,high=np.asarray(low,float),np.asarray(high,float)
        if (len(key)!=64 or any(c not in '0123456789abcdef' for c in key) or type(size)!=int
                or not 2<=size<=129 or low.shape!=(3,) or high.shape!=(3,)
                or not np.isfinite([low,high]).all() or np.any(high<=low)):raise ValueError('Invalid frozen linear scan table')
        root=Path(root);root.mkdir(parents=True,exist_ok=True);folder=root/key
        if not folder.exists():
            temporary=root/(key+'.working-'+uuid.uuid4().hex);temporary.mkdir()
            path=temporary/'aces.npy'
            nodes=np.lib.format.open_memmap(path,mode='w+',dtype=np.float64,shape=(size**3,3))
            try:
                for start,points in grid_blocks(size,low,high,1024):
                    values=np.asarray(render(points),float)
                    if values.shape!=points.shape or not np.isfinite(values).all():raise ValueError('Invalid linear ACES nodes')
                    nodes[start:start+len(values)]=values
                nodes.flush()
            finally:nodes._mmap.close()
            record={'schema':1,'key':key,'size':size,'low':low.tolist(),'high':high.tolist(),
                'sha256':digest(path),'quantity':'linear ACES2065-1 / AP0 / D60; no viewing compensation; red-fast density grid'}
            (temporary/'table.json').write_text(json.dumps(record));temporary.replace(folder)
        try:
            record=json.loads((folder/'table.json').read_text());path=folder/'aces.npy'
            if (record['schema']!=1 or record['key']!=key or record['size']!=size
                    or not np.array_equal(record['low'],low) or not np.array_equal(record['high'],high)
                    or digest(path)!=record['sha256']):raise ValueError('Frozen linear scan table changed')
            self=cls();self.nodes=np.load(path,mmap_mode='r',allow_pickle=False)
            if self.nodes.shape!=(size**3,3) or self.nodes.dtype!=np.float64:
                self.nodes._mmap.close();raise ValueError('Frozen linear scan table changed')
            self.size=size;self.low=low;self.high=high;self.path=path
            return self
        except (OSError,KeyError,json.JSONDecodeError):raise ValueError('Frozen linear scan table changed') from None

    def renderer(self,display):
        cursor=0
        def render(points):
            nonlocal cursor
            end=cursor+len(points)
            ids=np.arange(cursor,end);n=self.size
            expected=self.low+np.column_stack([ids%n,(ids//n)%n,ids//(n*n)])*(self.high-self.low)/(n-1)
            if end>len(self.nodes) or not np.allclose(points,expected,rtol=0,atol=1e-12):raise ValueError('Linear scan node order/domain changed')
            value=display(self.nodes[cursor:end]);cursor=end
            return value
        return render

    def close(self):self.nodes._mmap.close()
