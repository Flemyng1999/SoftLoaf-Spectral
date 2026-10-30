const test=require('node:test'),assert=require('node:assert/strict');
test('scan status reads retry a temporary disconnect without replaying processing mutations',async()=>{
 const {readScanStatus}=require('../design/gui-v2/scanning.js');
 const calls=[],delays=[];let attempts=0;
 const api=async(path,payload,signal)=>{calls.push({path,payload,signal});if(++attempts<3)throw new TypeError('Load failed');return {status:'complete'};};
 const payload={action:'job',id:'accepted-job'};
 assert.deepEqual(await readScanStatus(api,payload,{pause:async ms=>delays.push(ms)}),{status:'complete'});
 assert.equal(calls.length,3);assert(calls.every(c=>c.path==='/api/scan'&&c.payload===payload));assert.equal(delays.length,2);
 let rejected=0;await assert.rejects(readScanStatus(async()=>{rejected++;throw Object.assign(Error('unknown job'),{status:400});},payload),/unknown job/);assert.equal(rejected,1);
 let writes=0;await assert.rejects(readScanStatus(async()=>{writes++;},{action:'prepare'}),/只读/);assert.equal(writes,0);
 let outages=0;await assert.rejects(readScanStatus(async()=>{outages++;throw new TypeError('Load failed');},undefined,{pause:async()=>{}}),/连接/);assert.equal(outages,4);
});
test('chart photo rotations preserve source sampling coordinates and only reuse matching measured layouts',()=>{
 const {scanDisplayPoint,scanKnownLayout,scanWizardReady}=require('../design/gui-v2/scanning.js');
 for(let r=0;r<4;r++)for(const m of [false,true]){
  const p=[.23,.71],d=scanDisplayPoint(p,r,m),back=scanDisplayPoint(d,r,m,true);
  back.forEach((v,i)=>assert.ok(Math.abs(v-p[i])<1e-12));
 }
 const p={raw_contract:'RT',source_assets:{chart:'c',reference:'r'},sources:{corners:[[.1,.2],[.8,.2],[.8,.7],[.1,.7]]}};
 assert.deepEqual(scanKnownLayout([p],{chart:'c',reference:'r'},'RT'),p.sources.corners);
 assert.equal(scanKnownLayout([p],{chart:'c',reference:'different'},'RT'),null);
 assert.equal(scanWizardReady({reference:'r'},[],[]).inputs,false);
 assert.equal(scanWizardReady({reference:'r',chart:'c'},[],[]).inputs,true);
 assert.equal(scanWizardReady({reference:'r',chart:'c'},p.sources.corners,[]).positioned,false);
});
test('viewer and filmstrip use the same RT source and reject obsolete preview colours',()=>{
 const {scanFrameSource}=require('../design/gui-v2/scanning.js');
 const old={preview_url:'green',thumbnail_url:'green-thumb',embedded_url:'camera-jpeg',embedded_thumbnail_url:'jpeg-thumb',native_preview_url:'native',preview_engine:'old'};
 assert.deepEqual(scanFrameSource(old,'RT'),{image:null,thumbnail:null});
 const current={...old,preview_engine:'RT',preview_url:'RT-sRGB',thumbnail_url:'RT-sRGB-small'};
 assert.deepEqual(scanFrameSource(current,'RT'),{image:'RT-sRGB',thumbnail:'RT-sRGB-small'});
 assert.equal(scanFrameSource(current,'RT',{url:'positive'},true).image,'RT-sRGB');
 const corrected={...current,chart_preview_url:'unwarped',preview_context:'flat+geometry'};
 assert.equal(scanFrameSource(corrected,'RT',null,true,'different').image,'unwarped');
 assert.deepEqual(scanFrameSource(corrected,'RT',null,false,'different'),{image:null,thumbnail:null});
 assert.equal(scanFrameSource(corrected,'RT',null,false,'flat+geometry').image,'RT-sRGB');
});
test('chart guide preserves measured patch identity through all rotations and mirrors',()=>{
 const {scanChartLayout}=require('../design/gui-v2/scanning.js');
 for(let rotation=0;rotation<4;rotation++)for(const mirror of [false,true]){
  const g=scanChartLayout(rotation,mirror);assert.equal(g.points.length,24);
  assert.equal(new Set(g.points.map(p=>p.join(','))).size,24);
  for(const [x,y] of g.points){assert.ok(x>=0&&x<g.columns&&y>=0&&y<g.rows);}
  const first=g.points[0],last=g.points[23];assert.notDeepEqual(first,last);
 }
 assert.deepEqual(scanChartLayout(0,false).points[0],[0,0]);
 assert.deepEqual(scanChartLayout(0,true).points[0],[5,0]);
 assert.deepEqual(scanChartLayout(1,false).points[5],[3,5]);
});
test('RAW imports overlap uploads with bounded preparations and drain accepted work on failure',async()=>{
 const {importScanFiles}=require('../design/gui-v2/scanning.js');
 let running=0,max=0,uploads=0;const finish=[],events=[];
 const ops={upload:async f=>{uploads++;events.push('upload'+f);return {id:f};},
  prepare:async a=>{running++;max=Math.max(max,running);events.push('prepare'+a.id);await new Promise(r=>finish.push(r));running--;},progress:()=>{}};
 const work=importScanFiles([1,2,3],ops);await new Promise(r=>setImmediate(r));
 assert.equal(uploads,2);assert.equal(max,2);finish.shift()();await new Promise(r=>setImmediate(r));
 assert.equal(uploads,3);finish.splice(0).forEach(r=>r());await work;assert.equal(running,0);
 let release,drained=false;const failure=importScanFiles([1,2,3],{...ops,
  upload:async f=>{if(f===2)throw Error('copy failed');return {id:f};},
  prepare:async()=>{await new Promise(r=>release=r);drained=true;}});
 await new Promise(r=>setImmediate(r));release();await assert.rejects(failure,/copy failed/);assert.equal(drained,true);
});
test('scan border rectangles normalize drag direction and freeze requests',()=>{
 const {scanRectangle,scanSettings}=require('../design/gui-v2/scanning.js');
 assert.deepEqual(scanRectangle([.8,.7],[.2,.1]),[.2,.1,.8,.7]);
 const state={profile:'p',stock:'5207',ev:2,size:65,border:{asset:'a',roi:[.1,.2,.3,.4]}};
 const frozen=scanSettings(state);state.border.roi[0]=.9;
 assert.equal(frozen.border.roi[0],.1);assert.equal(frozen.view_ev,2);
});
test('partial scan results are visible before the roll finishes and geometry stays frozen',()=>{
 const {scanCurrent,scanSettings,scanCrop}=require('../design/gui-v2/scanning.js');
 const geometry={rotation:1,crop:[.1,.2,.8,.9]},s={profile:'p',stock:'5207',ev:0,size:65,border:{asset:'a',roi:[.1,.2,.3,.4]},geometry};
 const r={...scanSettings(s),material_id:'m',processing_id:'v',outputs:{a:{url:'/a'}}};
 const state={active_result:'r',results:{r},material_ids:{'5207':'m'},processing_id:'v',images:['a','b']};
 assert.equal(scanCurrent(state,s),r);
 assert.equal(scanCurrent(state,{...s,geometry:{...geometry,rotation:2}}),null);
 const frozen=scanSettings(s);geometry.crop[0]=.9;assert.equal(frozen.geometry.crop[0],.1);
 const crop=scanCrop([.1,.2,.9,.8],[.25,0,.75,1]);crop.forEach((x,i)=>assert.ok(Math.abs(x-[.3,.2,.7,.8][i])<1e-12));
});
test('two chart anchors span 1–24 and sampling survives all display rotations and mirrors',()=>{
 const {scanTwoPointCorners,scanDisplayPoint}=require('../design/gui-v2/scan-calibration.js');
 for(let rotation=0;rotation<4;rotation++)for(const mirror of [false,true]){
  const points=[[.2,.25],[.8,.75]].map(p=>scanDisplayPoint(p,rotation,mirror,true));
  const c=scanTwoPointCorners(points,rotation,mirror).map(p=>scanDisplayPoint(p,rotation,mirror));
  const expected=[[.2,.25],[.8,.25],[.8,.75],[.2,.75]];
  c.forEach((p,i)=>p.forEach((x,j)=>assert.ok(Math.abs(x-expected[i][j])<1e-12)));
 }
 assert.throws(()=>scanTwoPointCorners([[.8,.7],[.2,.3]]),/转正/);
 assert.throws(()=>scanTwoPointCorners([[.2,.3],[.2,.7]]),/转正/);
});
