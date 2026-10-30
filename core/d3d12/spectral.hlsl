// Generated from owned kernel SHA256 b65a39585dfac6744d7dc88b5410fccebea6a99b6088e4235293281cfd8c6298
StructuredBuffer<float> input : register(t0, space1);
StructuredBuffer<float> d : register(t1, space1);
StructuredBuffer<uint> m : register(t2, space1);
RWStructuredBuffer<float> output : register(u0, space1);
cbuffer DispatchCount : register(b0, space1) { uint count; };
#define NAN asfloat(0x7fc00000u)
float3 sl_select(float3 a,float3 b,bool3 condition) { return float3(condition.x?b.x:a.x,condition.y?b.y:a.y,condition.z?b.z:a.z); }
uint3 sl_axis(uint axis) { return uint3(axis==0?1:0,axis==1?1:0,axis==2?1:0); }
// Fused pointwise spectral calculation; no image-sized intermediate spectra.
// Row-major float tables and offset layout are packed by metal_renderer.py.
// ADX input constants/algorithm follow spectral_lut/negative.py and Academy
// ADX16_to_ACES a1.0.3. Copyright 2015 Academy of Motion Picture Arts and
// Sciences. All rights reserved. See third_party/aces-v1.2/LICENSE.md.



static const uint NS=0;
static const uint NV=1;
static const uint NC=2;
static const uint PC=3;
static const uint MODE=4;
static const uint ROUTE=5;
static const uint PURPOSE=6;
static const uint BASIS=7;
static const uint EXPOSURE=8;
static const uint AXIS=9;
static const uint AMOUNTS=10;
static const uint DYES=11;
static const uint BASE=12;
static const uint KERNEL=13;
static const uint ADAPT=14;
static const uint PAXIS=15;
static const uint PAMOUNTS=16;
static const uint PDYES=17;
static const uint PBASE=18;
static const uint PEXPOSURE=19;
static const uint PRINTFACTOR=20;
static const uint PREFLASH=21;
static const uint APD=22;
static const uint DMIN=23;
static const uint CID=24;
static const uint EXPACES=25;
static const uint AP0XYZ=26;
static const uint REFMATRIX=27;
static const uint REFKERNEL=28;
static const uint FANCHOR=29;
static const uint PANCHOR=30;
static const uint FILMSCALE=31;
static const uint INPUTSCALE=32;
static const uint PRIOR=33;
static const uint PN=34;
static const uint PK=35;
static const uint PRGB=36;
static const uint PSPECTRA=37;
static const uint PSCALE=38;
static const uint PLUMA=39;
static const uint PRIDGE=40;
static const uint LUTSIZE=41;
static const uint LUTTABLE=42;
static const uint LUTLOW=43;
static const uint LUTHIGH=44;
static const uint LUTDISPLAY=45;
float3 sl_vec(StructuredBuffer<float> d,uint offset) {return float3(d[offset],d[offset+1],d[offset+2]);}
float3 sl_matrix(float3 v,StructuredBuffer<float> d,uint offset) {
    return float3(dot(v,sl_vec(d,offset)),dot(v,sl_vec(d,offset+3)),dot(v,sl_vec(d,offset+6)));
}
float sl_curve(float x,uint channel,StructuredBuffer<float> d,uint axis,uint values,uint count) {
    if(x<=d[axis])return d[values+channel];
    if(x>=d[axis+count-1])return d[values+(count-1)*3+channel];
    uint lo=0,hi=count-1;
    [loop] while(hi-lo>1){uint mid=(lo+hi)/2;if(x<d[axis+mid])hi=mid;else lo=mid;}
    float t=(x-d[axis+lo])/(d[axis+hi]-d[axis+lo]);
    return lerp(d[values+lo*3+channel],d[values+hi*3+channel],t);
}
float3 sl_develop(float3 exposure,float anchor,StructuredBuffer<float> d,uint axis,uint values,uint count) {
    float3 x=anchor+log10(max(exposure,(float3)(1e-30f)));
    return float3(sl_curve(x.x,0,d,axis,values,count),sl_curve(x.y,1,d,axis,values,count),sl_curve(x.z,2,d,axis,values,count));
}
float sl_acescct_decode(float v){return v<=.155251141552511f?(v-.0729055341958355f)/10.5402377416545f:exp2(v*17.52f-9.72f);}
static const float sl_toe_x[11]={-.19f,.01f,.028f,.054f,.095f,.145f,.22f,.30f,.40f,.50f,.60f};
static const float sl_toe_y[11]={-6.f,-2.721718645f,-2.521718645f,-2.321718645f,-2.121718645f,-1.921718645f,-1.721718645f,-1.521718645f,-1.321718645f,-1.121718645f,-.926545676714876f};
float sl_log_exposure(float cid){
    if(cid<=sl_toe_x[0])return sl_toe_y[0];
    if(cid>.6f)return cid*(100.f/55.f)-((7120.f-1520.f)/8000.f*(100.f/55.f)-log10(.18f));
    [loop] for(uint i=1;i<11;i++)if(cid<=sl_toe_x[i])return lerp(sl_toe_y[i-1],sl_toe_y[i],(cid-sl_toe_x[i-1])/(sl_toe_x[i]-sl_toe_x[i-1]));
    return sl_toe_y[10];
}
// Exact k-th distance selection; only a fixed 512-sample thread scratch array.
float sl_radius(inout float keys[512],uint n,uint k) {
    uint left=0,right=n-1;
    [loop] while(left<right){
        float pivot=keys[(left+right)/2];int i=int(left),j=int(right);
        [loop] while(i<=j){[loop] while(keys[i]<pivot)i++;[loop] while(keys[j]>pivot)j--;if(i<=j){float t=keys[i];keys[i]=keys[j];keys[j]=t;i++;j--;}}
        if(int(k)<=j)right=uint(j);else if(int(k)>=i)left=uint(i);else break;
    }
    return keys[k];
}
float3 sl_solve(float3 a,float3 b,float3 c,float3 p) {
    // The regularized Gram matrix is symmetric positive definite. LDL avoids
    // subtracting nearly equal triple products in a determinant inverse.
    float scale=max(a.x,max(b.y,c.z));a/=scale;b/=scale;c/=scale;p/=scale;
    float l10=a.y/a.x,l20=a.z/a.x,d1=b.y-l10*a.y;
    float l21=(b.z-l20*a.y)/d1,d2=c.z-l20*a.z-l21*l21*d1;
    float y0=p.x,y1=p.y-l10*y0,y2=p.z-l20*y0-l21*y1;
    float z2=y2/d2,z1=y1/d1-l21*z2;
    return float3(y0/a.x-l10*z1-l20*z2,z1,z2);
}
// The fitted local prior is evaluated from its original training subset, not
// replaced with a second LUT or with an E100 material response.
void sl_local(float3 rgb,StructuredBuffer<float> d,StructuredBuffer<uint> m,
              inout float weights[512],out float3 coefficient,out float penalty) {
    float y=dot(rgb,sl_vec(d,m[PLUMA]));
    float2 scale=float2(d[m[PSCALE]],d[m[PSCALE]+1]);float2 query=rgb.xz/y/scale;
    float distances[512];uint n=m[PN];bool large=dot(query,query)>1e6f;
    [loop] for(uint j=0;j<n;j++){float2 x=sl_vec(d,m[PRGB]+j*3).xz/scale;float2 delta=query-x;distances[j]=large?dot(x,x)-2.f*dot(query,x):dot(delta,delta);}
    float threshold=sl_radius(distances,n,m[PK]-1);float radius=max(large?dot(query,query)+threshold:threshold,1e-24f);float total=0;
    [loop] for(uint j=0;j<n;j++){
        float2 x=sl_vec(d,m[PRGB]+j*3).xz/scale;float2 delta=query-x;float metric=large?dot(x,x)-2.f*dot(query,x):dot(delta,delta);float v=max(0.f,(threshold-metric)/radius);
        weights[j]=v*v;total+=weights[j];
    }
    if(total<1e-14f){
        uint found=0;
        [loop] for(uint j=0;j<n;j++){float2 x=sl_vec(d,m[PRGB]+j*3).xz/scale;float2 delta=query-x;float metric=large?dot(x,x)-2.f*dot(query,x):dot(delta,delta);weights[j]=metric<threshold?1.f:0.f;if(weights[j]>0.f)found++;}
        [loop] for(uint j=0;j<n&&found<m[PK];j++){float2 x=sl_vec(d,m[PRGB]+j*3).xz/scale;float2 delta=query-x;float metric=large?dot(x,x)-2.f*dot(query,x):dot(delta,delta);if(metric==threshold){weights[j]=1.f;found++;}}
        total=float(found);
    }
    float3 a=0,b=0,c=0;
    [loop] for(uint j=0;j<n;j++){
        weights[j]/=total;float3 x=sl_vec(d,m[PRGB]+j*3)*weights[j];float3 original=sl_vec(d,m[PRGB]+j*3);
        a+=original.x*x;b+=original.y*x;c+=original.z*x;
    }
    penalty=d[m[PRIDGE]]*(a.x+b.y+c.z)/3.f;
    a.x+=penalty;b.y+=penalty;c.z+=penalty;coefficient=sl_solve(a,b,c,rgb);
    [loop] for(uint j=0;j<n;j++)weights[j]*=dot(sl_vec(d,m[PRGB]+j*3),coefficient);
}
float sl_signed_root(float v,float inverse){return sign(v)*pow(abs(v),inverse);}
void sl_root_features(float3 rgb,out float features[13]) {
    features[0]=rgb.x;features[1]=rgb.y;features[2]=rgb.z;uint index=3;
    [loop] for(uint degree=2;degree<=3;degree++)[loop] for(uint r=0;r<=degree;r++)[loop] for(uint g=0;g<=degree-r;g++){
        uint b=degree-r-g;if(max(r,max(g,b))==degree)continue;
        float v=1;[loop] for(uint i=0;i<r;i++)v*=rgb.x;[loop] for(uint i=0;i<g;i++)v*=rgb.y;[loop] for(uint i=0;i<b;i++)v*=rgb.z;
        features[index++]=sl_signed_root(v,1.f/float(degree));
    }
}

