const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function cache(options){const c=vm.createContext({});vm.runInContext(fs.readFileSync('design/gui-v2/rendition-cache.js','utf8'),c);return c.createRenditionCache(options);}
test('frame LRU reuses photos and separates changed recipe exposure and display',()=>{
 const c=cache({budget:100,maxEntries:3});c.put('photo1-recipe1',{value:1},40);c.put('photo2-recipe1',{value:2},40);
 assert.equal(c.get('photo1-recipe1').value,1);assert.equal(c.get('photo1-recipe2'),null);
 c.put('photo3-recipe1',{value:3},40);assert.equal(c.get('photo2-recipe1'),null);assert.equal(c.bytes(),80);
});
test('oversized frames cannot grow memory and neighbors exclude current image',()=>{
 const c=cache({budget:100,maxEntries:3});c.put('large',{value:1},101);assert.equal(c.get('large'),null);
 assert.deepEqual(Array.from(c.neighbors(['a','b','c','d'],'b')),['c','a']);
});
test('settings shrink memory immediately and clear retained frames',()=>{
 const c=cache({budget:100});c.put('a',1,40);c.put('b',2,40);c.configure(45);
 assert.equal(c.bytes(),40);assert.equal(c.get('a'),null);assert.equal(c.get('b'),2);c.clear();assert.equal(c.bytes(),0);assert.equal(c.get('b'),null);
});
