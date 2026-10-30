const test=require('node:test'),assert=require('node:assert/strict');
const {parseSpectralCSV,formatSpectralCSV}=require('../design/gui-v2/spectral-csv.js');
test('CSV requires exact headers and preserves native samples',()=>{
 const curve=parseSpectralCSV('\ufeffwavelength_nm,value\r\n400,1\r\n550,2e-1\r\n700,0\r\n','viewing');
 assert.deepEqual(curve.wavelengths_nm,[400,550,700]);assert.deepEqual(curve.values,[1,.2,0]);
 assert.deepEqual(parseSpectralCSV(formatSpectralCSV(curve,'viewing'),'viewing'),curve);
});
test('CSV rejects JSON, missing headers, missing columns and guessed delimiters',()=>{
 for(const text of ['{"values":[1,2]}','400,1\n700,1','wavelength_nm,SPD\n400,1\n700,1','wavelength_nm;value\n400;1\n700;1','wavelength_nm,value\n400,\n700,1'])assert.throws(()=>parseSpectralCSV(text,'viewing'));
});
test('CSV refuses nonfinite, unordered, missing-band and invalid reversal curves',()=>{
 for(const text of ['wavelength_nm,value\n400,NaN\n700,1','wavelength_nm,value\n700,1\n400,2','wavelength_nm,value\n410,1\n700,2','wavelength_nm,value\n400,-1\n700,1'])assert.throws(()=>parseSpectralCSV(text,'viewing'));
 assert.throws(()=>parseSpectralCSV('log_exposure,R,G,B\n-2,0,1,1\n0,1,0,0','characteristic'));
});
test('material channels have a fixed named order and units',()=>{
 const curve=parseSpectralCSV('wavelength_nm,R,G,B\n400,1,2,3\n720,4,5,6','sensitivity');
 assert.deepEqual(curve.channels,{R:[1,4],G:[2,5],B:[3,6]});assert.equal(curve.quantity,'relative_energy_sensitivity');
 assert.throws(()=>parseSpectralCSV('wavelength_nm,B,G,R\n400,1,2,3\n720,4,5,6','sensitivity'));
});

test('negative and paper curves keep their declared increasing density metric',()=>{
 const m=parseSpectralCSV('log_exposure,R,G,B\n-2,.2,.5,.8\n0,1,1.5,1.8','characteristic',{density:'status_m_density',increasing:true});
 assert.equal(m.quantity,'status_m_density');
 assert.throws(()=>parseSpectralCSV('log_exposure,R,G,B\n-2,1,1,1\n0,0,0,0','characteristic',{density:'status_m_density',increasing:true}));
 assert.throws(()=>parseSpectralCSV('wavelength_nm,C,M,Y\n400,1,1,1\n700,1,1,1','dyes',{band:[360,730]}));
});

test('only explicitly net film dye density accepts signed increments',()=>{
 const text='wavelength_nm,C,M,Y\n360,1,-.02,.1\n730,.1,.2,-.004';
 const options={band:[360,730],density:'net_spectral_density',signed:true};
 const curve=parseSpectralCSV(text,'dyes',options);
 assert.equal(curve.quantity,'net_spectral_density');assert.equal(curve.channels.M[0],-.02);
 assert.deepEqual(parseSpectralCSV(formatSpectralCSV(curve,'dyes'),'dyes',options),curve);
 assert.throws(()=>parseSpectralCSV(text,'dyes',{band:[360,730]}));
 assert.throws(()=>parseSpectralCSV(text,'dyes',{density:'net_spectral_density'}));
 assert.throws(()=>parseSpectralCSV('wavelength_nm,R,G,B\n400,1,-.02,.1\n720,.1,.2,.1','sensitivity',options));
});

test('optical CSVs declare transmittance fractions and permit fully blocking paths',()=>{
 const t=parseSpectralCSV('wavelength_nm,C,M,Y\n360,0,.8,1\n730,0,.2,.9','filter_transmission');
 assert.equal(t.quantity,'spectral_transmittance');assert.equal(t.unit,'fraction');
 assert.deepEqual(parseSpectralCSV(formatSpectralCSV(t,'filter_transmission'),'filter_transmission'),t);
 assert.throws(()=>parseSpectralCSV('wavelength_nm,value\n360,1.01\n730,.9','transmission'));
 assert.throws(()=>parseSpectralCSV('wavelength_nm,value\n400,.8\n700,.9','transmission'));
 assert.deepEqual(parseSpectralCSV('wavelength_nm,value\n360,0\n730,0','base').values,[0,0]);
});
