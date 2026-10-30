const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const start=html.indexOf('function persistSession(){');
const end=html.indexOf('function renderPhotoControls(){',start);
const source=html.slice(start,end);
test('workspace writes are ordered and carry their last acknowledged revision',async()=>{
 const context=vm.createContext({console});
 vm.runInContext(`let sessionRevision=0,sessionQueue=Promise.resolve(),sessionKey='',sessionConflict=false,photoQueue=null;
 let bootstrap={capabilities:{session_persistence:true}},active={id:'a',revision:1},baseline=null,
 documents=[{id:'a',recipe:active,baseline:null}],deletedDocuments=[],requests=[],notices=[];
 const copy=x=>JSON.parse(JSON.stringify(x)),key=JSON.stringify,announce=x=>notices.push(x);
 const api=(path,body)=>new Promise(resolve=>requests.push({path,body,resolve}));
 ${source}`,context);
 vm.runInContext('persistSession(); active={id:"a",revision:2};persistSession()',context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(vm.runInContext('requests.length',context),1);
 assert.equal(vm.runInContext('requests[0].body.expected_revision',context),0);
 vm.runInContext('requests[0].resolve({ok:true,revision:1})',context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(vm.runInContext('requests[1].body.expected_revision',context),1);
 assert.equal(vm.runInContext('requests[1].body.session.documents[0].recipe.revision',context),2);
 vm.runInContext('requests[1].resolve({ok:true,revision:2})',context);
 await vm.runInContext('sessionQueue',context);
 assert.equal(vm.runInContext('sessionRevision',context),2);
});

test('empty workspace persists deletion recovery instead of skipping the write',async()=>{
 const context=vm.createContext({console});
 vm.runInContext(`let sessionRevision=3,sessionQueue=Promise.resolve(),sessionKey='',sessionConflict=false,photoQueue=null;
 let bootstrap={capabilities:{session_persistence:true}},active=null,baseline=null,documents=[],
 deletedDocuments=[{id:'deleted-a',index:0,document:{recipe:{id:'a',revision:2},baseline:null}}],requests=[];
 const copy=x=>JSON.parse(JSON.stringify(x)),key=JSON.stringify,announce=()=>{};
 const api=async(path,body)=>{requests.push(body);return {ok:true,revision:4}};
 ${source}persistSession()`,context);
 await vm.runInContext('sessionQueue',context);
 assert.equal(vm.runInContext('requests.length',context),1);
 assert.equal(vm.runInContext('requests[0].session.active_id',context),null);
 assert.equal(vm.runInContext('requests[0].session.deleted_documents[0].document.recipe.revision',context),2);
});
