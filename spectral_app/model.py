"""Three fixed material routes, sharing the application's characterized RGB input."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.optimize import least_squares,brentq

from experiments.gui_recipe_server import E100Model, RecipeError, validate_recipe, negative_output_draft, fingerprint, material_issues
from experiments.hsi_raw_lut import AP1,D60,D65,cat,color_kernel,csv,interpolate,sha
from spectral_lut.reference import quadrature_widths,decreasing_projection
from spectral_lut.reference import acescct_encode
from spectral_lut.metrics import srgb_code_error
from spectral_lut.negative import integrate_density,adx_codes,adx_to_aces
from spectral_lut.display import migrate_display_defaults, ROUTE_DEFAULT_VIEWS
import colour


def stage(spectra,kernel,axis,amounts,dyes,base,anchor=0,ev=0,core=None):
    if core is not None:return core.spectral_stage(spectra,kernel,axis,amounts,dyes,base,anchor,ev)
    h=np.asarray(spectra)@kernel*np.exp2(ev)
    logs=anchor+np.log10(np.maximum(h,1e-30))
    a=np.stack([np.interp(logs[...,c],axis,amounts[:,c]) for c in range(3)],-1)
    density=base+a@dyes.T
    if not np.isfinite(density).all() or np.any(density<0):
        raise ValueError('Invalid absolute spectral density.')
    return h,a,10.**-density


def fit_amounts(dyes,base,weights,targets):
    guess=np.full(3,.01);out=[]
    for target in targets:
        sol=least_squares(lambda a:integrate_density(10**-(base+a@dyes.T),weights)-target,guess,bounds=(0,np.inf),ftol=1e-12,xtol=1e-12,gtol=1e-12)
        if not sol.success:raise RecipeError('material_fit','材料的密度拟合未收敛。')
        guess=sol.x;out.append(guess)
    amounts=np.column_stack([-decreasing_projection(-np.array(out)[:,i]) for i in range(3)])
    residual=integrate_density(10**-(base+amounts@dyes.T),weights)-targets
    return amounts,float(np.max(np.abs(residual)))


def curve(table,axis,labels,quantity,unit):
    return {axis:table[:,0].tolist(),'channels':{c:table[:,i+1].tolist() for i,c in enumerate(labels)},'quantity':quantity,'unit':unit}


class SpectralModel(E100Model):
    def __init__(self,*args,materials=None,**kwargs):
        from .storage import DataStorage
        DataStorage.configured().activate_temporary_directory()
        self.metal=None
        kwargs.setdefault('preview_short_edge',2048)
        super().__init__(*args,**kwargs)
        from .input_priors import InputPriors
        self.input_priors=InputPriors(self.source_to_ap1,self.source_wavelengths)
        from .material_plots import load_e100_plot
        self.material_plot_sources=load_e100_plot(Path(__file__).resolve().parents[1],self.sources,np.diff(self.source_wavelengths)[0])
        self.direct_spectral_preview = True
        from .runtime_paths import science_root
        self.material_directory=Path(materials or science_root()/'local/materials/5207-v1')
        self.route_sources={};self.route_material_cache={}
        self.negative=self.paper=None
        if not (self.material_directory/'provenance.json').exists():return
        identity_path=Path(__file__).resolve().parents[1]/'data/5207-reference-manifest.json'
        identities=json.loads(identity_path.read_text())['sha256']
        files={name:self.material_directory/name for name in identities}
        if any(not p.is_file() or sha(p)!=identities[name] for name,p in files.items()):
            raise RecipeError('source_mismatch','5207 内置资料校验失败；请重新提取已核对版本。自定义材料应通过 CSV 导入。')
        self.route_sources={name:sha(p) for name,p in files.items()}
        self.calibration=json.loads(files['provenance.json'].read_text())
        char=csv(files['5207_characteristic.csv'],1);sens=csv(files['5207_sensitivity.csv'],1);dyes=csv(files['5207_dyes.csv'],1)
        self.negative_wavelengths=dyes[:,0]
        w=csv(files['apd_weights.csv'],1)
        if not np.array_equal(w[:,0],self.negative_wavelengths):
            raise RecipeError('source_mismatch','APD 输出权重与材料计算网格不匹配。')
        weights=w[:,1:]*quadrature_widths(w[:,0])[:,None]
        self.apd_weights=weights/weights.sum(0)
        from spectral_lut.densitometry import load_status_m
        products,self.status_m_source=load_status_m(Path(__file__).resolve().parents[1],self.negative_wavelengths,data_root=science_root())
        weights=products*quadrature_widths(self.negative_wavelengths)[:,None]
        self.status_m_weights=weights/weights.sum(0)
        self.negative_material={'schema':'softloaf.material/1','name':'Kodak 5207 · ECN-2','source':'Kodak H-1-5207t, July 2015, pp4–5; independently extracted published vector curves; local rights review pending',
            'sensitivity':curve(sens,'wavelengths_nm','RGB','relative_energy_sensitivity','relative'),
            'characteristic':curve(char,'log_exposure','RGB','status_m_density','D'),
            'dyes':curve(dyes,'wavelengths_nm','CMY','spectral_density','D'),
            'base':{'wavelengths_nm':dyes[:,0].tolist(),'values':dyes[:,4].tolist(),'quantity':'spectral_density','unit':'D'}}
        # Kodak labels these curves "D-mins subtracted". Retain their small
        # signed increments from the original hash-pinned vector extraction;
        # the legacy v1 CSV clipped them. Do not rewrite pinned source files.
        net=self.negative_material['dyes'];net['quantity']='net_spectral_density'
        for c in 'CMY':
            trace=np.asarray(self.calibration['traces']['5207_dye_'+c],dtype=float)
            net['channels'][c]=np.interp(net['wavelengths_nm'],trace[:,0],trace[:,1]).tolist()
        self.calibration['assumptions'].append('Model /2 uses signed Dmin-subtracted 5207 CMY curves from the retained original traces, superseding v1 CSV clipping. Absolute density remains nonnegative for every bounded layer combination.')
        self.calibration['assumptions'].append('Model /3 fits original Status M targets directly with ISO 5/3:1984 Table 4 products on 360–730 nm / 2 nm. Fixed modeled base alignment uses Status M, not the published Status M-to-APD compatibility matrix. APD is evaluated only by its output branch.')
        self.negative=self._negative_fit(self.negative_material)
        pc=csv(files['paper_characteristic.csv'],1);ps=csv(files['paper_sensitivity.csv'],1);pd=csv(files['paper_dyes.csv'],1)
        self.paper_material={'schema':'softloaf.material/1','name':'Kodak Ultra Endura · RA-4','source':'Kodak E-4020, July 2003, p7; published curves; reflection-density approximation, no exposure-paired print measurements',
            'sensitivity':curve(ps,'wavelengths_nm','RGB','relative_energy_sensitivity','relative'),
            'characteristic':curve(pc,'log_exposure','RGB','status_a_density','D'),
            'dyes':curve(pd,'wavelengths_nm','CMY','spectral_density','D')}
        self.paper=self._paper_fit(self.paper_material)
        self.printing_filter_curves={'name':'理想 CMY 吸收滤色','source':'Fixed original Ultra Endura dye shapes used as ideal absorbers; not measured enlarger filters',**copy.deepcopy(self.paper_material['dyes'])}
        self.printing_original_light={'name':'3200 K 模拟钨丝光','source':'Planck energy SPD, maximum normalized to 1','quantity':'relative_energy_spd','unit':'relative','wavelengths_nm':self.negative_wavelengths.tolist(),'values':self.printer_light(3200).tolist()}
        previous={'sha256':{**self.sources,**self.route_sources},'aces_reference':'aces-core v1.2 / ADX16_to_ACES a1.0.3'}
        version3={**previous,'model':'5207-paper-reference/3','density_fit':copy.deepcopy(self.status_m_source)}
        self.legacy_negative_refs=tuple({**previous,'model':f'5207-paper-reference/{version}'} for version in [1,2])+(version3,)
        self.negative_refs={**version3,'model':'5207-paper-reference/4','default_scene_temperature_k':5500}
        from .printing_optics import load_optics
        self.printing_assets=load_optics(Path(__file__).resolve().parents[1],self.negative_wavelengths)
        self.modern_paper_material=self.modern_paper=None
        if self.printing_assets:
            self.modern_paper_material=copy.deepcopy(self.paper_material)
            self.modern_paper_material['base']=copy.deepcopy(self.printing_assets['paper_base'])
            # Preserve the processed shape, align only its common density origin
            # to the original Status A Dmin constraints. Do not clip wavelengths.
            b=np.asarray(self.modern_paper_material['base']['values']);weights=self._paper_weights()
            offset=float(np.min(np.min(np.stack([self.paper_material['characteristic']['channels'][c] for c in 'RGB'],-1),axis=0)-integrate_density(10**-b,weights)))
            b=b+offset
            if np.any(b<0):raise RecipeError('paper_base','相纸白底形状无法与原始最低密度兼容。')
            self.modern_paper_material['base']['values']=b.tolist()
            self.modern_paper_material['base']['alignment_offset_D']=offset
            self.modern_paper=self._paper_fit(self.modern_paper_material)
        if self.route_sources!={name:sha(p) for name,p in files.items()}:raise RuntimeError('5207 materials changed while loading.')

    def material_fit_tolerance(self,custom):
        # A source-specific finite-band monotone-model allowance, not a new
        # measurement-accuracy claim. E100, unknown sources and CSV stay strict.
        p=custom.get('provenance',{});limits={
            'velvia50':('bebfb4305fd3edc5e3505a9a0f4a0a1078da1db7672aacb4aa1bac1de3d64cfd',.012),
            'provia100f':('e28d54e76e8fcdf44c8ffacc930b5b8f2ea54a7cdaeedfcc91790e68eb599de8',.006)}
        source=limits.get(p.get('stock_id'))
        if source and p.get('process')=='E-6' and p.get('source_pdf_sha256')==source[0]:
            for role in ('characteristic','dyes'):
                curve=custom.get(role,{})
                if not curve.get('import_file'):continue
                values={k:v for k,v in curve.items() if k in ('quantity','unit','wavelengths_nm','log_exposure','channels')}
                digest=hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
                if digest!=p.get('fit_reference_components',{}).get(role):return .001
            return source[1]
        return super().material_fit_tolerance(custom)

    def fit_material(self,custom,key):
        film,metadata=super().fit_material(custom,key)
        provenance=custom.get('provenance',{})
        if provenance.get('process')=='E-6' and provenance.get('stock_id')!='E100':
            from dataclasses import replace
            sensitivity=np.column_stack([np.interp(self.source_wavelengths,custom['sensitivity']['wavelengths_nm'],custom['sensitivity']['channels'][c]) for c in 'RGB'])
            reference_k=provenance['reference_temperature_k']
            reference=self.scene_light(reference_k)
            widths=quadrature_widths(self.source_wavelengths)
            frozen=provenance.get('exposure_reference')
            if not isinstance(frozen,dict) or frozen.get('temperature_k')!=reference_k or frozen.get('reflectance')!=.18:
                raise RecipeError('invalid_material','反转片需要冻结的片种曝光参考，CSV 不得触发重新标定。')
            if material_issues({**custom,'sensitivity':frozen}):raise RecipeError('invalid_material','冻结曝光参考的感光表格式或覆盖范围无效。')
            original_sensitivity=np.column_stack([np.interp(self.source_wavelengths,frozen['wavelengths_nm'],frozen['channels'][c]) for c in 'RGB'])
            denominator=np.sum(.18*original_sensitivity*reference[:,None]*widths[:,None],axis=0)
            kernel=sensitivity*self.source_light[:,None]*widths[:,None]/denominator
            if not np.isfinite(kernel).all() or np.any(denominator<=0):raise RecipeError('invalid_material','反转片感光响应无法建立明确的相对曝光标定。')
            kernel.setflags(write=False);film=replace(film,exposure_kernel=kernel)
            metadata={'name':custom['name'],'source':custom['source'],'fingerprint':key,'custom':True,
                'label':'原厂曲线参考 · E-6','density_metric':'Status A','provenance':copy.deepcopy(provenance),
                'neutral_StatusA_max_error_D':metadata['neutral_StatusA_max_error_D'],'neutral_fit_limit_D':metadata['neutral_fit_limit_D'],'gray_logH_anchor':film.gray_log_h,
                'reference_temperature_k':reference_k,'relative_exposure_denominators':denominator.tolist(),
                'anchor_policy':'Per-stock frozen 18% D55 relative exposure; fixed D50 Y=0.1 viewing anchor; no ISO-speed or full-color measurement claim'}
        return film,metadata

    def _tables(self,m,grid):
        def table(k,axis,labels,x):
            c=m[k];return np.stack([np.interp(x,c[axis],c['channels'][v]) for v in labels],-1)
        return np.array(m['characteristic']['log_exposure']),np.stack([m['characteristic']['channels'][c] for c in 'RGB'],-1),table('dyes','wavelengths_nm','CMY',grid),table('sensitivity','wavelengths_nm','RGB',self.source_wavelengths if m['characteristic']['quantity']=='status_m_density' else grid)

    def _negative_fit(self,m):
        grid=self.negative_wavelengths;axis,targets,dyes,sens=self._tables(m,grid)
        weights=self.status_m_weights
        published_base=np.interp(grid,m['base']['wavelengths_nm'],m['base']['values'])
        # A frozen model base is aligned to the lowest published exposure plateau.
        # This is never sampled from a user's image or refitted per recipe.
        shapes=weights/np.maximum(weights.max(0),1e-30)
        correction=least_squares(lambda x:integrate_density(10**-np.maximum(published_base+shapes@x,0),weights)-targets[0],np.zeros(3),ftol=1e-13,xtol=1e-13,gtol=1e-13)
        base=np.maximum(published_base+shapes@correction.x,0)
        try:amounts,error=fit_amounts(dyes,base,weights,targets)
        except (ValueError,FloatingPointError) as e:
            raise RecipeError('material_fit','染料拟合无法保持有效透射率；请检查净密度、片基和通道尺度。') from e
        if error>.006:raise RecipeError('material_fit',f'{m["name"]} 中性 Status M 拟合残差 {error:.5f} D 超出 0.006 D。')
        # Each channel can vary independently. A neutral fit alone cannot
        # establish passivity for colored exposures, so bound the full box.
        low,high=amounts.min(0),amounts.max(0)
        minimum_density=float(np.min(base+np.where(dyes>=0,dyes*low,dyes*high).sum(1)))
        if minimum_density<0:raise RecipeError('invalid_material','染料与片基组合会产生负的绝对光谱密度，请检查扣底方式和材料尺度。')
        daylight=self.scene_light(5500)
        denominator=.18*np.sum(sens*daylight[:,None]*quadrature_widths(self.source_wavelengths)[:,None],0)
        # Original denominators frozen for CSV amplitude controls.
        if hasattr(self,'negative_denominators'):denominator=self.negative_denominators
        else:self.negative_denominators=denominator.copy()
        frozen=m.get('provenance',{}).get('exposure_reference')
        if frozen is not None:
            try:
                if (frozen.get('reflectance')!=.18 or frozen.get('illuminant') not in ('CIE_D','Planck')
                        or frozen.get('quantity')!='relative_energy_sensitivity' or frozen.get('unit')!='relative'):
                    raise ValueError('invalid frozen reference')
                x=np.asarray(frozen['wavelengths_nm'],dtype=float)
                if len(x)<2 or not np.isfinite(x).all() or np.any(np.diff(x)<=0) or x[0]>400 or x[-1]<720:raise ValueError('invalid reference wavelengths')
                original=[]
                for c in 'RGB':
                    y=np.asarray(frozen['channels'][c],dtype=float)
                    if y.shape!=x.shape or not np.isfinite(y).all() or np.any(y<0):raise ValueError('invalid reference sensitivity')
                    original.append(np.interp(self.source_wavelengths,x,y))
                light=self.scene_light(frozen['temperature_k'],frozen['illuminant'])
                denominator=.18*np.sum(np.array(original).T*light[:,None]*quadrature_widths(self.source_wavelengths)[:,None],axis=0)
                if np.any(denominator<=0) or not np.isfinite(denominator).all():raise ValueError('invalid reference exposure')
            except (KeyError,TypeError,ValueError) as error:
                raise RecipeError('invalid_material','负片冻结曝光参考无效，不能改用 5207 标定。') from error
        metadata={'name':m['name'],'fingerprint':fingerprint(m),'fit_metric':'Status M','fit_reference':copy.deepcopy(self.status_m_source),'neutral_max_error_D':error,'gray_logH_anchor':0,'dye_density_quantity':m['dyes']['quantity'],'minimum_absolute_density_bound_D':minimum_density,
            'base_calibration':'published spectral minimum density aligned to lowest published neutral Status M plateau; approximate unexposed Dmin, fixed before LUT build',
            'base_adjustment_max_D':float(np.max(np.abs(base-published_base))),
            'published_base_status_m':integrate_density(10**-published_base,weights).tolist(),'modeled_base_status_m':integrate_density(10**-base,weights).tolist(),
            'exposure_anchor':'18% flat reflector at CIE D55 corresponds to manufacturer camera stops 0; relative, not ISO-calibrated'}
        if m.get('provenance'):metadata['provenance']=copy.deepcopy(m['provenance'])
        metadata['relative_exposure_denominators']=denominator.tolist()
        if frozen is not None:
            metadata['exposure_anchor']='Per-stock frozen 18% reference under its declared illuminant; relative camera-stops origin, not ISO calibration'
            metadata['reference_illuminant']={k:frozen[k] for k in ('temperature_k','illuminant','reflectance')}
        return SimpleNamespace(axis=axis,amounts=amounts,dyes=dyes,base=base,sensitivity=sens,denominators=denominator.copy(),metadata=metadata)

    def _paper_weights(self):
        grid=self.negative_wavelengths
        weights=np.column_stack([np.interp(grid,self.view_wavelengths,self.status_a_weights[:,i],left=0,right=0) for i in range(3)])
        return weights/weights.sum(0)

    def _paper_fit(self,m):
        grid=self.negative_wavelengths;axis,targets,dyes,sens=self._tables(m,grid)
        # Reuse only the archived finite-band Status A weighting data. This is
        # an explicit reflection-density approximation, not a scattering model.
        weights=self._paper_weights()
        base=np.interp(grid,m['base']['wavelengths_nm'],m['base']['values']) if m.get('base') else np.full(len(grid),float(np.min(targets[0])))
        if np.any(integrate_density(10**-base,weights)>targets.min(0)+.02):raise RecipeError('paper_base','相纸底密度超过特性曲线的最低密度。')
        amounts,error=fit_amounts(dyes,base,weights,targets)
        if error>.02:raise RecipeError('paper_fit',f'相纸中性拟合残差 {error:.5f} D 超出 0.02 D。')
        # Fixed per-channel printer balance makes the reference 18% gray fall
        # at a common midpoint on the paper's log-exposure axis.
        # This inherited software balance is deliberately explicit. Changing
        # the negative's default light must not silently recalibrate the paper.
        t=self._film_stage(np.full(len(self.source_wavelengths),.18),0,6500,self.negative)[2]
        lamp=self.printer_light(3200)
        denominator=t*lamp
        normal=np.sum(denominator[:,None]*sens*quadrature_widths(grid)[:,None],0)
        paper_provenance=m.get('provenance',{})
        frozen=paper_provenance.get('exposure_reference') if paper_provenance.get('material_version')=='kodak-paper-source/1' else None
        if paper_provenance.get('material_version')=='kodak-paper-source/1' and not isinstance(frozen,dict):raise RecipeError('invalid_material','相纸缺少冻结曝光参考。')
        if frozen is not None:
            try:
                reference=frozen['sensitivity']
                x=np.asarray(reference['wavelengths_nm'],dtype=float)
                if reference['quantity']!='relative_energy_sensitivity' or reference['unit']!='relative' or x.ndim!=1 or len(x)<2 or x[0]>360 or x[-1]<730 or not np.isfinite(x).all() or np.any(np.diff(x)<=0):raise ValueError()
                for c in 'RGB':
                    y=np.asarray(reference['channels'][c],dtype=float)
                    if y.shape!=x.shape or not np.isfinite(y).all() or np.any(y<0):raise ValueError()
                original=np.column_stack([np.interp(grid,reference['wavelengths_nm'],reference['channels'][c]) for c in 'RGB'])
                normal=np.sum(denominator[:,None]*original*quadrature_widths(grid)[:,None],0)
                if not np.isfinite(normal).all() or np.any(normal<=0):raise ValueError()
            except (KeyError,TypeError,ValueError):raise RecipeError('invalid_material','相纸缺少有效的冻结曝光参考。')
        elif hasattr(self,'paper_denominators'):normal=self.paper_denominators
        else:self.paper_denominators=normal.copy()
        d50=interpolate(csv(self.archive.parent/'data/CIE_std_illum_D50.csv'),grid)[:,0]
        cmf=interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'),grid)
        y_kernel=color_kernel(grid,d50,cmf)[:,1]
        def gray_y(x):
            a=np.array([np.interp(x,axis,amounts[:,c]) for c in range(3)])
            return 10**-(base+a@dyes.T)@y_kernel
        if frozen is not None and 'anchor_logH' in frozen:
            anchor=frozen['anchor_logH']
            if type(anchor) not in (int,float) or not np.isfinite(anchor):raise RecipeError('invalid_material','相纸冻结曝光原点无效。')
        else:anchor=brentq(lambda x:gray_y(x)-.1,axis[0],axis[-1])
        fitted=SimpleNamespace(axis=axis,amounts=amounts,dyes=dyes,base=base,sensitivity=sens,normal=normal,anchor=anchor,
            metadata={'name':m['name'],'fingerprint':fingerprint(m),'neutral_max_error_D':error,'gray_logH_anchor':anchor,
                'reference_scene_temperature_k':6500,
                'calibration':'frozen software balance under a simulated 3200 K lamp and 5207 18% D65 gray; paper anchor solved for D50 Y=0.1 before viewing gain; not a Kodak calibration or absolute lux-second exposure',
                'published_reference_conditions':{
                    'reference':'Kodak E-4020, July 2003, pp2–4,7; conditions of the builtin reference curves, not verified for user CSV',
                    'process':'RA-4','density_metric':'Status A','curve_exposure_seconds':.5,
                    'developer_temperature_c':35,'developer_time_seconds':45,
                    'enlarger_light_types':['tungsten','tungsten-halogen','photo-enlarger lamp'],
                    'specified_enlarger_temperature_k':None,'specified_enlarger_spd':False,
                    'suggested_test_filter_pack':'40M + 50Y; CP/dichroic filter units, not the model ideal CMY density parameters',
                    'evaluation_cct_k':5000,'evaluation_cct_tolerance_k':1000,
                    'evaluation_cri_range':[85,100],'evaluation_minimum_lux':538,
                    'evaluation_standard':'ANSI PH2.30-1989'},
                'viewing_model':'D50 is a spectral approximation to the published evaluation condition; gain is relative, not a measured lux setting',
                'base_model':{'source_scope':m['base'].get('source','user supplied spectral base') if m.get('base') else 'legacy constant density approximation','curve':copy.deepcopy(m.get('base'))},
                'reflection_model':'R=10^-(effective base + CMY density), no measured scattering or fluorescence; finite-band Status A approximation'})
        if frozen is not None:
            fitted.metadata.update(provenance=copy.deepcopy(paper_provenance),
                published_reference_conditions=copy.deepcopy(paper_provenance['source_conditions']),
                calibration=paper_provenance['exposure_anchor'],
                viewing_model='D50 colorimetry with relative gain; no measured paper-white, fluorescence or angular appearance calibration')
        return fitted

    def modern_printing(self,recipe=None):
        from .printing_optics import modern_settings,dichroic_transmission
        setting=modern_settings(self.printing_assets)
        material=self.route_material(recipe) if recipe else self.negative
        scene=recipe['scene'] if recipe else {'illuminant':'CIE_D','temperature_k':5500}
        k=scene.get('temperature_k',6500)
        t=self._film_stage(np.full(len(self.source_wavelengths),.18),0,k,material,scene['illuminant'])[2]
        lamp=self.printer_light(3400)*np.asarray(self.printing_assets['heat']['values'])
        f=np.column_stack([self.printing_assets['filters']['channels'][c] for c in 'CMY'])
        paper=self.modern_paper;kernel=paper.sensitivity*quadrature_widths(self.negative_wavelengths)[:,None]/paper.normal
        def exposure(x):return (t*lamp*dichroic_transmission(f,x[:3]))@kernel*np.exp2(x[3])
        solution=least_squares(lambda x:np.log10(np.maximum(exposure(x),1e-30)),[.2,.65,.55,0],bounds=([0,0,0,-4],[2,2,2,4]),ftol=1e-12,xtol=1e-12,gtol=1e-12)
        if not solution.success or np.max(np.abs(np.log10(exposure(solution.x))))>1e-5:raise RecipeError('printer_balance','内置光路无法达到起始灰片曝光，请检查材料。')
        setting.update(filters=solution.x[:3].tolist(),exposure_ev=float(solution.x[3]),
            neutral_start={'scene':copy.deepcopy(scene),'reflectance':.18,'target_paper_layer_exposure':[1,1,1],
                'achieved_paper_layer_exposure':exposure(solution.x).tolist(),'max_log10_layer_error':float(np.max(np.abs(np.log10(exposure(solution.x))))),
                'scope':'Frozen virtual gray test using the declared material, never a current-image fit or proof of color accuracy'})
        setting['preflash']['filters']=setting['filters'].copy()
        return setting

    def printer_optics(self,setting):
        """Resolve separate optics; imported SPD is pre-optics unless bypassed."""
        a=self.printing_assets;grid=self.negative_wavelengths
        optics=setting['optics']
        def component(role):
            selected=optics[role]
            if selected=='none':return np.ones(len(grid))
            curve=optics['custom_'+role] if selected=='custom' else a[role]
            return np.interp(grid,curve['wavelengths_nm'],curve['values'])
        return component('heat'),component('lens')

    @staticmethod
    def _daylight(k,grid):
        xy=colour.temperature.CCT_to_xy_CIE_D(k*1.4388/1.4380);sd=colour.sd_CIE_illuminant_D_series(xy)
        return np.interp(grid,sd.wavelengths,sd.values)

    def scene_light(self,temperature_k=None,illuminant=None):
        if illuminant!='Planck':return super().scene_light(temperature_k)
        if type(temperature_k) not in (int,float) or not np.isfinite(temperature_k) or not 2500<=temperature_k<=5000:
            raise RecipeError('invalid_light','钨丝光黑体近似范围为 2500–5000 K。')
        nm=self.source_wavelengths*1e-9
        light=1/(nm**5*np.expm1(1.438776877e-2/(nm*temperature_k)))
        cmf=interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'),self.source_wavelengths)
        weights=cmf[:,1]*quadrature_widths(self.source_wavelengths)
        return light*((self.source_light@weights)/(light@weights))

    def printer_light(self,k):
        # Planck energy SPD, arbitrary radiometric normalization.
        nm=self.negative_wavelengths*1e-9
        spd=1/(nm**5*np.expm1(1.438776877e-2/(nm*k)))
        return spd/spd.max()

    def _film_stage(self,reflectance,ev,k,material,scene_illuminant=None):
        if k is None:k=5500
        kernel=material.sensitivity*self.scene_light(k,scene_illuminant)[:,None]*quadrature_widths(self.source_wavelengths)[:,None]/getattr(material,'denominators',self.negative_denominators)
        return stage(reflectance,kernel,material.axis,material.amounts,material.dyes,material.base,0,ev,self.core)

    def route_material(self,recipe):
        original=self.negative if recipe['route']!='slide' else None
        custom=recipe['film'].get('custom_material')
        if not custom:return original
        key=fingerprint(custom)
        with self.material_lock:
            if key not in self.route_material_cache:
                self.route_material_cache[key]=self._negative_fit(custom)
                if len(self.route_material_cache)>16:self.route_material_cache.pop(next(iter(self.route_material_cache)))
            return self.route_material_cache[key]

    def parameters(self,recipe):
        p=super().parameters(recipe)
        p['input_model']=recipe.get('input_model')
        if recipe['route']!='slide':p.update(route=recipe['route'],printing=copy.deepcopy(recipe['printing']),material=self.route_material(recipe),
            scene_temperature_k=recipe['scene'].get('temperature_k',6500 if recipe['scene']['illuminant']=='D65' else 5500),scene_illuminant=recipe['scene']['illuminant'])
        if recipe['route']=='print':p['paper_material']=self.route_paper(recipe)
        return p

    def route_paper(self,recipe):
        custom=recipe['printing'].get('custom_material')
        if not custom:return self.modern_paper if recipe['printing'].get('pipeline')=='spectral-v2' else self.paper
        key='paper:'+fingerprint(custom)
        with self.material_lock:
            if key not in self.route_material_cache:
                self.route_material_cache[key]=self._paper_fit(custom)
                if len(self.route_material_cache)>16:self.route_material_cache.pop(next(iter(self.route_material_cache)))
            return self.route_material_cache[key]

    def sample(self,rgb,route='slide',printing=None,material=None,input_model=None,**p):
        from .input_priors import LEGACY
        descriptor=self.input_priors.validate(input_model,route)
        reflectance=self.input_priors.reconstruct(rgb,route,descriptor)
        if reflectance is None:reflectance=np.maximum(np.asarray(rgb)@self.basis,0)
        return self.sample_spectra(reflectance,route=route,printing=printing,material=material,**p)

    def sample_spectra(self,reflectance,route='slide',input_model=None,printing=None,material=None,paper_material=None,exposure_ev=0,viewing_light='D50',viewing_gain=1.8,display=None,custom_material=None,scene_temperature_k=None,display_target='sRGB',scene_illuminant=None):
        if display is None:display=ROUTE_DEFAULT_VIEWS[route]
        if route=='slide':
            film,_=self.material(custom_material)
            kernel=film.exposure_kernel*(self.scene_light(scene_temperature_k)/self.source_light)[:,None]
            h,a,t=stage(reflectance,kernel,film.log_h,film.amounts,film.dyes,np.zeros(len(film.dyes)),film.gray_log_h,exposure_ev,self.core)
            light=self.light(viewing_light);vk=color_kernel(self.view_wavelengths,light,self.cmfs)
            raw=t@vk*viewing_gain;xyz=raw@self.fixed_adaptation.T
            return {'reflectance':reflectance,'exposure':h,'dye_amounts':a,'transmission':t,'viewed_spectrum':t*light/(light*self.cmfs[:,1]*quadrature_widths(self.view_wavelengths)).sum()*viewing_gain,'XYZ_view':raw,'XYZ':xyz,**self.display_result(xyz,display,display_target)}
        material=material or self.negative
        h,a,t=self._film_stage(reflectance,exposure_ev,scene_temperature_k,material,scene_illuminant)
        result={'reflectance':reflectance,'exposure':h,'dye_amounts':a,'transmission':t}
        if route=='negative':
            apd=integrate_density(t,self.apd_weights);dmin=integrate_density(10**-material.base,self.apd_weights)
            codes=adx_codes(apd,dmin)
            aces=adx_to_aces(codes);xyz=aces@colour.RGB_COLOURSPACES['ACES2065-1'].matrix_RGB_to_XYZ.T@cat(D60,D65).T
            result.update(apd=apd,dmin_apd=dmin,adx16_float=codes,ACES=aces,XYZ_view=xyz,XYZ=xyz)
        else:
            setting=printing or {}
            paper=paper_material or (self.modern_paper if setting.get('pipeline')=='spectral-v2' else self.paper)
            if setting.get('light')=='custom':
                spd=setting['custom_spd'];lamp=np.interp(self.negative_wavelengths,spd['wavelengths_nm'],spd['values'])
                y=interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'),self.negative_wavelengths)[:,1]*quadrature_widths(self.negative_wavelengths)
                lamp=lamp*(self.printer_light(3200)@y)/(lamp@y)
            else:lamp=self.printer_light(setting.get('temperature_k',3200))
            modern=setting.get('pipeline')=='spectral-v2'
            bare_lamp=lamp.copy()
            heat,lens=self.printer_optics(setting) if modern else (np.ones_like(lamp),np.ones_like(lamp))
            lamp=lamp*heat*lens
            # Legacy absorption and modern partial-insertion optics stay distinct.
            filter_source=setting.get('custom_filters',self.printing_assets['filters'] if modern else self.printing_filter_curves)
            filter_density=np.stack([np.interp(self.negative_wavelengths,filter_source['wavelengths_nm'],filter_source['channels'][c]) for c in 'CMY'],-1)
            filters=np.array(setting.get('filters',[0,0,0]))
            from .printing_optics import dichroic_transmission
            filter_t=dichroic_transmission(filter_density,filters) if modern else 10**-(filter_density@filters)
            incident=t*lamp*filter_t
            kernel=paper.sensitivity*quadrature_widths(self.negative_wavelengths)[:,None]/paper.normal
            preflash_spectrum=np.zeros_like(lamp)
            if modern:
                flash=setting['preflash']
                preflash_spectrum=lamp*dichroic_transmission(filter_density,flash['filters'])*10**-material.base*flash['exposure']
                total_incident=incident*np.exp2(setting.get('exposure_ev',0))+preflash_spectrum
                ph,pa,r=stage(total_incident,kernel,paper.axis,paper.amounts,paper.dyes,paper.base,paper.anchor,0,self.core)
            else:
                total_incident=incident*np.exp2(setting.get('exposure_ev',0))
                ph,pa,r=stage(incident,kernel,paper.axis,paper.amounts,paper.dyes,paper.base,paper.anchor,setting.get('exposure_ev',0),self.core)
            grid=self.negative_wavelengths
            light=np.interp(grid,viewing_light['wavelengths_nm'],viewing_light['values']) if isinstance(viewing_light,dict) else interpolate(csv(self.archive.parent/f'data/CIE_std_illum_{viewing_light}.csv'),grid)[:,0]
            cmf=interpolate(csv(self.archive.parent/'data/CIE_xyz_official.csv'),grid)
            vk=color_kernel(grid,light,cmf);d50=interpolate(csv(self.archive.parent/'data/CIE_std_illum_D50.csv'),grid)[:,0]
            raw=r@vk*viewing_gain;adapt=cat(color_kernel(grid,d50,cmf).sum(0),D65)
            result.update(paper_exposure=ph,paper_amounts=pa,paper_reflectance=r,printer_light=lamp,filter_transmission=filter_t,print_incident=incident,total_print_incident=total_incident,preflash_spectrum=preflash_spectrum,preflash_exposure=preflash_spectrum@kernel,bare_printer_light=bare_lamp,heat_transmission=heat,lens_transmission=lens,
                viewed_spectrum=r*light/(light*cmf[:,1]*quadrature_widths(grid)).sum()*viewing_gain,XYZ_view=raw,XYZ=raw@adapt.T)
        result.update(self.display_result(result['XYZ'],display,display_target))
        return result

    def validate(self,recipe,compute=False):
        result=self._validate_material_recipe(recipe,compute)
        normalized=result.get('normalized_recipe')
        if normalized and result.get('ok'):
            try:normalized['input_model']=self.input_priors.validate(normalized.get('input_model'),normalized['route'])
            except ValueError as error:raise RecipeError('input_prior_mismatch',str(error)) from None
            if 'input_model' not in recipe and recipe.get('asset_refs'):normalized['revision']+=1
        return result

    def _validate_material_recipe(self,recipe,compute=False):
        if not isinstance(recipe,dict):return super().validate(recipe,compute)
        if recipe.get('route')=='slide':
            if not isinstance(recipe.get('film'),dict):return super().validate(recipe,compute)
            stock=recipe.get('film',{}).get('stock')
            if stock=='E100':return super().validate(recipe,compute)
            material=recipe.get('film',{}).get('custom_material')
            if not isinstance(material,dict) or not isinstance(material.get('provenance'),dict):raise RecipeError('invalid_material','反转片需要完整材料及来源对象。')
            identity=material['provenance']
            if identity.get('stock_id')!=stock or identity.get('process')!='E-6' or identity.get('density_metric')!='Status A':raise RecipeError('process_mismatch','其他反转片需要匹配片种、E-6 处理和原始 Status A 定义的完整材料。')
            reference=identity.get('reference_temperature_k')
            if type(reference) not in (int,float) or not 4000<=reference<=10000:raise RecipeError('invalid_material','反转片需要明确的相对曝光参考光。')
            probe=copy.deepcopy(recipe);probe['film']['stock']='E100'
            result=super().validate(probe,compute);result['normalized_recipe']['film']['stock']=stock
            return result
        route=recipe.get('route')
        if route not in ('negative','print'):return super().validate(recipe,compute)
        if self.negative is None:raise RecipeError('missing_materials','缺少已核对的本地 5207 和相纸资料，请先提取原厂曲线。')
        if not isinstance(recipe.get('film'),dict):raise RecipeError('invalid_recipe','需要完整的胶片节点设置。')
        r=migrate_display_defaults(recipe);probe=copy.deepcopy(r);probe['route']='slide';probe.setdefault('film',{})['stock']='E100';probe['film'].pop('custom_material',None);probe['asset_refs']={}
        if r.get('scene',{}).get('illuminant')=='Planck':
            self.scene_light(r['scene'].get('temperature_k'),'Planck')
            if set(r['scene'])!={'illuminant','temperature_k'}:raise RecipeError('invalid_light','钨丝光需要色温，并使用明确的黑体近似。')
            probe['scene']={'illuminant':'D65'}
        check=validate_recipe(probe)
        if not check['ok']:raise RecipeError('invalid_recipe',check['issues'][0]['message'],check['issues'])
        custom=r['film'].get('custom_material')
        if custom is not None and not isinstance(custom,dict):raise RecipeError('invalid_material','材料需要完整的对象格式。')
        identity=(custom or {}).get('provenance',{})
        if not isinstance(identity,dict):raise RecipeError('invalid_material','材料来源需要按字段记录。')
        if identity.get('process') and identity['process'] not in ('ECN-2','C-41'):
            raise RecipeError('process_mismatch','负片材料需要独立的 ECN-2 或 C-41 体系，不能使用 E-6、RA-4 或电影正片材料。')
        if r['film'].get('stock')!='5207':
            if (not custom or identity.get('stock_id')!=r['film'].get('stock')
                    or identity.get('process') not in ('ECN-2','C-41')
                    or identity.get('density_metric')!='Status M'):
                raise RecipeError('invalid_recipe','其他负片需要匹配片种、冲洗体系和 Status M 定义的完整材料。')
        if r.get('digitization')!={'light':'unconfigured','sensor':'unconfigured','calibration':None}:raise RecipeError('legacy_digitization','此配方含旧翻拍设置，请保留原文件并另建 APD 配方。')
        old=r.get('negative_output')
        if old is not None and old not in (negative_output_draft(),self.negative_descriptor()):raise RecipeError('invalid_recipe','APD 标准条件或转换版本与当前材料不匹配。')
        if route=='negative':r['negative_output']=self.negative_descriptor()
        else:r.pop('negative_output',None)
        legacy=r.get('asset_refs') in self.legacy_negative_refs
        inherited_d65=r['scene']=={'illuminant':'D65'} and (legacy or not r.get('asset_refs'))
        if legacy or inherited_d65:
            r['revision']+=1
        elif r.get('asset_refs') and r['asset_refs']!=self.negative_refs:raise RecipeError('source_mismatch','5207 材料或转换来源版本不匹配。')
        if inherited_d65:r['scene']={'illuminant':'CIE_D','temperature_k':5500}
        r['asset_refs']=copy.deepcopy(self.negative_refs)
        r['name']={'5207 · APD 草案':'5207 · APD','5207 · 光学放大草案':'5207 · Ultra Endura'}.get(r['name'],r['name'])
        printing=r.setdefault('printing',{})
        if printing.get('light') in (None,'unconfigured'):printing.update(light='Planck',temperature_k=3200,exposure_ev=0,filters=[0,0,0],paper='Ultra Endura')
        printing.setdefault('pipeline','legacy-v1')
        if printing['pipeline'] not in ('legacy-v1','spectral-v2'):raise RecipeError('invalid_optics','未知的放大计算版本。')
        modern=printing['pipeline']=='spectral-v2'
        if modern and not self.printing_assets:raise RecipeError('missing_optics','缺少已标识的放大光路资料。')
        if printing.get('light') not in ('Planck','custom') or not isinstance(printing.get('paper'),str) or not printing['paper'].strip():raise RecipeError('invalid_recipe','需要已定义的放大光源和相纸材料。')
        if printing['paper']!='Ultra Endura' and printing.get('custom_material') is None:raise RecipeError('invalid_recipe','所选相纸需要保存完整材料曲线，不能仅凭名称切换。')
        def source_curve(c,labels,quantity):
            try:
                if c['quantity']!=quantity or c['unit']!=('D' if quantity=='spectral_density' else 'fraction' if quantity=='spectral_transmittance' else 'relative') or any(not isinstance(c[k],str) or not c[k].strip() for k in ['name','source']):raise ValueError()
                x=np.asarray(c['wavelengths_nm']);ys=[c['values']] if labels is None else [c['channels'][v] for v in labels]
                if x.ndim!=1 or not 2<=len(x)<=8192 or x[0]>360 or x[-1]<730 or not np.isfinite(x).all() or np.any(np.diff(x)<=0):raise ValueError()
                for raw in ys:
                    y=np.asarray(raw)
                    if x.shape!=y.shape or not np.isfinite(y).all() or np.any(y<0) or (quantity=='spectral_transmittance' and np.any(y>1)):raise ValueError()
                if labels is None and quantity=='relative_energy_spd' and not np.any(np.interp(self.negative_wavelengths,x,ys[0])>0):raise ValueError()
            except (KeyError,TypeError,ValueError):raise RecipeError('invalid_material','放大光和滤色 CSV 需声明正确量、单位、名称、来源及完整 360–730 nm 非负曲线。')
        if printing['light']=='custom':source_curve(printing.get('custom_spd'),None,'relative_energy_spd')
        elif printing.get('custom_spd') is not None:raise RecipeError('invalid_recipe','内置放大光与 CSV 光源冲突。')
        if printing.get('custom_filters') is not None:source_curve(printing['custom_filters'],'CMY','spectral_transmittance' if modern else 'spectral_density')
        def number(v,low,high):return type(v) in (float,int) and np.isfinite(v) and low<=v<=high
        if modern:
            if printing.get('filter_model')!='dichroic':raise RecipeError('invalid_optics','现代放大采用二向色透射率模型。')
            optics=printing.get('optics');flash=printing.get('preflash')
            if not isinstance(optics,dict) or not isinstance(flash,dict):raise RecipeError('invalid_optics','缺少完整的光路或预闪光设置。')
            for role,builtin in [('heat','KG3'),('lens','reference-lens')]:
                if optics.get(role) not in ('none',builtin,'custom'):raise RecipeError('invalid_optics','未知的光路组件。')
                if optics[role]=='custom':source_curve(optics.get('custom_'+role),None,'spectral_transmittance')
                elif optics.get('custom_'+role) is not None:raise RecipeError('invalid_optics','内置光路与导入曲线冲突。')
            if not number(flash.get('exposure'),0,1) or not isinstance(flash.get('filters'),list) or len(flash['filters'])!=3 or any(not number(v,0,2) for v in flash['filters']):raise RecipeError('invalid_optics','预闪曝光 0–1；滤色控制 0–2。')
            expected=self.printing_assets['source']['commit']
            if printing.get('optical_source_commit') not in (None,expected):raise RecipeError('source_mismatch','放大光路来源版本不匹配。')
            printing['optical_source_commit']=expected
            digest=fingerprint(self.printing_assets['source'])
            if printing.get('optical_sources_sha256') not in (None,digest):raise RecipeError('source_mismatch','放大光路资料哈希不匹配。')
            printing['optical_sources_sha256']=digest
        elif any(k in printing for k in ('optics','preflash','filter_model','optical_source_commit','optical_sources_sha256')):
            raise RecipeError('invalid_optics','旧版吸收滤色不接受新版光路设置，请明确切换版本。')
        if not number(printing.get('temperature_k'),2500,5000) or not number(printing.get('exposure_ev'),-4,4) or not isinstance(printing.get('filters'),list) or len(printing['filters'])!=3 or any(not number(v,0,2) for v in printing['filters']):raise RecipeError('invalid_recipe','放大色温 2500–5000 K，曝光 ±4 EV，CMY 滤色密度 0–2 D。')
        if r['film'].get('custom_material') is not None:self._validate_negative_material(r['film']['custom_material']);self.route_material(r)
        if route=='print' and r['viewing']['illuminant']=='custom':
            x=r['viewing']['custom_spd']['wavelengths_nm']
            if x[0]>360 or x[-1]<730:raise RecipeError('invalid_spd','相纸观看光需要完整覆盖 360–730 nm。')
        if printing.get('custom_material') is not None:
            cm=printing['custom_material'];probe=copy.deepcopy(cm)
            try:
                if probe['characteristic']['quantity']!='status_a_density':raise ValueError()
                for v in probe['characteristic']['channels'].values():
                    if np.any(np.diff(v)<-1e-12):raise ValueError()
                probe['characteristic']['channels']={c:list(reversed(v)) for c,v in probe['characteristic']['channels'].items()}
                from experiments.gui_recipe_server import material_issues
                if material_issues(probe):raise ValueError()
                for k in ['sensitivity','dyes']:
                    x=cm[k]['wavelengths_nm']
                    if x[0]>360 or x[-1]<730:raise ValueError()
            except (KeyError,TypeError,ValueError):raise RecipeError('invalid_material','相纸材料需要递增 Status A 曲线和完整 360–730 nm 光谱。')
            if cm.get('base') is not None:source_curve(cm['base'],None,'spectral_density')
            self.route_paper(r)
        return {'ok':True,'normalized_recipe':r,'computable':True,'issues':[]}

    def negative_descriptor(self):
        return {'metric':'APD','value_type':'float_density','spectral_coverage_nm':[360,730], 'spectral_weights':'TB-2014-005 historical standard table, 2 nm; normalized trapezoidal',
            'base_density':'frozen calibrated modeled unexposed plateau','channel_gains':[1,.92,.95],
            'standard_conversion':{'name':'APD/ADX16-to-ACES','reference':'aces-core v1.2 (2019)','version':'a1.0.3','status':'implemented'},'normative_conformance':False,'model_tail_assumptions':True}

    def spectral_verification(self,recipe,cube,purpose):
        """Small fixed development check, separate from LUT interpolation."""
        from experiments.hsi_raw_lut import batched
        spectra=[]
        if 'scene43_rgb' in self.measured_inputs:
            scene=self.measured_inputs['scene43_rgb'];h,w=scene.shape[:2]
            spectra.append(scene[np.linspace(0,h-1,32).astype(int)[:,None],np.linspace(0,w-1,48).astype(int)[None,:]].reshape(-1,scene.shape[-1]))
        if 'chart' in self.measured_inputs:spectra.append(self.measured_inputs['chart'][32::64,32::64].reshape(-1,len(self.source_wavelengths)))
        if not spectra:return None
        reflectance=np.concatenate(spectra);n=len(reflectance)
        reflectance=np.concatenate([reflectance*2.**ev for ev in [-2,0,2]])
        rgb=reflectance@self.source_to_ap1;points=acescct_encode(rgb)
        inside=np.all((points>=cube.domain_min)&(points<=cube.domain_max),axis=-1)
        reflectance,rgb,points=reflectance[inside],rgb[inside],points[inside]
        p=self.parameters(recipe)
        physical=batched(lambda x:self.sample_spectra(x,**p)['display_rgb'],reflectance,chunk=512)
        estimated=batched(lambda x:self.sample(x,**p)['display_rgb'],rgb,chunk=512)
        lut=self.core.apply_cube(cube,points) if self.core else cube.apply(points)
        if purpose!='display':lut=self.render(lut,recipe['display']['view'],recipe['display'].get('target','sRGB'))
        return {'measured_input_count':n,'exposure_variants':[-2,0,2],
            'excluded_outside_LUT_domain':int(np.count_nonzero(~inside)),
            'rgb_approximation':srgb_code_error(physical,estimated)[0],
            'total_lut_vs_spectral':srgb_code_error(physical,lut)[0],
            'scope':'Fixed source-group development samples: scene43 preview 48×32 plus 24 measured BabelColor patches, three EV; not fresh blind data, not real-film accuracy. Total uses the float64 cube plus the same display transform.'}

    def _validate_negative_material(self,m):
        from experiments.gui_recipe_server import material_issues
        # Apply existing structural/numeric coverage checks with reversed
        # monotonicity; retain Status M as the actual imported quantity.
        probe=copy.deepcopy(m)
        try:
            characteristic=probe['characteristic']
            if characteristic['quantity']!='status_m_density':raise ValueError()
            for v in characteristic['channels'].values():
                if np.any(np.diff(np.asarray(v,dtype=float)) < -1e-12):raise ValueError()
            characteristic['quantity']='status_a_density';characteristic['channels']={c:list(reversed(v)) for c,v in characteristic['channels'].items()}
            signed=probe['dyes']['quantity']=='net_spectral_density'
            if signed:probe['dyes']['quantity']='spectral_density'
            issues=material_issues(probe,allow_signed_dyes=signed)
            base=m['base']
            if base.get('quantity')!='spectral_density' or base.get('unit')!='D':raise ValueError('片基需要光谱密度 D。')
            if any(type(v) not in (float,int) for v in base['wavelengths_nm']+base['values']):raise ValueError()
            x=np.array(base['wavelengths_nm']);y=np.array(base['values'])
            if x.ndim!=1 or x.shape!=y.shape or len(x)<2 or x[0]>360 or x[-1]<730 or np.any(np.diff(x)<=0) or np.any(y<0) or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError()
            for key in ['dyes']:
                x=m[key]['wavelengths_nm']
                if x[0]>360 or x[-1]<730:raise ValueError()
            if issues:raise ValueError(issues[0]['message'])
        except (KeyError,TypeError,ValueError) as e:raise RecipeError('invalid_material','5207 CSV 材料需要递增 Status M 曲线、完整 360–730 nm CMY 与片基密度，以及 400–720 nm 线性感光谱。'+str(e))
