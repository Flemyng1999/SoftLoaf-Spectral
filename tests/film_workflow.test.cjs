const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const html=fs.readFileSync('design/gui-v2/index.html','utf8');
function helpers(){const c=vm.createContext({});vm.runInContext(html.slice(html.indexOf('function setPositiveMethod('),html.indexOf('function newRecipeFromPreset(')),c);return c;}
test('changing negative stock adopts its frozen reference light and leaves exposure/viewing intact',()=>{
 const c=helpers();c.recipe={route:'print',film:{stock:'5207',exposure_ev:.5},scene:{illuminant:'CIE_D',temperature_k:5500},viewing:{illuminant:'D50',gain:2}};
 c.material={provenance:{stock_id:'5219',process:'ECN-2',exposure_reference:{illuminant:'Planck',temperature_k:3200}}};
 vm.runInContext('replaceNegativeMaterial(recipe,"5219",material)',c);
 assert.deepEqual(JSON.parse(JSON.stringify(c.recipe.scene)),{illuminant:'Planck',temperature_k:3200});
 assert.equal(c.recipe.film.exposure_ev,.5);assert.equal(c.recipe.viewing.gain,2);assert.equal(c.recipe.route,'print');
});

test('opening an upgraded file marks its canonical recipe unsaved until the user saves it',async()=>{
 const old={id:'saved',revision:4,film:{stock:'E100'},scene:{illuminant:'CIE_D',temperature_k:6500}};
 const normalized={...old,revision:5,scene:{illuminant:'CIE_D',temperature_k:5500}};
 const c=vm.createContext({saveKey:'old-key',normalized,opened:null,remembered:false,notices:[],
  api:async()=>({computable:true,normalized_recipe:normalized}),$:()=>({value:'selected'}),
  addDocument:()=>{},render:()=>{}});
 vm.runInContext(`const announce=text=>notices.push(text),remember=()=>{remembered=true};
 ${html.slice(html.indexOf('async function openRecipe('),html.indexOf('function exportLabel('))}`,c);
 await c.openRecipe({size:100,text:async()=>JSON.stringify(old)});
 assert.equal(c.saveKey,null);assert.equal(c.remembered,true);
 assert.match(c.notices[0],/片种参考/);
 assert.equal(old.revision,4);
 c.saveKey='saved-current';c.remembered=false;
 await c.openRecipe({size:100,text:async()=>JSON.stringify(normalized)});
 assert.equal(c.saveKey,'saved-current');assert.equal(c.remembered,false);
});
