"""One inverse coordinate map for crop, quarter-turns, scale and radial geometry.

No image is resampled here. The sampler consumes the resulting coordinates once.
Radial scale is a polynomial in radius / half original image diagonal.
"""
import numpy as np
from scipy.optimize import brentq

DEFAULT={'rotation':0,'crop':[0,0,1,1],'radial':[1,0,0,0,0],'zoom':1}


def maximum_scale(radial,end=1):
    c=np.asarray(radial,float);roots=np.polynomial.polynomial.polyroots(np.arange(1,len(c))*c[1:])
    x=[0.,end,*[r.real for r in roots if abs(r.imag)<1e-9 and 0<r.real<end]]
    return float(np.max(np.polynomial.polynomial.polyval(x,c)))


def auto_zoom(radial):
    upper=maximum_scale(radial)
    if upper<=1:return 1.
    return float(brentq(lambda z:maximum_scale(radial,1/z)-z,1,upper+1e-5)+2e-6)


class Geometry:
    def __init__(self,settings,width,height):
        self.settings={**DEFAULT,**(settings or {})};s=self.settings
        self.rotation=s['rotation'];self.crop=np.asarray(s['crop'],float);self.radial=np.asarray(s['radial'],float);self.zoom=s['zoom']
        if (type(self.rotation)!=int or not 0<=self.rotation<=3 or self.crop.shape!=(4,)
                or self.radial.shape!=(5,) or not np.isfinite(self.crop).all() or not np.isfinite(self.radial).all()
                or np.any(self.crop<0) or np.any(self.crop>1) or np.any(self.crop[2:]-self.crop[:2]<.005)
                or not np.isfinite(self.zoom) or not 1<=self.zoom<=4 or np.max(np.abs(self.radial))>4):raise ValueError('Invalid frozen geometry')
        derivative=np.arange(1,6)*self.radial
        extrema=np.polynomial.polynomial.polyroots(np.arange(1,5)*derivative[1:])
        radii=[0.,1.01,*[r.real for r in extrema if abs(r.imag)<1e-9 and 0<r.real<1.01]]
        if np.min(np.polynomial.polynomial.polyval(radii,derivative))<=.05:raise ValueError('Geometry folds or becomes singular')
        self.width=int(width);self.height=int(height)
    def size(self,short_edge=None):
        w,h=(self.height,self.width) if self.rotation%2 else (self.width,self.height)
        w=max(1,round(w*(self.crop[2]-self.crop[0])));h=max(1,round(h*(self.crop[3]-self.crop[1])))
        f=min(1,short_edge/min(w,h)) if short_edge else 1
        return max(1,round(w*f)),max(1,round(h*f))
    def map(self,x,y,size):
        u=self.crop[0]+(np.asarray(x)+.5)/size[0]*(self.crop[2]-self.crop[0])
        v=self.crop[1]+(np.asarray(y)+.5)/size[1]*(self.crop[3]-self.crop[1])
        if self.rotation==1:u,v=v,1-u
        elif self.rotation==2:u,v=1-u,1-v
        elif self.rotation==3:u,v=1-v,u
        dx=(u-.5)*self.width/self.zoom;dy=(v-.5)*self.height/self.zoom
        radius=np.hypot(dx,dy)/(.5*np.hypot(self.width,self.height))
        scale=np.polynomial.polynomial.polyval(radius,self.radial)
        return (self.width-1)/2+dx*scale,(self.height-1)/2+dy*scale
    def coordinates(self,region,size):
        y,x=np.mgrid[region.y:region.y+region.height,region.x:region.x+region.width]
        sx,sy=self.map(x,y,size);ax,ay=self.map(x+1,y,size);bx,by=self.map(x,y+1,size)
        rx=np.maximum(1,np.hypot(ax-sx,bx-sx));ry=np.maximum(1,np.hypot(ay-sy,by-sy))
        ix,iy=np.floor(sx),np.floor(sy)
        # Preserve subpixel precision on large originals by transporting integer
        # and fractional coordinates separately rather than rounding x+y first.
        return np.column_stack([ix.ravel(),iy.ravel(),(sx-ix).ravel(),(sy-iy).ravel(),rx.ravel(),ry.ravel()]).astype(np.float32)


def source_bounds(coordinates,width,height):
    x=coordinates[:,0].astype(float)+coordinates[:,2];y=coordinates[:,1].astype(float)+coordinates[:,3]
    x0=max(0,int(np.floor(np.min(x-coordinates[:,4]))));y0=max(0,int(np.floor(np.min(y-coordinates[:,5]))))
    x1=min(width,int(np.ceil(np.max(x+coordinates[:,4])))+1);y1=min(height,int(np.ceil(np.max(y+coordinates[:,5])))+1)
    if x1<=x0 or y1<=y0:return 0,0,1,1
    return x0,y0,x1-x0,y1-y0
