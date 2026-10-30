"""Portable, descriptive export credits; metadata never changes LUT numbers."""
import hashlib
import json
from pathlib import PurePath


APPLICATION = {
    'name': 'SoftLoaf Spectral',
    'author': 'Yangming Feng and contributors',
    'repository': 'https://github.com/Flemyng1999/SoftLoaf-Spectral',
}


def lut_metadata(recipe, frozen, purpose, conditions, application_version, created_utc):
    """Describe the actual CUBE role, including the material-only CTF companion."""
    includes_display = purpose == 'display'
    display = recipe['display']
    target = display.get('target', 'sRGB')
    output = target + ' encoded RGB / D65' if includes_display else 'relative XYZ D65'
    app = {**APPLICATION, 'version': application_version}
    comments = [
        f'Software: {app["name"]} {application_version}',
        f'Author: {app["author"]}',
        f'Project: {app["repository"]}',
        'Copyright (C) 2026 Yangming Feng and contributors (software)',
        f'Created UTC: {created_utc}',
        f'Recipe: {recipe["name"]}',
        f'Recipe ID: {recipe["id"]}; revision: {recipe["revision"]}',
        f'Recipe SHA-256: {frozen["fingerprint"]}',
        f'Process: {recipe["route"]}; film: {recipe["film"]["stock"]}',
        'Input: ACEScct / AP1 primaries / D60 white; developed and profiled RGB, not RAW mosaic',
        f'Output: {output}',
        f'Includes display: {"yes" if includes_display else "no"}',
        'Interpolation: tetrahedral; values outside DOMAIN_MIN/MAX are clamped',
        f'Observer: {conditions["observer"]}',
        f'Film exposure: {recipe["film"]["exposure_ev"]} EV',
        f'Scene illumination: {recipe["scene"]["illuminant"]}; {conditions["scene_temperature_k"]} K',
    ]
    if includes_display:
        comments.append(f'Display transform: {display["view"]}; target: {target}')
        resolved = conditions['display']
        comments.append(f'Output primaries: {resolved["primaries"]}; transfer: {resolved["encoding"]}')
    resolved = conditions.get('display', {})
    if includes_display or purpose == 'pipeline':
        config = resolved.get('ocio_config', {})
        if config.get('id'):
            comments.append(f'OCIO config: {config["id"]}; OCIO: {resolved.get("ocio_version", "not recorded")}')
    if purpose == 'pipeline':
        comments.append(f'Material CUBE only; recipe.ctf contains the complete {display["view"]} / {target} display chain')
    elif not includes_display:
        comments.append('Material CUBE only; attach a matching XYZ D65 display transform')
    for label, key in [('Exposure wavelengths nm', 'exposure_wavelengths_nm'),
                       ('Density/viewing wavelengths nm', 'view_wavelengths_nm')]:
        axis = conditions.get(key, [])
        if axis:
            comments.append(f'{label}: {axis[0]} to {axis[-1]}; {len(axis)} samples')
    if recipe['route'] in ('slide', 'print'):
        v = recipe['viewing']
        comments.append(f'Viewing: {v["illuminant"]}; relative gain: {v["gain"]}')
    if recipe['route'] == 'print':
        p = recipe['printing']
        comments.append(f'Paper: {p["paper"]}; enlarger: {p["temperature_k"]} K; exposure: {p["exposure_ev"]} EV; CMY filters: {p["filters"]}')
        if p.get('calibration_note'):comments.append('Printing calibration: '+p['calibration_note'])
        comments.append('Printing pipeline: '+p.get('pipeline','legacy-v1'))
        if p.get('pipeline')=='spectral-v2':
            comments.append('Filter model: partial-insertion dichroic transmittance; controls in log insertion, not calibrated CP units')
            comments.append('Optics: heat='+('Schott KG3' if p['optics']['heat']=='KG3' else p['optics']['heat'])+'; lens='+p['optics']['lens'])
            comments.append('Preflash: '+json.dumps(p['preflash'],ensure_ascii=False))
            comments.append('CMY filter source: '+('user transmittance CSV' if p.get('custom_filters') else 'Edmund Optics digitized curves via spektrafilm'))
            sources=conditions['optical_sources']
            comments.append('Optical data: Andrea Volpato, spektrafilm; '+sources['repository']+'; commit '+sources['commit'])
            comments.append('Optical processing: '+sources['resampling'])
            for file,record in sorted(sources['files'].items()):comments.append('Optical source '+file+': SHA-256 '+record['sha256']+'; '+record['url'])
            base=(conditions.get('paper') or {}).get('base_model',{}).get('curve') or {}
            if base.get('provenance'):
                comments.append('Paper base: processed spektrafilm Ultra Endura profile shape, CC BY-SA 4.0; Dmin origin aligned by SoftLoaf Spectral; not measured paper white')
                comments.append('Paper base source SHA-256: '+sources['paper_profile_sha256'])
            elif base.get('import_file'):comments.append('Paper base: user CSV; SHA-256 '+base['import_file']['sha256'])
            else:comments.append('Paper base: constant or custom material minimum density; frozen material fingerprint identifies source')
            if p.get('custom_filters'):comments.append('User CMY filter transmittance SHA-256: '+hashlib.sha256(json.dumps(p['custom_filters'],sort_keys=True).encode()).hexdigest())
            for role in ['heat','lens']:
                curve=p['optics'].get('custom_'+role)
                if curve:comments.append('User optical '+role+': '+PurePath(curve['name']).name+'; '+json.dumps(curve.get('import_file',{})))

    if conditions.get('scene_light_model'):comments.append('Scene light model: '+conditions['scene_light_model'])
    if recipe['route'] == 'negative':
        comments.append('Material fit: Status M; output branch: transmittance -> APD -> ADX -> ACES -> XYZ D65')
        comments.append('Academy transform attribution and license: ACES-LICENSE.md')
    if conditions.get('positive_method_scope'):
        comments.append('Positive rendering scope: '+conditions['positive_method_scope'])
    if display['view'] in ('Default', 'Colorful', 'Umbra') and (includes_display or purpose=='pipeline'):
        comments.append('OpenDRT: Jed Smith and contributors; MIT; https://github.com/jedypod/open-display-transform')
    refs = recipe.get('asset_refs', {})
    comments.append(f'Material model: {refs.get("model", "unversioned local reference")}')
    for key in ('material', 'paper'):
        material = conditions.get(key) or {}
        if material.get('name'):
            comments.append(f'{key.capitalize()}: {material["name"]}')
        if material.get('fingerprint'):
            comments.append(f'{key.capitalize()} SHA-256: {material["fingerprint"]}')
        if material.get('neutral_StatusA_max_error_D') is not None:
            comments.append(f'Neutral Status A model fit max residual: {material["neutral_StatusA_max_error_D"]:.8g} D; allowed model residual: {material.get("neutral_fit_limit_D", .001):.8g} D; not full-color accuracy')
        provenance=material.get('provenance',{})
        if provenance:
            comments.append(f'{key.capitalize()} process: {provenance.get("process")}; density metric: {provenance.get("density_metric")}')
            comments.append(f'{key.capitalize()} model note: {provenance.get("summary", "experimental material")}')
            for component, source in sorted(provenance.get('substitutions',{}).items()):
                comments.append(f'Temporary substitute [{key}.{component}]: {source}')
            for component, file in sorted(provenance.get('user_overrides',{}).items()):
                comments.append(f'User CSV override [{key}.{component}]: {file["name"]}; SHA-256: {file["sha256"]}; replaces the original reference component')
            for credit in provenance.get('credits',[]):
                comments.append(f'Material attribution: {credit}')
            for role, source in sorted(provenance.get('sources',{}).items()):
                comments.append(f'Material source [{role}]: {source.get("url") or source.get("file", "not recorded")}')
                if source.get('sha256'):
                    comments.append(f'Material source SHA-256 [{role}]: {source["sha256"]}')
            if provenance.get('density_metric_evidence'):
                comments.append('Density definition evidence: '+json.dumps(provenance['density_metric_evidence'],ensure_ascii=False))
            if provenance.get('source_conditions'):
                comments.append('Manufacturer curve conditions: '+json.dumps(provenance['source_conditions'],ensure_ascii=False))
            for assumption in provenance.get('tail_assumptions',[]):comments.append('Material tail assumption: '+assumption)
            if provenance.get('exposure_anchor'):
                comments.append(f'Material exposure calibration: {provenance["exposure_anchor"]}')
            if provenance.get('sensitivity_common_scale') is not None:
                comments.append(f'Common sensitivity amplitude scale: {provenance["sensitivity_common_scale"]}; preserves channel ratios, not ISO speed calibration')
            if provenance.get('characteristic_processing'):
                comments.append('Characteristic processing: '+provenance['characteristic_processing'])
            if provenance.get('original_status_m_curve_point_max_error_D') is not None:
                comments.append(f'Original Status M vector point max residual: {provenance["original_status_m_curve_point_max_error_D"]} D; neutral fit only')
            if provenance.get('manufacturer_reference_illuminant'):
                comments.append(f'Manufacturer exposure reference: {provenance["manufacturer_reference_illuminant"]}; simulated scene is declared separately')
    for name, digest in sorted(refs.get('sha256', {}).items()):
        comments.append(f'Source SHA-256 {PurePath(name).name}: {digest}')
    if conditions.get('compute_kernel_sha256'):
        comments.append(f'Calculation kernel SHA-256: {conditions["compute_kernel_sha256"]}')
    if conditions.get('pixel_compute',{}).get('backend')=='Metal':
        gpu=conditions['pixel_compute']
        comments.append('Pixel processing: Metal float32; '+gpu['device']+'; checked against float64 reference')
        comments.append('Metal spectral shader SHA-256: '+gpu['spectral_shader_sha256'])
        comments.append('Metal execution library SHA-256: '+gpu['library_sha256'])
    # A custom source string may contain a personal path. Identify it by hash,
    # while the versioned recipe remains the complete reproduction record.
    for section in ('film', 'printing'):
        custom = recipe.get(section, {}).get('custom_material')
        if custom:
            digest = hashlib.sha256(json.dumps(custom, ensure_ascii=False, allow_nan=False,
                sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
            comments.append(f'Custom {section} material SHA-256: {digest}')
    comments.extend([
        'Fixed pointwise transform; photo input exposure and adaptive processing are not included',
        'RGB spectral approximation and finite-band material model; not measured full-color film accuracy',
        'Software license: AGPL-3.0-only; external materials retain their own rights',
        'Local research export; material and derived LUT redistribution permissions pending review',
    ])
    return {'application': app, 'created_utc': created_utc,
            'title': f'SoftLoaf Spectral - {recipe["name"]}', 'comments': comments}
