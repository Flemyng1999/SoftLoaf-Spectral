# Recipe workbench prototype contract

This iteration follows the ordinary-user, spectral-user and interaction-design
agent walkthroughs. Those are heuristic reviews, not empirical user testing.
The prototype is a localhost project app, not an inline visualization. Its
E100 path reuses the existing float64 reference and pinned OCIO/OpenDRT package.
The original experiment entry point retains 5207 drafts. The desktop application
computes negative APD and optical-printing output and exports verified LUTs.
This is follow-up work for Issue #2 on the current task branch.

The [0.1 application](application-v0.1.zh-CN.md) now hosts this same interface in
a macOS window with a C++ pointwise backend. It adds explicitly interpreted
PNG/JPEG trials, full-size PNG export, applied-recipe recovery and native file
dialogs. The original experiment entry point retains its Python reference path.

The user-facing route starts at `light`; RGB spectral estimation is not a
recipe node. The current backend still returns its legacy `estimate` diagnostic
and uses its existing smooth prior. Removing the navigation item does not claim
that a direct database-to-response fitting method has replaced that calculation.

In the desktop application A is now an immutable original-scene reference:
native measured scene reflectance → D65/CIE XYZ integration → fixed finite-band
white adaptation → OCIO XYZ-D65-to-sRGB, without film or OpenDRT. RGB-only inputs
use their characterized RGB/XYZ reference and explicitly lack measured spectra.
The application response adds `reference`; `baseline` is null, while historical
baseline recipes remain in workspace files. The original experiment API retains
its legacy recipe-comparison behavior described below.

On desktop widths the toolbar and footer stay in the viewport; the three content
columns scroll independently. The native WebKit child follows the window's
unobscured content layout guide across window resizes. Reversal/print XYZ bridge
details are under viewing rather than a separate user-facing interface node;
the negative standard-output node remains distinct.

## Objects

- Recipe: the work being made. Contains material, film exposure offset,
  simulated process, viewing, display, source references and version.
- Test input: an optional photograph or built-in RGB test input, its exposure
  correction and selected point. It is not part of the exported film recipe.
- Baseline: a complete recipe snapshot. Evaluate A and B on the same current
  test input and selected point; never retain a different sample as if it were
  a parameter comparison.
- Export: a frozen recipe version, purpose, encoding and verification result.
  A finished old job must not mark a newer recipe as exported.

Use one negative material object within a negative recipe, independently of its
positive rendering method. ECN-2 and C-41 keep their own source/Status M identity;
either may use the APD or optical-paper branch. C-41 APD/ACES rendering is explicitly
experimental rather than prohibited. Changing its endpoint
between standard APD output and optical printing retains that front-end. Opening
another complete recipe opens another object; it does not inherit hidden fields.

## Recipe JSON

The server supplies complete default/template objects; the UI should clone
those rather than invent missing material settings.

```json
{
  "schema": "softloaf.recipe/1",
  "id": "user-generated-id",
  "name": "E100 · D50",
  "revision": 1,
  "route": "slide",
  "film": {"stock": "E100", "exposure_ev": 0},
  "scene": {"illuminant": "D65"},
  "viewing": {"illuminant": "D50", "gain": 1.8},
  "display": {"view": "Default"},
  "digitization": {"light": "unconfigured", "sensor": "unconfigured", "calibration": null},
  "printing": {"light": "unconfigured", "paper": "Ultra Endura"},
  "asset_refs": {}
}
```

Routes are `slide`, `negative`, `print`. `negative` and `print` use stock 5207.
Only the slide/E100 numerical engine is currently supported. Recipe exposure
is a creative offset applied at film exposure. It does not change reflectance
or the frozen material exposure anchor. Input exposure applies to both A/B
test inputs and is excluded from LUT generation. Actual RAW development is
outside this iteration; no RAW filename may masquerade as a decoded preview.

The negative branch now uses standard Academy Printing Density (APD), without
a recapture light, simulated camera response or device calibration. The active
declaration is `negative_output`: APD/ST 2065-2:2012, ADX/ST 2065-3:2012,
`value_type:"float_density"`, and explicitly missing standard weights,
coverage, normalization, Dmin, channel gains and a pinned standard conversion.
These null values are missing inputs, not default numeric values. The draft
cannot compute APD or export a negative LUT yet. APD density and ADX code
values must never be substituted for each other.

The target design additionally requires a stock-bound Status M-to-APD matrix
and offset as a hidden default material operation. It adds no main-flow node
or enable switch; professional material details expose source and residuals.
It applies at a Status M data boundary, never again after direct spectral APD
integration. This is not implemented by the present draft schema or engine;
reading the supplied bulletin does not populate its missing inputs. See
[the density-conversion contract](apd-adx.zh-CN.md).

