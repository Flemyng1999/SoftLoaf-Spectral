const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const extract=(start,end)=>{const a=html.indexOf(start);assert.ok(a>=0,start);return html.slice(a,html.indexOf(end,a));};

test('recipe selector lists every document by identity and groups by process',()=>{
 const controls={};const $=id=>controls[id]??=( {innerHTML:'',value:'',textContent:''} );
 const c=vm.createContext({$,esc:s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;')});
 vm.runInContext(`let documents=[{id:'a',recipe:{name:'旧名字',route:'negative'}},{id:'b',recipe:{name:'第二份',route:'negative'}},{id:'c',recipe:{name:'相纸',route:'print'}},{id:'d',recipe:{name:'透射',route:'slide'}}];let active={id:'a',name:'自定义 <配方>',route:'negative'};${extract('function renderRecipeSelector(', 'function renderLibrary(')}renderRecipeSelector();`,c);
 assert.equal(controls['recipe-select'].value,'a');
 assert.match(controls['recipe-select'].innerHTML,/<option value="a">自定义 &lt;配方>/);
 assert.match(controls['recipe-select'].innerHTML,/<option value="b">第二份/);
 assert.equal((controls['recipe-select'].innerHTML.match(/<option /g)||[]).length,4);
 assert.match(controls['recipe-select'].innerHTML,/<optgroup label="负片 · APD 输出">/);
 assert.equal(controls['recipe-process'].textContent,'负片 · APD 输出');
});

test('selection switches the exact document without changing its process',()=>{
 const c=vm.createContext({});
 vm.runInContext(`let active={id:'a'},documents=[{id:'a'},{id:'b'},{id:'c'}],selected=[];const setActive=id=>selected.push(id);${extract('function selectRecipe(', 'function renderNodeLayout(')}selectRecipe('b');selectRecipe('a');selectRecipe('missing');`,c);
 assert.deepEqual(Array.from(vm.runInContext('selected',c)),['b']);
 assert.match(html,/\$\('recipe-select'\)\.onchange=e=>selectRecipe\(e.target.value\)/);
 assert.match(html,/<details class="recipe-library"><summary>已打开的配方<\/summary>/);
 assert.doesNotMatch(html,/function changeRoute\(/);
});
