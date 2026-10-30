/* Plot-only clipping. Source samples and CSV exports remain unchanged. */
function spectralDisplayBand(quantity){return quantity==='APD_spectral_weights'?[400,750]:[400,700];}
function spectralDisplaySamples(axis,values,low=400,high=700){
  const xs=[],ys=[];
  for(let i=0;i<axis.length;i++){
    if(i&&axis[i-1]<low&&axis[i]>low){const t=(low-axis[i-1])/(axis[i]-axis[i-1]);xs.push(low);ys.push(values[i-1]+t*(values[i]-values[i-1]));}
    if(axis[i]>=low&&axis[i]<=high){xs.push(axis[i]);ys.push(values[i]);}
    if(i&&axis[i-1]<high&&axis[i]>high){const t=(high-axis[i-1])/(axis[i]-axis[i-1]);xs.push(high);ys.push(values[i-1]+t*(values[i]-values[i-1]));}
  }
  return {xs,values:ys};
}
// Extra vendor detail belongs only to its unchanged builtin curve. Replacements
// (including a persisted custom material) always plot their own CSV samples.
function spectralPlotData(value,reference,native,axis,channels,key){
  const useNative=!!native&&!!reference&&key(value)===key(native.reference_curve||reference);
  return {native:useNative,series:channels.map(channel=>({channel,
    xs:useNative?(native.channels[channel][axis]||native.channels[channel].wavelengths_nm):value[axis],
    values:useNative?native.channels[channel].values:(value.channels?.[channel]||value.values)}))};
}
/* Source curves are replaced only by validated CSV imports. All graphs are read-only. */
function spectralReferenceMaterial(s){
 const custom=s.active.film.custom_material,reference=s.assets[s.active.film.stock];
 if(!custom&&s.active.film.stock==='5207'&&s.assets.legacy_5207)return s.assets.legacy_5207;
 if(custom&&reference&&custom.provenance?.material_version!==reference.provenance?.material_version)return custom;
 return reference||custom||s.assets[s.active.route==='slide'?'E100':'5207'];
}
function spectralMaterialProvenance(material,reference){
 if(!reference.provenance)return;
 const p=JSON.parse(JSON.stringify(reference.provenance)),overrides={};p.substitutions={...p.substitutions};p.sources={...p.sources};
 for(const role of ['sensitivity','characteristic','dyes','base']){
  const file=material[role]?.import_file;if(!file)continue;
  overrides[role]={...file};delete p.substitutions[role];
  if(role==='dyes')delete p.substitutions.dye_tails;
  if(role==='sensitivity'){delete p.sources.processed_sensitivity;delete p.sensitivity_common_scale;}
  if(role==='characteristic'){delete p.original_status_m_curve_point_max_error_D;p.characteristic_processing='User CSV source samples; raw density metric retained; source monotonicity checked, not silently projected';}
 }
 p.user_overrides=overrides;
 if(Object.keys(overrides).length){const labels={sensitivity:'感光',characteristic:'特性曲线',dyes:'染料',base:'片基',exposure_anchor:'曝光标定',dye_tails:'染料尾部'};
  p.summary=p.process==='E-6'?'E-6 反转片参考；CSV 替换：'+Object.keys(overrides).map(k=>labels[k]).join('、')+'；相对曝光标定，非实拍校准。':'实验模型；CSV 替换：'+Object.keys(overrides).map(k=>labels[k]).join('、')+'；5207 暂代：'+Object.keys(p.substitutions).map(k=>labels[k]||k).join('、')+'。';}
 material.provenance=p;
}
function spectralPaperReference(s){
 const custom=s.active.printing?.custom_material,id=custom?.provenance?.stock_id;
 if(custom)return s.assets['paper:'+id]||custom;
 return s.active.printing?.pipeline==='spectral-v2'?(s.assets.paper_v2||s.assets.paper):s.assets.paper;
}
function spectralPaperPlotKey(s){const id=s.active.printing?.custom_material?.provenance?.stock_id;return id?'paper:'+id:'paper';}
function createSpectralEditor(hooks) {
  const el = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const drafts = new Map();
  const kinds = {
    viewing: {label: '观看光源', channels: ['SPD'], quantity: 'relative_energy_spd', unit: 'relative', axis: 'wavelengths_nm', xLabel: '波长 nm', yLabel: '相对能量', band: [400,700], result: 'view'},
    sensitivity: {label: '感光光谱', channels: ['R', 'G', 'B'], quantity: 'relative_energy_sensitivity', unit: 'relative', axis: 'wavelengths_nm', xLabel: '波长 nm', yLabel: '相对能量响应', result: 'film'},
    characteristic: {label: '胶片特性曲线', channels: ['R', 'G', 'B'], quantity: 'status_a_density', unit: 'D', axis: 'log_exposure', xLabel: 'log₁₀ 相对曝光', yLabel: 'Status A 密度 D', result: 'film'},
    dyes: {label: '染料光谱', channels: ['C', 'M', 'Y'], quantity: 'spectral_density', unit: 'D', axis: 'wavelengths_nm', xLabel: '波长 nm', yLabel: '光谱密度 D', result: 'film'}
  };
  kinds.enlarger={label:'放大光谱',channels:['SPD'],quantity:'relative_energy_spd',unit:'relative',axis:'wavelengths_nm',xLabel:'波长 nm',yLabel:'相对能量',result:'enlarger',band:[360,730]};
  kinds.filters={label:'CMY 滤色谱',channels:['C','M','Y'],quantity:'spectral_density',unit:'D',axis:'wavelengths_nm',xLabel:'波长 nm',yLabel:'吸收密度 D',result:'filter',band:[360,730]};
  kinds.base={label:'片基密度谱',channels:['BASE'],quantity:'spectral_density',unit:'D',axis:'wavelengths_nm',xLabel:'波长 nm',yLabel:'片基密度 D',result:'film'};
  for(const k of ['sensitivity','characteristic','dyes','base'])kinds['paper_'+k]={...kinds[k],label:'相纸'+kinds[k].label.replace('胶片',''),result:'paper'};
  kinds.paper_base.label='相纸白底密度谱';kinds.paper_base.yLabel='最低反射密度 D';
  for(const role of ['heat','lens'])kinds[role]={label:role==='heat'?'隔热玻璃透射谱':'镜头透射谱',channels:['T'],quantity:'spectral_transmittance',unit:'fraction',axis:'wavelengths_nm',xLabel:'波长 nm',yLabel:'透射率',result:'enlarger',band:[360,730]};
  const colors = {T:'#397fae',BASE:'#8c83b8', SPD: '#397fae', R: '#c95753', G: '#32866a', B: '#537bc0', C: '#228eaa', M: '#a56aa2', Y: '#ad8a29'};
  let current = null, opened = false, target = 'viewing', channel = 'SPD', point = 0, applying = false, importing = false;
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const bareTarget=()=>target==='enlarger'?'viewing':target==='filters'?(state().active.printing?.pipeline==='spectral-v2'?'filter_transmission':'dyes'):['heat','lens'].includes(target)?'transmission':target.replace(/^paper_/,''),paperTarget=()=>target.startsWith('paper_');
  const originalFilm=s=>spectralReferenceMaterial(s);
  const spec = () => {const value={...kinds[target]};if(target==='filters'&&state().active.printing?.pipeline==='spectral-v2'){value.quantity='spectral_transmittance';value.unit='fraction';value.yLabel='透射率';}if(value.axis==='wavelengths_nm')value.band=target==='paper_sensitivity'?[400,750]:[400,700];if(bareTarget()==='characteristic'&&(paperTarget()||state().active.route!=='slide')){value.quantity=paperTarget()?'status_a_density':'status_m_density';value.yLabel=paperTarget()?'Status A 密度 D':'Status M 密度 D';}return value;};
  const curve = () => ['heat','lens'].includes(target)?current[target]:target==='enlarger'?current.printlight:target==='filters'?current.filters:target === 'viewing' ? current.light : paperTarget()?current.paper[bareTarget()]:current.material[target];
  const xs = () => curve()[spec().axis];
  const ys = (c = channel) => target === 'viewing'||target==='enlarger'||target==='base'||['heat','lens'].includes(target)||target==='paper_base' ? curve().values : curve().channels[c];
  const record = () => target==='paper_base'?current.paper.base:['heat','lens'].includes(target)?current[target]:target==='enlarger'?current.printlight:target==='filters'?current.filters:target === 'viewing' ? current.light : paperTarget()?current.paper:current.material;
  const dirty = () => !!current?.changed.size;
  const state = () => hooks.getState();
  const plotData=()=>{const s=state(),reference=paperTarget()?spectralPaperReference(s)?.[bareTarget()]:originalFilm(s)?.[target];
    return spectralPlotData(curve(),reference,s.assets.material_plot_sources?.[paperTarget()?spectralPaperPlotKey(s):s.active.film.stock==='5207'&&!s.active.film.custom_material?'legacy_5207':s.active.film.stock]?.[bareTarget()],spec().axis,spec().channels,hooks.key);};

  function makeDraft(s) {
    const material = clone(s.active.film.custom_material || originalFilm(s));
    const matching=s.result?.version?.recipe_id===s.active.id&&s.result?.version?.revision===s.active.revision;
    const lamp=matching?s.result?.current?.nodes?.enlarger?.details?.light:null;
    const printlight=clone(s.active.printing?.custom_spd||(lamp?{name:(s.active.printing.temperature_k||3200)+' K 放大光',source:'Planck model; current applied recipe',quantity:'relative_energy_spd',unit:'relative',wavelengths_nm:lamp.wavelengths_nm,values:lamp.series[0].values}:(s.active.printing?.pipeline==='spectral-v2'?s.assets.printing_light_v2:s.assets.printing_light))||{});
    const filters=clone(s.active.printing?.custom_filters||(s.active.printing?.pipeline==='spectral-v2'?s.assets.printing_optics?.filters:s.assets.printing_filters)||{});
    const paper=clone(s.active.printing?.custom_material||spectralPaperReference(s)||{});
    if(paper.characteristic&&!paper.base){const x=s.assets.printing_light?.wavelengths_nm||[360,730];paper.base={quantity:'spectral_density',unit:'D',wavelengths_nm:clone(x),values:x.map(()=>Math.min(...Object.values(paper.characteristic.channels).map(v=>v[0]))),name:'旧配方常数底密度',source:'Legacy finite-band paper model'};}
    const optical={};for(const role of ['heat','lens']){const selected=s.active.printing?.optics?.[role];optical[role]=clone(selected==='custom'?s.active.printing.optics['custom_'+role]:s.assets.printing_optics?.[role]||{});if(selected==='none'&&optical[role].values){optical[role].values=optical[role].values.map(()=>1);optical[role].name='未启用 · 透射率 1';}}
    const light = clone(s.active.viewing.custom_spd || s.assets.viewing_lights[s.active.viewing.illuminant]);
    return {id: s.active.id, material, ...optical, printlight, filters, originalPrintlight:clone(printlight), originalFilters:clone(filters), printingKey:hooks.key(s.active.printing||{}), paper, paperKey:hooks.key(s.active.printing?.custom_material||spectralPaperReference(s)||{}), originalPaper:clone(paper), light, originalMaterial: clone(material), originalLight: clone(light),
      materialKey: hooks.key(s.active.film.custom_material || originalFilm(s)), lightKey: hooks.key(s.active.viewing.custom_spd || s.assets.viewing_lights[s.active.viewing.illuminant]), changed: new Set()};
  }
  function open(nextTarget = target) {
    const s = state();
    if(applying||importing){hooks.message('正在读取或校验光谱，请等当前操作完成。');return false;}
    if (!s.active || !s.assets || !s.assets[s.active.film.stock]) {
      hooks.message('当前材料没有可用的光谱数据。'); return false;
    }
    if(nextTarget==='enlarger'&&s.active.printing?.light!=='custom'&&(s.result?.version?.recipe_id!==s.active.id||s.result?.version?.revision!==s.active.revision)){hooks.message('请等当前配方计算完成，再查看对应的放大光谱。');return false;}
    const saved=drafts.get(s.active.id);current = saved?.changed.size?saved:makeDraft(s);
    drafts.set(s.active.id, current);
    target = kinds[nextTarget] ? nextTarget : 'viewing'; channel = spec().channels[0]; point = Math.floor(xs().length / 2);
    opened = true; el('spectral-editor').hidden = false; el('spectrum-error').textContent = '';
    hooks.selectNode(spec().result); render();return true;
  }
  function touch() {
    current.changed.add(target);
    const r = record();
    if (target === 'viewing' && r.name === current.originalLight.name) r.name += ' · 自定义';
    if (target !== 'viewing' && r.name === (paperTarget()?current.originalPaper:current.originalMaterial).name) r.name = (paperTarget()?current.originalPaper.name:state().active.film.stock)+' · 自定义材料';
    el('spectrum-error').textContent = ''; render();
  }
  function setFocusedValue(id, value) { if (document.activeElement !== el(id)) el(id).value = value; }
  function render() {
    const s = state();
    const usable = !!s.assets && !!s.assets[s.active?.film?.stock];
    el('spectral-open').disabled = !usable; el('view-spectrum-open').disabled = !usable;
    el('spectral-open').textContent = drafts.get(s.active?.id)?.changed.size ? '材料与光谱 · 待应用' : '材料与光谱…';
    if (opened && current?.id !== s.active?.id) opened = false;
    el('spectral-editor').hidden = !opened;
    el('workspace').classList.toggle('spectral-mode', opened);
    el('diagnostics').hidden = opened;
    if (!opened || !current) return;
    const materialKey=hooks.key(s.active.film.custom_material||originalFilm(s)),lightKey=hooks.key(s.active.viewing.custom_spd||s.assets.viewing_lights[s.active.viewing.illuminant]);
    if(!dirty()&&(current.printingKey!==hooks.key(s.active.printing||{})||current.materialKey!==materialKey||current.lightKey!==lightKey||current.paperKey!==hooks.key(s.active.printing?.custom_material||spectralPaperReference(s)||{}))){current=makeDraft(s);drafts.set(s.active.id,current);}
    const meta = spec();el('spectrum-source-title').textContent=meta.label; point = Math.max(0, Math.min(point, xs().length - 1));
    el('spectrum-target').innerHTML=Object.entries(kinds).filter(([k])=>(k.startsWith('paper_')||['enlarger','filters'].includes(k))?s.active.route==='print':['heat','lens'].includes(k)?s.active.route==='print'&&s.active.printing?.pipeline==='spectral-v2':k==='base'?s.active.route!=='slide':true).map(([k,v])=>`<option value="${k}">${esc(v.label)}</option>`).join('');el('spectrum-target').value = target;el('spectrum-meta-title').textContent='名称与来源 · '+(record().name||'未命名');
    el('spectrum-legend').innerHTML = meta.channels.map(c => `<span style="color:${colors[c]}">${c}</span>`).join('');
    const native=s.assets.material_plot_sources?.[paperTarget()?spectralPaperPlotKey(s):s.active.film.stock==='5207'&&!s.active.film.custom_material?'legacy_5207':s.active.film.stock]?.[bareTarget()];
    el('spectrum-sampling').textContent=plotData().native?`${native.sampling_kind==='manufacturer_chart_digitization'?'原厂图表采样':'原厂矢量曲线'}${spec().axis==='wavelengths_nm'?' · 曝光计算 '+native.calculation_step_nm+' nm':''}`:`${xs().length} 个${['heat','lens','filters','paper_base'].includes(target)&&!curve().import_file?'计算':''}采样点`;
    setFocusedValue('spectrum-name', record().name || ''); setFocusedValue('spectrum-source', record().source || '');
    el('spectrum-draft-state').textContent = importing ? '正在读取数据…' : applying ? '正在校验并拟合…' : dirty() ? '待应用 · 当前结果尚未更新' : '未修改';
    el('spectrum-apply').disabled = !dirty() || applying; el('spectrum-import').disabled = applying;
    el('spectrum-description').textContent = ['heat','lens'].includes(target)?'导入光路透射率 0–1。复合光源已包含此组件时，请在放大机设置中旁路，避免重复相乘。':target==='filters'&&s.active.printing?.pipeline==='spectral-v2'?'导入 CMY 二向色滤片透射率 0–1；控制量采用部分插入模型，不是相纸染料密度。':target==='paper_base'?'相纸最低光谱密度 D，须与 Status A 最低密度兼容。内置纸白为声明的模型假设，并非实测白纸。':target === 'viewing'
      ? '改变灯的光谱形状。观看光按白 Y 归一化；亮度用右侧观看增益调整。'
      : target === 'sensitivity'
      ? '导入三个感光通道。沿用参考通道尺度，不会把你改过的幅度自动归一化。'
      : bareTarget() === 'characteristic'
      ? '横轴是 log₁₀ 曝光，纵轴保留原始测量密度。反转片随曝光递减；负片和相纸随曝光递增。应用时重拟合。'
      : target==='dyes'&&s.active.route!=='slide'
      ? '导入扣除 D-min 的 CMY 净密度，可保留负值；与片基合成后的绝对密度必须非负。'
      : '导入 CMY 染料的光谱密度。应用时重拟合中性曲线；无法匹配的组合会被拒绝。';
    el('spectrum-format').textContent='UTF-8 CSV；固定表头：'+spectralCSVFormats[bareTarget()].header.join(',')+'。每行一个样本，单位 '+meta.unit+'；不接受 JSON、分号或省略表头。';
    draw();
    const node = s.result?.current?.nodes?.[meta.result];
    el('spectrum-result-name').textContent = `${meta.result === 'view' ? '观看光谱' : meta.result==='paper'?'相纸反射率':['enlarger','filter'].includes(meta.result)?'相纸入射曝光':'胶片透射率'} · 只读`;
    hooks.graph('spectrum-result', node?.output, s.result?.baseline?.nodes?.[meta.result]?.output, 'var(--amber)');
    el('spectrum-result-status').textContent = dirty() ? '待应用；当前配方尚未改变。' : s.previewStatus;
    [...el('spectral-editor').querySelectorAll('input,select,button'),...el('spectral-inspector').querySelectorAll('input,select,button')].forEach(control=>{if(control.id!=='spectrum-close')control.disabled=applying||importing||(control.id==='spectrum-apply'&&!dirty());});
  }

  function geometry() {
    const visible=(x,y)=>spec().band?spectralDisplaySamples(x,y,...spec().band).values:y;
    const values=plotData().series.flatMap(s=>visible(s.xs,s.values));
    const width = Math.max(250, el('spectrum-plot').clientWidth), height = 300;
    const left = 53, right = 16, top = 33, bottom = 39;
    const xmin=spec().band?.[0]??xs()[0],xmax=spec().band?.[1]??xs()[xs().length-1],ymin=Math.min(0,...values)*1.15,ymax = Math.max(1e-8, ...values) * 1.15;
    return {width, height, left, right, top, bottom, xmin, xmax, ymin, ymax,
      x: v => left + (v-xmin)/(xmax-xmin)*(width-left-right),
      y: v => top + (ymax-v)/(ymax-ymin)*(height-top-bottom)};
  }
  function draw() {
    if (!opened) return;
    const g = geometry();
    let svg = `<svg viewBox="0 0 ${g.width} ${g.height}" role="img" aria-label="${spec().label}，全部通道，只读"><title>${spec().label}</title><text x="${g.left}" y="15">${spec().yLabel}</text><defs><clipPath id="spectrum-source-clip"><rect x="${g.left}" y="${g.top}" width="${g.width-g.left-g.right}" height="${g.height-g.top-g.bottom}"/></clipPath></defs>`;
    for (const fraction of [0, .5, 1]) {
      const value = g.ymin+fraction*(g.ymax-g.ymin), y = g.y(value);
      svg += `<path class="grid" d="M${g.left} ${y}H${g.width-g.right}"/><text x="${g.left-7}" y="${y+4}" text-anchor="end">${value === 0 ? '0' : Number(value.toPrecision(3))}</text>`;
    }
    if(g.ymin<0)svg+=`<path class="grid" d="M${g.left} ${g.y(0)}H${g.width-g.right}"/>`;
    for (const fraction of [0, 1/3, 2/3, 1]) {
      const value = g.xmin + fraction*(g.xmax-g.xmin), x = g.x(value);
      svg += `<path class="grid" d="M${x} ${g.top}V${g.height-g.bottom}"/><text x="${x}" y="${g.height-20}" text-anchor="middle">${bareTarget() === 'characteristic' ? value.toFixed(2) : Math.round(value)}</text>`;
    }
    for (const series of plotData().series) {
      const path = series.values.map((v,i) => `${i?'L':'M'}${g.x(series.xs[i]).toFixed(2)} ${g.y(v).toFixed(2)}`).join(' ');
      svg += `<path data-curve="${series.channel}" d="${path}" clip-path="url(#spectrum-source-clip)" fill="none" stroke="${colors[series.channel]}" stroke-width="2"/>`;
    }
    svg += `<text x="${g.left+(g.width-g.left-g.right)/2}" y="${g.height-3}" text-anchor="middle">${spec().xLabel}</text></svg>`;
    el('spectrum-plot').innerHTML = svg;
  }
  el('spectrum-target').onchange = event => {target=event.target.value;channel=spec().channels[0];point=Math.floor(xs().length/2);hooks.selectNode(spec().result);render();};
  for (const id of ['spectrum-name','spectrum-source']) el(id).oninput = event => {record()[id==='spectrum-name'?'name':'source']=event.target.value.trim();touch();};
  el('spectrum-reset').onclick = () => {if(target==='viewing')current.light=clone(current.originalLight);else if(target==='enlarger')current.printlight=clone(state().active.printing?.pipeline==='spectral-v2'?state().assets.printing_light_v2:state().assets.printing_light);else if(target==='filters')current.filters=clone(state().active.printing?.pipeline==='spectral-v2'?state().assets.printing_optics.filters:state().assets.printing_filters);else if(['heat','lens'].includes(target))current[target]=clone(state().assets.printing_optics[target]);else if(paperTarget())current.paper[bareTarget()]=clone(spectralPaperReference(state())[bareTarget()]||current.originalPaper[bareTarget()]);else{current.material[target]=clone(originalFilm(state())[target]);spectralMaterialProvenance(current.material,originalFilm(state()));}touch();};
  el('spectrum-reload').onclick = () => {const s=state();current=makeDraft(s);drafts.set(s.active.id,current);point=Math.min(point,xs().length-1);el('spectrum-error').textContent='';render();};
  el('spectrum-close').onclick = () => {opened=false;render();};
  el('spectrum-export').onclick = () => {
    const value=curve(),blob=new Blob([formatSpectralCSV(value,bareTarget())],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=target+'-template.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  };
  el('spectrum-import').onclick = () => el('spectrum-file').click();
  el('spectrum-file').onchange = async event => {
    const file=event.target.files[0];if(!file)return;
    const importDraft=current,importTarget=target;importing=true;render();
    try{
      if(file.size>400000)throw Error('单个文件请控制在 400 KB 以内。');
      if(!/\.csv$/i.test(file.name))throw Error('曲线只接受 .csv 文件，请下载对应模板。');
      const raw=await file.arrayBuffer(),text=new TextDecoder('utf-8',{fatal:true}).decode(raw),digest=await crypto.subtle.digest('SHA-256',raw),importFile={name:file.name,sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')};
      if(!opened||applying||current!==importDraft||target!==importTarget||state().active.id!==importDraft.id)throw Error('导入时目标配方或曲线已切换，请重新选择文件。');
      const kind=bareTarget(),negative=state().active.route!=='slide',options={};if((target==='viewing'&&state().active.route==='print')||['enlarger','filters','heat','lens'].includes(target))options.band=[360,730];if(kind==='characteristic'&&(negative||paperTarget())){options.density=paperTarget()?'status_a_density':'status_m_density';options.increasing=true;}if((negative&&kind==='dyes')||paperTarget()&&kind!=='characteristic')options.band=[360,730];if(target==='dyes'&&negative){options.density='net_spectral_density';options.signed=true;}const value=parseSpectralCSV(text,kind,options);
      if(['heat','lens'].includes(target))current[target]={...value,name:file.name,source:'用户 CSV：'+file.name,import_file:importFile};else if(target==='enlarger')current.printlight={...value,name:file.name,source:'用户 CSV：'+file.name,import_file:importFile};else if(target==='filters')current.filters={...value,name:file.name,source:'用户 CSV：'+file.name,import_file:importFile};else if(target==='viewing')current.light={...value,name:file.name,source:'用户 CSV：'+file.name,import_file:importFile};
      else{const material=paperTarget()?current.paper:current.material;material[bareTarget()]={...value,source:'用户 CSV：'+file.name,import_file:importFile};material.name=(paperTarget()?current.originalPaper.name:state().active.film.stock)+' · CSV 材料';material.source='参考材料与 CSV：'+file.name;if(paperTarget()&&material.provenance){const p=material.provenance;p.user_overrides={...p.user_overrides,[bareTarget()]:importFile};p.summary='相纸参考 + 自定义 CSV；原厂条件不验证替换曲线。';}else if(!paperTarget())spectralMaterialProvenance(material,originalFilm(state()));}
      current.changed.add(target);
      channel=spec().channels[0];point=Math.floor(xs().length/2);el('spectrum-error').textContent='';hooks.selectNode(spec().result);render();
    }catch(error){el('spectrum-error').textContent=error.message;hooks.message('数据未导入：'+error.message,true);}
    finally{importing=false;event.target.value='';render();}
  };
  el('spectrum-apply').onclick = async () => {
    if(applying||importing||!dirty())return;applying=true;render();
    try{
      await hooks.awaitEdits();const s=state();
      if(s.active.id!==current.id)throw Error('当前配方已切换，请重新打开对应光谱草稿。');
      const materialChanged=[...current.changed].some(k=>!['viewing','enlarger','filters','heat','lens'].includes(k)&&!k.startsWith('paper_')),printerChanged=['enlarger','filters','heat','lens'].some(k=>current.changed.has(k)),paperChanged=[...current.changed].some(k=>k.startsWith('paper_')),lightChanged=current.changed.has('viewing');
      if((materialChanged&&hooks.key(s.active.film.custom_material||originalFilm(s))!==current.materialKey)||(lightChanged&&hooks.key(s.active.viewing.custom_spd||s.assets.viewing_lights[s.active.viewing.illuminant])!==current.lightKey))throw Error('这份配方的源数据已在别处更改。可先导出草稿，再重新载入配方。');
      if(printerChanged&&hooks.key(s.active.printing||{})!==current.printingKey)throw Error('放大设置已更改，请重新载入。');
      if(paperChanged&&hooks.key(s.active.printing?.custom_material||spectralPaperReference(s)||{})!==current.paperKey)throw Error('相纸材料已在别处更改，请重新载入。');
      if(document.activeElement===el('spectrum-name'))record().name=el('spectrum-name').value.trim();
      if(document.activeElement===el('spectrum-source'))record().source=el('spectrum-source').value.trim();
      const next=clone(s.active);next.revision++;
      if(lightChanged){next.viewing.illuminant='custom';next.viewing.custom_spd=clone(current.light);}
      if(materialChanged)next.film.custom_material=clone(current.material);
      if(paperChanged)next.printing.custom_material=clone(current.paper);
      if(current.changed.has('enlarger')){next.printing.light='custom';next.printing.custom_spd=clone(current.printlight);}
      if(current.changed.has('filters'))next.printing.custom_filters=clone(current.filters);
      for(const role of ['heat','lens'])if(current.changed.has(role)){next.printing.optics[role]='custom';next.printing.optics['custom_'+role]=clone(current[role]);}
      const validated=await hooks.validate(next);
      hooks.commit(validated,s);current=makeDraft(state());drafts.set(current.id,current);
      hooks.message('光谱已应用到配方；预览和下次生成的 LUT 使用相同数据。');
    }catch(error){el('spectrum-error').textContent=error.message;hooks.message('光谱未应用：'+error.message,true);}
    finally{applying=false;render();}
  };
  new ResizeObserver(()=>{if(opened){draw();renderResultOnly();}}).observe(el('spectrum-plot'));
  function renderResultOnly(){const s=state(),node=s.result?.current?.nodes?.[spec().result];hooks.graph('spectrum-result',node?.output,s.result?.baseline?.nodes?.[spec().result]?.output,'var(--amber)');}
  return {open,render,close:()=>{opened=false;render();},target:()=>target,pendingTargets:()=>[...(drafts.get(state().active?.id)?.changed||[])],hasPending:()=>importing||applying||!!drafts.get(state().active?.id)?.changed.size};
}