`digitization` remains an inactive legacy container for old recipe files.
An old draft with no configured recapture settings can gain the explicit APD
declaration while remaining non-computable. An old file with configured light,
sensor or capture calibration is rejected as `legacy_digitization`, preserving
that file rather than silently claiming APD reproduces it. Edited custom
weights cannot pass as a standard APD configuration.

Custom viewing light, when supported, is embedded as
`viewing.custom_spd = {name, wavelengths_nm, values, quantity, unit, source}`.
Use `quantity: "relative_energy_spd"` and unit `"relative"` or `"a.u."`;
name/source are required. Samples must be finite, nonnegative, strictly ordered
and cover the entire 400–700 nm viewing band. Set `viewing.illuminant="custom"`
only when this complete object is present; reject conflicting built-in/custom
settings. The backend validates it before the UI commits the replacement. Keep
the complete imported samples when saving; do not silently omit them.

An optional `film.custom_material` is a complete `softloaf.material/1` object
with `schema`, `name`, `source` and three datasets. `sensitivity` contains
`wavelengths_nm`, `channels:{R,G,B}`, quantity `relative_energy_sensitivity`,
unit `relative`; `characteristic` contains `log_exposure`, `channels:{R,G,B}`,
quantity `status_a_density`, unit `D`; `dyes` contains `wavelengths_nm`,
`channels:{C,M,Y}`, quantity `spectral_density`, unit `D`.

All arrays must be finite, nonnegative and equally sized with strictly
increasing axes. Sensitivity covers 400–720 nm and dyes 400–700 nm. Reversal
characteristic density must not increase with log exposure. The server refits
effective dye amounts using the fixed numerical Status A weights, checks
maximum neutral density residual ≤0.001 D, then solves the fixed D50/Y=.1
relative gray anchor. Incompatible curves or an absent anchor are errors;
there is no fallback to old dye coefficients. Sensitivity retains the fixed
original channel denominators, so custom amplitude changes survive. Record
this as a synthetic material variant, not measured E100 calibration.

Keep original samples and component metadata intact. Imported records may
include `import_file:{name,sha256}` for the exact input file; only the basename,
never a private absolute path. The canonical complete material fingerprint
identifies the fitted snapshot. A bounded thread-safe cache shares that fit
between validation, diagnostics, preview and export.

## HTTP API

Bind only 127.0.0.1. No external services, directory listing or arbitrary file
paths. Reject unexpected origins on mutation endpoints. Serve only the new UI,
known prototype assets and registered generated downloads.

Errors use `{ok:false, error:{code,message}, issues?:[], computable?:false}`.
Return a meaningful HTTP error status for malformed/unsupported computation.
Clients inspect both the HTTP status and this body; they must not turn an
unsupported route into a blank "success" image.

### GET /api/bootstrap

Returns `{ok, default_recipe, templates, inputs, samples, capabilities}`.

- `templates`: objects `{id, name, description, available, recipe}` for the three
  fixed routes. E100 is computable; the other two explicitly indicate draft.
- `inputs`: `{id, name, kind, width?, height?}`. Include `chart` (representative
  RGB patches, not measured ColorChecker data) and, if present, `scene43_rgb`.
- `scene43_rgb` is a local development HSI scene integrated to ordinary AP1 RGB
  first. The preview then uses the same RGB spectral prior as the LUT, never
  direct HSI-to-film truth. It is an optional built-in test input, not a user
  requirement to acquire HSI or sensor sensitivities.
- `samples`: representative patch records `{id, name, input_srgb}`.
- `capabilities`: routes, usable viewing-light IDs/labels, actual OpenDRT view
  IDs/labels, source/encoding conditions and RAW unsupported status.
- `spectral_assets`: `{E100: complete_reference_material,
  viewing_lights:{D50:complete_SPD,D65:complete_SPD}}`. These are local source
  datasets for the editor, not embedded public UI assets. The exact script
  `/assets/spectral-editor.js` is separately allowlisted by the local server.

### POST /api/evaluate

```json
{
  "recipe": {},
  "baseline": null,
  "input": {"id": "scene43_rgb", "exposure_ev": 0},
  "selection": {"x": 0.5, "y": 0.5, "sample_id": "gray18"}
}
```

For a chart use `sample_id`; for the photo use normalized x/y. Respond with:

```text
{ok, version, baseline_version, input, selection,
 current: {preview, nodes, sample},
 baseline: {preview, nodes, sample} | null,
 conditions, warnings}
```

- `version`: `{recipe_id, revision, fingerprint}`; the response identifies the
  exact parameter snapshot. UI ignores late responses for older requests.
- `preview`: `{kind:"image", data_url, width, height}` for rendered photo or
  chart. Both current and baseline use identical current input processing.
- `nodes`: map IDs `estimate`, `light`, `film`, `view`, `interface`, `display`
  to `{name, input, output, details?}`. A value is either
  `{kind:"spectrum", quantity, unit, wavelengths_nm, series:[{name,values}]}`
  or `{kind:"channels", quantity, unit, labels, values}`.
