const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs/promises'),os=require('os'),path=require('path');
const {chromium}=require(process.env.SOFTLOAF_PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'../..');
async function browser(work){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'softloaf-browser-'));
 const context=await chromium.launchPersistentContext(dir,{headless:true,...(process.env.SOFTLOAF_CHROME?{executablePath:process.env.SOFTLOAF_CHROME}:{}),args:['--disk-cache-dir='+dir+'/cache']});
 try{await work(await context.newPage());}finally{await context.close();await fs.rm(dir,{recursive:true,force:true});}
}
async function setup(page,reject=false){
 await page.setContent('<html><body><label>语言<select id="ui-language"><option value="system">跟随系统</option><option value="zh-CN">简体中文</option><option value="en">English</option></select></label><button id="save" title="保存配方">保存配方</button><div id="recipe-list"><strong>保存配方</strong></div><input id="recipe-name" value="我的配方"><span id="progress">已导入 13 张 RAW。</span></body></html>');
 for(const name of ['i18n-en.js','i18n.js'])await page.addScriptTag({path:path.join(root,'design/gui-v2',name)});
 await page.evaluate(async reject=>{let language='zh-CN';window.ui=createUII18n({systemLanguage:'en-US',request:async(_path,body)=>{if(body){if(reject)throw Error('write failed');language=body.language;}return {ok:true,language};},status:message=>window.preferenceError=message});await window.ui.ready;},reject);
}
test('settings language switches live, translates dynamic updates and preserves user values',async()=>browser(async page=>{
 const errors=[];page.on('pageerror',error=>errors.push(error.message));await setup(page);
 await page.locator('body').evaluate(body=>{const brand=document.createElement('div');brand.className='brand';brand.textContent='面包光谱';body.prepend(brand);});
 await page.waitForFunction(()=>document.title==='面包光谱');
 await page.locator('#ui-language').selectOption('en');await page.waitForFunction(()=>document.documentElement.lang==='en');
 assert.equal(await page.title(),'SoftLoaf Spectral');assert.equal(await page.locator('.brand').textContent(),'SoftLoaf Spectral');
 assert.equal(await page.locator('#save').textContent(),'Save recipe');assert.equal(await page.locator('#save').getAttribute('title'),'Save recipe');
 assert.equal(await page.locator('#recipe-list strong').textContent(),'保存配方');assert.equal(await page.locator('#recipe-name').inputValue(),'我的配方');
 await page.locator('#progress').evaluate(e=>e.textContent='已导入 4 张 RAW。');await page.waitForFunction(()=>document.querySelector('#progress').textContent==='Imported 4 RAW files.');
 await page.locator('#ui-language').selectOption('zh-CN');await page.waitForFunction(()=>document.documentElement.lang==='zh-CN');
 assert.equal(await page.title(),'面包光谱');assert.equal(await page.locator('.brand').textContent(),'面包光谱');
 assert.equal(await page.locator('#save').textContent(),'保存配方');assert.equal(await page.locator('#progress').textContent(),'已导入 4 张 RAW。');assert.deepEqual(errors,[]);
}));
test('failed preference write restores the authoritative language and control',async()=>browser(async page=>{
 await setup(page,true);await page.locator('#ui-language').selectOption('en');await page.waitForFunction(()=>window.preferenceError==='write failed');
 assert.equal(await page.locator('html').getAttribute('lang'),'zh-CN');assert.equal(await page.locator('#ui-language').inputValue(),'zh-CN');assert.equal(await page.locator('#ui-language').isEnabled(),true);
}));
test('dynamic SVG labels, diagnostic units, built-in inputs and conflict messages translate and round-trip',async()=>browser(async page=>{
 await setup(page);await page.locator('#ui-language').selectOption('en');
 await page.locator('body').evaluate(body=>{
  const panel=document.createElement('section');panel.id='dynamic-panel';panel.innerHTML='<h3>片基密度谱</h3><svg><text>片基密度 D</text><text>波长 nm</text></svg><p>186 个采样点</p><p>XYZ · D65 → 色度转换 → sRGB</p><p>本机工作区未保存：另一窗口已经更新工作区；未覆盖其保存内容，请先下载当前配方。 可使用「保存配方」带走当前版本。</p><select><option>内置高光谱场景</option><option>Colour 24 色卡</option></select><span data-user-content>用户的片基密度谱</span>';body.append(panel);
 });
 await page.waitForFunction(()=>document.querySelector('#dynamic-panel h3').textContent==='Film-base density spectrum');
 assert.deepEqual(await page.locator('#dynamic-panel svg text').allTextContents(),['Film-base density (D)','Wavelength (nm)']);
 assert.equal(await page.locator('#dynamic-panel p').first().textContent(),'186 samples');
 assert.ok(!/[\u4e00-\u9fff]/u.test((await page.locator('#dynamic-panel p').allTextContents()).join(' ')));
 assert.deepEqual(await page.locator('#dynamic-panel option').allTextContents(),['Built-in hyperspectral scene','Colour 24-patch chart']);
 assert.equal(await page.locator('[data-user-content]').textContent(),'用户的片基密度谱');
 await page.locator('#progress').evaluate(e=>e.textContent='正在生成 65³ LUT…');
 await page.waitForFunction(()=>document.querySelector('#progress').textContent==='Generating 65³ LUT…');
 await page.locator('#progress').evaluate(e=>e.textContent='插值：≤2/255 100.00% · 最大 1.57/255');
 await page.waitForFunction(()=>document.querySelector('#progress').textContent==='Interpolation: 100.00% within 2/255 · Max 1.57 codes');
 await page.locator('#ui-language').selectOption('zh-CN');await page.waitForFunction(()=>document.querySelector('#dynamic-panel h3').textContent==='片基密度谱');
 assert.deepEqual(await page.locator('#dynamic-panel svg text').allTextContents(),['片基密度 D','波长 nm']);
}));
