const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const html=fs.readFileSync('design/gui-v2/index.html','utf8');
test('provisional Status M stock is computable only in its own process family',()=>{
 const text=html.slice(html.indexOf('const key=r=>'),html.indexOf('const nodeNames='));
 const c=vm.createContext({bootstrap:{capabilities:{routes:['slide','negative','print'].map(id=>({id,computable:true}))}}});vm.runInContext(text,c);
 const check=(route,process)=>{c.recipe={route,film:{stock:'portra400',custom_material:{provenance:{stock_id:'portra400',process,density_metric:'Status M'}}}};return vm.runInContext('supported(recipe)',c)};
 assert.equal(check('print','C-41'),true);assert.equal(check('negative','C-41'),true);
 assert.equal(check('negative','ECN-2'),true);assert.equal(check('print','E-6'),false);
});
test('negative reference never falls back to reversal material and CSV overrides retain their identity',()=>{
 const text=fs.readFileSync('design/gui-v2/spectral-editor.js','utf8');
 const c=vm.createContext({});vm.runInContext(text.slice(0,text.indexOf('function createSpectralEditor(')),c);
 c.state={active:{route:'print',film:{stock:'portra400'}},assets:{E100:{name:'wrong'},'5207':{name:'negative'}}};
 assert.equal(vm.runInContext('spectralReferenceMaterial(state).name',c),'negative');
 c.reference={provenance:{stock_id:'portra400',process:'C-41',density_metric:'Status M',substitutions:{dyes:'5207',exposure_anchor:'5207'}}};
 c.material={dyes:{import_file:{name:'my-dyes.csv',sha256:'abc'}}};
 vm.runInContext('spectralMaterialProvenance(material,reference)',c);
 assert.equal(c.material.provenance.process,'C-41');assert.equal(c.material.provenance.substitutions.dyes,undefined);
 assert.equal(c.material.provenance.substitutions.exposure_anchor,'5207');
 assert.equal(c.material.provenance.user_overrides.dyes.sha256,'abc');
});
test('old material snapshots do not adopt a newer reference or its source plot',()=>{
 const text=fs.readFileSync('design/gui-v2/spectral-editor.js','utf8');const c=vm.createContext({});vm.runInContext(text.slice(0,text.indexOf('function createSpectralEditor(')),c);
 c.state={active:{route:'negative',film:{stock:'5207'}},assets:{legacy_5207:{name:'legacy'},'5207':{name:'new',provenance:{material_version:'v2'}}}};
 assert.equal(vm.runInContext('spectralReferenceMaterial(state).name',c),'legacy');
 c.state.active.film.custom_material={name:'saved old snapshot',provenance:{}};
 assert.equal(vm.runInContext('spectralReferenceMaterial(state).name',c),'saved old snapshot');
 c.value={wavelengths_nm:[400],channels:{R:[2]}};c.reference=c.value;c.native={reference_curve:{wavelengths_nm:[400],channels:{R:[3]}},channels:{R:{wavelengths_nm:[400,401],values:[3,3]}}};
 assert.equal(vm.runInContext('spectralPlotData(value,reference,native,"wavelengths_nm",["R"],JSON.stringify).native',c),false);
});
