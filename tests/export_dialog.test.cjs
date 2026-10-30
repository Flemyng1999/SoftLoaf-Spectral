const {readFileSync}=require('node:fs');const vm=require('node:vm');const test=require('node:test');const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const code=html.slice(html.indexOf('function exportLabel(){'),html.indexOf('async function runExport(){'));
function context(){
 const c=vm.createContext({});vm.runInContext(`
 const elements={};const $=id=>elements[id]||(elements[id]={open:true,innerHTML:'',textContent:'',value:'65'});
 const document={querySelectorAll:()=>[]},esc=x=>String(x),key=JSON.stringify,supported=()=>true;
 let active={id:'a',revision:1,name:'My film',display:{target:'Display P3',view:'Colorful'}},exportPreparing=false,exportJob=null;
 let resultMeta={recipe:active},result={version:{fingerprint:'current'}};
 let exportResult={ok:true,purpose:'display',frozen:{recipe_id:'a',revision:1,fingerprint:'current'},verification:{integrity_passed:true,independent_ocio:{fraction_within_2_codes_float:.9713,fraction_within_2_codes_u8:.9762,max_abs_code_float:15.4,mean_pixel_max_code_float:.33,p95_pixel_max_code_float:.95,max_abs_code_u8:15,pixel_count:38081}},
 files:[{name:'recipe.cube',url:'/cube',size:600},{name:'recipe.json',url:'/json'},{name:'recipe.zip',url:'/zip'}]};
 ${code}`,c);return c;
}
test('export presents one CUBE download and a short interpolation metric',()=>{
 const c=context();vm.runInContext('renderExport()',c);
 assert.equal(vm.runInContext("$('export-download').href",c),'/cube');
 assert.equal(vm.runInContext("$('export-download').hidden",c),false);
 assert.equal(vm.runInContext("$('export-run').hidden",c),true);
 assert.match(vm.runInContext("$('export-state').textContent",c),/97.13%/);
 assert.equal(/检查记录|recipe.json|recipe.zip|<details/.test(vm.runInContext("$('export-state').innerHTML",c)),false);
});
test('changed recipe or failed integrity cannot be downloaded as a current LUT',()=>{
 const c=context();vm.runInContext('active={...active,revision:2};renderExport()',c);
 assert.equal(vm.runInContext("$('export-download').hidden",c),true);
 vm.runInContext('active={...active,revision:1};exportResult.verification.integrity_passed=false;renderExport()',c);
 assert.equal(vm.runInContext("$('export-download').hidden",c),true);
});
