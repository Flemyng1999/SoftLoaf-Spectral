"""Reflectance -> 5207 -> APD/ADX reference checks; no RAW/workspace changes.

Cineon neutral aims are comparison points, not film-stock fitting constraints.
The actual model uses Status M for material fitting and APD only at output.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import colour
import PyOpenColorIO as ocio
from spectral_app.model import SpectralModel,stage
from spectral_app.storage import DataStorage
from spectral_app.scanning.rendering import amounts_to_display
from spectral_lut.native import NativeCore
from spectral_lut.reference import quadrature_widths
from spectral_lut.negative import integrate_density,adx_codes,adx_to_aces
from spectral_lut.display import ACES_VIEW,TARGETS

CINEON_AIMS={'Dmin':95,'black_2percent':180,'digital_LAD':445,'gray_18percent':470,'white_90percent':685}


def evaluate(model,reflectance):
    material=model.negative
    wave=model.source_wavelengths
    kernel=material.sensitivity*model.scene_light(5500)[:,None]*quadrature_widths(wave)[:,None]/material.denominators
    exposure,amounts,transmission=stage(reflectance,kernel,material.axis,material.amounts,material.dyes,material.base,core=model.core)
    apd=integrate_density(transmission,model.apd_weights)
    base=integrate_density(10**-material.base,model.apd_weights)
    ten=adx_codes(apd,base,bits=10);sixteen=adx_codes(apd,base)
    aces=adx_to_aces(sixteen)
    official=(ten/1023).astype(np.float32)
    graph=ocio.GroupTransform()
    graph.appendTransform(ocio.BuiltinTransform(style='ADX10_to_ACES2065-1'))
    graph.appendTransform(ocio.DisplayViewTransform(src='ACES2065-1',display=TARGETS['sRGB']['aces_display'],view=TARGETS['sRGB']['aces_view']))
    model.display_manager.config.getProcessor(graph).getOptimizedCPUProcessor(ocio.OPTIMIZATION_LOSSLESS).applyRGB(official)
    rendered=amounts_to_display(model,material,amounts)
    return {'relative_film_exposure':exposure.tolist(),'Status_M':integrate_density(transmission,model.status_m_weights).tolist(),
        'APD_net':(apd-base).tolist(),'ADX10_float':ten.tolist(),'ADX10_integer':np.floor(ten+.5).tolist(),
        'ADX16_float':sixteen.tolist(),'ACES2065_1':aces.tolist(),
        'ACES_Y':(aces@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ[1]).tolist(),
        'encoded_sRGB_ACES2':rendered.tolist(),
        'ADX16_minus_16_ADX10_max':float(np.max(np.abs(sixteen-ten*16))),
        'official_ADX10_and_ACES2_max_codes':float(np.max(np.abs(rendered-official))*255)}


def run(output):
    storage=DataStorage.configured();storage.validate();storage.activate_temporary_directory()
    output=storage.directory(output)
    root=Path(__file__).resolve().parents[1]
    model=SpectralModel(root/'local/film-color-slides/hyperspectral-demo',root/'local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip',output/'model',core=NativeCore())
    wave=model.source_wavelengths
    levels=np.array([0,.01,.02,.18,.9,1.])
    neutral=evaluate(model,np.repeat(levels[:,None],len(wave),axis=1))
    stops=np.arange(-6,4.001,.125);ramp=evaluate(model,np.repeat((.18*2**stops)[:,None],len(wave),axis=1))
    # The extended ramp above 100% is an exposure-equivalent radiance factor,
    # explicitly not a passive reflectance. The neutral and chart cases are <=1.
    rows=[]
    for i,level in enumerate(levels):
        aim={0:95,.02:180,.18:470,.9:685}.get(float(level))
        rows.append({'reflectance':float(level),'Cineon_aim':aim,'ADX10':neutral['ADX10_float'][i],
            'aim_difference_codes':None if aim is None else (np.asarray(neutral['ADX10_float'][i])-aim).tolist(),
            'ACES_Y':neutral['ACES_Y'][i]})
    chart=colour.SDS_COLOURCHECKERS['BabelColor Average'];names=list(chart)
    spectra=np.array([np.interp(wave,sd.wavelengths,sd.values) for sd in chart.values()])
    measured=evaluate(model,spectra)
    source_light=model.scene_light(5500);cmfs=colour.MSDS_CMFS['CIE 1931 2 Degree Standard Observer'].copy().align(colour.SpectralShape(wave[0],wave[-1],wave[1]-wave[0]))
    y=source_light*cmfs.values[:,1]*quadrature_widths(wave);scene_Y=spectra@y/y.sum()
    details={'schema':'softloaf.reflectance-cineon-check/1','film':model.negative.metadata,
        'scene':{'illuminant':'CIE daylight / 5500 K','reflectance':'spectral fraction 0..1','film_reference':'flat 18% reflector','exposure_ev':0,
                 'wavelengths_nm':wave.tolist(),'observer':'none for film exposure; CIE 1931 2 degree only for chart scene Y'},
        'output':{'density':'Status M material fit -> transmittance -> APD -> Dmin-subtracted ADX','observer':'APD spectral products, not XYZ CMFs',
                  'encoding':'continuous integer-code units; round only in reported integer column','display':model.display_manager.config_metadata,
                  'view':ACES_VIEW,'target':'sRGB D65; ACES AP0 D60 before official display conversion','display_exposure_ev':0},
        'comparison':{'Cineon_aims':CINEON_AIMS,'density_per_code_D':.002,'generic_film_gamma':.6,'generic_codes_per_stop':.6*np.log10(2)/.002,
                      'notice':'Cineon generic normal-negative aims are not exact per-stock acceptance limits. APD differs from unpublished CPD; ADX also uses fixed RGB encoding gains.'},
        'neutral_rows':rows,'neutral':neutral,'ramp':{'stops':stops.tolist(),'scope':'exposure-equivalent scalar; above 100% is not passive reflectance',**ramp},
        'colourchecker':{'dataset':'colour.SDS_COLOURCHECKERS[BabelColor Average]','patch_names':names,'scene_relative_Y':scene_Y.tolist(),**measured}}
    (output/'cineon-check.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,5.5),layout='constrained')
    for c,color in enumerate(['#c94c4c','#288665','#4c72ba']):ax.plot(stops,np.array(ramp['ADX10_float'])[:,c],color=color,label='ADX10 '+'RGB'[c])
    for label,rho,code in [('2% black',.02,180),('18% gray',.18,470),('90% white',.9,685)]:
        x=np.log2(rho/.18);ax.scatter(x,code,color='black',marker='x',s=55);ax.annotate(f'{label}: {code}',(x,code),xytext=(10,10),textcoords='offset points',fontsize=9)
    ax.axhline(95,color='gray',ls=':',lw=1,label='Dmin: 95');ax.axhline(445,color='gray',ls='--',lw=1,label='Digital LAD: 445')
    ax.set(xlabel='Exposure relative to flat 18% gray (EV)',ylabel='10-bit density code value',title='5207 / D55 / APD -> ADX10; Cineon generic aims',xlim=(-6,4),ylim=(70,950));ax.grid(alpha=.18);ax.legend(loc='upper left',fontsize=9)
    fig.savefig(output/'cineon-neutral-check.png',dpi=160);plt.close(fig)
    print(json.dumps({'neutral_rows':rows,'ADX10_official_max_codes':max(neutral['official_ADX10_and_ACES2_max_codes'],ramp['official_ADX10_and_ACES2_max_codes'],measured['official_ADX10_and_ACES2_max_codes']),
        'ADX16_vs_ADX10_max':max(neutral['ADX16_minus_16_ADX10_max'],measured['ADX16_minus_16_ADX10_max']),
        'chart_neutrals':[{ 'name':names[i],'scene_Y':scene_Y[i],'ADX10':measured['ADX10_float'][i]} for i in range(18,24)]},ensure_ascii=False,indent=2))
    return details


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();run(args.output)
