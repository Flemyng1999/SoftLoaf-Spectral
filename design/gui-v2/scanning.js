(function(root){
'use strict';
const clone=x=>JSON.parse(JSON.stringify(x));
const calibrationTools=typeof module==='object'&&module.exports?require('./scan-calibration.js'):Object.fromEntries(['scanTwoPointCorners','scanDisplayPoint','scanKnownLayout','scanWizardReady','scanChartOrientation','scanCalibrationMarkup','createScanCalibration'].map(k=>[k,root[k]]));
function scanRectangle(a,b){return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];}
function scanSettings(s){return {profile:s.profile,stock:s.stock,view_ev:Number(s.ev),size:Number(s.size),border:clone(s.border),geometry:clone(s.geometry||{rotation:0,crop:[0,0,1,1],radial:[1,0,0,0,0],zoom:1})};}
function scanCurrent(state,s){const r=state?.results?.[state.active_result];return r&&r.material_id===state.material_ids?.[s.stock]&&r.processing_id===state.processing_id&&r.profile===s.profile&&r.stock===s.stock&&r.view_ev===Number(s.ev)&&r.size===Number(s.size)&&JSON.stringify(r.border)===JSON.stringify(s.border)&&JSON.stringify(r.geometry||{})===JSON.stringify(s.geometry||{})?r:null;}
function scanCrop(base,roi){return [base[0]+roi[0]*(base[2]-base[0]),base[1]+roi[1]*(base[3]-base[1]),base[0]+roi[2]*(base[2]-base[0]),base[1]+roi[3]*(base[3]-base[1])];}
function scanFrameSource(asset,contract,output,original=false,context=null){
 const rawReady=!!contract&&asset?.preview_engine===contract,ready=rawReady&&(!context||asset.preview_context===context);
 return {image:original?(rawReady?(asset.chart_preview_url||asset.preview_url):null):output?output.url:ready?asset.preview_url:null,thumbnail:output?.thumbnail_url||(ready?asset.thumbnail_url:null)};
}
function scanChartLayout(rotation=0,mirror=false){
 let columns=6,rows=4,points=Array.from({length:24},(_,i)=>[mirror?5-i%6:i%6,Math.floor(i/6)]);
 for(let n=0;n<rotation%4;n++){points=points.map(([x,y])=>[rows-1-y,x]);[columns,rows]=[rows,columns];}
 return {columns,rows,points};
}
async function importScanFiles(files,{upload,prepare,progress,maxPending=2}){
 const pending=new Set();let uploaded=0,completed=0,failure=null;
 const report=()=>progress({uploaded,completed,total:files.length});
 try{for(const file of files){
  if(pending.size===maxPending)await Promise.race(pending);if(failure)throw failure;
  const asset=await upload(file);uploaded++;report();
  const task=Promise.resolve().then(()=>prepare(asset)).then(()=>{completed++;report();},error=>{failure=failure||error;}).finally(()=>pending.delete(task));
  pending.add(task);
 }}catch(error){failure=failure||error;}
 await Promise.all(pending);if(failure)throw failure;return {uploaded,completed};
}
// Retry only status queries. An accepted upload/development is never replayed.
async function readScanStatus(api,payload,{pause=ms=>new Promise(r=>setTimeout(r,ms)),timeoutMs=10000}={}){
 if(payload!==undefined&&(payload.action!=='job'||payload.cancel))throw Error('仅允许重试只读扫描查询。');
 for(let attempt=0;attempt<4;attempt++){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{return await api('/api/scan',payload,controller.signal);}
  catch(e){
   if(!(e instanceof TypeError||e.name==='AbortError'||[502,503,504].includes(e.status)))throw e;
   if(attempt===3)throw Error('本机服务连接中断；已导入的原件仍保留，请重新打开工作区。');
  }finally{clearTimeout(timer);}
  await pause([250,750,1500][attempt]);
 }
}
function createScanWorkbench({container,sidebar,api,status,onPanelsChange=()=>{}}){
 const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let state=null,loading=false,visible=false,busy=false,uploading=false,importing=false,active=null,profile=null,stock='5207',ev=0,size=65,border=null,original=false,selecting=false,drag=null,lastExport=[];
 let calibration=null,geoBusy=false,geoSequence=0,geoTimer=null;
 let upgrading=false;
 let geometry={rotation:0,crop:[0,0,1,1],radial:[1,0,0,0,0],zoom:1},geoDraft={},geoShown=null,geoDrag=null,flatDraft=null;
 sidebar.innerHTML='<h2 class="side-heading">扫描标定</h2><div id="scan-profiles" class="recipes"></div>';
 container.innerHTML=`<div class="scan-top"><button id="scan-import">导入 RAW…</button><button id="scan-new-roll" class="quiet">新一卷</button><input id="scan-raw-files" type="file" multiple hidden><span id="scan-count" class="muted"></span><button id="scan-new-profile" class="quiet scan-tool" type="button" title="建立标定" aria-label="建立标定" aria-haspopup="dialog" aria-controls="scan-calibration-dialog"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7.5 4v16M12 4v16M16.5 4v16M3 9.3h18M3 14.7h18"/></svg></button><button id="scan-flat-tool" class="quiet scan-tool" type="button" title="平场矫正" aria-label="平场矫正" aria-haspopup="dialog" aria-controls="scan-flat-dialog"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2.5"/><ellipse cx="12" cy="12" rx="5.5" ry="4.5"/><ellipse cx="12" cy="12" rx="2.2" ry="1.8"/></svg></button><button id="scan-geometry-tool" class="quiet scan-tool" type="button" title="镜头畸变矫正" aria-label="镜头畸变矫正" aria-haspopup="dialog" aria-controls="scan-geometry-dialog"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 4Q12 6 20 4Q18 12 20 20Q12 18 4 20Q6 12 4 4Z"/><path d="M9 5Q10.5 12 9 19M15 5Q13.5 12 15 19M5 9Q12 10.5 19 9M5 15Q12 13.5 19 15"/></svg></button><button id="scan-original" class="quiet">取样预览</button></div>
 <div class="scan-body"><div class="scan-viewer"><div id="scan-surface" class="scan-surface"><img id="scan-image" draggable="false" alt="负片正相预览"><svg id="scan-overlay" viewBox="0 0 1 1" preserveAspectRatio="none"></svg></div><p id="scan-empty" class="muted">建立扫描标定，然后导入负片 RAW。</p></div>
 <aside class="scan-edit"><h2>负片正相</h2><label class="field">负片<select id="scan-stock" aria-label="扫描负片材料"></select></label>
 <label class="field">曝光补偿 <span id="scan-ev-value">0.0 EV</span><input id="scan-ev" aria-label="正片曝光补偿" type="range" min="-4" max="4" step=".1" value="0"></label>
 <label class="field">LUT 尺寸<input id="scan-size" aria-label="扫描 LUT 尺寸" type="number" min="2" max="129" value="65"></label>
 <div class="field"><span id="scan-base-label">片基尚未选择</span><button id="scan-base">选择片基</button><p class="help">每卷一次，框选已显影、未曝光的片边。</p></div>
 <button id="scan-positive" class="primary">一键正相</button><p class="help">APD → ACES 2.0 · sRGB</p><p id="scan-dirty" class="help"></p>
 <div id="scan-lut-downloads" class="scan-downloads"></div><button id="scan-export">导出正片…</button><div id="scan-export-downloads" class="scan-downloads"></div>
 <details id="scan-adx-reference" class="scan-reference"><summary>ADX10 参考值</summary>
 <table aria-label="Cineon 正常负片经验码值"><caption>Cineon 正常负片 · 10-bit</caption><thead><tr><th scope="col">参考点</th><th scope="col">码值</th></tr></thead>
 <tbody><tr><th scope="row">片基 Dmin</th><td>95</td></tr><tr><th scope="row">2% 黑</th><td>180</td></tr><tr><th scope="row">Digital LAD</th><td>445</td></tr><tr><th scope="row">18% 灰</th><td>470</td></tr><tr><th scope="row">90% 白</th><td>685</td></tr></tbody></table>
 <p class="help">0.002 D/码 · γ≈0.6 时约 90 码/挡</p><p class="help">经验参考，非当前图像取样值。实际值随片种、曝光与显影变化。</p>
 </details></aside></div>
 <details id="scan-filmstrip" class="scan-strip" open><summary>胶片条</summary><div id="scan-strip-items" class="filmstrip-rail"></div></details>
 <dialog id="scan-calibration-dialog" class="scan-wizard">${calibrationTools.scanCalibrationMarkup()}</dialog>
 <dialog id="scan-flat-dialog"><div class="dialog-head"><h2>平场矫正</h2><button id="scan-flat-close" class="quiet">关闭</button></div>
 <p class="help">同光路拍摄均匀平场。修正亮度不均与色偏，不改变中央白平衡。</p>
 <button id="scan-flat-import">导入平场 RAW…</button><input id="scan-flat-files" type="file" multiple hidden>
 <label class="field">使用平场<select id="scan-flat-choice"></select></label><p id="scan-flat-info" class="help"></p><p id="scan-flat-error" class="error" role="alert"></p>
 <div data-scan-progress-slot></div><div class="dialog-actions"><button id="scan-flat-apply" class="primary">应用到整卷</button></div></dialog>
 <dialog id="scan-geometry-dialog"><div class="dialog-head"><h2>几何矫正</h2><button id="scan-geometry-close" class="quiet">关闭</button></div>
 <div class="scan-geometry-controls"><label class="field">镜头<select id="scan-lens-mode"><option value="off">不矫正</option><option value="profile">镜头配置</option><option value="manual">手动畸变</option></select></label>
 <label class="field scan-lens-profile">搜索镜头<input id="scan-lens-search" placeholder="镜头名称"></label><label class="field scan-lens-profile">配置<select id="scan-lens-choice"></select></label>
 <label class="field scan-lens-profile">焦距 mm<input id="scan-lens-focal" type="number" min="1" max="2000"></label><label class="field scan-lens-profile">传感器裁切系数<input id="scan-lens-crop" type="number" min=".1" max="10" step=".01"></label>
 <label class="field" id="scan-lens-manual">畸变<input id="scan-lens-strength" type="range" min="-.2" max=".2" step=".001" value="0"></label>
 <label class="field">旋转<select id="scan-rotation"><option value="0">0°</option><option value="1">90°</option><option value="2">180°</option><option value="3">270°</option></select></label>
 <label><input id="scan-auto-crop" type="checkbox" checked> 自动去除黑边</label></div>
 <div class="scan-geometry-actions"><button id="scan-geometry-preview">更新预览</button><button id="scan-crop-reset" class="quiet">重置裁切</button><span class="help">在预览中拖出裁切范围</span></div>
 <div id="scan-geometry-surface" class="scan-surface"><img id="scan-geometry-image" draggable="false" alt="综合几何矫正预览"><svg id="scan-geometry-overlay" viewBox="0 0 1 1" preserveAspectRatio="none"></svg></div>
 <p id="scan-geometry-info" class="help">畸变、旋转、裁切、缩放合并取样一次。平场已包含暗角修正。</p><p id="scan-geometry-error" class="error" role="alert"></p>
 <div data-scan-progress-slot></div><div class="dialog-actions"><button id="scan-geometry-apply" class="primary">应用到整卷</button></div></dialog>`;
 const profileMenu=document.createElement('div');profileMenu.className='recipe-context-menu';profileMenu.id='scan-profile-context-menu';profileMenu.hidden=true;profileMenu.setAttribute('role','menu');profileMenu.setAttribute('aria-label','扫描标定操作');profileMenu.innerHTML='<button id="scan-delete-profile" type="button" role="menuitem">删除</button><button id="scan-restore-profile" type="button" role="menuitem" hidden>恢复上次删除</button>';document.body.append(profileMenu);
 const restoreProfile=$('scan-restore-profile');
 let menuProfile=null;
 function closeProfileMenu(focus=false){profileMenu.hidden=true;if(focus&&menuProfile)$('scan-profiles').querySelector(`[data-scan-profile="${menuProfile}"]`)?.focus();}
 function openProfileMenu(button,x,y){if(locked()||(!button&&!state?.deleted_profile_order?.length))return;menuProfile=button?.dataset.scanProfile||null;profileMenu.firstElementChild.hidden=!button;restoreProfile.hidden=!state?.deleted_profile_order?.length;profileMenu.hidden=false;const r=profileMenu.getBoundingClientRect();profileMenu.style.left=Math.max(8,Math.min(x,window.innerWidth-r.width-8))+'px';profileMenu.style.top=Math.max(8,Math.min(y,window.innerHeight-r.height-8))+'px';profileMenu.querySelector('button:not([hidden])').focus();}
 sidebar.oncontextmenu=e=>{e.preventDefault();openProfileMenu(e.target.closest('[data-scan-profile]'),e.clientX,e.clientY);};
 $('scan-profiles').onkeydown=e=>{if(e.key!=='ContextMenu'&&!(e.shiftKey&&e.key==='F10'))return;const b=e.target.closest('[data-scan-profile]');if(!b)return;e.preventDefault();const r=b.getBoundingClientRect();openProfileMenu(b,r.left+12,r.bottom-4);};
 document.addEventListener('pointerdown',e=>{if(!profileMenu.contains(e.target))closeProfileMenu();});
 document.addEventListener('keydown',e=>{if(!profileMenu.hidden&&e.key==='Escape'){e.preventDefault();closeProfileMenu(true);}});
 async function changeProfiles(action,id){if(locked())return;const previous=profile;closeProfileMenu();busy=true;render();const task=wait(action==='delete-profile'?'删除标定':'恢复标定');
  try{await api('/api/scan',{action,profile:id});await refresh();lastExport=[];}
  finally{task();busy=false;render();}
  if(previous!==profile&&state.images.length)await job('refresh',{inputs:orderedImages()});
  say(action==='delete-profile'?(profile?'已删除扫描标定，可撤销。':'已删除当前标定，请选择其他标定继续。'):'扫描标定已恢复。');
 }
 profileMenu.firstElementChild.onclick=()=>changeProfiles('delete-profile',menuProfile).catch(e=>say(e.message,true));
 restoreProfile.onclick=()=>{const id=state?.deleted_profile_order?.at(-1);if(id)changeProfiles('restore-profile',id).catch(e=>say(e.message,true));};
 const rawAccept='.arw,.dng,.cr2,.cr3,.nef,.nrw,.rw2,.orf,.pef,.srw';$('scan-raw-files').accept=rawAccept;
 const say=(text,error=false)=>status(text,error);
 const progressNode=document.createElement('div');progressNode.className='scan-task-progress';progressNode.hidden=true;progressNode.innerHTML='<span role="status" aria-live="polite"></span><progress aria-label="处理进度"></progress>';
 const waiting=new Map();let nextWait=0;
 function showProgress(){
  const entry=[...waiting.values()].at(-1),slot=container.querySelector('dialog[open] [data-scan-progress-slot]')||document.querySelector('.statusbar');
  if(slot&&progressNode.parentElement!==slot)slot.append(progressNode);progressNode.hidden=!entry;
  if(entry){progressNode.firstElementChild.textContent=entry.label;const bar=progressNode.lastElementChild;if(entry.total>0){bar.max=entry.total;bar.value=Math.min(entry.total,entry.done||0);}else bar.removeAttribute('value');}
 }
 function wait(label,total=0){const id=++nextWait;waiting.set(id,{label,total,done:0});showProgress();const end=()=>{waiting.delete(id);showProgress();};end.update=(label,done=0,total=0)=>{if(waiting.has(id)){waiting.set(id,{label,done,total});showProgress();}};return end;}
 function locked(){return busy||uploading||importing||geoBusy;}
 function settings(){return scanSettings({profile,stock,ev,size,border,geometry});}
 function current(){return scanCurrent(state,{profile,stock,ev,size,border,geometry});}
 function render(){
  if(!state)return;const assets=state.assets||{},images=state.images||[];if(!images.includes(active))active=images[0]||null;
  if(visible)onPanelsChange();
  $('scan-profiles').innerHTML=Object.values(state.profiles).map(p=>`<button class="recipe-item" data-scan-profile="${esc(p.id)}" aria-pressed="${p.id===profile}"><strong>${esc(p.name)}</strong><span>${esc(p.capture.Model)} · ${esc(p.target)} · ${p.flat_mode==='off'?'无平场':'含平场'}</span></button>`).join('');
  $('scan-stock').innerHTML=(state.stocks||['5207']).map(s=>`<option value="${esc(s)}">Kodak VISION3 ${esc(s)}</option>`).join('');$('scan-stock').value=stock;
  restoreProfile.hidden=!(state.deleted_profile_order||[]).length;restoreProfile.disabled=locked();
  const blocked=locked(),flatOn=!!state.profiles[profile]&&state.profiles[profile].flat_mode!=='off',lensOn=!!geometry.mode&&geometry.mode!=='off';
  $('scan-flat-tool').setAttribute('aria-pressed',String(flatOn));$('scan-flat-tool').title='平场矫正 · '+(flatOn?'已启用':'未启用');
  $('scan-geometry-tool').setAttribute('aria-pressed',String(lensOn));$('scan-geometry-tool').title='镜头畸变矫正 · '+(lensOn?'已启用':'未启用');
  const result=current(),output=result?.outputs?.[active],image=active&&scanFrameSource(assets[active],state.raw_contract,output,original,state.preview_context).image;
  $('scan-image').hidden=!image;$('scan-empty').hidden=!!image;$('scan-empty').textContent=images.length?'正在准备当前照片的预览…':'建立扫描标定，然后导入负片 RAW。';if(image&&$('scan-image').getAttribute('src')!==image)$('scan-image').src=image;
  $('scan-image').alt=original?'RawTherapee sRGB 取样预览':output?'当前扫描标定生成的正片':'RawTherapee sRGB 预览';
  $('scan-original').textContent=original?'查看正片':'取样预览';$('scan-count').textContent=images.length?images.length+' 张':'';
  $('scan-base-label').textContent=border?'片基已选择':'片基尚未选择';$('scan-base').textContent=selecting?'请在片边拖出取样区':'选择片基';
  $('scan-positive').disabled=blocked||!profile||!images.length||!border;$('scan-export').disabled=blocked||!result||!images.every(id=>result.outputs?.[id]);
  for(const id of ['scan-import','scan-new-roll','scan-new-profile','scan-flat-tool','scan-geometry-tool'])$(id).disabled=blocked;
  container.querySelectorAll('[data-scan-role]').forEach(b=>b.disabled=blocked);
  for(const id of ['scan-stock','scan-size','scan-ev','scan-base','scan-original'])$(id).disabled=blocked;
  $('scan-dirty').textContent=result?(images.every(id=>result.outputs?.[id])?'已应用':'已处理 '+images.filter(id=>result.outputs?.[id]).length+'/'+images.length)+' · '+result.size+'³'+(result.interpolation?' · 插值 P95 '+result.interpolation.p95_codes.toFixed(2)+' / 最大 '+result.interpolation.max_codes.toFixed(2)+' 码':''):images.length?'准备好后点击“一键正相”。':'';
  const rail=$('scan-strip-items'),existing=new Map([...rail.children].map(b=>[b.dataset.scanImage,b]));
  images.forEach((id,index)=>{const thumb=scanFrameSource(assets[id],state.raw_contract,result?.outputs?.[id],false,state.preview_context).thumbnail;
   let button=existing.get(id);if(!button){button=document.createElement('button');button.className='filmstrip-item';button.dataset.scanImage=id;button.innerHTML='<span class="scan-pending">准备中</span><span></span>';}
   button.setAttribute('aria-pressed',String(id===active));button.lastElementChild.textContent=assets[id]?.name||'RAW';
   let picture=button.firstElementChild;if(thumb){if(picture.tagName!=='IMG'){const img=document.createElement('img');img.loading='lazy';img.alt='';picture.replaceWith(img);picture=img;}if(picture.getAttribute('src')!==thumb)picture.src=thumb;}
   else if(picture.tagName==='IMG'){const pending=document.createElement('span');pending.className='scan-pending';pending.textContent='准备中';picture.replaceWith(pending);}
   if(rail.children[index]!==button)rail.insertBefore(button,rail.children[index]||null);existing.delete(id);
  });existing.forEach(button=>button.remove());
  $('scan-lut-downloads').innerHTML=result?result.files.filter(f=>/\.(cube|clf)$/.test(f.name)).map(f=>`<a href="${esc(f.url)}" download="${esc(f.name)}">${f.name.endsWith('.cube')?'保存 LUT…':'CLF'}</a>`).join(''):'';
  $('scan-export-downloads').innerHTML=lastExport.map(f=>`<a href="${esc(f.url)}" download="${esc(f.name)}">${f.name==='positives.zip'?'保存全部正片…':'保存正片…'}</a>`).join('');
  for(const id of ['scan-flat-close','scan-flat-import','scan-flat-choice','scan-flat-apply','scan-geometry-close'])$(id).disabled=blocked;
  container.querySelectorAll('[data-scan-profile]').forEach(b=>b.disabled=blocked);
  $('scan-geometry-dialog').querySelectorAll('input,select,button').forEach(e=>e.disabled=busy||uploading||importing);
  if(geoBusy)$('scan-geometry-apply').disabled=$('scan-geometry-preview').disabled=true;
  calibration?.render();showProgress();drawBorder();
 }
 let refreshPending=null;
 async function refresh(){if(refreshPending)return refreshPending;refreshPending=(async()=>{const fresh=await readScanStatus(api);if(!state){profile=fresh.active_profile;border=fresh.border;const r=fresh.results?.[fresh.active_result];if(r){stock=r.stock;ev=r.view_ev;size=r.size;}}
  state=fresh;geometry=clone(fresh.geometry||geometry);profile=fresh.active_profile;$('scan-ev').value=ev;$('scan-size').value=size;$('scan-ev-value').textContent=(Number(ev)>=0?'+':'')+Number(ev).toFixed(1)+' EV';render();if(state.warning)say(state.warning,true);})();try{return await refreshPending;}finally{refreshPending=null;}}
 async function ensureRTPreviews(){
  if(upgrading||busy||!state)return;
  const inputs=state.images.filter(id=>state.assets[id]?.preview_engine!==state.raw_contract||state.assets[id]?.preview_context!==state.preview_context);
  if(!inputs.length)return;
  upgrading=true;try{await job('prepare',{inputs});say('RawTherapee 预览已就绪。');}catch(e){say(e.message,true);}finally{upgrading=false;}
 }
 async function technicalPreview(){
  if(!active)return;
  if(!state.assets[active]?.chart_preview_url||state.assets[active]?.preview_engine!==state.raw_contract)await job('prepare',{inputs:[active],chart:true});
  original=true;render();
 }
 async function job(action,fields){
  if(busy)throw Error('请等待当前扫描任务完成。');busy=true;render();const task=wait('准备处理');
  try{let j=await api('/api/scan',{action,...clone(fields)});const id=j.id;let completed=-1,phase='';
   while(j.status==='queued'||j.status==='running'){
    task.update(j.phase||'排队中',j.completed,j.total);
    if((j.completed!==completed||j.phase!==phase)&&['positive','prepare','refresh','geometry','refit-flat'].includes(action)){completed=j.completed;phase=j.phase;await refresh();}
    await new Promise(r=>setTimeout(r,500));j=await readScanStatus(api,{action:'job',id});
   }
   if(j.status!=='complete')throw Error(j.error||'扫描任务未完成。');await refresh();return j.result;
  }finally{task();busy=false;render();}
 }
 async function upload(file,kind){
  uploading=true;render();const task=wait('导入 '+file.name);
  try{return await new Promise((resolve,reject)=>{
   const xhr=new XMLHttpRequest();xhr.open('POST','/api/scan-upload');xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-File-Name',encodeURIComponent(file.name));xhr.setRequestHeader('X-Scan-Kind',kind);
   xhr.upload.onprogress=e=>task.update('导入 '+file.name,e.loaded,e.lengthComputable?e.total:0);
   xhr.upload.onload=()=>task.update('检查导入文件');
   xhr.onload=()=>{try{const r=JSON.parse(xhr.responseText);if(!r.ok)throw Error(r.error?.message||'导入失败。');resolve(r.asset);}catch(e){reject(e);}};
   xhr.onerror=()=>reject(Error('导入中断，请检查本机连接。'));xhr.send(file);
  });}finally{task();uploading=false;await refresh();}
 }
 function point(event,surface){const r=surface.getBoundingClientRect();return [Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))];}
 function rectangle(roi){return `<rect x="${roi[0]}" y="${roi[1]}" width="${roi[2]-roi[0]}" height="${roi[3]-roi[1]}" fill="#1678ff22" stroke="#1680ff" stroke-width=".003"/>`;}
 function positionOverlay(image,overlay){const i=$(image),o=$(overlay),r=i.getBoundingClientRect(),p=o.parentElement.getBoundingClientRect();Object.assign(o.style,{left:r.left-p.left+'px',top:r.top-p.top+'px',width:r.width+'px',height:r.height+'px'});}
 function drawBorder(roi){positionOverlay('scan-image','scan-overlay');$('scan-overlay').innerHTML=roi?rectangle(roi):original&&border?.asset===active?rectangle(border.roi):'';}
 $('scan-image').onload=()=>drawBorder();window.addEventListener('resize',()=>drawBorder());
 $('scan-surface').onpointerdown=e=>{if(!selecting||!active)return;e.preventDefault();drag=point(e,$('scan-image'));$('scan-surface').setPointerCapture(e.pointerId);drawBorder(scanRectangle(drag,drag));};
 $('scan-surface').onpointermove=e=>{if(drag)drawBorder(scanRectangle(drag,point(e,$('scan-image'))));};
 $('scan-surface').onpointerup=e=>{if(!drag)return;const roi=scanRectangle(drag,point(e,$('scan-image')));drag=null;if(roi[2]-roi[0]<.002||roi[3]-roi[1]<.002){say('片基取样区过小，请重新拖选。',true);return;}border={asset:active,roi};selecting=false;render();say('片基已选，全卷使用同一次对齐。');};
 $('scan-surface').onpointercancel=()=>{drag=null;drawBorder();};
 $('scan-base').onclick=async()=>{if(!active){say('请先导入负片 RAW。',true);return;}try{await technicalPreview();selecting=true;render();}catch(e){say(e.message,true);}};
 $('scan-original').onclick=async()=>{try{selecting=false;if(original){original=false;render();}else await technicalPreview();}catch(e){say(e.message,true);}};
 let repairing=false;
 $('scan-image').onerror=async()=>{if(repairing||locked()||!active)return;repairing=true;try{if(original)await job('prepare',{inputs:[active],chart:true});else if(current())await job('positive',{...settings(),inputs:[active]});else await job('refresh',{inputs:[active]});$('scan-image').removeAttribute('src');render();}catch(e){say(e.message,true);}finally{repairing=false;}};
 $('scan-strip-items').onclick=e=>{const b=e.target.closest('[data-scan-image]');if(b){active=b.dataset.scanImage;selecting=false;render();if(original)technicalPreview().catch(e=>say(e.message,true));}};
 $('scan-strip-items').onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key)||!state?.images.length)return;e.preventDefault();const i=state.images.indexOf(active),n=Math.max(0,Math.min(state.images.length-1,i+(e.key==='ArrowRight'?1:-1)));active=state.images[n];selecting=false;render();const button=$('scan-strip-items').querySelector(`[data-scan-image="${active}"]`);button?.focus();button?.scrollIntoView({block:'nearest',inline:'nearest'});};
 $('scan-profiles').onclick=async e=>{const b=e.target.closest('[data-scan-profile]');if(!b||locked()||b.dataset.scanProfile===profile)return;try{profile=b.dataset.scanProfile;lastExport=[];await api('/api/scan',{action:'select',profile});await refresh();if(state.images.length)await job('refresh',{inputs:orderedImages()});say('已切换扫描标定。');}catch(e){say(e.message,true);}};
 function orderedImages(){return active?[active,...state.images.filter(id=>id!==active)]:state.images;}
 $('scan-stock').onchange=e=>{stock=e.target.value;lastExport=[];render();};
 $('scan-size').onchange=e=>{size=Number(e.target.value);lastExport=[];render();};
 $('scan-ev').oninput=e=>{ev=Number(e.target.value);$('scan-ev-value').textContent=(ev>=0?'+':'')+ev.toFixed(1)+' EV';};$('scan-ev').onchange=()=>{lastExport=[];render();};
 $('scan-positive').onclick=async()=>{try{lastExport=[];original=false;await job('positive',{...settings(),inputs:[active,...state.images.filter(id=>id!==active)]});original=false;render();say('正相完成 · '+state.images.length+' 张 · '+size+'³ LUT');}catch(e){say(e.message,true);}};
 $('scan-export').onclick=async()=>{try{const r=await job('export',{...settings(),inputs:state.images});lastExport=r.files.filter(f=>f.download&&(f.name==='positives.zip'||(state.images.length===1&&f.name.endsWith('.png'))));render();say('正片已导出，可以保存。');}catch(e){say(e.message,true);}};
 $('scan-import').onclick=()=>$('scan-raw-files').click();
 $('scan-new-roll').onclick=async()=>{if(busy||uploading||importing)return;try{state=await api('/api/scan',{action:'new-roll'});border=null;active=null;lastExport=[];original=false;ev=0;geometry=clone(state.geometry);$('scan-ev').value=0;$('scan-ev-value').textContent='0.0 EV';render();say('新一卷已准备好；原件、标定和 RAW 阶段仍保留。');}catch(e){say(e.message,true);}};
 $('scan-raw-files').onchange=async e=>{const files=[...e.target.files];e.target.value='';if(!files.length||importing)return;importing=true;render();const task=wait('导入 RAW');try{
  await importScanFiles(files,{maxPending:state.prepare_window||2,upload:file=>upload(file,'raw'),progress:({uploaded,completed,total})=>task.update('导入 '+uploaded+'/'+total+' · 预览 '+completed+'/'+total,uploaded+completed,total*2),prepare:async a=>{
   let j=await api('/api/scan',{action:'prepare',inputs:[a.id],roll:true});await refresh();
   while(['queued','running'].includes(j.status)){await new Promise(r=>setTimeout(r,500));j=await readScanStatus(api,{action:'job',id:j.id});}
   await refresh();if(j.status!=='complete')throw Error(j.error||'RAW 准备失败。');
  }});say('已导入 '+files.length+' 张 RAW。');
 }catch(error){say(error.message,true);}finally{task();importing=false;await refresh();}};
 calibration=calibrationTools.createScanCalibration({dialog:$('scan-calibration-dialog'),api,upload,
  prepare:id=>job('prepare',{inputs:[id],chart:true}),calibrate:async fields=>{const r=await job('calibrate',fields);profile=r.profile.id;if(state.images.length)await job('refresh',{inputs:orderedImages()});return r;},
  getState:()=>state,isBusy:locked,wait,status:say,onSaved:p=>{profile=p.id;border=null;lastExport=[];original=false;render();}});
 $('scan-new-profile').onclick=()=>calibration.open();
 function flatOptions(select,polynomial){select.innerHTML='<option value="">不使用</option>'+(polynomial?'<option value="polynomial">当前平场</option>':'')+Object.values(state.flats||{}).map(f=>`<option value="${esc(f.id)}">${esc(f.name)}</option>`).join('');}
 function flatInfo(){flatDraft=$('scan-flat-choice').value;const f=state.flats?.[flatDraft];$('scan-flat-info').textContent=f?'有效区域 '+(f.supported_fraction*100).toFixed(1)+'% · 增益 '+f.gain_range.map(x=>x.toFixed(2)).join('–'):flatDraft==='polynomial'?'使用当前标定中的平场。':'不修正平场；色卡将重新计算标定。';}
 $('scan-flat-tool').onclick=()=>{const p=state.profiles[profile];flatOptions($('scan-flat-choice'),p?.flat_mode==='polynomial'||p?.source_assets?.flat);$('scan-flat-choice').value=p?.flat_asset||(p?.source_assets?.flat?'polynomial':'');flatInfo();$('scan-flat-error').textContent='';$('scan-flat-dialog').showModal();};
 $('scan-flat-close').onclick=()=>{if(!busy&&!uploading)$('scan-flat-dialog').close();};$('scan-flat-choice').onchange=flatInfo;
 $('scan-flat-import').onclick=()=>$('scan-flat-files').click();$('scan-flat-files').accept=rawAccept;
 $('scan-flat-files').onchange=async e=>{const files=[...e.target.files];e.target.value='';try{if(!files.length)return;if(files.length>8)throw Error('最多选择8张平场。');const inputs=[];for(const f of files)inputs.push((await upload(f,'raw')).id);const r=await job('flat',{inputs});flatOptions($('scan-flat-choice'),!!state.profiles[profile]?.source_assets?.flat);$('scan-flat-choice').value=r.flat.id;flatInfo();$('scan-flat-error').textContent='';}catch(error){$('scan-flat-error').textContent=error.message;say(error.message,true);}};
 $('scan-flat-apply').onclick=async()=>{try{if(!profile)throw Error('请先建立色卡标定；新标定中可选择这份平场。');if(flatDraft==='polynomial'){$('scan-flat-dialog').close();return;}const r=await job('refit-flat',{profile,flat_asset:flatDraft||null});profile=r.profile.id;lastExport=[];$('scan-flat-dialog').close();render();if(state.images.length&&border)await job('positive',{...settings(),inputs:[active,...state.images.filter(id=>id!==active)]});say('平场与色卡标定已一致应用。');}catch(e){$('scan-flat-error').textContent=e.message;say(e.message,true);}};
 for(const id of ['scan-flat-dialog','scan-geometry-dialog'])$(id).addEventListener('cancel',e=>{if(locked())e.preventDefault();});
 let lensProfiles=[];
 function lensList(selected){const term=$('scan-lens-search').value.toLowerCase();$('scan-lens-choice').innerHTML=lensProfiles.filter(p=>p.name.toLowerCase().includes(term)).map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');if(selected)$('scan-lens-choice').value=selected;}
 function lensMode(){container.querySelectorAll('.scan-lens-profile').forEach(e=>e.hidden=$('scan-lens-mode').value!=='profile');$('scan-lens-manual').hidden=$('scan-lens-mode').value!=='manual';}
 function geoSettings(){return {...clone(geoDraft),mode:$('scan-lens-mode').value,profile_id:$('scan-lens-choice').value,focal_length:Number($('scan-lens-focal').value),crop_factor:Number($('scan-lens-crop').value),rotation:Number($('scan-rotation').value),strength:Number($('scan-lens-strength').value),auto_crop:$('scan-auto-crop').checked};}
 async function geoPreview(){
  clearTimeout(geoTimer);if(busy)return;const seq=++geoSequence;if(!active)return;const captured=geoSettings();geoBusy=true;const task=wait('更新矫正预览');$('scan-geometry-preview').disabled=$('scan-geometry-apply').disabled=true;
  try{const r=await api('/api/scan',{action:'geometry-preview',asset:active,settings:captured,result:original?null:current()?.id||null});if(seq!==geoSequence)return;geoDraft=clone(r.settings);geoShown=clone(r.settings);$('scan-geometry-image').src=r.preview.data_url;$('scan-geometry-overlay').innerHTML='';$('scan-geometry-error').textContent='';$('scan-geometry-info').textContent=(r.technical?'RawTherapee sRGB · ':'')+'畸变、旋转、裁切、缩放一次取样'+(r.settings.lens?' · '+r.settings.lens.profile:'');}
  catch(e){if(seq===geoSequence)$('scan-geometry-error').textContent=e.message;}
  finally{task();if(seq===geoSequence){geoBusy=false;$('scan-geometry-preview').disabled=false;$('scan-geometry-apply').disabled=!!$('scan-geometry-error').textContent;}}
 }
 function scheduleGeometry(){geoSequence++;$('scan-geometry-apply').disabled=true;clearTimeout(geoTimer);geoTimer=setTimeout(geoPreview,180);}
 $('scan-geometry-tool').onclick=async()=>{if(!active){say('请先导入 RAW。',true);return;}try{geoDraft=clone(geometry);const reading=wait('读取镜头配置');let r;try{r=await api('/api/scan',{action:'lenses',asset:active});}finally{reading();}lensProfiles=r.profiles;$('scan-lens-search').value='';lensList(geometry.profile_id||r.match.profile_id);$('scan-lens-mode').value=geometry.mode||'off';$('scan-lens-focal').value=geometry.focal_length||r.match.focal_length||'';$('scan-lens-crop').value=geometry.crop_factor||r.match.crop_factor||'';$('scan-lens-strength').value=geometry.strength||0;$('scan-rotation').value=geometry.rotation||0;$('scan-auto-crop').checked=geometry.auto_crop!==false;lensMode();$('scan-geometry-dialog').showModal();await geoPreview();}catch(e){say(e.message,true);}};
 $('scan-geometry-close').onclick=()=>{if(!geoBusy&&!busy){clearTimeout(geoTimer);$('scan-geometry-dialog').close();}};$('scan-lens-search').oninput=()=>lensList();$('scan-lens-mode').onchange=()=>{lensMode();scheduleGeometry();};
 for(const id of ['scan-lens-choice','scan-lens-focal','scan-lens-crop','scan-auto-crop'])$(id).onchange=scheduleGeometry;
 $('scan-lens-strength').oninput=scheduleGeometry;
 $('scan-geometry-preview').onclick=geoPreview;$('scan-rotation').onchange=()=>{geoDraft.crop=[0,0,1,1];geoPreview();};$('scan-crop-reset').onclick=()=>{geoDraft.crop=[0,0,1,1];geoPreview();};
 $('scan-geometry-image').onload=()=>positionOverlay('scan-geometry-image','scan-geometry-overlay');
 const geoSurface=$('scan-geometry-surface');geoSurface.onpointerdown=e=>{if(!geoShown||$('scan-geometry-preview').disabled)return;e.preventDefault();geoDrag=point(e,$('scan-geometry-image'));geoSurface.setPointerCapture(e.pointerId);};
 geoSurface.onpointermove=e=>{if(geoDrag)$('scan-geometry-overlay').innerHTML=rectangle(scanRectangle(geoDrag,point(e,$('scan-geometry-image'))));};
 geoSurface.onpointerup=e=>{if(!geoDrag)return;const roi=scanRectangle(geoDrag,point(e,$('scan-geometry-image')));geoDrag=null;if(roi[2]-roi[0]<.02||roi[3]-roi[1]<.02)return;geoDraft.crop=scanCrop(geoShown.crop,roi);geoPreview();};geoSurface.onpointercancel=()=>{geoDrag=null;};
 $('scan-geometry-apply').onclick=async()=>{try{if(geoBusy||$('scan-geometry-apply').disabled)return;await job('geometry',{asset:active,settings:geoSettings(),inputs:orderedImages()});geometry=clone(state.geometry);lastExport=[];$('scan-geometry-dialog').close();render();if(profile&&border)await job('positive',{...settings(),inputs:[active,...state.images.filter(id=>id!==active)]});say('综合几何矫正已应用到整卷。');}catch(e){$('scan-geometry-error').textContent=e.message;say(e.message,true);}};
 let panelPending=false;
 async function toggleSidebar(){
  if(!state||panelPending)return;closeProfileMenu();panelPending=true;
  const previous=state.panels?.sidebar_collapsed===true;
  state.panels={...state.panels,sidebar_collapsed:!previous};onPanelsChange();
  try{await api('/api/scan',{action:'panels',sidebar_collapsed:!previous});}
  catch(e){state.panels.sidebar_collapsed=previous;say(e.message,true);}
  finally{panelPending=false;onPanelsChange();}
 }
 return {toggleSidebar,sidebarCollapsed:()=>state?.panels?.sidebar_collapsed===true,sidebarPending:()=>!state||panelPending,show(){const entering=!visible;visible=true;const restored=()=>{if(!state.warning)say(state.images.length?'已恢复扫描工作区 · '+state.images.length+' 张':'选择标定，导入负片 RAW。');};if(!loading&&!state){loading=true;refresh().then(()=>{restored();return ensureRTPreviews();}).catch(e=>say(e.message,true)).finally(()=>loading=false);}else{render();if(entering&&state)restored();ensureRTPreviews();}},hide(){visible=false;closeProfileMenu();},isBusy:()=>locked()||loading||calibration.isPending()};
}
const exports={...calibrationTools,scanRectangle,scanSettings,scanCurrent,scanCrop,scanFrameSource,scanChartLayout,importScanFiles,readScanStatus,createScanWorkbench};if(typeof module==='object'&&module.exports)module.exports=exports;else Object.assign(root,exports);
})(typeof globalThis!=='undefined'?globalThis:this);
