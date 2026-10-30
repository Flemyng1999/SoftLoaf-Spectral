(function(root){
'use strict';
const copy=x=>JSON.parse(JSON.stringify(x));
function scanDisplayPoint(point,rotation=0,mirror=false,inverse=false){
 let [x,y]=point;
 if(inverse){for(let n=0;n<rotation%4;n++)[x,y]=[y,1-x];if(mirror)x=1-x;}
 else{if(mirror)x=1-x;for(let n=0;n<rotation%4;n++)[x,y]=[1-y,x];}
 return [x,y];
}
function scanTwoPointCorners(points,rotation=0,mirror=false){
 if(points.length!==2)throw Error('请选择 CC01 和 CC24 的中心。');
 const [a,b]=points.map(p=>scanDisplayPoint(p,rotation,mirror));
 if(![...a,...b].every(Number.isFinite)||b[0]-a[0]<.02||b[1]-a[1]<.02)throw Error('请先将照片转正，使 CC01 在左上、CC24 在右下，再重新点选。');
 return [a,[b[0],a[1]],b,[a[0],b[1]]].map(p=>scanDisplayPoint(p,rotation,mirror,true));
}
function scanKnownLayout(profiles,draft,contract){
 const p=profiles.find(p=>p.raw_contract===contract&&p.source_assets?.chart===draft.chart&&p.source_assets?.reference===draft.reference);
 return p?.sources?.corners?copy(p.sources.corners):null;
}
function scanWizardReady(draft,corners,centres){return {inputs:!!(draft.reference&&draft.chart),positioned:corners.length===4&&centres.length===24};}
function scanChartOrientation(corners){
 let best={score:Infinity,rotation:0,mirror:false};
 for(let rotation=0;rotation<4;rotation++)for(const mirror of [false,true]){
  const p=corners.map(p=>scanDisplayPoint(p,rotation,mirror)),xs=p.map(p=>p[0]),ys=p.map(p=>p[1]);
  const left=Math.min(...xs),top=Math.min(...ys),w=Math.max(...xs)-left,h=Math.max(...ys)-top;
  const wanted=[[0,0],[1,0],[1,1],[0,1]],score=p.reduce((s,p,i)=>s+((p[0]-left)/w-wanted[i][0])**2+((p[1]-top)/h-wanted[i][1])**2,0);
  if(score<best.score)best={score,rotation,mirror};
 }
 return best;
}
function scanCalibrationMarkup(){return `
 <div class="dialog-head"><h2>建立扫描标定</h2><button id="scan-calibration-close" class="quiet">关闭</button></div>
 <ol class="scan-wizard-steps" aria-label="标定步骤"><li data-wizard-step="1">1 选择色卡</li><li data-wizard-step="2">2 检查定位</li><li data-wizard-step="3">3 保存标定</li></ol>
 <div class="scan-wizard-content">
  <section data-wizard-panel="1"><h3>选择色卡资料和拍摄照片</h3><p class="help">色卡编号应与手中的卡片一致。更换光源或拍摄条件后，请重新拍摄色卡。</p>
   <div class="scan-source-card"><label for="scan-target-choice">色卡编号</label><select id="scan-target-choice" aria-label="色卡编号"></select><button data-scan-role="reference">导入其他色卡资料…</button><span id="scan-reference-name" class="help"></span></div>
   <div class="scan-source-card"><label for="scan-chart-choice">色卡照片</label><select id="scan-chart-choice" aria-label="色卡照片"></select><button data-scan-role="chart">选择色卡 RAW…</button><span id="scan-chart-name" class="help"></span></div>
   <details class="scan-format-help"><summary>自备色卡资料的格式</summary><p class="help">CSV 使用 CC01–CC24 对应实测透射光谱，列顺序不限。</p><button id="scan-target-template" class="quiet">下载 CSV 模板</button></details>
   <input id="scan-calibration-file" type="file" hidden>
  </section>
  <section data-wizard-panel="2" hidden class="scan-position-step"><div class="scan-chart-toolbar"><span id="scan-chart-position-title">定位 CC01 和 CC24</span><button id="scan-chart-rotate" class="quiet" title="向右旋转照片" aria-label="向右旋转照片">↻ 旋转照片</button><button id="scan-chart-mirror" class="quiet" title="左右翻转照片" aria-label="左右翻转照片">⇆ 左右翻转</button></div>
   <div class="scan-position-layout"><div id="scan-chart-panel"><div id="scan-chart-surface" class="scan-surface"><img id="scan-chart-image" draggable="false" alt="色卡照片，点击色块中心"><svg id="scan-chart-overlay" viewBox="0 0 1 1" preserveAspectRatio="none"></svg></div></div>
    <aside class="scan-position-guide"><h3 id="scan-chart-guide" role="status"></h3><svg id="scan-chart-map" viewBox="0 0 144 96" role="img" aria-label="CC01–CC24 示意，颜色不用于标定"></svg><p class="help" id="scan-chart-position-help">先将照片转到与示意图相同的方向，再点击照片中亮框对应的色块中心。</p><button id="scan-chart-undo" class="quiet">撤销上一个点</button><button id="scan-chart-reset" class="quiet">重新定位</button><button id="scan-chart-perspective" class="quiet" aria-pressed="false" hidden>透视微调</button></aside></div>
  </section>
  <section data-wizard-panel="3" hidden><h3>保存这套拍摄条件的标定</h3><p id="scan-calibration-summary" class="help"></p><label class="field">标定名称<input id="scan-calibration-name" aria-label="标定名称" type="text"></label><label class="field">平场<select id="scan-calibration-flat"></select></label><p class="help">保存后可用于同机身、同光源与拍摄条件的负片。</p></section>
 </div>
 <p id="scan-calibration-error" class="error" role="alert"></p>
 <div class="scan-wizard-footer"><div data-scan-progress-slot></div><div class="dialog-actions"><button id="scan-calibration-back" class="quiet">上一步</button><button id="scan-calibration-next" class="primary">下一步</button><button id="scan-calibrate" class="primary" hidden>建立标定</button></div></div>`;}

function createScanCalibration({dialog,api,upload,prepare,calibrate,getState,isBusy,onSaved,status,wait}){
 const $=id=>dialog.querySelector('#'+id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const accept='.arw,.dng,.cr2,.cr3,.nef,.nrw,.rw2,.orf,.pef,.srw';
 let step=1,draft={},corners=[],centres=[],anchors=[],colors=null,rotation=0,mirror=false,role='',pending=false,referenceTarget='',saved=false,patchKeys=[],keyed=false,perspective=false,dragCorner=null;
 function error(message=''){$('scan-calibration-error').textContent=message;}
 function options(){
  const s=getState(),all=Object.values(s.assets).filter(a=>a.kind==='reference'),modern=new Set(all.filter(a=>a.metadata.id_scheme==='CC').map(a=>a.metadata.target)),refs=all.filter(a=>a.metadata.id_scheme==='CC'||!modern.has(a.metadata.target));
  $('scan-target-choice').innerHTML='<option value="">选择色卡编号…</option>'+refs.map(a=>`<option value="${esc(a.id)}">${esc(a.metadata.target||a.name)} · 已有测量资料</option>`).join('');
  const ids=[...new Set([draft.chart,...Object.values(s.profiles).map(p=>p.source_assets?.chart)].filter(Boolean))];
  $('scan-chart-choice').innerHTML='<option value="">选择照片…</option>'+ids.map(i=>`<option value="${esc(i)}">${esc(s.assets[i]?.name)}</option>`).join('');
  $('scan-target-choice').value=draft.reference||'';$('scan-chart-choice').value=draft.chart||'';
  const oldFlat=$('scan-calibration-flat').value,p=s.profiles[s.active_profile];$('scan-calibration-flat').innerHTML='<option value="">不使用</option>'+(p?.source_assets?.flat?'<option value="current">当前平场</option>':'')+Object.values(s.flats||{}).map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('');
  $('scan-calibration-flat').value=oldFlat||(p?.source_assets?.chart===draft.chart?(p?.flat_asset||(p?.source_assets?.flat?'current':'')):'');
 }
 function fit(){
  if(step!==2||!$('scan-chart-image').naturalWidth)return;
  const image=$('scan-chart-image'),panel=$('scan-chart-panel'),w=image.naturalWidth,h=image.naturalHeight;
  const scale=Math.min((panel.clientWidth-18)/(rotation%2?h:w),(panel.clientHeight-18)/(rotation%2?w:h));
  if(!(scale>0))return;
  Object.assign($('scan-chart-surface').style,{width:(rotation%2?h:w)*scale+'px',height:(rotation%2?w:h)*scale+'px'});
  Object.assign(image.style,{width:w*scale+'px',height:h*scale+'px',transform:`translate(-50%,-50%) rotate(${rotation*90}deg) scaleX(${mirror?-1:1})`});
 }
 function render(){
  const locked=isBusy()||pending,ready=scanWizardReady(draft,corners,centres);
  dialog.querySelectorAll('[data-wizard-panel]').forEach(e=>e.hidden=Number(e.dataset.wizardPanel)!==step);
  dialog.querySelectorAll('[data-wizard-step]').forEach(e=>{e.setAttribute('aria-current',Number(e.dataset.wizardStep)===step?'step':'false');e.classList.toggle('complete',Number(e.dataset.wizardStep)<step);});
  $('scan-calibration-back').hidden=step===1;$('scan-calibration-next').hidden=step===3;$('scan-calibrate').hidden=step!==3;
  $('scan-calibration-next').disabled=locked||(step===1?!(ready.inputs&&colors&&keyed):!ready.positioned);
  $('scan-calibration-next').textContent=step===2?'定位正确，继续':'下一步';$('scan-calibrate').disabled=locked||!ready.positioned;
  for(const id of ['scan-calibration-back','scan-calibration-close','scan-target-choice','scan-chart-choice','scan-chart-rotate','scan-chart-mirror','scan-chart-reset','scan-calibration-flat','scan-calibration-name'])$(id).disabled=locked;
  dialog.querySelectorAll('[data-scan-role]').forEach(b=>b.disabled=locked);
  $('scan-chart-undo').disabled=locked||!anchors.length;
  $('scan-chart-perspective').hidden=!centres.length&&!perspective;$('scan-chart-perspective').disabled=locked;$('scan-chart-perspective').setAttribute('aria-pressed',String(perspective));
  const points=centres.length?centres:anchors;
  $('scan-chart-overlay').innerHTML=points.map((p,i)=>{const [x,y]=scanDisplayPoint(p,rotation,mirror);return `<circle cx="${x}" cy="${y}" r=".009" fill="#1678ff33" stroke="#1680ff" stroke-width=".003"/>${centres.length?'':`<text x="${x+.015}" y="${y}" font-size=".035" fill="white" stroke="#111" stroke-width=".001">${esc(patchKeys[i===0?0:23]||'')}</text>`}`;}).join('');
  if(perspective)$('scan-chart-overlay').innerHTML+=corners.map((p,i)=>{const [x,y]=scanDisplayPoint(p,rotation,mirror);return `<circle class="scan-corner-handle" data-scan-corner="${i}" cx="${x}" cy="${y}" r=".014"/>`;}).join('');
  const next=centres.length?null:[0,23][anchors.length];
  $('scan-chart-map').innerHTML=Array.from({length:24},(_,i)=>`<rect x="${i%6*24+2}" y="${Math.floor(i/6)*24+2}" width="20" height="20" rx="2" fill="${colors?'rgb('+colors[i].join(',')+')':'#888'}"><title>${esc(patchKeys[i]||'')}</title></rect><text x="${i%6*24+12}" y="${Math.floor(i/6)*24+14}" text-anchor="middle" font-size="6" fill="white" stroke="#111" stroke-width=".4" paint-order="stroke">${esc(patchKeys[i]||'')}</text>${i===next?`<rect class="chart-highlight" x="${i%6*24+1}" y="${Math.floor(i/6)*24+1}" width="22" height="22" rx="3"/>`:''}`).join('');
  $('scan-chart-guide').textContent=centres.length?'检查这 24 个圆点':anchors.length?'2 / 2 · 点击 '+patchKeys[23]:'1 / 2 · 点击 '+patchKeys[0];
  $('scan-chart-position-help').textContent=centres.length?(perspective?'拖动四个角点修正透视。所有圆点都落在对应色块内后继续。':'每个圆点都应落在对应色块内。有倾斜时可用透视微调。'):'先将照片转到与示意图同方向，再点照片中亮框对应的色块中心。';
  $('scan-chart-position-title').textContent=centres.length?'已定位 24 个色块':'点选首尾两个色块';
  $('scan-calibration-summary').textContent=`色卡 ${referenceTarget} · 24 个色块 · ${getState()?.assets[draft.chart]?.metadata.Model||''}`;
  requestAnimationFrame(fit);
 }
 async function knownLayout(){
  corners=[];centres=[];anchors=[];perspective=false;
  let known=scanKnownLayout(Object.values(getState().profiles),draft,getState().raw_contract);
  if(!known&&draft.chart&&draft.reference&&keyed){const g=await api('/api/scan',{action:'target-guide',reference:draft.reference,chart:draft.chart});known=g.known_corners;}
  if(known&&keyed){corners=known;centres=(await api('/api/scan',{action:'layout',corners})).centres;anchors=[corners[0],corners[2]];const orientation=scanChartOrientation(corners);rotation=orientation.rotation;mirror=orientation.mirror;}
 }
 async function reference(id){
  if(!id){draft.reference=null;colors=null;render();return;}
  draft.reference=id;pending=true;render();const task=wait('读取色卡资料');
  try{const g=await api('/api/scan',{action:'target-guide',reference:id});draft.reference=g.reference;colors=g.colors;keyed=!!g.keyed;patchKeys=g.patch_keys||[];referenceTarget=g.target;if(!keyed)error('请导入使用 CC01–CC24 的光谱 CSV。旧编号仅保留用于已有标定。');$('scan-reference-name').textContent=`色卡编号 ${g.target}`;await knownLayout();options();}
  finally{pending=false;task();render();}
 }
 async function chart(id){
  if(!id){draft.chart=null;render();return;}
  pending=true;if(draft.chart!==id)$('scan-calibration-flat').value='';draft.chart=id;render();
  try{await prepare(id);$('scan-chart-image').src=getState().assets[id].chart_preview_url;$('scan-chart-name').textContent=getState().assets[id].name;await knownLayout();options();}
  finally{pending=false;render();}
 }
 async function open(){
  const s=getState(),p=s.profiles[s.active_profile];if(saved){draft={};corners=[];centres=[];saved=false;}
  step=1;error();dialog.showModal();options();render();
  try{
   if(!draft.reference&&p?.source_assets.reference){await reference(p.source_assets.reference);$('scan-target-choice').value=draft.reference;}
   if(!draft.chart&&p?.source_assets.chart){await chart(p.source_assets.chart);options();}
   if(!$('scan-calibration-name').value)$('scan-calibration-name').value=p?.name||`${s.assets[draft.chart]?.metadata.Model||'相机'} · ${referenceTarget}`;
  }catch(e){error(e.message);}
 }
 function go(value){step=value;error();render();}
 $('scan-calibration-next').onclick=()=>go(step+1);$('scan-calibration-back').onclick=()=>go(step-1);
 $('scan-calibration-close').onclick=()=>{if(!isBusy()&&!pending)dialog.close();};dialog.addEventListener('cancel',e=>{if(isBusy()||pending)e.preventDefault();});
 $('scan-target-choice').onchange=e=>reference(e.target.value).catch(e=>error(e.message));$('scan-chart-choice').onchange=e=>chart(e.target.value).catch(e=>error(e.message));
 dialog.querySelectorAll('[data-scan-role]').forEach(b=>b.onclick=()=>{role=b.dataset.scanRole;$('scan-calibration-file').accept=role==='reference'?'.csv':accept;$('scan-calibration-file').click();});
 $('scan-calibration-file').onchange=async e=>{const file=e.target.files[0],kind=role;e.target.value='';if(!file)return;try{const a=await upload(file,kind==='reference'?'reference':'raw');if(kind==='reference')await reference(a.id);else await chart(a.id);options();error();}catch(e){error(e.message);}};
 $('scan-chart-image').onload=fit;$('scan-chart-image').onerror=()=>error('色卡预览未能加载，请重新选择这张照片。');window.addEventListener('resize',fit);
 $('scan-chart-rotate').onclick=()=>{rotation=(rotation+1)%4;render();};$('scan-chart-mirror').onclick=()=>{mirror=!mirror;render();};
 $('scan-chart-reset').onclick=()=>{anchors=[];corners=[];centres=[];perspective=false;error();render();};$('scan-chart-undo').onclick=()=>{anchors.pop();corners=[];centres=[];perspective=false;error();render();};
 $('scan-chart-perspective').onclick=()=>{perspective=!perspective;render();};
 function photoPoint(e){const r=$('scan-chart-image').getBoundingClientRect();return scanDisplayPoint([(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height],rotation,mirror,true);}
 $('scan-chart-surface').onclick=async e=>{
  if(isBusy()||pending||!keyed||!draft.chart||centres.length||anchors.length===2||e.target!==$('scan-chart-image'))return;
  anchors.push(photoPoint(e));pending=true;
  try{if(anchors.length===2){corners=scanTwoPointCorners(anchors,rotation,mirror);centres=(await api('/api/scan',{action:'layout',corners})).centres;}error();}
  catch(e){anchors.pop();corners=[];error(e.message);}finally{pending=false;render();}
 };
 const surface=$('scan-chart-surface');
 surface.onpointerdown=e=>{const handle=e.target.closest('[data-scan-corner]');if(!handle||isBusy()||pending)return;e.preventDefault();dragCorner={index:Number(handle.dataset.scanCorner),before:copy(corners)};surface.setPointerCapture(e.pointerId);};
 surface.onpointermove=e=>{if(!dragCorner)return;const p=photoPoint(e);if(p.some(v=>v<0||v>1))return;corners[dragCorner.index]=p;centres=[];render();};
 surface.onpointerup=async()=>{if(!dragCorner)return;const before=dragCorner.before;dragCorner=null;pending=true;const task=wait('更新色块定位');try{centres=(await api('/api/scan',{action:'layout',corners})).centres;anchors=[corners[0],corners[2]];error();}catch(e){corners=before;centres=(await api('/api/scan',{action:'layout',corners})).centres;error(e.message);}finally{task();pending=false;render();}};
 surface.onpointercancel=()=>{if(dragCorner){corners=dragCorner.before;dragCorner=null;api('/api/scan',{action:'layout',corners}).then(r=>{centres=r.centres;render();}).catch(e=>error(e.message));}};
 $('scan-calibrate').onclick=async()=>{try{
  const selected=$('scan-calibration-flat').value,p=getState().profiles[getState().active_profile];
  const value={...draft,corners,name:$('scan-calibration-name').value.trim(),flat_asset:selected&&selected!=='current'?selected:null,flat:selected==='current'?p?.source_assets.flat:null};
  if(!value.name){error('请给这套标定起个名字。');$('scan-calibration-name').focus();return;}
  const result=await calibrate(value);saved=true;dialog.close();await onSaved(result.profile);status('标定已保存，可以导入同条件拍摄的负片。');
 }catch(e){error(e.message);}};
 $('scan-target-template').onclick=()=>{const labels=getState().target_patch_keys;const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['# softloaf.transmission-target/3\n# target=填写色卡编号\n# CC01=左上；CC24=右下；透射率0–1，波长nm\nwavelength_nm,'+labels.join(',')+'\n'],{type:'text/csv'}));a.download='transmission-target-template.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
 return {open,render,isPending:()=>pending};
}
const exports={scanTwoPointCorners,scanDisplayPoint,scanKnownLayout,scanWizardReady,scanChartOrientation,scanCalibrationMarkup,createScanCalibration};
if(typeof module==='object'&&module.exports)module.exports=exports;else Object.assign(root,exports);
})(typeof globalThis!=='undefined'?globalThis:this);
