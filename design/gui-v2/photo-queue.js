(function(root){
'use strict';
function photoInputAccept(capabilities={}){
 return ['.png','.jpg','.jpeg',...(capabilities.raw_supported?capabilities.raw_extensions||[]:[])].join(',');
}
function createPhotoQueue(inputs=[],saved=null,defaultId=null){
 const items=new Map(inputs.map(item=>[item.id,item]));
 const order=[...new Set([...(saved?.order||[]),...inputs.map(item=>item.id)])].filter(id=>items.has(id));
 const exposures={};for(const [id,v] of Object.entries(saved?.exposures||{}))if(items.has(id)&&Number.isFinite(v)&&v>=-4&&v<=4)exposures[id]=v;
 const panels={recipes_collapsed:saved?.panels?.recipes_collapsed===true,filmstrip_collapsed:saved?.panels?.filmstrip_collapsed===true};
 let selected=items.has(saved?.active_input_id)?saved.active_input_id:items.has(defaultId)?defaultId:order[0]||null;
 const current=()=>selected?{id:selected,exposure_ev:exposures[selected]||0}:null;
 const sources=()=>order.map(id=>items.get(id));
 return {
  current,sources,
  panels(){return {...panels};},
  togglePanel(name){if(!Object.hasOwn(panels,name))throw Error('未知面板。');panels[name]=!panels[name];return {...panels};},
  upsert(item){if(!items.has(item.id))order.push(item.id);items.set(item.id,item);},
  select(id){if(!items.has(id))throw Error('照片不在当前工作区。');selected=id;return current();},
  setExposure(v){if(!selected||!Number.isFinite(v)||v < -4||v > 4)throw Error('输入曝光范围为 −4 到 +4 EV。');exposures[selected]=v;return current();},
  stripItems(){const imported=sources().filter(i=>i.kind.startsWith('imported_'));return imported.length?imported:sources().filter(i=>i.kind==='rgb_photo');},
  batchInputs(){return sources().filter(i=>i.kind.startsWith('imported_')).map(i=>({id:i.id,exposure_ev:exposures[i.id]||0}));},
  snapshot(){return {order:[...order],active_input_id:selected,exposures:{...exposures},panels:{...panels}};}
 };
}
if(typeof module!=='undefined'&&module.exports)module.exports={createPhotoQueue,photoInputAccept};
else {root.createPhotoQueue=createPhotoQueue;root.photoInputAccept=photoInputAccept;}
})(typeof globalThis!=='undefined'?globalThis:this);
