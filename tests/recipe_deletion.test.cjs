const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
function setup(){
 const start=html.indexOf('async function deleteRecipe(');assert.ok(start>=0,'recipe removal must be implemented');
 const source=html.slice(start,html.indexOf('function queueEdit(',start));
 const c=vm.createContext({console});
 vm.runInContext(`const copy=x=>JSON.parse(JSON.stringify(x));let serial=0;const uid=()=> 'new-'+(++serial);
 let documents=['a','b','c'].map(id=>({id,recipe:{id,name:id,revision:1,film:{exposure_ev:0}},baseline:{value:id},history:[{revision:0}],saveKey:null}));
 let active=copy(documents[1].recipe),deletedDocuments=[],deleteBusy=false,editQueue=Promise.resolve(),documentEpoch=1,evalSeq=0,
 baseline=copy(documents[1].baseline),history=[],saveKey=null,result={},resultMeta={},busy=false,lastWorking=null;
 let renders=0,evaluations=0,messages=[],pending=false;
 const spectralEditor={hasPending:()=>pending,target:()=> 'sensitivity',close(){}};
 const announce=(text)=>messages.push(text),showNodeTab=()=>{},render=()=>renders++;
 const remember=()=>{const d=documents.find(d=>d.id===active?.id);if(d){d.recipe=copy(active);d.baseline=copy(baseline);d.history=copy(history);}};
 const setActive=(id,rememberCurrent=true)=>{if(rememberCurrent)remember();active=copy(documents.find(d=>d.id===id).recipe);documentEpoch++;evaluations++;render();};
 const focusRecipe=()=>{};
 ${source}`,c);return c;
}
const read=(c,source)=>JSON.parse(vm.runInContext('JSON.stringify('+source+')',c));
test('deleting inactive recipe leaves current recipe and preview alone',async()=>{
 const c=setup();await vm.runInContext("deleteRecipe('a')",c);
 assert.deepEqual(read(c,'documents.map(d=>d.id)'),['b','c']);
 assert.equal(read(c,'active.id'),'b');assert.equal(read(c,'evaluations'),0);
 assert.equal(read(c,'deletedDocuments[0].document.baseline.value'),'a');
});
test('active recipe removal selects its neighbor and undo restores edits and order',async()=>{
 const c=setup();vm.runInContext('active.film.exposure_ev=.7',c);
 await vm.runInContext("deleteRecipe('b')",c);
 assert.equal(read(c,'active.id'),'c');assert.equal(read(c,'deletedDocuments[0].document.recipe.film.exposure_ev'),.7);
 await vm.runInContext('undoDeletedRecipe()',c);
 assert.deepEqual(read(c,'documents.map(d=>d.id)'),['a','b','c']);
 assert.equal(read(c,'active.film.exposure_ev'),.7);
 assert.deepEqual(read(c,'deletedDocuments'),[]);
});
test('deleting final recipe produces a recoverable empty workspace',async()=>{
 const c=setup();await vm.runInContext("deleteRecipe('a');",c);await vm.runInContext("deleteRecipe('c')",c);await vm.runInContext("deleteRecipe('b')",c);
 assert.deepEqual(read(c,'documents'),[]);assert.equal(read(c,'active'),null);
 assert.equal(read(c,'deletedDocuments.length'),3);
 await vm.runInContext('undoDeletedRecipe()',c);assert.equal(read(c,'active.id'),'b');
});
test('delete waits for queued edits and refuses an unapplied spectral draft',async()=>{
 const c=setup();vm.runInContext('let finish;editQueue=new Promise(resolve=>finish=resolve)',c);
 const deleting=vm.runInContext("deleteRecipe('b')",c);
 assert.equal(read(c,'documents.length'),3);
 vm.runInContext('active.film.exposure_ev=1.5;finish()',c);await deleting;
 assert.equal(read(c,'deletedDocuments[0].document.recipe.film.exposure_ev'),1.5);
 await vm.runInContext('undoDeletedRecipe()',c);vm.runInContext('pending=true',c);
 await vm.runInContext("deleteRecipe('b')",c);
 assert.equal(read(c,'documents.length'),3);assert.equal(read(c,'messages.length')>0,true);
});
test('restoring a reopened identifier creates a separate recipe instead of overwriting it',async()=>{
 const c=setup();await vm.runInContext("deleteRecipe('a')",c);
 vm.runInContext("documents.push({id:'a',recipe:{id:'a',name:'重新打开',revision:5},history:[],baseline:null})",c);
 await vm.runInContext('undoDeletedRecipe()',c);
 assert.equal(read(c,"documents.find(d=>d.id==='a').recipe.name"),'重新打开');
 assert.equal(read(c,'documents.length'),4);
 assert.notEqual(read(c,'active.id'),'a');assert.equal(read(c,'active.name'),'a');
});
