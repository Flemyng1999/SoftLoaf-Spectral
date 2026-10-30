/* Bounded display-frame ownership. Disk/source stages live in the backend. */
function createRenditionCache({budget=256*1024*1024,maxEntries=8}={}){
 const entries=new Map();let used=0;
 return {
  get(key){const item=entries.get(key);if(!item)return null;entries.delete(key);entries.set(key,item);return item.value;},
  put(key,value,bytes){if(entries.has(key)){used-=entries.get(key).bytes;entries.delete(key);}bytes=Math.max(1,bytes);if(bytes>budget)return;
   while(entries.size&&(used+bytes>budget||entries.size>=maxEntries)){const first=entries.keys().next().value;used-=entries.get(first).bytes;entries.delete(first);}
   entries.set(key,{value,bytes});used+=bytes;
  },
  clear(){entries.clear();used=0;},
  configure(value){budget=value;while(entries.size&&used>budget){const key=entries.keys().next().value;used-=entries.get(key).bytes;entries.delete(key);}},
  bytes:()=>used,
  neighbors(ids,id){const index=ids.indexOf(id);return index<0?[]:[ids[index+1],ids[index-1]].filter(Boolean);}
 };
}