float3 sl_xyz(StructuredBuffer<float> input,uint pixel,StructuredBuffer<float> d,StructuredBuffer<uint> m) {
    uint mode=m[MODE],route=m[ROUTE];float input_scale=d[m[INPUTSCALE]];
    float3 rgb=mode==1?(float3)(0):sl_vec(input,pixel*3);
    if(mode==2)rgb=float3(sl_acescct_decode(rgb.x),sl_acescct_decode(rgb.y),sl_acescct_decode(rgb.z));
    rgb*=input_scale;
    if(route==3){
        if(mode!=1)return sl_matrix(rgb,d,m[REFMATRIX]);
        float3 xyz=0;[loop] for(uint i=0;i<m[NS];i++)xyz+=input[pixel*m[NS]+i]*input_scale*sl_vec(d,m[REFKERNEL]+i*3);return xyz;
    }
    float weights[512],features[13];float3 coefficient=0;float penalty=0;
    bool local=mode!=1&&m[PRIOR]==1&&dot(rgb,sl_vec(d,m[PLUMA]))>1e-8f;
    if(local)sl_local(rgb,d,m,weights,coefficient,penalty);
    if(mode!=1&&m[PRIOR]==2)sl_root_features(rgb,features);
    float3 exposure=0;
    [loop] for(uint i=0;i<m[NS];i++){
        float reflectance;
        if(mode==1)reflectance=input[pixel*m[NS]+i]*input_scale;
        else{
            float3 base=float3(d[m[BASIS]+i],d[m[BASIS]+m[NS]+i],d[m[BASIS]+2*m[NS]+i]);
            reflectance=dot(rgb,base);
            if(local){reflectance=penalty*dot(coefficient,base);[loop] for(uint j=0;j<m[PN];j++)if(weights[j]!=0.f)reflectance+=weights[j]*d[m[PSPECTRA]+j*m[NS]+i];}
            else if(m[PRIOR]==2)[loop] for(uint j=0;j<m[PN];j++)reflectance+=features[j]/d[m[PSCALE]+j]*d[m[PSPECTRA]+j*m[NS]+i];
            reflectance=max(0.f,reflectance);
        }
        exposure+=reflectance*sl_vec(d,m[EXPOSURE]+i*3);
    }
    if(m[PURPOSE]==3)return exposure*d[m[FILMSCALE]];
    float3 amounts=sl_develop(exposure*d[m[FILMSCALE]],d[m[FANCHOR]],d,m[AXIS],m[AMOUNTS],m[NC]);
    float3 integrated=0;
    [loop] for(uint j=0;j<m[NV];j++){
        float density=d[m[BASE]+j]+dot(amounts,sl_vec(d,m[DYES]+j*3));
        if(density<-.000001f)return (float3)(NAN);
        float transmission=pow(10.f,-max(density,0.f));
        if(route==1)integrated+=transmission*sl_vec(d,m[APD]+j*3);
        else if(route==2)integrated+=(transmission*d[m[PRINTFACTOR]+j]+d[m[PREFLASH]+j])*sl_vec(d,m[PEXPOSURE]+j*3);
        else integrated+=transmission*sl_vec(d,m[KERNEL]+j*3);
    }
    if(route==1){
        float3 apd=-log10(max(integrated,(float3)(1.17549435e-38f)));
        if(m[PURPOSE]==2)return apd;
        float3 cid=sl_matrix((apd-sl_vec(d,m[DMIN]))*float3(1.f,.92f,.95f),d,m[CID]);
        float3 loge=float3(sl_log_exposure(cid.x),sl_log_exposure(cid.y),sl_log_exposure(cid.z));
        return sl_matrix(sl_matrix(pow((float3)(10.f),loge),d,m[EXPACES]),d,m[AP0XYZ]);
    }
    if(route==2){
        float3 paper=sl_develop(integrated,d[m[PANCHOR]],d,m[PAXIS],m[PAMOUNTS],m[PC]);
        integrated=0;
        [loop] for(uint j=0;j<m[NV];j++){
            float density=d[m[PBASE]+j]+dot(paper,sl_vec(d,m[PDYES]+j*3));
            if(density<-.000001f)return (float3)(NAN);
            integrated+=pow(10.f,-max(density,0.f))*sl_vec(d,m[KERNEL]+j*3);
        }
    }
    return sl_matrix(integrated,d,m[ADAPT]);
}

