/* One CSV contract for all imported source curves. No inferred column order. */
const spectralCSVFormats={
 transmission:{header:['wavelength_nm','value'],axis:'wavelengths_nm',channels:null,quantity:'spectral_transmittance',unit:'fraction',band:[360,730],max:8192},
 filter_transmission:{header:['wavelength_nm','C','M','Y'],axis:'wavelengths_nm',channels:['C','M','Y'],quantity:'spectral_transmittance',unit:'fraction',band:[360,730],max:8192},
 viewing:{header:['wavelength_nm','value'],axis:'wavelengths_nm',channels:null,quantity:'relative_energy_spd',unit:'relative',band:[400,700],max:8192},
 sensitivity:{header:['wavelength_nm','R','G','B'],axis:'wavelengths_nm',channels:['R','G','B'],quantity:'relative_energy_sensitivity',unit:'relative',band:[400,720],max:8192},
 characteristic:{header:['log_exposure','R','G','B'],axis:'log_exposure',channels:['R','G','B'],quantity:'status_a_density',unit:'D',max:1024},
 dyes:{header:['wavelength_nm','C','M','Y'],axis:'wavelengths_nm',channels:['C','M','Y'],quantity:'spectral_density',unit:'D',band:[400,700],max:8192},
 base:{header:['wavelength_nm','value'],axis:'wavelengths_nm',channels:null,quantity:'spectral_density',unit:'D',band:[360,730],max:8192}
};
function parseSpectralCSV(text,kind,options={}){
 const original=spectralCSVFormats[kind];if(!original)throw Error('未知曲线类型。');
 const f={...original,band:options.band||original.band,quantity:options.density||original.quantity};
 const lines=String(text).replace(/^\uFEFF/,'').trim().split(/\r?\n/);
 if(lines[0]?.trim()!==f.header.join(','))throw Error('CSV 第一行必须为：'+f.header.join(','));
 if(lines.length<3||lines.length>f.max+1)throw Error('CSV 需要 2–'+f.max+' 行数据。');
 const numeric=/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;
 const rows=lines.slice(1).map((line,index)=>{
  const cols=line.split(',').map(v=>v.trim());
  if(cols.length!==f.header.length||cols.some(v=>!numeric.test(v)||!Number.isFinite(Number(v))))throw Error('第 '+(index+2)+' 行列数或数字不正确。');
  return cols.map(Number);
 });
 const signed=kind==='dyes'&&options.signed===true&&f.quantity==='net_spectral_density';
 if(rows.some((r,i)=>(i&&r[0]<=rows[i-1][0])||(!signed&&r.slice(1).some(v=>v<0))))throw Error('横轴必须严格递增；绝对光谱量必须非负。');
 if(f.band&&(rows[0][0]>f.band[0]||rows.at(-1)[0]<f.band[1]))throw Error('需要完整覆盖 '+f.band.join('–')+' nm，不能补猜缺失波段。');
 if(kind==='characteristic'&&rows.some((r,i)=>i&&r.slice(1).some((v,c)=>options.increasing?v<rows[i-1][c+1]:v>rows[i-1][c+1])))throw Error(options.increasing?'负片或相纸密度须随曝光递增或持平。':'E100 的 Status A 密度须随曝光递减或持平。');
 if(f.quantity==='spectral_transmittance'&&rows.some(r=>r.slice(1).some(v=>v>1)))throw Error('透射率必须在 0–1 之间。');
 if(['relative_energy_spd','relative_energy_sensitivity'].includes(f.quantity)&&f.header.slice(1).some((_,c)=>!rows.some(r=>r[c+1]>0)))throw Error('光谱通道不能全为零。');
 const result={quantity:f.quantity,unit:f.unit,[f.axis]:rows.map(r=>r[0])};
 if(f.channels)result.channels=Object.fromEntries(f.channels.map((c,i)=>[c,rows.map(r=>r[i+1])]));else result.values=rows.map(r=>r[1]);
 return result;
}
function formatSpectralCSV(curve,kind){
 const f=spectralCSVFormats[kind];return f.header.join(',')+'\n'+curve[f.axis].map((x,i)=>[x,...(f.channels?f.channels.map(c=>curve.channels[c][i]):[curve.values[i]])].join(',')).join('\n')+'\n';
}
if(typeof module!=='undefined')module.exports={parseSpectralCSV,formatSpectralCSV};
