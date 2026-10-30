"""Native shader selection and OCIO compute-stage binding, without pixel math."""
from pathlib import Path
import re


def shader_path(backend,kernel):
    if kernel not in ('scan','spectral'):raise ValueError('Unknown compute kernel')
    name=getattr(backend,'name','metal')
    if name not in ('metal','d3d12'):raise ValueError('Unknown GPU backend')
    return Path(__file__).resolve().parents[1]/'core'/name/(kernel+('.hlsl' if name=='d3d12' else '.metal'))


def _sample_function(texture):
    name=texture['name'];binding=texture['binding'];dimension=texture['dimension'];linear=texture['linear']
    vector='' if dimension==1 else str(dimension);shape='float'+vector;integer='int'+vector
    sizes=['w','h','z'][:dimension];dimensions=','.join(sizes)
    size='float('+dimensions+')' if dimension==1 else shape+'('+dimensions+')'
    integer_size='int('+dimensions+')' if dimension==1 else integer+'('+dimensions+')'
    def load(index):return name+'.Load(int'+str(dimension+1)+'('+index+',0))'
    start='float4 sl_sample_'+str(binding)+'('+shape+' coord){uint '+dimensions+';'+name+'.GetDimensions('+dimensions+');'
    if not linear:return start+integer+' p=('+integer+')clamp(floor(coord*'+size+'),0,'+size+'-1);return '+load('p')+';}\n'
    start+=shape+' q=clamp(coord*'+size+'-.5,0,'+size+'-1);'+integer+' a=('+integer+')floor(q),b=min(a+1,'+integer_size+'-1);'+shape+' f=q-('+shape+')a;'
    if dimension==1:return start+'return lerp('+load('a')+','+load('b')+',f);}\n'
    corners={}
    from itertools import product
    for bits in product((0,1),repeat=dimension):
        key=''.join(map(str,bits));coord=integer+'('+','.join(('b' if bit else 'a')+'.'+axis for bit,axis in zip(bits,'xyz'))+')'
        corners[key]=load(coord)
    def blend(prefix,axis):
        if axis==dimension:return corners[prefix]
        return 'lerp('+blend(prefix+'0',axis+1)+','+blend(prefix+'1',axis+1)+',f.'+'xyz'[axis]+')'
    return start+'return '+blend('',0)+';}\n'


def hlsl_ocio(text,bindings,textures=()):
    for name,(kind,binding) in bindings.items():
        prefix='s' if kind=='sampler' else 't'
        text=re.sub(r'\b'+re.escape(name)+r'\s*;',name+' : register('+prefix+str(binding)+');',text)
    position=0;resources={t['name']:t for t in textures}
    while (match:=re.search(r'(\w+)\.Sample(?:Level)?\(',text[position:])):
        start=position+match.start();arguments=position+match.end();depth=1;end=arguments;parts=[];part=arguments
        while depth:
            c=text[end]
            if c==',' and depth==1:parts.append(text[part:end].strip());part=end+1
            depth+=(c=='(')-(c==')');end+=1
        parts.append(text[part:end-1].strip())
        if match[1] not in resources:raise RuntimeError('Unknown OCIO HLSL texture')
        if len(parts) not in (2,3) or (len(parts)==3 and parts[2] not in ('0','0.0','0.f','0.0f')):raise RuntimeError('Unsupported OCIO HLSL sampling contract')
        expression='sl_sample_'+str(resources[match[1]]['binding'])+'('+parts[1]+')'
        text=text[:start]+expression+text[end:];position=start+len(expression)
    helpers='\n'.join(_sample_function(t) for t in textures)
    function=text.index('float4 sl_display(');text=text[:function]+helpers+'\n'+text[function:]
    prototypes='\n'.join('float4 sl_sample_'+str(t['binding'])+'(float'+('' if t['dimension']==1 else str(t['dimension']))+' coord);' for t in textures)
    return prototypes+'\n'+text
