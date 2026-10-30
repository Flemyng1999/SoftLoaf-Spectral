const {readFileSync}=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');const test=require('node:test');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
test('material nodes open their named source curve before computed diagnostics',()=>{
 const start=html.indexOf('function nodeInspectionTabs('),end=html.indexOf('function showNode(',start);
 assert.ok(start>=0,'source-first material navigation must exist');
 const c=vm.createContext({});vm.runInContext(html.slice(start,end),c);
 const tabs=(node,route)=>JSON.parse(vm.runInContext(`JSON.stringify(nodeInspectionTabs('${node}','${route}'))`,c));
 assert.equal(tabs('film','slide')[0][0],'sensitivity');
 assert.equal(tabs('film','negative')[0][0],'sensitivity');
 assert.equal(tabs('light','slide')[0][1],'标准日光光谱');
 assert.equal(tabs('paper','print')[0][0],'paper_sensitivity');
 assert.equal(tabs('view','print')[0][0],'viewing');
 assert.equal(tabs('film','negative').at(-1)[0],'result');
 assert.equal(tabs('interface','negative')[0][0],'process');
 assert.equal(tabs('interface','negative')[0][1],'APD → XYZ');
 assert.ok(tabs('interface','negative').some(([id])=>id==='observer'));
});
