const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
// Exercise the actual async handlers with deferred validation responses.
const html=readFileSync(new URL('../design/gui-v2/index.html', 'file://'+__filename),'utf8');
const extract=(start,end)=>html.slice(html.indexOf(start),html.indexOf(end,html.indexOf(start)));
const queue=extract('function queueEdit(', 'function render(){');
const save=extract('async function save(){','async function openRecipe(');
function context(){
 const c=vm.createContext({console});
 vm.runInContext(`let spectralEditor=null;let active={id:'a',name:'A',revision:1,film:{exposure_ev:0}},history=[],editQueue=Promise.resolve(),action='',documentEpoch=0,saveKey=null,documents=[];const $=id=>({value:id==='export-grid'?'33':active.name,close(){},reportValidity(){return true;}});const copy=x=>JSON.parse(JSON.stringify(x)),key=JSON.stringify;let requests=[],downloaded=[];const api=(p,x)=>new Promise(resolve=>requests.push({x,resolve}));const remember=()=>{},render=()=>{},evaluate=()=>{},announce=()=>{},downloadJSON=x=>downloaded.push(copy(x)); ${queue} ${save}`,c);
 return c;
}
const test=require('node:test');
test('queued edits stay in their original document',async()=>{
 const c=context();
 const pending=vm.runInContext("queueEdit(r=>r.film.exposure_ev=.5)",c);
 vm.runInContext("active={id:'b',name:'B',revision:1,film:{exposure_ev:0}};documentEpoch++",c);
 await new Promise(resolve=>setImmediate(resolve));
 const cross=vm.runInContext('requests.length',c);
 if(cross){vm.runInContext('requests[0].resolve({normalized_recipe:requests[0].x.recipe})',c);}
 await pending;
 assert.equal(vm.runInContext('active.film.exposure_ev',c),0,'queued edit must not move to another document');
});
test('saving a frozen snapshot preserves later edits',async()=>{
 const s=context();
 const saving=vm.runInContext('save()',s);
 await new Promise(resolve=>setImmediate(resolve));
 vm.runInContext("active={...active,revision:2,film:{exposure_ev:1}}; requests[0].resolve({normalized_recipe:requests[0].x.recipe})",s);
 await saving;
 assert.equal(vm.runInContext('active.film.exposure_ev',s),1,'saving old snapshot must not overwrite a newer edit');
 assert.equal(vm.runInContext('downloaded[0].film.exposure_ev',s),0,'download must contain the saved snapshot');
});
test('export waits for submitted edits before freezing',async()=>{
 const c=context();
 const run=extract('async function runExport(){','function showNode(');
 vm.runInContext(`let exportJob=null,exportResult=null,exportPreparing=false,exports=[];const supported=()=>true,uid=()=>'id',renderExport=()=>{},document={querySelector:()=>({value:'pipeline'})};const fetch=async(path,options)=>{exports.push(JSON.parse(options.body));return {ok:false,json:async()=>({ok:false,verification:{accepted:false},files:[]})}};${run}`,c);
 const editing=vm.runInContext('queueEdit(r=>r.film.exposure_ev=.5)',c);
 const exporting=vm.runInContext('runExport()',c);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(vm.runInContext('exports.length',c),0,'no export before queued validation commits');
 vm.runInContext('requests[0].resolve({normalized_recipe:requests[0].x.recipe})',c);
 await editing;await exporting;
 assert.equal(vm.runInContext('exports[0].recipe.film.exposure_ev',c),.5);
 assert.equal(vm.runInContext('exports[0].grid',c),33);
});
test('reused revision number cannot identify a different export as current',()=>{
 const c=context();
 const label=extract('function exportLabel(){','function renderExport(){');
 vm.runInContext(`active.revision=3;let exportJob=null,exportResult={frozen:{recipe_id:'a',revision:3,fingerprint:'old'}},resultMeta={recipe:copy(active)},result={version:{fingerprint:'new'}};${label}`,c);
 assert.equal(/ · 当前版本$/.test(vm.runInContext('exportLabel()',c)),false);
 vm.runInContext("exportResult.frozen.fingerprint='new'",c);
 assert.equal(/ · 当前版本$/.test(vm.runInContext('exportLabel()',c)),true);
});
test('restore uses the successful snapshot and retains unfinished edits',()=>{
 const c=context();
 const restore=extract('function restoreLastWorking(){',"document.addEventListener('click'");
 vm.runInContext(`let lastWorking=copy(active);documents=[{id:'a',recipe:{...copy(active),revision:2,film:{exposure_ev:1}},history:[],saveKey:null}];active={id:'draft',name:'5207'};const setActive=id=>{active=copy(documents.find(d=>d.id===id).recipe)},addDocument=()=>{throw Error('unexpected new document')};${restore}restoreLastWorking()`,c);
 assert.equal(vm.runInContext('active.revision',c),1);
 assert.equal(vm.runInContext('active.film.exposure_ev',c),0);
 assert.equal(vm.runInContext('documents[0].history[0].film.exposure_ev',c),1);
});

test('save returns to a pending spectral draft instead of dropping it',async()=>{
 const c=context();vm.runInContext("let reopened=0;const showNodeTab=()=>reopened++;spectralEditor={hasPending:()=>true,target:()=> 'sensitivity'}",c);
 await vm.runInContext('save()',c);
 assert.equal(vm.runInContext('requests.length',c),0);
 assert.equal(vm.runInContext('downloaded.length',c),0);
 assert.equal(vm.runInContext('reopened',c),1);
});
test('export refuses to freeze an unapplied spectral draft',async()=>{
 const c=context(),run=extract('async function runExport(){','function showNode(');
 vm.runInContext(`let reopened=0,exportCalls=0;const showNodeTab=()=>reopened++,fetch=()=>exportCalls++;spectralEditor={hasPending:()=>true,target:()=> 'viewing'};${run}`,c);
 await vm.runInContext('runExport()',c);
 assert.equal(vm.runInContext('exportCalls',c),0);
 assert.equal(vm.runInContext('reopened',c),1);
});
