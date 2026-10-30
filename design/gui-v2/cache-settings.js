/* Machine storage preferences; independent of recipes and photo editing. */
function createCacheSettings({onBudgets,onInvalidate,onOpen=()=>{}}){
 const dialog=document.createElement('dialog');dialog.id='cache-settings-dialog';dialog.setAttribute('aria-label','设置');
 dialog.innerHTML=`<div class="dialog-head"><h2>设置</h2><button data-cache-close class="quiet">完成</button></div>
 <label class="field">语言<select id="ui-language" aria-label="语言"><option value="system">跟随系统</option><option value="zh-CN">简体中文</option><option value="en">English</option></select></label><h3>缓存设置</h3>
 <div class="cache-summary"><strong id="cache-used">正在统计…</strong><span id="cache-free"></span></div><div class="cache-meter"><span></span></div>
 <form id="cache-policy"><label class="field">磁盘缓存<select name="disk_mode"><option value="automatic">自动</option><option value="custom">自定容量</option><option value="off">关闭</option></select></label>
 <label class="cache-inline" id="cache-custom-disk">容量上限 <span><input name="disk_gib" type="number" min="1" max="512" step="1" required> GiB</span></label>
 <p id="cache-disk-note"></p><details><summary>内存与空间预留</summary><label class="field">内存预算<select name="memory_mode"><option value="automatic">自动</option><option value="custom">自定</option></select></label>
 <label class="cache-inline" id="cache-custom-memory">内存上限 <span><input name="memory_mib" type="number" min="256" max="8192" step="128" required> MiB</span></label>
 <label class="cache-inline">磁盘预留 <span><input name="reserve_gib" type="number" min="0" max="256" step="1" placeholder="自动"> GiB</span></label><p id="cache-memory-note"></p></details></form>
 <div class="cache-location"><span class="small muted">缓存位置</span><div id="cache-path"></div><div class="cache-buttons"><button id="cache-location-button">更改位置…</button><button id="cache-default-location" class="quiet">恢复默认位置</button></div></div>
 <div class="cache-protected"><span>保留数据</span><strong id="cache-protected-size"></strong><p>RAW 开发结果与浮点预览保留，不随缓存清理。</p></div>
 <div class="cache-buttons"><button id="cache-clear">清理显示缓存</button><button id="cache-memory">释放空闲内存</button><button id="cache-refresh" class="quiet">刷新</button><button id="cache-old" class="quiet" hidden>清理旧位置</button></div>
 <p id="cache-state" role="status" aria-live="polite"></p><progress id="cache-progress" hidden></progress><button id="cache-cancel" hidden>停止迁移</button>
 <form id="cache-location-form" hidden><label class="field">T7 上的父文件夹<input id="cache-location-input" type="text" placeholder="/Volumes/T7 Touch" required></label><p>将在其中建立 SoftLoaf Spectral Cache 文件夹。</p><button type="submit">复制并切换</button><button type="button" id="cache-location-back" class="quiet">取消</button></form>`;
 document.body.append(dialog);const $=id=>dialog.querySelector('#'+id),form=$('cache-policy');let state=null,poll=null,updating=false,errorMessage='';
 const bytes=n=>n==null?'—':n<1024**3?(n/1024**2).toFixed(0)+' MiB':(n/1024**3).toFixed(1)+' GiB';
 async function request(path,body){const response=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const result=await response.json();if(!response.ok||!result.ok)throw Error(result.error?.message||'设置未完成');return result;}
 function render(populate=false){
  if(!state)return;const {settings:s,limits:l,inventory:i,job:j}=state,running=j.status==='running';
  $('cache-used').textContent='显示缓存 '+bytes((i.display_bytes||0)+(i.session_bytes||0));$('cache-free').textContent='磁盘可用 '+bytes(state.free_bytes);
  dialog.querySelector('.cache-meter span').style.width=Math.min(100,100*(i.display_bytes||0)/l.disk_bytes)+'%';
  if(populate){for(const key of ['disk_mode','disk_gib','memory_mode','memory_mib'])form.elements[key].value=s[key];form.elements.reserve_gib.value=s.reserve_gib??'';}
  $('cache-custom-disk').hidden=form.elements.disk_mode.value!=='custom';$('cache-custom-memory').hidden=form.elements.memory_mode.value!=='custom';
  $('cache-disk-note').textContent=s.disk_mode==='off'?'关闭持久缓存；当前会话仍使用临时预览。':'上限 '+bytes(l.disk_bytes)+' · 预留 '+bytes(l.reserve_bytes);
  $('cache-memory-note').textContent='预算 '+bytes(l.memory_bytes)+'，用于图像、显示缓存及分块处理；不包括 RAW 解码器与系统占用。';
  $('cache-path').textContent=state.location;$('cache-protected-size').textContent=bytes((i.retained_raw_bytes||0)+(i.retained_preview_bytes||0));
  for(const element of [...form.elements,...dialog.querySelectorAll('.cache-buttons button')])element.disabled=running||updating;
  $('cache-old').hidden=!s.old_locations?.length;$('cache-default-location').disabled=running||state.location===state.default_location;
  $('cache-progress').hidden=!running||j.action!=='move';$('cache-progress').max=j.total_bytes||1;$('cache-progress').value=j.completed_bytes||0;
  $('cache-cancel').hidden=!running||j.action!=='move';
  $('cache-state').textContent=errorMessage|| (running?(j.action==='move'?'正在复制并校验…':'正在整理…'):j.status==='failed'?j.error:j.status==='cancelled'?'已停止，原位置保持不变。':j.status==='complete'?'已更新。':'');
 }
 async function refresh(populate=false){try{const previous=state;state=await request('/api/cache-settings');render(populate);onBudgets(state.limits);if(previous?.job.status==='running'&&state.job.status==='complete'&&['clear','move','memory'].includes(state.job.action))onInvalidate();}catch(e){errorMessage=e.message;$('cache-state').textContent=e.message;}}
 async function operation(action,extra={}){errorMessage='';try{state=await request('/api/cache-maintenance',{action,...extra});render();if(['clear','memory'].includes(action))onInvalidate();}catch(e){errorMessage=e.message;$('cache-state').textContent=e.message;}}
 form.onchange=async()=>{
  if(!form.reportValidity()||updating)return;errorMessage='';updating=true;render();
  try{const data={disk_mode:form.elements.disk_mode.value,disk_gib:Number(form.elements.disk_gib.value),memory_mode:form.elements.memory_mode.value,memory_mib:Number(form.elements.memory_mib.value),reserve_gib:form.elements.reserve_gib.value===''?null:Number(form.elements.reserve_gib.value)};
   state=await request('/api/cache-settings',{settings:data});onBudgets(state.limits);onInvalidate();
  }catch(e){errorMessage=e.message;$('cache-state').textContent=e.message;}finally{updating=false;render(true);}
 };
 form.onsubmit=e=>e.preventDefault();
 dialog.querySelector('[data-cache-close]').onclick=()=>dialog.close();dialog.onclose=()=>{clearInterval(poll);poll=null;};
 $('cache-clear').onclick=()=>operation('clear');$('cache-memory').onclick=()=>operation('memory');$('cache-refresh').onclick=()=>operation('refresh');$('cache-old').onclick=()=>operation('old');$('cache-cancel').onclick=()=>operation('cancel');
 function location(value){$('cache-location-input').value=value||'';$('cache-location-form').hidden=false;$('cache-location-input').focus();}
 $('cache-location-button').onclick=()=>{if(window.webkit?.messageHandlers?.cacheFolder)window.webkit.messageHandlers.cacheFolder.postMessage({});else location('/Volumes/T7 Touch');};
 window.softloafCacheLocationSelection=value=>{if(value)location(value);};
 $('cache-location-back').onclick=()=>{$('cache-location-form').hidden=true;};
 $('cache-location-form').onsubmit=async e=>{e.preventDefault();if(!$('cache-location-input').reportValidity())return;await operation('move',{location:$('cache-location-input').value.replace(/\/$/,'')+'/SoftLoaf Spectral Cache'});$('cache-location-form').hidden=true;};
 $('cache-default-location').onclick=()=>operation('move',{location:null});
 return {async open(){if(dialog.open)return;onOpen();dialog.showModal();await refresh(true);if(state?.job.status!=='running')await operation('refresh');if(dialog.open)poll=setInterval(()=>refresh(false),700);}};
}
