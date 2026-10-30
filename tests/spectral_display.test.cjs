const {readFileSync}=require('node:fs');const vm=require('node:vm');const test=require('node:test');const assert=require('node:assert/strict');
const source=readFileSync(new URL('../design/gui-v2/spectral-editor.js','file://'+__filename),'utf8');const c=vm.createContext({});vm.runInContext(source,c);
test('spectral display clips and interpolates boundaries without changing source data',()=>{
 const x=[380,420,680,720],y=[100,1,2,100];
 assert.equal(typeof c.spectralDisplaySamples,'function');
 const visible=c.spectralDisplaySamples(x,y,400,700);
 assert.deepEqual(Array.from(visible.xs),[400,420,680,700]);
 assert.deepEqual(Array.from(visible.values),[50.5,1,2,51]);
 assert.deepEqual(x,[380,420,680,720]);assert.deepEqual(y,[100,1,2,100]);
});
test('paper sensitivity can use 400–750 nm without inventing missing samples',()=>{
 assert.equal(typeof c.spectralDisplaySamples,'function');
 const visible=c.spectralDisplaySamples([360,400,700,730],[0,.1,1,.2],400,750);
 assert.deepEqual(Array.from(visible.xs),[400,700,730]);
});
test('APD display includes the red tail to 730 nm on an axis ending at 750',()=>{
 assert.deepEqual(Array.from(c.spectralDisplayBand('APD_spectral_weights')),[400,750]);
 assert.deepEqual(Array.from(c.spectralDisplayBand('cie1931_xyz_matching_functions')),[400,700]);
 const x=[360,400,700,720,730],y=[0,.1,1,.4,.2];
 const visible=c.spectralDisplaySamples(x,y,...c.spectralDisplayBand('APD_spectral_weights'));
 assert.deepEqual(Array.from(visible.xs),[400,700,720,730]);
 assert.deepEqual(x,[360,400,700,720,730]);
});

test('source chart has a static legend with no channel selection or faded channels',()=>{
 const html=readFileSync(new URL('../design/gui-v2/index.html','file://'+__filename),'utf8');
 assert.doesNotMatch(html,/查看通道|data-spectrum-channel/);
 assert.doesNotMatch(source,/data-spectrum-channel|c===channel\?2\.2|<circle/);
 assert.match(html,/id="spectrum-legend"/);
});

test('native plot detail is used only for the unchanged builtin and never for custom CSV',()=>{
 const builtin={wavelengths_nm:[400,550,700],channels:{R:[0,1,0],G:[0,2,0],B:[0,3,0]}};
 const native={channels:Object.fromEntries(['R','G','B'].map(channel=>[channel,{wavelengths_nm:[401,450,550,650,699],values:[0,.3,2,.2,0]}]))};
 const plot=value=>c.spectralPlotData(value,builtin,native,'wavelengths_nm',['R','G','B'],JSON.stringify);
 const detailed=plot(builtin);
 assert.equal(detailed.native,true);assert.equal(detailed.series.length,3);
 assert.deepEqual(Array.from(detailed.series[0].xs),native.channels.R.wavelengths_nm);
 const custom=JSON.parse(JSON.stringify(builtin));custom.channels.R=[0,5,0];
 const replaced=plot(custom);
 assert.equal(replaced.native,false);
 assert.deepEqual(Array.from(replaced.series[0].values),[0,5,0]);
 assert.deepEqual(Array.from(replaced.series[0].xs),[400,550,700]);
 assert.equal(c.spectralPlotData(builtin,builtin,undefined,'wavelengths_nm',['R','G','B'],JSON.stringify).native,false);
});
