"""Node diagnostics expose the actual material-stage intermediate arrays."""
import copy
import numpy as np
import colour
from experiments.gui_recipe_server import template,spectrum,channels,png_preview,RecipeError
from experiments.hsi_raw_lut import D60,D65,cat
from spectral_lut.negative_trace import apd_to_xyz_trace


class PipelineRoutes:
    def bootstrap(self):
        result=super().bootstrap()
        from pathlib import Path
        from .presets import load_recipe_presets,visible_negative_presets
        try:
            all_presets=load_recipe_presets(Path(__file__).resolve().parents[1])
            result['recipe_presets']=visible_negative_presets(all_presets)
            for entry in all_presets:
                stock=entry['recipe']['film']['stock']
                result['spectral_assets'][stock]=copy.deepcopy(entry['recipe']['film']['custom_material'])
        except (ValueError,KeyError,OSError):
            all_presets=[]
            result['recipe_presets']=[]
            result['preset_warning']='实验配方资料校验失败，已保留原有三种流程。'
        from .reversal_presets import load_reversal_presets
        result['reversal_presets']=[]
        try:
            for entry in load_reversal_presets(Path(__file__).resolve().parents[1]):
                r=template('slide');r.update(name=entry['name']+' · D50',scene={'illuminant':'CIE_D','temperature_k':5500})
                r['film'].update(stock=entry['id'],custom_material=copy.deepcopy(entry['material']))
                r=self.model.validate(r)['normalized_recipe']
                result['reversal_presets'].append({'id':entry['id'],'name':entry['name'],'process':'E-6','route':'slide','recipe':r,'summary':entry['material']['provenance']['summary']})
                result['spectral_assets'][entry['id']]=copy.deepcopy(entry['material'])
                self.model.material_plot_sources[entry['id']]={'sensitivity':copy.deepcopy(entry['plot'])}
        except (ValueError,KeyError,OSError,RecipeError):
            result['reversal_warning']='新增反转片资料未通过校验，仅保留 E100。'
        result['spectral_assets']['material_plot_sources']=copy.deepcopy(getattr(self.model,'material_plot_sources',{}))
        if getattr(self.model,'negative',None) is None:return result
        from .paper_presets import load_paper_presets
        result['paper_presets']=[]
        try:
            papers=load_paper_presets(Path(__file__).resolve().parents[1])
            for entry in papers:
                self.model._paper_fit(entry['material'])
            result['paper_presets']=[{k:copy.deepcopy(v) for k,v in e.items() if k!='plot'} for e in papers]
            for entry in papers:
                result['spectral_assets']['paper:'+entry['id']]=copy.deepcopy(entry['material'])
                result['spectral_assets']['material_plot_sources']['paper:'+entry['id']]=copy.deepcopy(entry['plot'])
        except (ValueError,KeyError,OSError,RecipeError):
            result['paper_warning']='新增相纸未通过校验，保留已有相纸和配方。'
        for t in result['templates']:
            if t['id']=='slide':continue
            route=t['id'];preferred=next((e['recipe'] for e in all_presets if e['recipe']['film']['stock']=='5207' and e['recipe']['route']==route),None)
            r=copy.deepcopy(preferred) if preferred else template(route);r['name']='5207 · '+('APD' if route=='negative' else 'Ultra Endura')
            t.update(available=True,recipe=self.model.validate(r)['normalized_recipe'],description='光谱参考计算 · 中性标定，完整色彩准确度待测')
        result['spectral_assets'].update({'5207':copy.deepcopy(self.model.negative_material),'paper':copy.deepcopy(self.model.paper_material),
            'printing_light':copy.deepcopy(self.model.printing_original_light),'printing_filters':copy.deepcopy(self.model.printing_filter_curves)})
        if self.model.printing_assets:
            result['spectral_assets']['printing_light_v2']={**copy.deepcopy(self.model.printing_original_light),'name':'3400 K 模拟钨丝光','values':self.model.printer_light(3400).tolist()}
            result['spectral_assets']['printing_optics']=copy.deepcopy(self.model.printing_assets)
            result['spectral_assets']['paper_v2']=copy.deepcopy(self.model.modern_paper_material)
            preferred=next((e['recipe'] for e in all_presets if e['recipe']['film']['stock']=='5207'),None)
            result['printing_defaults_by_stock']={'5207':self.model.modern_printing(preferred)}
            for entry in all_presets:
                stock=entry['recipe']['film']['stock']
                if stock not in result['printing_defaults_by_stock']:
                    result['printing_defaults_by_stock'][stock]=self.model.modern_printing(entry['recipe'])
            result['printing_defaults']=copy.deepcopy(result['printing_defaults_by_stock']['5207'])
            for t in result['templates']:
                if t['id']=='print':
                    t['recipe']['printing']=copy.deepcopy(result['printing_defaults'])
                    t['recipe']=self.model.validate(t['recipe'])['normalized_recipe']
        # Display the pinned manufacturer's original vector detail independently
        # of the versioned 10 nm computation material. Never persist it in recipes.
        traces=self.model.calibration['traces']
        result['spectral_assets']['material_plot_sources']['5207']={'sensitivity':{
            'quantity':'relative_energy_sensitivity','unit':'relative',
            'source':'Kodak H-1-5207t, July 2015, p4',
            'provenance_sha256':self.model.route_sources['provenance.json'],
            'calculation_step_nm':float(np.diff(self.model.source_wavelengths)[0]),
            'channels':{c:{'wavelengths_nm':[p[0] for p in traces['5207_sensitivity_'+c]],
                           'values':[10.**p[1] for p in traces['5207_sensitivity_'+c]]} for c in 'RGB'}}}
        result['spectral_assets']['legacy_5207']=copy.deepcopy(self.model.negative_material)
        result['spectral_assets']['material_plot_sources']['legacy_5207']=copy.deepcopy(result['spectral_assets']['material_plot_sources']['5207'])
        from .material_plots import load_vision3_plots
        try:
            plots=load_vision3_plots(Path(__file__).resolve().parents[1])
            for entry in all_presets:
                if entry['recipe']['film']['stock'] in plots:
                    result['spectral_assets'][entry['recipe']['film']['stock']]=copy.deepcopy(entry['recipe']['film']['custom_material'])
            result['spectral_assets']['material_plot_sources'].update(plots)
        except (ValueError,KeyError,OSError):
            result['material_plot_warning']='新增原厂曲线详情未通过校验，使用配方自身的采样点。'
        for r in result['capabilities']['routes']:
            r['computable']=True
            if r['id']=='negative':r['standard_conversion_implemented']=True;r['normative_conformance']=False
        result['capabilities']['source']='Three local spectral material models; ordinary RGB uses a declared spectral prior; physical accuracy is not established by numerical checks'
        return result

    def conditions(self,recipe):
        if recipe['route']=='slide':return super().conditions(recipe)
        m=self.model;material=m.route_material(recipe)
        return {'observer':'CIE 1931 2 degree','input':'scene-linear ACEScg / AP1 D60; no RAW decoding',
            'compute_backend':'C++23 float64 / ABI 1' if m.core else 'Python NumPy float64 reference',
            'compute_kernel_sha256':m.core.sha256 if m.core else None,'route':recipe['route'],
            'material':copy.deepcopy(material.metadata),'paper':copy.deepcopy(m.route_paper(recipe).metadata) if recipe['route']=='print' else None,
            'exposure_wavelengths_nm':m.source_wavelengths.tolist(),'view_wavelengths_nm':m.negative_wavelengths.tolist(),
            'scene_temperature_k':recipe['scene'].get('temperature_k',6500 if recipe['scene']['illuminant']=='D65' else 5500),
            'scene_light_spectrum':spectrum('relative_energy_spd','relative',m.source_wavelengths,SPD=m.scene_light(recipe['scene'].get('temperature_k'),recipe['scene']['illuminant'])),
            'scene_illuminant':recipe['scene']['illuminant'],
            'scene_light_model':'Planck blackbody energy SPD approximation; equal finite-band photopic Y to D65' if recipe['scene']['illuminant']=='Planck' else 'CIE D-series daylight; equal finite-band photopic Y to D65',
            'input_reference_illuminant':'fixed D65','film_exposure_ev':recipe['film']['exposure_ev'],
            'spectral_prior':'minimum-first-difference + nonnegative projection; approximation from ordinary RGB',
            'density':('film fitted directly to original Status M targets; modeled transmission integrated as absolute APD including base only at output; no Status M-to-APD matrix'
                if recipe['route']=='negative' else 'film fitted directly in Status M; negative spectral transmittance directly exposes paper; paper uses a finite-band Status A reflection-density approximation; no APD/ADX computation'),
            'negative_output':copy.deepcopy(recipe['negative_output']) if recipe['route']=='negative' else None,
            'positive_method':('APD / ADX / ACES film input transform' if recipe['route']=='negative' else 'optical paper printing'),
            'positive_method_scope':('Experimental application of a motion-picture film input transform to C-41; no stock-specific color validation'
                if recipe['route']=='negative' and material.metadata.get('provenance',{}).get('process')=='C-41'
                else 'Numerical material model; stock-specific full-color validation pending'),
            'output_domain':('scene-referred ACES from the declared film input transform; not direct observation of the negative'
                if recipe['route']=='negative' else 'observed XYZ under the declared paper reflection viewing conditions; not original scene radiance'),
            'printing':copy.deepcopy(recipe['printing']) if recipe['route']=='print' else None,
            'optical_sources':copy.deepcopy(m.printing_assets['source']) if recipe['route']=='print' and recipe['printing'].get('pipeline')=='spectral-v2' else None,
            'viewing':copy.deepcopy(recipe['viewing']) if recipe['route']=='print' else None,
            'adaptation':'ACES2065-1 AP0 D60 to XYZ D65 Bradford' if recipe['route']=='negative' else 'fixed finite-band D50 white to D65 Bradford; replacement viewing light is not neutralized',
            'display':m.display_manager.metadata(recipe['display']['view'],recipe['display'].get('target','sRGB')),
            'sources':copy.deepcopy(m.negative_refs),'assumptions':copy.deepcopy(m.calibration['assumptions']),
            'rights':'Local material inputs only; redistribution and derived LUT permissions pending',
            'accuracy_scope':'Numerical calculation and neutral-density fitting; not measured full-color film or exposure-to-print validation'}

    def evaluate_one(self,recipe,image,point,spectra=None,spectral_point=None,input_ev=0):
        if recipe['route']=='slide':return super().evaluate_one(recipe,image,point,spectra,spectral_point,input_ev=input_ev)
        from experiments.hsi_raw_lut import batched
        m=self.model;p=m.parameters(recipe);compute=m.sample if spectra is None else m.sample_spectra
        sample=compute(point if spectra is None else spectral_point,**p)
        streaming=getattr(self,'image_previews',None)
        preview=streaming.render(image if spectra is None else spectra,recipe,spectral=spectra is not None,input_ev=input_ev) if streaming else None
        output=None if streaming else m.metal.render(image if spectra is None else spectra,recipe,spectral=spectra is not None,input_ev=input_ev) if m.metal else batched(lambda x:compute(x,**p)['display_rgb'],image if spectra is None else spectra,chunk=2048)
        source,grid=m.source_wavelengths,m.negative_wavelengths
        light=m.scene_light(p['scene_temperature_k'],p.get('scene_illuminant'))
        incident=spectrum('relative_spectral_exposure','relative',source,H=sample['reflectance']*light*np.exp2(recipe['film']['exposure_ev']))
        transmission=spectrum('spectral_transmittance','fraction',grid,T=sample['transmission'])
        xyz=channels('adapted_XYZ_D65','relative Y','XYZ',sample['XYZ'])
        nodes={
            'light':{'name':'拍摄日光','input':spectrum('relative_energy_spd','relative',source,SPD=light),'output':incident,'details':{'temperature_k':recipe['scene'].get('temperature_k',6500)}},
            'film':{'name':('5207 曝光与 ECN-2 显影' if recipe['film']['stock']=='5207' else p['material'].metadata['name']+' · '+p['material'].metadata['provenance']['process']),'input':incident,'output':transmission,'details':{'material':copy.deepcopy(p['material'].metadata),'material_curves':copy.deepcopy(recipe['film'].get('custom_material') or m.negative_material),
                'layer_exposure':channels('normalized_layer_exposure','relative','RGB',sample['exposure']),'dye_amounts':channels('effective_CMY_amount','relative','CMY',sample['dye_amounts']),
                'density':spectrum('optical_density','D',grid,D=-np.log10(sample['transmission']))}},
            'display':{'name':'显示输出','input':xyz,'output':channels('encoded_'+recipe['display'].get('target','sRGB'),'0–1','RGB',sample['display_rgb']),
                'details':{**m.display_manager.metadata(recipe['display']['view'],recipe['display'].get('target','sRGB')),
                    'process':m.display_manager.trace(sample['XYZ'],recipe['display']['view'],recipe['display'].get('target','sRGB'))}}}
        if recipe['route']=='negative':
            nodes['apd']={'name':'APD 密度','input':transmission,'output':channels('academy_printing_density','D','RGB',sample['apd']),
                'details':{'standard_products':spectrum('APD_spectral_weights','normalized per nm',grid,**{c:m.apd_weights[:,i]/2 for i,c in enumerate('RGB')}),
                    'dmin_apd':sample['dmin_apd'].tolist(),'matrix_applied_to':'none; film fitted directly in Status M; APD integrated from transmittance only at output'}}
            nodes['interface']={'name':'APD / ADX16 → ACES 1.2','input':nodes['apd']['output'],'output':xyz,
                'details':{'adx16_float_code_values':sample['adx16_float'].tolist(),'aces2065_1_AP0_D60':sample['ACES'].tolist(),'conversion':recipe['negative_output'],'density_to_code':'1520 + 8000 × (APD − Dmin) × [1, 0.92, 0.95]; unquantized internally',
                    'process':apd_to_xyz_trace(sample['apd'],sample['dmin_apd'],
                        colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ,cat(D60,D65))}}
        else:
            illuminated=sample['transmission']*sample['printer_light']*np.exp2(recipe['printing']['exposure_ev'])
            nodes['enlarger']={'name':'放大照明','input':transmission,'output':spectrum('relative_paper_exposure_spectrum','relative',grid,H=illuminated),
                'details':{'light':spectrum('relative_energy_spd','relative',grid,SPD=sample['bare_printer_light']),'effective_light':spectrum('relative_energy_spd','relative',grid,SPD=sample['printer_light']),'heat_transmission':spectrum('spectral_transmittance','fraction',grid,T=sample['heat_transmission']),'lens_transmission':spectrum('spectral_transmittance','fraction',grid,T=sample['lens_transmission']),'temperature_k':recipe['printing']['temperature_k']}}
            nodes['filter']={'name':'放大滤色','input':nodes['enlarger']['output'],'output':spectrum('relative_paper_exposure_spectrum','relative',grid,H=sample['print_incident']*np.exp2(recipe['printing']['exposure_ev'])),
                'details':{'transmission':spectrum('spectral_transmittance','fraction',grid,T=sample['filter_transmission']),'CMY_density_controls':recipe['printing']['filters'],'exposure_ev':recipe['printing']['exposure_ev'],'model':'partial-insertion dichroic transmittances; logarithmic controls, not calibrated CP units' if recipe['printing'].get('pipeline')=='spectral-v2' else 'ideal absorbers using declared paper dye spectral shapes; not measured enlarger filters'}}
            nodes['paper']={'name':m.route_paper(recipe).metadata['name'],'input':spectrum('relative_paper_exposure_spectrum','relative',grid,H=sample['total_print_incident']),'output':spectrum('spectral_reflectance','fraction',grid,R=sample['paper_reflectance']),
                'details':{'material':copy.deepcopy(m.route_paper(recipe).metadata),'material_curves':copy.deepcopy(recipe['printing'].get('custom_material') or (m.modern_paper_material if recipe['printing'].get('pipeline')=='spectral-v2' else m.paper_material)),'layer_exposure':channels('paper_layer_exposure','relative','RGB',sample['paper_exposure']),'effective_CMY':sample['paper_amounts'].tolist(),'preflash':spectrum('relative_paper_exposure_spectrum','relative',grid,H=sample['preflash_spectrum']),'preflash_layer_exposure':sample['preflash_exposure'].tolist()}}
            nodes['view']={'name':'成品反射观看','input':nodes['paper']['output'],'output':spectrum('relative_viewed_spectral_radiance','relative per nm',grid,L=sample['viewed_spectrum']),
                'details':{'viewing':copy.deepcopy(recipe['viewing']),'observed_xyz':sample['XYZ_view'].tolist(),'XYZ_D65':sample['XYZ'].tolist()}}
        return {'preview':preview or png_preview(output,m.display_profile(recipe['display'].get('target','sRGB'))),'nodes':nodes,'sample':{'input_ap1':np.asarray(point).tolist(),'xyz_d65':sample['XYZ'].tolist(),'display_rgb':sample['display_rgb'].tolist(),'display_target':recipe['display'].get('target','sRGB'),**({'srgb':sample['display_rgb'].tolist()} if recipe['display'].get('target','sRGB')=='sRGB' else {})}}
