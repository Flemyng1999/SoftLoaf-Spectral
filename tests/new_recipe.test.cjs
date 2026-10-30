const {readFileSync}=require('node:fs');const vm=require('node:vm');const test=require('node:test');const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const begin=html.indexOf('function newRecipeFromTemplate('),end=html.indexOf('function renderLibrary()',begin);
const c=vm.createContext({});if(begin>=0)vm.runInContext(html.slice(begin,end),c);
const templates=['slide','negative','print'].map(route=>({id:route,available:true,recipe:{id:route+'-default',name:route,revision:1,route,film:{stock:route==='slide'?'E100':'5207',exposure_ev:0},display:{view:'Default'},printing:{paper:'Ultra Endura'}}}));
test('new recipe starts from the chosen built-in process, independent of the current recipe',()=>{
 assert.equal(typeof c.newRecipeFromTemplate,'function');
 const before=JSON.stringify(templates);
 for(const route of ['slide','negative','print']){
  const r=c.newRecipeFromTemplate(route,templates,'new-'+route);
  assert.equal(r.id,'new-'+route);assert.equal(r.route,route);assert.equal(r.revision,1);
  assert.equal(r.film.stock,route==='slide'?'E100':'5207');assert.equal(r.film.exposure_ev,0);
  assert.equal(/E100|5207/.test(r.name),false);assert.equal(r.film.custom_material,undefined);assert.equal(r.display.view,'Default');
  r.film.exposure_ev=4;
 }
 assert.equal(JSON.stringify(templates),before);
});
test('unavailable or unknown processes cannot silently create the wrong recipe',()=>{
 assert.equal(typeof c.newRecipeFromTemplate,'function');
 assert.throws(()=>c.newRecipeFromTemplate('unknown',templates,'id'));
 assert.throws(()=>c.newRecipeFromTemplate('negative',[{...templates[1],available:false}],'id'));
});
test('negative material and positive method are independent and provenance is retained',()=>{
 const source={id:'portra400-print',route:'print',recipe:{id:'source',name:'Portra',revision:3,route:'print',film:{stock:'portra400',custom_material:{provenance:{process:'C-41',substitutions:{dyes:'5207'}}}},display:{view:'Display Encoding',target:'Display P3'},printing:{filters:[.2,.1,0]}}};
 const before=JSON.stringify(source);
 const apd=c.newRecipeFromPreset('negative',[source],'portra400','new');
 assert.equal(apd.route,'negative');assert.equal(apd.display.view,'ACES 2.0 - SDR 100 nits');
 assert.equal(apd.display.target,'Display P3');assert.deepEqual(Array.from(apd.printing.filters),[.2,.1,0]);
 assert.equal(apd.film.custom_material.provenance.process,'C-41');
 const r=c.newRecipeFromPreset('print',[source],source.id,'new');
 assert.equal(r.id,'new');assert.equal(r.revision,1);assert.equal(r.film.custom_material.provenance.process,'C-41');
 r.film.custom_material.provenance.substitutions.dyes='changed';
 assert.equal(JSON.stringify(source),before);
});
test('switching method and material preserves custom curves, exposure and scan-independent settings',()=>{
 const r={route:'print',name:'My recipe',film:{stock:'portra',exposure_ev:-.7,custom_material:{name:'CSV',sensitivity:{custom:true}}},scene:{temperature_k:5500},printing:{filters:[.2,.1,0]},viewing:{gain:1.8},display:{view:'Display Encoding',target:'Display P3'}};
 c.recipe=r;vm.runInContext('setPositiveMethod(recipe,"negative")',c);
 assert.equal(r.route,'negative');assert.equal(r.display.view,'ACES 2.0 - SDR 100 nits');
 assert.equal(r.name,'My recipe');assert.equal(r.film.custom_material.name,'CSV');assert.equal(r.film.exposure_ev,-.7);
 vm.runInContext('setPositiveMethod(recipe,"print")',c);assert.equal(r.display.view,'Display Encoding');
 r.display.view='Colorful';vm.runInContext('setPositiveMethod(recipe,"negative")',c);assert.equal(r.display.view,'Colorful');
 c.material={name:'Other',provenance:{process:'ECN-2'}};
 vm.runInContext('replaceNegativeMaterial(recipe,"other",material)',c);
 assert.equal(r.film.stock,'other');assert.equal(r.film.custom_material.name,'Other');assert.equal(r.film.exposure_ev,-.7);
 assert.equal(r.scene.temperature_k,5500);assert.equal(r.viewing.gain,1.8);assert.deepEqual(r.printing.filters,[.2,.1,0]);
 r.film.custom_material.name='Edited';assert.equal(c.material.name,'Other');
});
test('material catalog deduplicates positive branches and retains the fixed print starting balance',()=>{
 const list=[{id:'stock-negative',recipe:{film:{stock:'stock'},route:'negative'}},{id:'stock-print',recipe:{film:{stock:'stock'},route:'print'}}];
 c.entries=list;const result=vm.runInContext('negativeMaterialEntries(entries)',c);
 assert.equal(result.length,1);assert.equal(result[0].id,'stock');assert.equal(result[0].recipe.route,'print');
});
test('new dialog retains the selected negative when its positive method changes',()=>{
 let route='print';
 const select={value:'portra400',set innerHTML(value){this.html=value;this.value='';},get innerHTML(){return this.html;}};
 const fields={'new-recipe-dialog':{querySelector:()=>({value:route})},'new-material':select,'new-material-field':{},'new-material-note':{}};
 c.$=id=>fields[id];c.esc=s=>String(s);
 c.bootstrap={recipe_presets:[{id:'portra400-print',process:'C-41',summary:'Borrowed dyes',recipe:{route:'print',film:{stock:'portra400',custom_material:{name:'Portra 400'}}}}]};
 vm.runInContext('renderNewMaterials()',c);assert.equal(select.value,'portra400');
 route='negative';vm.runInContext('renderNewMaterials()',c);
 assert.equal(select.value,'portra400');assert.match(fields['new-material-note'].textContent,/APD 正相为实验组合/);
 assert.match(select.html,/value="portra400"/);assert.doesNotMatch(select.html,/value="portra400-print"/);
});

