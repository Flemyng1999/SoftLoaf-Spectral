const test=require('node:test'),assert=require('node:assert/strict');
const {effectiveLanguage,translateText}=require('../design/gui-v2/i18n.js');
test('language resolution is explicit and preserves user or material names',()=>{
 assert.equal(effectiveLanguage('system','zh-Hant'),'zh-CN');assert.equal(effectiveLanguage('system','en-GB'),'en');
 assert.equal(effectiveLanguage('zh-CN','en-US'),'zh-CN');
 assert.equal(translateText('保存配方','en'),'Save recipe');
 assert.equal(translateText('面包光谱','en'),'SoftLoaf Spectral');
 assert.equal(translateText('面包光谱','zh-CN'),'面包光谱');
 assert.equal(translateText('  已导入 13 张 RAW。\n','en'),'  Imported 13 RAW files.\n');
 assert.equal(translateText('Kodak VISION3 5207','en'),'Kodak VISION3 5207');
 assert.equal(translateText('My 用户配方','en'),'My 用户配方');
 assert.equal(translateText('保存配方','zh-CN'),'保存配方');
 assert.equal(translateText(' \n  ','en'),' \n  ');
});
test('English covers spectrum plots, conversion diagnostics and reported workspace conflicts',()=>{
 for(const text of ['片基密度谱','片基密度 D','波长 nm','转换过程','XYZ 到显示 RGB','矩阵变换','范围限制','输入 XYZ','内置高光谱场景','Colour 24 色卡','186 个采样点','正在处理 sample.NEF 原始尺寸 · 冻结配方 r2…','186 个计算采样点','取样：22 · neutral 5 (.70 D)','相对 XYZ D65 · 相对 Y','本机工作区未保存：另一窗口已经更新工作区；未覆盖其保存内容，请先下载当前配方。 可使用「保存配方」带走当前版本。']){
  const translated=translateText(text,'en');assert.ok(!/[\u4e00-\u9fff]/u.test(translated),translated);assert.equal(translateText(text,'zh-CN'),text);
 }
 assert.equal(translateText('用户照片.NEF','en'),'用户照片.NEF');
 assert.equal(translateText('正在处理 原片.NEF 原始尺寸 · 冻结配方 r2…','en'),'Processing 原片.NEF at original size · Frozen recipe r2…');
});
test('LUT progress and frozen-export failures translate while retaining grid and revision',()=>{
 assert.equal(translateText('正在生成 65³ LUT…','en'),'Generating 65³ LUT…');
 assert.equal(translateText('正在生成 LUT…','en'),'Generating LUT…');
 assert.equal(translateText('插值：≤2/255 100.00% · 最大 1.57/255','en'),'Interpolation: 100.00% within 2/255 · Max 1.57 codes');
 assert.equal(translateText('冻结 r3 生成失败，请查看实际原因。','en'),'Recipe r3 generation failed; see the error details.');
});
