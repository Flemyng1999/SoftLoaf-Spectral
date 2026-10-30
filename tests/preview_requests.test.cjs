const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('at most one frame runs; pending adjustments coalesce to the newest request',async()=>{
 const c=vm.createContext({});vm.runInContext(fs.readFileSync('design/gui-v2/preview-requests.js','utf8'),c);
 const started=[],release=[];const scheduler=c.createLatestPreviewTask(async id=>{started.push(id);await new Promise(resolve=>release.push(resolve));return id});
 const first=scheduler.submit(1);scheduler.submit(2);const last=scheduler.submit(3);
 assert.deepEqual(started,[1]);release.shift()();await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(started,[1,3]);release.shift()();assert.equal(await first,3);assert.equal(await last,3);
 assert.equal(scheduler.busy(),false);
});