test('E-6 material selection preserves recipe settings and rejects other processing systems',()=>{
 const r={route:'slide',name:'My slide',film:{stock:'E100',exposure_ev:.5},scene:{temperature_k:6500},viewing:{gain:2},display:{view:'Display Encoding',target:'Display P3'}};
 const material={name:'Velvia 100',provenance:{stock_id:'velvia100',process:'E-6',density_metric:'Status A'},sensitivity:{channels:{R:[1]}}};
 c.replaceReversalMaterial(r,'velvia100',material);
 assert.equal(r.film.stock,'velvia100');assert.equal(r.name,'My slide');assert.equal(r.film.exposure_ev,.5);
 assert.equal(r.scene.temperature_k,6500);assert.equal(r.viewing.gain,2);assert.equal(r.display.target,'Display P3');
 r.film.custom_material.name='CSV';assert.equal(material.name,'Velvia 100');
 assert.throws(()=>c.replaceReversalMaterial(r,'k64',{provenance:{stock_id:'k64',process:'K-14'}}));
 assert.throws(()=>c.replaceReversalMaterial({...r,route:'print'},'velvia100',material));
 c.replaceReversalMaterial(r,'E100');assert.equal(r.film.custom_material,undefined);assert.equal(r.film.exposure_ev,.5);
 const entry={id:'velvia100',route:'slide',recipe:{...r,film:{stock:'velvia100',custom_material:material}}};
 const fresh=c.newRecipeFromPreset('slide',[entry],'velvia100','new-slide');
 assert.equal(fresh.id,'new-slide');assert.equal(fresh.route,'slide');assert.equal(fresh.film.custom_material.provenance.process,'E-6');
 assert.throws(()=>c.newRecipeFromPreset('negative',[entry],'velvia100','bad'));
});
test('selecting the updated 5207 keeps its source snapshot',()=>{
 c.recipe={route:'negative',film:{stock:'5219',exposure_ev:.2}};c.material={name:'5207 own source',provenance:{stock_id:'5207',process:'ECN-2',material_version:'vision3-source/2'}};
 vm.runInContext('replaceNegativeMaterial(recipe,"5207",material)',c);
 assert.equal(c.recipe.film.custom_material.name,c.material.name);assert.equal(c.recipe.film.exposure_ev,.2);
});
