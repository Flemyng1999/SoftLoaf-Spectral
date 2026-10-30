const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');

// Delayed file reading must not race a submitted material edit. The real
// editor handlers run here with minimal controls, not a second implementation.
test('file import finishes before an existing spectral draft can be applied',async()=>{
 const controls=new Map();
 function control(id){
  if(!controls.has(id))controls.set(id,{id,value:'',textContent:'',innerHTML:'',hidden:false,clientWidth:400,
   classList:{toggle(){}},addEventListener(){},querySelector(){return control(id+'-child')},
   querySelectorAll(){return [...controls.values()]}});
  return controls.get(id);
 }
 const context=vm.createContext({document:{getElementById:control,activeElement:null},console,TextDecoder,Uint8Array,
  crypto:webcrypto,ResizeObserver:class{observe(){}},setTimeout});
 const source=readFileSync(new URL('../design/gui-v2/spectral-editor.js','file://'+__filename),'utf8');
 vm.runInContext(readFileSync(new URL('../design/gui-v2/spectral-csv.js','file://'+__filename),'utf8'),context);
 vm.runInContext(source,context);
 const light={name:'D50',source:'synthetic test SPD',quantity:'relative_energy_spd',unit:'relative',wavelengths_nm:[400,550,700],values:[1,1,1]};
 const material={name:'test material',source:'synthetic test data'};
 const state={active:{id:'a',name:'A',revision:1,route:'slide',film:{stock:'E100'},viewing:{illuminant:'D50'}},
  epoch:1,assets:{E100:material,viewing_lights:{D50:light}},result:null,previewStatus:''};
 const commits=[];
 const editor=context.createSpectralEditor({getState:()=>state,key:JSON.stringify,graph(){},message(){},selectNode(){},
  awaitEdits:()=>Promise.resolve(),validate:async recipe=>recipe,commit:recipe=>{commits.push(recipe);state.active=recipe}});
 editor.open('viewing');
 const firstCSV=new TextEncoder().encode('wavelength_nm,value\n400,1\n550,1.5\n700,1');
 await control('spectrum-file').onchange({target:{files:[{name:'first.csv',size:firstCSV.length,arrayBuffer:async()=>firstCSV.buffer}],value:''}});
 assert.equal(editor.hasPending(),true);
 let finishRead;
 const file={size:30,name:'lamp.csv',arrayBuffer:()=>new Promise(resolve=>{finishRead=resolve})};
 const importing=control('spectrum-file').onchange({target:{files:[file],value:'lamp.csv'}});
 await control('spectrum-apply').onclick();
 assert.equal(commits.length,0,'applying is blocked while imported samples are incomplete');
 finishRead(new TextEncoder().encode('wavelength_nm,value\n400,1\n550,2\n700,1').buffer);
 await importing;
 await control('spectrum-apply').onclick();
 assert.equal(commits.length,1);
 assert.deepEqual(Array.from(commits[0].viewing.custom_spd.values),[1,2,1]);
 assert.match(commits[0].viewing.custom_spd.import_file.sha256,/^[0-9a-f]{64}$/);
 assert.equal(editor.hasPending(),false);
});

test('opening an applied printer spectrum refreshes an earlier clean fallback draft',()=>{
 const controls=new Map();const control=id=>{if(!controls.has(id))controls.set(id,{value:'',textContent:'',innerHTML:'',clientWidth:400,classList:{toggle(){}},querySelector(){return control(id+'-child')},querySelectorAll(){return []}});return controls.get(id)};
 const c=vm.createContext({document:{getElementById:control,activeElement:null},ResizeObserver:class{observe(){}},setTimeout});
 for(const file of ['spectral-csv.js','spectral-editor.js'])vm.runInContext(readFileSync('design/gui-v2/'+file,'utf8'),c);
 const lamp={name:'3400 K fallback',source:'test',quantity:'relative_energy_spd',unit:'relative',wavelengths_nm:[360,550,730],values:[1,1,1]};
 const state={active:{id:'a',revision:1,route:'print',film:{stock:'5207'},printing:{pipeline:'spectral-v2',temperature_k:3500,optics:{heat:'none',lens:'none'}},viewing:{illuminant:'D50'}},assets:{'5207':{name:'test'},printing_light:lamp,printing_light_v2:lamp,viewing_lights:{D50:lamp}},result:null};
 const editor=c.createSpectralEditor({getState:()=>state,key:JSON.stringify,graph(){},message(){},selectNode(){}});
 editor.open('viewing');editor.close();
 state.result={version:{recipe_id:'a',revision:1},current:{nodes:{enlarger:{details:{light:{wavelengths_nm:[360,550,730],series:[{values:[.2,.6,.1]}]}}}}}};
 assert.equal(editor.open('enlarger'),true);
 assert.equal(control('spectrum-name').value,'3500 K 放大光');
 assert.equal(editor.hasPending(),false);
});
