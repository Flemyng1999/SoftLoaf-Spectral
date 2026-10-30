"""Float64 bounded inversion of a fixed passive CMY transmittance model."""
import numpy as np
from scipy.spatial import cKDTree


class MaterialInverse:
    def __init__(self,dyes,base,weights,low,high):
        self.dyes=np.asarray(dyes,float);self.base=np.asarray(base,float);self.weights=np.asarray(weights,float)
        self.low=np.asarray(low,float);self.high=np.asarray(high,float)
        if (self.dyes.shape!=(len(self.base),3) or self.weights.shape!=self.dyes.shape or self.low.shape!=(3,) or self.high.shape!=(3,)
                or np.any(self.high<=self.low) or not all(np.isfinite(a).all() for a in (self.dyes,self.base,self.weights,self.low,self.high))
                or np.min(self.weights)<0 or np.any(self.weights.sum(0)<=0)):raise ValueError('Invalid material inverse')
        minimum=self.base+np.where(self.dyes>=0,self.dyes*self.low,self.dyes*self.high).sum(1)
        if np.min(minimum)<-1e-12:raise ValueError('Non-passive material domain')
        grid=np.meshgrid(*(np.linspace(l,h,17) for l,h in zip(self.low,self.high)),indexing='ij')
        self.grid=np.stack(grid,-1).reshape(-1,3)
        prediction=self.forward(self.grid)
        self.tree=cKDTree(np.log10(np.maximum(prediction,1e-12)))

    def forward(self,amounts):
        return 10**-(self.base+np.asarray(amounts)@self.dyes.T)@self.weights

    def solve(self,camera,*,iterations=18):
        rgb=np.asarray(camera,float)
        if rgb.ndim!=2 or rgb.shape[1]!=3 or not np.isfinite(rgb).all():raise ValueError('Expected finite Nx3 camera channels')
        observed=np.log10(np.maximum(rgb,1e-12))
        a=self.grid[self.tree.query(observed)[1]].copy()
        # Independent vectorized Gauss-Newton in log sensor signals. Production
        # image orchestration supplies bounded blocks; this is a float64 oracle.
        for _ in range(iterations):
            t=10**-(self.base+a@self.dyes.T);prediction=t@self.weights
            j=-np.einsum('nl,lc,lk->nck',t,self.weights,self.dyes,optimize=True)/np.maximum(prediction[:,:,None],1e-30)
            residual=np.log10(np.maximum(prediction,1e-30))-observed
            normal=np.einsum('nck,ncj->nkj',j,j)+np.eye(3)*1e-10
            step=np.linalg.solve(normal,np.einsum('nck,nc->nk',j,residual)[...,None])[...,0]
            step=np.clip(step,-.3,.3)
            new=np.clip(a-step,self.low,self.high)
            if np.max(np.abs(new-a),initial=0)<1e-10:a=new;break
            a=new
        prediction=self.forward(a);error=np.max(np.abs(np.log10(np.maximum(prediction,1e-30))-observed),axis=1)
        t=10**-(self.base+a@self.dyes.T)
        jacobian=-np.einsum('nl,lc,lk->nck',t,self.weights,self.dyes,optimize=True)/np.maximum(prediction[:,:,None],1e-30)
        condition=np.linalg.cond(jacobian)
        bounds=np.any((a-self.low<1e-6)|(self.high-a<1e-6),axis=1)
        return {'amounts':a,'prediction':prediction,'max_log10_residual':error,'at_bound':bounds,'jacobian_condition':condition,
            'valid':(error<.01)&(condition<1e5)&np.all(rgb>1/65535,axis=1)&np.all(rgb<1.001,axis=1)}
