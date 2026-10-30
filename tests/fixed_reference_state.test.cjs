const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const evaluate=html.slice(html.indexOf('const previewTasks='),html.indexOf('function graph('));

test('fixed scene reference ignores a restored old A recipe without deleting it',async()=>{
 const context=vm.createContext({console});
 vm.runInContext(readFileSync('design/gui-v2/preview-requests.js','utf8'),context);
 vm.runInContext(readFileSync('design/gui-v2/rendition-cache.js','utf8'),context);
 vm.runInContext(`let diagnosticSampler=null;let active={id:'a',revision:2,route:'slide'},baseline={id:'old',revision:1},
 bootstrap={capabilities:{fixed_scene_reference:true}},evalSeq=0,busy=false,computeError='',
 result=null,resultMeta=null,lastWorking=null,testInput={id:'scene43_rgb',exposure_ev:0},selection={x:.5,y:.5};
 const key=JSON.stringify,copy=x=>JSON.parse(JSON.stringify(x)),supported=()=>true,render=()=>{},announce=()=>{};
 let requests=[];const api=async(path,body)=>{requests.push(body);return {ok:true,selection:body.selection,reference:{method:'spectral_XYZ_to_sRGB'}}};
 ${evaluate}`,context);
 await vm.runInContext('evaluate()',context);
 assert.equal(vm.runInContext('requests[0].baseline',context),null);
 assert.equal(vm.runInContext('baseline.id',context),'old');
 assert.equal(vm.runInContext('resultMeta.baseline',context),null);
});


test('cached photo switches immediately while an obsolete request is still running',async()=>{
 const context=vm.createContext({console});
 for(const path of ['preview-requests.js','rendition-cache.js'])vm.runInContext(readFileSync('design/gui-v2/'+path,'utf8'),context);
 vm.runInContext(`let diagnosticSampler=null,mainView='spectra',active={id:'a',revision:1},baseline=null,
 bootstrap={capabilities:{fixed_scene_reference:true}},evalSeq=0,busy=false,computeError='',result=null,resultMeta=null,lastWorking=null,
 testInput={id:'photo1',exposure_ev:0},selection={x:.5,y:.5};
 const key=JSON.stringify,copy=x=>JSON.parse(JSON.stringify(x)),supported=()=>true,render=()=>{},announce=()=>{};
 let requests=[];const api=(path,body)=>new Promise(resolve=>requests.push({body,resolve}));
 function response(index){const input=requests[index].body.input;requests[index].resolve({ok:true,input,selection:{x:.5,y:.5},current:{preview:{kind:'image',width:10,height:10,data_url:'/previews/'+input.id+'.png'}}});}
 ${evaluate}`,context);
 const first=vm.runInContext('evaluate()',context);vm.runInContext('response(0)',context);await first;
 const pending=vm.runInContext("testInput={id:'photo2',exposure_ev:0};evaluate()",context);
 const immediate=vm.runInContext("testInput={id:'photo1',exposure_ev:0};evaluate()",context);
 assert.equal(vm.runInContext('result.input.id',context),'photo1');assert.equal(vm.runInContext('busy',context),false);
 await immediate;assert.equal(vm.runInContext('requests.length',context),2);
 vm.runInContext('response(1)',context);await pending;
 assert.equal(vm.runInContext('result.input.id',context),'photo1');
});
