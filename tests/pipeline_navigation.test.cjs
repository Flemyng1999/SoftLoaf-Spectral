const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const test=require('node:test');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const declarations=html.slice(html.indexOf('const nodeNames='),html.indexOf('function announce('));

test('all fixed routes start with the physical recipe rather than RGB reconstruction',()=>{
 const context=vm.createContext({});
 vm.runInContext(`let active={route:'slide'};${declarations}`,context);
 const nodes=route=>JSON.parse(vm.runInContext(`active.route=${JSON.stringify(route)};JSON.stringify(Object.keys(nodeLabels()))`,context));
 assert.deepEqual(nodes('slide'),['light','film','view','display']);
 assert.deepEqual(nodes('negative'),['light','film','apd','interface','display']);
 assert.deepEqual(nodes('print'),['light','film','enlarger','filter','paper','view','display']);
});

test('route names describe processes and stock is confined to material nodes',()=>{
 const context=vm.createContext({});vm.runInContext(`let active={route:'negative'};${declarations}`,context);
 assert.equal(vm.runInContext('nodeLabels().film',context),'胶片曝光与显影');
});