float3 sl_lut_point(uint3 p,StructuredBuffer<float> d,StructuredBuffer<uint> m){
    uint n=m[LUTSIZE];return sl_vec(d,m[LUTTABLE]+((p.z*n+p.y)*n+p.x)*3);
}
float3 sl_tetra(float3 values,StructuredBuffer<float> d,StructuredBuffer<uint> m){
    uint n=m[LUTSIZE];float3 position=clamp((values-sl_vec(d,m[LUTLOW]))/(sl_vec(d,m[LUTHIGH])-sl_vec(d,m[LUTLOW])),0.f,1.f)*float(n-1);
    uint3 base=min((uint3)(floor(position)),(uint3)(n-2));float3 f=position-(float3)(base);uint order[3]={0,1,2};
    [loop] for(uint i=0;i<2;i++)[loop] for(uint j=0;j<2-i;j++)if(f[order[j]]<f[order[j+1]]){uint t=order[j];order[j]=order[j+1];order[j+1]=t;}
    uint3 a=base,b=base+1;a+=sl_axis(order[0]);b-=sl_axis(order[2]);
    float3 c0=sl_lut_point(base,d,m),c1=sl_lut_point(a,d,m),c2=sl_lut_point(b,d,m),c3=sl_lut_point(base+1,d,m);
    return c0+f[order[0]]*(c1-c0)+f[order[1]]*(c2-c1)+f[order[2]]*(c3-c2);
}

