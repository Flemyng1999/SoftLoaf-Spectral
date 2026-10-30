const {readFileSync}=require('node:fs');const vm=require('node:vm');const test=require('node:test');const assert=require('node:assert/strict');
function setup(){
 const c=vm.createContext({});vm.runInContext(readFileSync(new URL('../design/gui-v2/diagnostic-samples.js','file://'+__filename),'utf8'),c);
 const state={active:{id:'a',revision:1,film:{exposure_ev:0}},computable:true,samples:[{id:'cc01'},{id:'cc13'},{id:'cc22',name:'22 · neutral 5 (.70 D)'}]};
 const requests=[],photo={id:'user-photo',exposure_ev:1},point={x:.2,y:.8};
 const sampler=c.createDiagnosticSampler({getState:()=>state,render(){},api:(_path,body)=>new Promise((resolve,reject)=>requests.push({body,resolve,reject}))});
 return {state,requests,sampler,photo,point};
}
test('calculation results default to neutral 5 and retain an explicit image-sampling choice',async()=>{
 const {sampler,requests,state}=setup();
 assert.equal(sampler.selected(),'cc22');
 const pending=sampler.refresh();assert.equal(requests[0].body.selection.sample_id,'cc22');
 requests[0].resolve({selection:{sample_id:'cc22'}});await pending;
 assert.equal(sampler.get().selection.sample_id,'cc22');
 await sampler.select(null);state.active.revision++;
 await sampler.refresh();assert.equal(requests.length,1);assert.equal(sampler.selected(),null);
});
test('chart diagnostics use measured chart input and do not replace photo or recipe state',async()=>{
 const {state,requests,sampler,photo,point}=setup(),before=JSON.stringify({state,photo,point});
 const pending=sampler.select('cc13');
 assert.equal(requests[0].body.input.id,'chart');assert.equal(requests[0].body.input.exposure_ev,0);
 assert.equal(requests[0].body.selection.sample_id,'cc13');assert.equal(requests[0].body.baseline,null);
 requests[0].resolve({selection:{sample_id:'cc13'},current:{sample:{value:13}}});await pending;
 assert.equal(sampler.get().current.sample.value,13);assert.equal(JSON.stringify({state,photo,point}),before);
 await sampler.refresh();assert.equal(requests.length,1,'reuse the same completed recipe and patch');
 await sampler.select(null);assert.equal(sampler.get(),null);assert.equal(sampler.selected(),null);
});
test('late responses cannot replace the selected patch or a newer recipe',async()=>{
 const {state,requests,sampler}=setup();
 const a=sampler.select('cc01'),b=sampler.select('cc13');
 requests[1].resolve({selection:{sample_id:'cc13'}});await b;
 requests[0].resolve({selection:{sample_id:'cc01'}});await a;
 assert.equal(sampler.get().selection.sample_id,'cc13');
 state.active.revision=2;assert.equal(sampler.get(),null);
 const c=sampler.refresh();assert.equal(requests[2].body.recipe.revision,2);
 requests[2].resolve({selection:{sample_id:'cc13'},version:{revision:2}});await c;
 assert.equal(sampler.get().version.revision,2);
 const d=sampler.select('cc01');await sampler.select(null);
 requests[3].resolve({selection:{sample_id:'cc01'}});await d;
 assert.equal(sampler.get(),null);
});
test('unknown patches make no request and failures remain separate from photo results',async()=>{
 const {requests,sampler}=setup();await sampler.select('unknown');assert.equal(requests.length,0);
 const pending=sampler.select('cc01');requests[0].reject(Error('test failure'));await pending;
 assert.equal(sampler.get(),null);assert.equal(sampler.status().error,'test failure');
});
test('hidden diagnostics do not decode or evaluate chart pixels while editing photographs',async()=>{
 const {requests,sampler,state}=setup();state.visible=false;
 const hidden=sampler.refresh();assert.equal(requests.length,0);await hidden;
 state.active.revision++;await sampler.refresh();assert.equal(requests.length,0);
 state.visible=true;const pending=sampler.refresh();assert.equal(requests.length,1);
 requests[0].resolve({selection:{sample_id:'cc22'}});await pending;
 assert.equal(sampler.get().selection.sample_id,'cc22');
});
