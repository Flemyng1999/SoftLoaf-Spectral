const {readFileSync}=require('node:fs');const vm=require('node:vm');const test=require('node:test');const assert=require('node:assert/strict');
const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
const source=html.slice(html.indexOf('function renderDisplayProcess('),html.indexOf('function renderDiagnosticSamples('));
const c=vm.createContext({esc:String,bootstrap:{capabilities:{display_views:[{id:'Default',label:'OpenDRT Default'}]}}});vm.runInContext(source,c);
test('APD process renders its own input, formula, toe table and XYZ output',()=>{
 const rendered=c.renderDisplayProcess({pipeline:'APD_to_XYZ',label:'APD → XYZ D65',reference:'ACES v1.2',
  input:[.1,.2,.3],input_label:'APD · 绝对密度 D',output:[.4,.5,.6],output_label:'XYZ · D65 · 相对 Y',
  steps:[{kind:'formula',title:'CID → 对数曝光',input:[.1,.2,.3],output:[-.4,-.5,-.6],formula:'log₁₀ E',table:[[.1,-1],[.2,0]],table_labels:['CID','log₁₀ E'],branches:['趾部查表','趾部查表','直线段']}]});
 assert.match(rendered,/APD · 绝对密度 D/);assert.match(rendered,/XYZ · D65 · 相对 Y/);
 assert.match(rendered,/CID → 对数曝光/);assert.match(rendered,/趾部查表 · 2 点/);assert.match(rendered,/B：直线段/);
 assert.doesNotMatch(rendered,/undefined|编码 RGB|OpenDRT/);
});
test('display process still renders XYZ input and encoded display RGB',()=>{
 const rendered=c.renderDisplayProcess({view:'Default',target:'Display P3',input_xyz_d65:[.1,.2,.3],output:[.4,.5,.6],steps:[]});
 assert.match(rendered,/XYZ · D65 → OpenDRT Default → Display P3/);
 assert.match(rendered,/Display P3 · D65 · 编码 RGB/);assert.doesNotMatch(rendered,/undefined|APD/);
});
