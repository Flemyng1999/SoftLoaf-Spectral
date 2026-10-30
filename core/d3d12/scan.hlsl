// Generated from owned kernel SHA256 e24a314f7bacab2a710ada7c2177f40740e3880fe451d53d0bf081e885f81317
StructuredBuffer<float> input : register(t0, space1);
StructuredBuffer<float> d : register(t1, space1);
StructuredBuffer<uint> m : register(t2, space1);
RWStructuredBuffer<float> output : register(u0, space1);
cbuffer DispatchCount : register(b0, space1) { uint count; };
#define NAN asfloat(0x7fc00000u)
float3 sl_select(float3 a,float3 b,bool3 condition) { return float3(condition.x?b.x:a.x,condition.y?b.y:a.y,condition.z?b.z:a.z); }
uint3 sl_axis(uint axis) { return uint3(axis==0?1:0,axis==1?1:0,axis==2?1:0); }
// One source sampling pass: frozen geometry coordinates + source-space flat,
// camera log density and tetrahedral LUT. Coordinates carry their source halo.


float3 scan_vec(StructuredBuffer<float> a,uint i){return float3(a[i],a[i+1],a[i+2]);}
float3 srgb_linear(float3 c){return sl_select(pow(max((c+.055f)/1.055f,0.f),(float3)(2.4f)),c/12.92f,c<=.04045f);}
float3 srgb_encoded(float3 c){return sl_select(1.055f*pow(max(c,0.f),(float3)(1.f/2.4f))-.055f,12.92f*c,c<=.0031308f);}
float3 flat_delta(StructuredBuffer<float> d,uint offset,uint w,uint2 p){uint q=offset+(p.y*w+p.x)*4;return (scan_vec(d,q)-1.f)*d[q+3];}
float3 spatial_gain(StructuredBuffer<float> d,StructuredBuffer<uint> m,int x,int y){
    float2 q=clamp((float2(x,y)+.5f)/float2(m[4],m[5])*float2(m[9],m[10])-.5f,(float2)(0),float2(m[9]-1,m[10]-1));
    uint2 b=min((uint2)(floor(q)),uint2(m[9]-2,m[10]-2));float2 f=q-(float2)(b);
    return 1.f+lerp(lerp(flat_delta(d,m[11],m[9],b),flat_delta(d,m[11],m[9],b+uint2(1,0)),f.x),
                  lerp(flat_delta(d,m[11],m[9],b+uint2(0,1)),flat_delta(d,m[11],m[9],b+1),f.x),f.y);
}
float3 scan_point(uint3 p,StructuredBuffer<float> d,uint n){return scan_vec(d,24+((p.z*n+p.y)*n+p.x)*3);}
float3 tetra(float3 value,StructuredBuffer<float> d,uint n){
    float3 q=clamp((value-scan_vec(d,18))/(scan_vec(d,21)-scan_vec(d,18)),0.f,1.f)*float(n-1);
    uint3 b=min((uint3)(floor(q)),(uint3)(n-2));float3 f=q-(float3)(b);uint o[3]={0,1,2};
    [loop] for(uint i=0;i<2;i++)[loop] for(uint j=0;j<2-i;j++)if(f[o[j]]<f[o[j+1]]){uint t=o[j];o[j]=o[j+1];o[j+1]=t;}
    uint3 a=b+1,c=b;a-=sl_axis(o[2]);c+=sl_axis(o[0]);
    float3 v0=scan_point(b,d,n),v1=scan_point(c,d,n),v2=scan_point(a,d,n),v3=scan_point(b+1,d,n);
    return v0+f[o[0]]*(v1-v0)+f[o[1]]*(v2-v1)+f[o[2]]*(v3-v2);
}
[numthreads(64,1,1)]
void sl_pixels(uint3 dispatch_id : SV_DispatchThreadID) {
    uint i=dispatch_id.x;
    if(i>=count)return;
    int ix=int(input[i*6]),iy=int(input[i*6+1]);float fx=input[i*6+2],fy=input[i*6+3],rx=input[i*6+4],ry=input[i*6+5];
    float px=float(ix)+fx,py=float(iy)+fy;float3 color=0;float total=0;
    if(px>=-.5f&&py>=-.5f&&px<float(m[4])-.5f&&py<float(m[5])-.5f){
        int nx=int(ceil(rx))+1,ny=int(ceil(ry))+1;
        [loop] for(int dy=-ny;dy<=ny;dy++){
            int y=iy+dy;if(y<0||y>=int(m[5]))continue;float wy=max(0.f,1.f-abs(float(dy)-fy)/ry);if(wy==0)continue;
            [loop] for(int dx=-nx;dx<=nx;dx++){
                int x=ix+dx;if(x<0||x>=int(m[4]))continue;float w=wy*max(0.f,1.f-abs(float(dx)-fx)/rx);if(w==0)continue;
                int lx=x-int(m[2]),ly=y-int(m[3]);
                if(lx<0||ly<0||lx>=int(m[0])||ly>=int(m[1])){color=(float3)(NAN);total=1;break;}
                float xx=2.f*float(x)/float(max(m[4]-1,1u))-1.f,yy=2.f*float(y)/float(max(m[5]-1,1u))-1.f;
                float3 logflat=scan_vec(d,0)+yy*scan_vec(d,3)+xx*scan_vec(d,6)+yy*yy*scan_vec(d,9)+xx*yy*scan_vec(d,12)+xx*xx*scan_vec(d,15);
                float3 gain=m[9]>1?spatial_gain(d,m,x,y):exp(-logflat);
                float3 value=scan_vec(d,m[7]+(uint(ly)*m[0]+uint(lx))*3);
                if(m[8]==3u)value=srgb_linear(value);
                color+=w*value*(m[8]>=2u?1.f:1.f/65535.f)*gain;total+=w;
            }
        }
        color=total>0?color/total:(float3)(0);
        if(m[6]>1)color=tetra(-log10(max(color,(float3)(1e-12f))),d,m[6]);
        else if(m[8]==3u)color=srgb_encoded(color);
        else if(m[8]==1u)color=pow(clamp(color,0.f,1.f),(float3)(1.f/2.2f));
    }
    output[i*3]=color.x;output[i*3+1]=color.y;output[i*3+2]=color.z;
}
