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
