(function(root){
'use strict';
const english=typeof module==='object'&&module.exports?require('./i18n-en.js'):root.SoftloafEnglish;
function effectiveLanguage(choice,system='en'){return choice==='system'?(/^zh/i.test(system)?'zh-CN':'en'):choice;}
const formats=[
 [/^正在生成(?: (\d+)³)? LUT…$/,grid=>`Generating ${grid?grid+'³ ':''}LUT…`],
 [/^冻结 r(\d+) 生成失败，请查看实际原因。$/,rev=>`Recipe r${rev} generation failed; see the error details.`],
 [/^插值：≤2\/255 ([\d.]+)% · 最大 ([\d.]+)(?: 码|\/255)$/,(percent,max)=>`Interpolation: ${percent}% within 2/255 · Max ${max} codes`],

 [/^正在处理 (.+) 原始尺寸 · 冻结配方 r(\d+)…$/,(name,rev)=>`Processing ${name} at original size · Frozen recipe r${rev}…`],
 [/^正在排队 · (\d+) 张$/,n=>`Queued · ${n} photos`],
 [/^(等待导出|正在导出) (\d+) \/ (\d+) · (.+)$/,(state,n,total,name)=>`${state==='等待导出'?'Queued':'Exporting'} ${n} / ${total} · ${name}`],
 [/^(已停止；)?已完成 (\d+) \/ (\d+) 张(?:，(\d+) 张失败)?$/,(stopped,n,total,failed)=>`${stopped?'Stopped; ':''}Completed ${n} / ${total} photos${failed?`, ${failed} failed`:''}`],
 [/^导入 (\d+) \/ (\d+)$/,(n,total)=>`Import ${n} / ${total}`],
 [/^已导入 (\d+) 张$/,n=>`Imported ${n} photos`],
 [/^(.+) · 白平衡回退$/,name=>`${name} · White-balance fallback`],
 [/^有效区域 ([\d.]+)% · 增益 (.+)$/,(percent,gain)=>`Valid area ${percent}% · Gain ${gain}`],
 [/^平场矫正 · (.+)$/,state=>`Flat-field correction · ${translateText(state,'en')}`],
 [/^镜头畸变矫正 · (.+)$/,state=>`Lens distortion correction · ${translateText(state,'en')}`],

 [/^· (.+)$/,v=>`· ${translateText(v,'en')}`],
 [/^执行矩阵 (\d+)$/,n=>`Applied matrix ${n}`],
 [/^([RGB])：(.+)$/,(c,part)=>`${c}: ${translateText(part,'en')}`],
 [/^([\d,.]+) 点 LUT$/,n=>`${n}-point LUT`],
 [/^温度 ([\d.]+) K$/,n=>`Temperature ${n} K`],

 [/^(\d+) 个(计算|源)?采样点$/,(n,kind)=>`${n} ${kind==='计算'?'calculation ':kind==='源'?'source ':''}samples`],
 [/^取样：(.+)$/,v=>`Sample: ${translateText(v,'en')}`],
 [/^取样点：(\d+)% \/ (\d+)%$/,(x,y)=>`Sample point: ${x}% / ${y}%`],
 [/^(\d+) \/ (\d+) 张$/,(n,total)=>`${n} / ${total} photos`],
 [/^曝光计算 ([\d.]+) nm$/,n=>`Exposure calculation at ${n} nm`],
 [/^标准日光光谱 · (.+)$/,v=>`Daylight spectrum · ${v}`],
 [/^([CMY]) 滤色(密度|控制)$/,(c,kind)=>`${c} filter ${kind==='密度'?'density':'control'}`],
 [/^([\d.]+) K 放大光$/,n=>`${n} K enlarger light`],
 [/^趾部查表 · (\d+) 点$/,n=>`Toe lookup table · ${n} points`],
 [/^当前取样的逐步计算 · (.+)$/,v=>`Selected sample calculation · ${v}`],
 [/^已应用配方 r(\d+) 的当前取样结果。$/,n=>`Applied the current sample result for recipe r${n}.`],
 [/^(.+) · 已生成并读回验证 · 配方 r(\d+) · (\d+) × (\d+)$/,(name,rev,w,h)=>`${name} · Generated and verified · Recipe r${rev} · ${w} × ${h}`],
 [/^本机工作区未保存：(.+) 可使用「保存配方」带走当前版本。$/,v=>`Workspace not saved: ${translateText(v,'en')} Use “Save recipe” to keep the current version.`],
 [/^UTF-8 CSV；固定表头：(.+)。每行一个样本，单位 (.+)；不接受 JSON、分号或省略表头。$/,(headers,unit)=>`UTF-8 CSV; required header: ${headers}. One sample per row; units: ${unit}. JSON, semicolons and missing headers are not accepted.`],
 [/^当前节点 · (.+)：(.+)$/,(node,note)=>`Current node · ${translateText(node,'en')}: ${translateText(note,'en')}`],
 [/^更新中；暂显示 (.+) 的上次结果。$/,v=>`Updating; showing the previous result for ${v}.`],
 [/^照片模式(.+)$/,v=>`Photo mode ${translateText(v,'en')}`],
 [/^(.+) · 输入曝光 ([+−\-\d.]+ EV)$/,(name,ev)=>`${translateText(name,'en')} · Input exposure ${ev}`],
 [/^(.+) · (计算中…|计算失败，请重试|上次结果|待应用)$/,(name,state)=>`${translateText(name,'en')} · ${translateText(state,'en')}`],

 [/^名称与来源 · (.+)$/,v=>`Name and source · ${translateText(v,'en')}`],
 [/^(\d \/ 2) · 点击 (CC\d+)$/,(a,b)=>`${a} · Click ${b}`],
 [/^色卡编号 (.+)$/,v=>`Target ID ${v}`],
 [/^色卡 (.+) · 24 个色块 · (.*)$/,(a,b)=>`Target ${a} · 24 patches · ${b}`],
 [/^(.+) · 已有测量资料$/,v=>`${v} · Measurements available`],
 [/^显示缓存 (.+)$/,v=>`Display cache ${v}`],
 [/^磁盘可用 (.+)$/,v=>`Free disk space ${v}`],
 [/^上限 (.+) · 预留 (.+)$/,(a,b)=>`Limit ${a} · Reserve ${b}`],
 [/^预算 (.+)，用于图像、显示缓存及分块处理；不包括 RAW 解码器与系统占用。$/,v=>`Budget ${v} for images, display caches and block processing; excludes RAW decoders and system use.`],
 [/^已导入 (\d+) 张 RAW。$/,n=>`Imported ${n} RAW files.`],
 [/^已恢复扫描工作区 · (\d+) 张$/,n=>`Scan workspace restored · ${n} photos`],
 [/^正相完成 · (\d+) 张 · (\d+)³ LUT$/,(n,s)=>`Conversion complete · ${n} photos · ${s}³ LUT`],
 [/^(\d+) 张$/,n=>`${n} photos`],
 [/^导入 (\d+)\/(\d+) · 预览 (\d+)\/(\d+)$/,(a,b,c,d)=>`Import ${a}/${b} · Preview ${c}/${d}`],
 [/^矫正预览 (\d+)\/(\d+) · (.+)$/,(a,b,n)=>`Corrected preview ${a}/${b} · ${n}`],
 [/^(.+) · (已启用|未启用)$/,(a,b)=>`${translateText(a,'en')} · ${translateText(b,'en')}`],
 [/^已应用 · (.+)$/,v=>`Applied · ${v.replace('插值 P95','Interpolation P95').replace('最大','Max').replace('码','codes')}`],
 [/^曝光补偿\s*([+−\-\d.]+ EV)$/,v=>`Exposure compensation ${v}`],
 [/^导入 (.+)$/,v=>`Import ${translateText(v,'en')}`],
 [/^生成 (\d+)³ LUT$/,s=>`Generating ${s}³ LUT`]
];
function translateText(source,language){
 if(language!=='en'||typeof source!=='string')return source;
 const key=source.trim();if(!key)return source;let value=Object.hasOwn(english,key)?english[key]:key;
 if(value===key)for(const [pattern,format] of formats){const match=key.match(pattern);if(match){value=format(...match.slice(1));break;}}
 if(value===key&&key.includes('\n'))value=key.split('\n').map(part=>translateText(part,'en')).join('\n');
 if(value===key&&key.includes('　'))value=key.split('　').map(part=>translateText(part,'en')).join('　');
 if(value===key&&key.includes(' → '))value=key.split(' → ').map(part=>translateText(part,'en')).join(' → ');
 if(value===key&&key.includes(' · '))value=key.split(' · ').map(part=>translateText(part,'en')).join(' · ');
 return source.slice(0,source.length-source.trimStart().length)+value+source.slice(source.trimEnd().length);
}
function createUII18n({request,status=()=>{},document:doc=root.document,systemLanguage=root.navigator?.language||'en'}){
 let choice='system',language=effectiveLanguage(choice,systemLanguage),scheduled=false,pending=false,notified=null;
 const texts=new WeakMap(),attributes=new WeakMap();
 const excluded='script,style,pre,code,input,textarea,[data-user-content],#recipe-select option,#recipe-list strong,#photo-recipe-list strong,#scan-profiles strong,.filmstrip-item span';
 const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;queueMicrotask(()=>{scheduled=false;apply();});}});
 function apply(){
  observer.disconnect();
  try{
   doc.documentElement.lang=language;
   doc.title=language==='en'?'SoftLoaf Spectral':'面包光谱';
   if(notified!==language){
    root.webkit?.messageHandlers?.uiLanguage?.postMessage(language);
    root.chrome?.webview?.postMessage({kind:'language',value:language});
    notified=language;
   }
   const walker=doc.createTreeWalker(doc.body,NodeFilter.SHOW_TEXT);let node;
   while((node=walker.nextNode())){if(!node.parentElement||node.parentElement.closest(excluded))continue;
    let saved=texts.get(node);if(!saved||node.nodeValue!==saved.rendered)saved={source:node.nodeValue};
    saved.rendered=translateText(saved.source,language);texts.set(node,saved);if(node.nodeValue!==saved.rendered)node.nodeValue=saved.rendered;
   }
   for(const element of doc.body.querySelectorAll('[title],[aria-label],[placeholder],[alt],optgroup[label]')){
    if(element.closest('[data-user-content]'))continue;
    const saved=attributes.get(element)||{};
    for(const name of ['title','aria-label','placeholder','alt',...(element.tagName==='OPTGROUP'?['label']:[])]){if(!element.hasAttribute(name))continue;const value=element.getAttribute(name);let entry=saved[name];if(!entry||value!==entry.rendered)entry={source:value};entry.rendered=translateText(entry.source,language);saved[name]=entry;if(value!==entry.rendered)element.setAttribute(name,entry.rendered);}
    attributes.set(element,saved);
   }
   const select=doc.getElementById('ui-language');if(select){select.value=choice;select.disabled=pending;}
  }finally{observer.observe(doc.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder','alt','label']});}
 }
 async function setLanguage(value){
  if(pending)return;pending=true;apply();
  try{const state=await request('/api/preferences',{language:value});choice=state.language;language=effectiveLanguage(choice,systemLanguage);}
  catch(error){status(error.message,true);}
  finally{pending=false;apply();}
 }
 doc.getElementById('ui-language').onchange=e=>setLanguage(e.target.value);
 const ready=request('/api/preferences').then(state=>{choice=state.language;language=effectiveLanguage(choice,systemLanguage);if(state.warning)status(state.warning,true);apply();}).catch(error=>status(error.message,true));
 apply();return {ready,setLanguage,language:()=>language,choice:()=>choice,apply,close:()=>observer.disconnect()};
}
const exports={effectiveLanguage,translateText,createUII18n};if(typeof module==='object'&&module.exports)module.exports=exports;else Object.assign(root,exports);
})(typeof globalThis==='object'?globalThis:this);
