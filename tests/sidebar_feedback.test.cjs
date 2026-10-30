const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');

// Small DOM fixture: exercises keyed row reconciliation, not CSS or rendering.
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.textContent='';}
 append(...els){for(const e of els)this.insertBefore(e,null);}
 insertBefore(el,other){el.remove();el.parent=this;const index=this.children.indexOf(other);this.children.splice(index<0?this.children.length:index,0,el);}
 remove(){if(this.parent){this.parent.children.splice(this.parent.children.indexOf(this),1);this.parent=null;}}
 setAttribute(key,value){this.attributes[key]=String(value);}
 querySelector(tag){return this.children.find(e=>e.tagName===tag)||null;}
}

test('sidebar updates selection and names without replacing focused or hovered rows',()=>{
 const start=html.indexOf('function syncSidebarButtons(');
 assert.ok(start>=0,'stable sidebar reconciliation is required');
 const context=vm.createContext({document:{createElement:tag=>new Element(tag)}});
 vm.runInContext(html.slice(start,html.indexOf('function renderLibrary(',start)),context);
 const list=new Element('div'),rows=[{id:'a',label:'第一份',detail:'反转片'},{id:'b',label:'第二份',detail:'APD'}];
 context.syncSidebarButtons(list,rows,'a','document');
 const [a,b]=list.children;
 assert.equal(a.attributes['aria-pressed'],'true');assert.equal(a.tabIndex,0);
 assert.equal(b.tabIndex,-1);
 context.syncSidebarButtons(list,[{...rows[0],label:'改名 <配方>'},rows[1]],'b','document');
 assert.equal(list.children[0],a);assert.equal(list.children[1],b);
 assert.equal(a.querySelector('strong').textContent,'改名 <配方>');
 assert.equal(a.attributes['aria-pressed'],'false');assert.equal(b.attributes['aria-pressed'],'true');
 assert.equal(b.tabIndex,0);assert.equal(a.tabIndex,-1);
});

test('changing a process removes only missing sidebar nodes and retains shared nodes',()=>{
 const start=html.indexOf('function syncSidebarButtons(');assert.ok(start>=0);
 const context=vm.createContext({document:{createElement:tag=>new Element(tag)}});
 vm.runInContext(html.slice(start,html.indexOf('function renderLibrary(',start)),context);
 const list=new Element('div');
 context.syncSidebarButtons(list,[{id:'light',label:'光源'},{id:'film',label:'胶片'},{id:'view',label:'观看'}],'film','node');
 const film=list.children[1],removed=list.children[2];
 context.syncSidebarButtons(list,[{id:'light',label:'光源'},{id:'film',label:'胶片'},{id:'apd',label:'密度'},{id:'display',label:'显示'}],'film','node');
 assert.equal(list.children[1],film);assert.equal(removed.parent,null);
 assert.deepEqual(list.children.map(e=>e.dataset.node),['light','film','apd','display']);
});