- `sample`: `{input_ap1, xyz_d65, srgb}` for the selected current input point.
- No plausible placeholder values for a missing model. Return a structured
  unsupported result for 5207 with a specific reason and keep the prior usable
  recipe available for restoration.

Keep film transmittance independent of viewing light. Default D50 must match
the existing reference. Alternative lights use an explicitly recorded fixed
D50 adaptation reference, with per-light white Y normalization and the same
view gain. Do not imply automatic human adaptation or absolute exposure.

### POST /api/validate

Accept `{recipe}`. Return `{ok, normalized_recipe, computable, issues}`. Known
5207 drafts can be structurally valid and non-computable. A source mismatch or
invalid custom SPD is a concrete issue, not a silent replacement by a preset.
Custom materials also undergo the real numerical fit before `ok` is returned.
Do not commit the candidate on JSON structure validation alone.

### POST /api/export

Accept `{recipe, purpose, request_id, grid}`. `grid` is an integer edge size
2–129, default 65. The default UI purpose is `pipeline`: an
OCIO-native CTF operation graph containing the selected-size material LUT followed by
the resolved fixed display operations, from ACEScct to standard sRGB. It is
for hosts that support OCIO/CTF, not a generic photo-editor CUBE preset. The
actual display graph contains `InverseLUT1D`, which this OCIO CLF writer
rejects; CTF preserves it without another baking approximation.

Advanced purposes are `display` (one CUBE from ACEScct to standard sRGB,
including OpenDRT) and `internal` (ACEScct to relative viewed XYZ D65,
excluding display). Domain [-0.25, 0.75] and tetrahedral interpolation remain
fixed. The UI suggests 17/33/65/129 and accepts custom valid integers. Input exposure is not accepted as
an export argument.

Return `{ok, export_id, frozen, verification, warnings, files}`. `frozen` includes recipe
ID, revision and parameter fingerprint. Files expose registered same-origin
download URLs and names for cube, recipe, manifest and optional ZIP bundle.
The manifest records conditions, sources, formats, versions and checks. The
pipeline bundle includes `recipe.ctf`, the advanced material `recipe.cube`,
`recipe.json`, `manifest.json` and the upstream OpenDRT MIT notice. The primary
download selects `recipe.zip` by name, not the first item in `files`. CTF must
embed all operations and pass an independent OCIO file readback, in addition
to the material CUBE readback. Experimental data and exports remain local
until redistribution permissions have been reviewed.

Read CUBE back with the float64 evaluator and independent OCIO. Compare outputs
against the continuous reference, including after the identical display chain.
Record the fraction of a fixed, independent build-check sample set within
2/255 per channel in both continuous and rounded sRGB codes. Reaching 99% on
those samples is a sample check, not a whole-domain or real-film accuracy claim.
`verification.accepted` reports the error reference line; it does not gate
downloads. `verification.integrity_passed` separately checks serialization and
independent execution. With intact files, return `ok:true` and downloads even
when quality misses the line, plus a `quality_reference_missed` warning. File
integrity errors still return `ok:false`. Display sample count, both error
fractions, mean/P95/maximum and actual file size; do not rename a warning as an
accuracy pass or substitute internal XYZ for a requested display effect.
This supersedes the earlier policy that withheld the display-baked CUBE.

## UI task contract

Open a complete recipe and built-in input with a visible result. Keep the
selected input point, recipe version and cause/effect in one workbench. A/B
compares whole recipes; inspecting a node never switches to a different input.
Common film exposure is named 胶片曝光, with a direct +0.5 EV action and one-step
undo. Material calibration anchors stay in advanced metadata.

Save a named actual JSON file and reopen it with validation. Keep custom data
and references. Session persistence alone is not "saved to a file". Export
first asks the use/purpose and explains input requirements, including why a
profiled/developed ACEScct input is required rather than a RAW mosaic.

Work status (modified/saved) and computation/export status are separate. Keep
last working recipe on failed replacements. Prototype graphics and previews
must correspond to current real computation or clearly show unsupported state.

The current UI is node-first: fixed route and ordered nodes on the left,
selected input/result quantities in the center, selected-node controls on the
right. Film data tabs contain sensitivity, characteristic and dye curves;
viewing data stays in the viewing node. Test-image preview is a secondary
view. Do not bring back a second, stacked material workbench over a permanent
photo workspace. Source-curve drafts persist when changing nodes; importing
or applying counts as pending work and blocks saving/exporting an incomplete
recipe. The applied transmittance and viewed spectrum remain read-only.


## Scan-negative input (design, not implemented)

The requested scan workflow outputs a positive display image, including orange-mask
correction and reversal. It is a separate input purpose, not a new film chemical
process and not the ordinary scene-emulation LUT. See
[scan input and calibration design](scan-negative-lut.zh-CN.md).
