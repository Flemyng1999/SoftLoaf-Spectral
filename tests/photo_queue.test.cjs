const test=require('node:test');const assert=require('node:assert/strict');
const {createPhotoQueue}=require('../design/gui-v2/photo-queue.js');
const items=[{id:'scene',name:'示例',kind:'rgb_photo'},{id:'a',name:'A.png',kind:'imported_rgb_photo'},
 {id:'b',name:'B.png',kind:'imported_rgb_photo'}];
test('queue preserves import order and stores input exposure per photograph',()=>{
 const q=createPhotoQueue(items,null,'a');q.setExposure(.7);q.select('b');assert.equal(q.current().exposure_ev,0);
 q.setExposure(-.5);q.select('a');assert.equal(q.current().exposure_ev,.7);
 assert.deepEqual(q.batchInputs(),[{id:'a',exposure_ev:.7},{id:'b',exposure_ev:-.5}]);
 q.upsert({...items[1],name:'A again.png'});assert.deepEqual(q.stripItems().map(i=>i.id),['a','b']);
});
test('restarting restores selected photo, queue order and individual exposure',()=>{
 const q=createPhotoQueue(items,null,'b');q.setExposure(1);
 const restored=createPhotoQueue([...items].reverse(),q.snapshot(),'scene');
 assert.deepEqual(restored.stripItems().map(i=>i.id),['a','b']);
 assert.deepEqual(restored.current(),{id:'b',exposure_ev:1});
});
test('batch snapshots exclude builtin samples and cannot change during later edits',()=>{
 const q=createPhotoQueue(items,null,'scene');const job=q.batchInputs();q.select('a');q.setExposure(2);
 assert.deepEqual(job,[{id:'a',exposure_ev:0},{id:'b',exposure_ev:0}]);
 assert.equal(q.stripItems()[0].id,'a');
 assert.throws(()=>q.setExposure(20));assert.throws(()=>q.select('missing'));
});

test('file picker accepts exactly the RAW formats advertised by the active backend',()=>{
 const {photoInputAccept}=require('../design/gui-v2/photo-queue.js');
 assert.equal(photoInputAccept({raw_supported:true,raw_extensions:['.ori','.crw','.x3f']}),'.png,.jpg,.jpeg,.ori,.crw,.x3f');
 assert.equal(photoInputAccept({raw_supported:false,raw_extensions:['.x3f']}),'.png,.jpg,.jpeg');
});

test('photo panels collapse independently and restore without altering photo selection or exposure',()=>{
 const q=createPhotoQueue(items,null,'a');q.setExposure(.7);
 assert.deepEqual(q.panels(),{recipes_collapsed:false,filmstrip_collapsed:false});
 q.togglePanel('recipes_collapsed');assert.deepEqual(q.panels(),{recipes_collapsed:true,filmstrip_collapsed:false});
 q.togglePanel('filmstrip_collapsed');const snapshot=q.snapshot();
 const restored=createPhotoQueue(items,snapshot,'scene');
 assert.deepEqual(restored.panels(),{recipes_collapsed:true,filmstrip_collapsed:true});
 assert.deepEqual(restored.current(),{id:'a',exposure_ev:.7});
 restored.togglePanel('recipes_collapsed');assert.equal(restored.panels().filmstrip_collapsed,true);
 snapshot.panels.filmstrip_collapsed=false;assert.equal(q.panels().filmstrip_collapsed,true);
});
