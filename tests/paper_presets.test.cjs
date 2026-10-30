const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict');
const context=vm.createContext({});
test('paper changes preserve negative, optics, exposure and saved snapshots',()=>{
 vm.runInContext(fs.readFileSync('design/gui-v2/paper-presets.js','utf8'),context);
 const recipe={route:'print',film:{stock:'5219',exposure_ev:.5},printing:{paper:'Ultra Endura',filters:[.1,.2,.3],exposure_ev:.7}};
 const material={name:'Premier',provenance:{process:'RA-4',density_metric:'Status A',stock_id:'endura-premier'}};
 context.recipe=recipe;context.material=material;
 vm.runInContext('replacePaperMaterial(recipe,"endura-premier",material)',context);
 assert.equal(recipe.film.stock,'5219');assert.equal(recipe.film.exposure_ev,.5);
 assert.deepEqual(recipe.printing.filters,[.1,.2,.3]);assert.equal(recipe.printing.exposure_ev,.7);
 recipe.printing.custom_material.name='CSV';assert.equal(material.name,'Premier');
 assert.equal(vm.runInContext('paperChoice(recipe)',context),'endura-premier');
 assert.throws(()=>vm.runInContext('replacePaperMaterial({...recipe,route:"slide"},"endura-premier",material)',context));
 vm.runInContext('replacePaperMaterial(recipe,"Ultra Endura")',context);assert.equal(recipe.printing.custom_material,undefined);
});
test('native paper characteristic detail uses exposure axis and never replaces a CSV',()=>{
 const text=fs.readFileSync('design/gui-v2/spectral-editor.js','utf8');vm.runInContext(text.slice(0,text.indexOf('function createSpectralEditor(')),context);
 context.value={log_exposure:[-2,-1],channels:{R:[0,1]}};context.native={reference_curve:context.value,channels:{R:{log_exposure:[-2,-1.5,-1],values:[0,.4,1]}}};
 const result=vm.runInContext('spectralPlotData(value,value,native,"log_exposure",["R"],JSON.stringify)',context);
 assert.deepEqual(Array.from(result.series[0].xs),[-2,-1.5,-1]);
});