/* OCIO_SOURCE */

[numthreads(64,1,1)]
void sl_pixels(uint3 dispatch_id : SV_DispatchThreadID) {
    uint pixel=dispatch_id.x;
    if(pixel>=count)return;
    float3 result;
    if(m[ROUTE]==5){
        float3 value=sl_tetra(sl_vec(input,pixel*3),d,m);
        result=m[LUTDISPLAY]?sl_display(float4(value,1.f)).rgb:value;
    }else if(m[ROUTE]==4){
        float3 s=sl_vec(input,pixel*3);float scale=d[m[INPUTSCALE]];
        if(scale==1.f)result=s;
        else{
            float3 sl_linear=sl_select(pow((max(s,0.f)+.055f)/1.055f,(float3)(2.4f)),s/12.92f,s<=.04045f)*scale;
            result=sl_select(1.055f*pow(max(sl_linear,0.f),(float3)(1.f/2.4f))-.055f,12.92f*sl_linear,sl_linear<=.0031308f);
        }
    }else{
        float3 xyz=sl_xyz(input,pixel,d,m);
        result=m[PURPOSE]!=0?xyz:sl_display(float4(xyz,1.f)).rgb;
    }
    if(m[PURPOSE]==0)result=clamp(result,0.f,1.f);
    output[pixel*3]=result.x;output[pixel*3+1]=result.y;output[pixel*3+2]=result.z;
}
