# Development

The [local desktop version 0.1](application-v0.1.zh-CN.md) now builds a C++23
float64 library and a macOS development window. Reversal intermediates are
compared with the Python reference; RGB trial import, PNG readback, recipe
recovery and independent LUT execution have tests. This does not complete
the camera RAW, independent full-color material validation or distribution milestones below.
The [5207 audit](5207-pipeline-audit.zh-CN.md) records the newly connected APD
and printing calculations, cross-implementation checks and approximation errors.

## 1. E100 reference program

The first program will reproduce E100. The E-4000 characteristic plot specifies
Status A, and the curves are available as vectors. The Python implementation
will extract curves, integrate exposure, fit density and calculate viewing
colors. It will use float64 as the numerical reference.

Before using this program as a reference:

- Document how to obtain each input and review its permitted use.
- Reproduce eight scenes at three exposures without another application's code,
  binaries, installed profiles or local absolute paths.
- Save source hashes, settings, spectra, XYZ and linear RGB. Read the saved PNGs
  back and compare them with the reference values.
- Keep transmission positive and at most one; neutral transmission must not
  decrease with exposure. Reproduce neutral Status A curves within 0.001 D.
- Compare with the earlier calculation and explain any differences.
- Use OpenColorIO for fixed conversions and a pinned OpenDRT OCIO configuration
  for display rendering. Record the observed-XYZ bridge and actual file encoding;
  retain spectra and XYZ before rendering for material checks.

The 0.001 D tolerance applies to neutral-curve fitting. Material accuracy needs
separate tests against measured E100 output with known exposure and processing.

## 2. RGB processing and the first LUT

Build ordinary RAW grading, preview and image export alongside the RGB
approximation; LUT generation must also work without an imported photograph.
Start with a matching, tested DCP or matrix profile for at least one camera; do not require
camera spectral sensitivities. Record RAW development, profile components,
white balance, exposure normalization and the OCIO working-space conversion.
Verify single/dual-illuminant behavior, matrix direction, calibration signatures,
exposure scaling and profile-table boundaries against independent results.

Test camera input characterization on held-out colors and scenes separately
from film-model accuracy. Add camera coverage with reviewed profiles or measured
chart data, and evaluate spectral-response-based alternatives when available.
See [RAW input and camera profiles](raw-input-and-dcp.zh-CN.md) (Chinese).

The local integration now uses RawTherapee 5.12 with shared technical PP3 settings and separate float32 sRGB and linear AP1 TIFF handoffs. Real CLI tests and independent colorimetric math check the two output branches, ICCs and ACEScct encoding. This is not a real-camera characterization test; highlight range, additional cameras, custom profiles and difficult lighting still need external measurements. See [implementation and limits](raw-handoff-and-batch.zh-CN.md) (Chinese).

Compare direct RGB fitting with a specified spectral prior using whole scenes
reserved for validation. Keep pixels from the same photograph, repeated patches
and exposure variants in the same split. The earlier eight scenes are
development data and cannot serve as an independent final test set.

Optimize hyperspectral sampling after establishing the reference. Keep scene
splits fixed, preserve spectral diversity and metamer pairs, and record sample
selection and weights. Compare reduced sampling with full reference results
before replacing the current development inputs.

The [sampling-database proposal](spectral-sampling-database.zh-CN.md) now has
finite-band feasibility, measured-coreset and synthetic-metamer pilot results.
The original pilot did not change the default prior. The selected separate
reversal/negative models are now connected to the application and bounded GPU
LUT production; see [current integration and checks](optimized-sampling-gpu-lut.zh-CN.md).
Continue comparing sampling and reconstruction methods
under matched budgets and source-group splits, retaining color/spectral coverage,
quality flags, training weights and reconstruction residuals. Do not call a
uniform RGB box a measured spectral database or treat uniform synthetic samples
as the probability distribution of real photographs. Some source reflectance
factors exceed one and require interpretation before a bounded-diffuse model.

The [local 0.1 database build](../research/sampling-database-build.md) now keeps
reversal and negative banks, selections, metadata and models separate. E100
uses a development-selected local prior and has continuous, 33/65 LUT and
spectral-reference comparisons. The negative bank independently tests input
reconstruction only; APD output and display errors remain unimplemented, with
no borrowed E100 labels. Cross-family access, source-split leakage, corrupt
spectra, fabricated negative outputs and missing-band extrapolation are tested.
Both banks retain source grids and quality flags; existing files are not
overwritten. New data sources and previously unused scenes are still needed
for final independent validation.

Film LUTs and accelerated RGB models must derive from the selected spectral-node
recipe. Compare each approximation with that recipe, including after supported
parameter changes. A look fitted independently of the material calculation is
not an implementation of those spectral nodes.

The application's internal film LUT is planned as ACEScct input to relative XYZ
D65 with a saved Y scale and viewing definition. Keep OpenDRT after this LUT and
test the unrendered result as well as the final image. Changing material, lights,
paper, spectral prior or inversion calibration regenerates the affected LUT;
changing only the OpenDRT view must not apply or bake it into the film LUT.

The first external display-baked export is planned as ACEScct input to fixed
sRGB display output. Record the supported domain, exposure range, negative-value handling, shaper and
interpolation. Test `.cube` serialization in an independent implementation or host.
Compare 33, 65 and 129 point grids before selecting a default.

The local [recipe workbench](gui-design.zh-CN.md) now checks an additional
ordinary-RGB build sample set. Its default E100 65³ material LUT followed by
the resolved display chain passes that sample check; a single 65³ CUBE with
the display baked in misses the error reference line. The user can now download
it with those errors displayed. An OCIO-native CTF export
preserves the material LUT and display operations as separate operations in
one file. CLF writing rejects the actual display chain's inverse 1D LUT.
This local prototype result does not replace the held-out spectral-scene,
whole-domain, camera-characterization or independent material validation below.

The [33-edge sampling trial](../research/lut-sampling-33.md) reaches 99% on
pooled development pixels using fitted nodes and trilinear interpolation, but
does not pass every frame or the boundary/monotonicity checks. Retain the
65-edge control as the more reliable tested candidate. Required recipe inputs
are listed in [the node-input contract](lut-generation-inputs.zh-CN.md) (Chinese).

The LUT accepts developed, profiled three-channel values in its stated encoding,
not a RAW mosaic. Keep demosaicing, per-image white balance and adaptive steps
outside the cube. Different cameras may share this film LUT after their input
transforms, but cross-camera agreement must be measured. Display-baked LUTs
already contain the selected OpenDRT and output encoding; do not apply them again.

Use the saved OCIO/OpenDRT recipe for preview, image export and LUT generation.
Verify the exact output transfer function; OpenDRT's `sRGB Display` name does not
by itself specify standard piecewise sRGB file encoding. Record configuration
and dependency hashes and test LUT boundaries against the same CPU processor.

Verify that sample diagnostics, preview and the completed LUT use the same
recipe version. Clearly label pending updates and preview quality; a stale LUT
must not be presented as the completed result of new parameters. Final exports
wait for a matching, verified generation. Validate the LUT across its declared
domain, not only on pixels from the current photograph.

The user's error reference, revised on 2026-10-26, is at least 99% of
pixels differing by at most 2/255 in all three RGB channels in the final
standard-encoded sRGB output, with display conditions held fixed. Report both
continuous output differences in 8-bit code units and differences after actual
PNG quantization. Report both relative to 99%. Record per-frame and pooled
fractions separately; a pooled pass does not imply that each frame passes.
Retain maximum errors as diagnostics, including the remaining pixels.

Later on the same day the user made LUT size selectable and this error level
informational rather than an export gate. The workbench now accepts edge sizes
2–129, with 17/33/65/129 suggestions and 65 as default. Report both error fractions,
sample count, mean, P95, maximum and file size; allow downloads below the reference
line. File integrity, missing data and unsupported computations still require
errors. Earlier notes about withholding a display CUBE describe the previous
policy, not the current behavior.

The first [IT8-derived LUT trial](../research/it8-lut-trial.md) has audited one
288-patch reflective target and generated 33/65 LUTs using its spectral second
moment as the prior. It improves that chart's training results but not natural
HSI diagnostics; do not replace the default prior or claim final accuracy from
this exploratory linear method. Keep approximation and interpolation separate.

Apply this check separately to total error against direct spectral integration
and to LUT interpolation error against the same continuous RGB calculation.
Retain delta E00 as a diagnostic. The earlier interpolation proposal was a
95th-percentile delta E00 of at most 0.5 and maximum at most 2.0; meeting that
proposal does not establish compliance with the new code-value limit. None of
these comparisons proves real film accuracy. Check dark ramps and domain
boundaries separately, and retain the pre-display results and clipping records.

Publish the settings, inputs, build instructions, licenses, revision and results
with each LUT. Pending data rights prevent distribution of the affected assets.

## 3. 5207 and optical printing

Implement 5207 independently from documented methods. Use standard Academy
Printing Density (APD) for the negative output branch, without recapture
lighting, simulated sensor responses or capture calibration. Obtain and verify
the fixed standard responsivities, coverage and normalization; distinguish
floating APD density from ADX encoding. Freeze Dmin, channel gains and the
pinned APD/ADX-to-ACES conversion before LUT export. Missing spectral bands or
standard data must block conformance claims, not be silently filled with zeros.

Fit Kodak's original Status M characteristic curves with Status M measurement
products. Model /3 now does this directly; APD is computed from transmittance
only by its output branch. The supplied TB-2014-005 contains historical APD
responsivities and a Status M-to-APD compatibility example, which /3 no longer
uses for fitting. A future density-only import could use a separately tested
stock-specific approximation, with source metric, offsets, base/fog convention,
conditioning and held-out color residuals recorded. A neutral ramp alone cannot
validate such a conversion or the material's full-color response.
Distinguish ADX round-half-up/file quantization from continuous internal values.
See [the APD/ADX source notes](apd-adx.zh-CN.md) (Chinese).

UI acceptance must check that material replacement retains its Status M metric
and that professional details identify the source and fitting residuals. APD
weight changes must not affect material fitting or optical printing. Normative
verification remains pending; see the [source and pipeline checks](5207-status-m-validation.zh-CN.md).

For optical printing, retain separate enlarger and viewing lights. Improve the
paper spectrum fit and obtain paired exposure/print measurements. The existing
paper result has large errors for some colors and needs further work.

Compare all three routes on common scenes with declared viewing conditions.
State any differences in tone or display processing that remain in the comparison.

## 4. Filters and host support

After testing the fixed reference, add CLF/OCIO configuration export and GPU processing.
Compare optimized output with float64, then measure runtime, precision and memory
on named hardware. The desktop application will use the tested processing and
export code. Host plugins can be added for a specific use case. Grain and
halation require separate filters.

OCIO is used earlier as the conversion library. Validate its configuration and
dependencies, compare CPU/GPU output, and measure any error already present in
the upstream baked OpenDRT configuration separately from our LUT-export error.
See [Color management](color-management.zh-CN.md) (Chinese).

## Measurements

Report four kinds of error separately:

| Error | Comparison |
| --- | --- |
| Material model | Prediction against independently measured film/print output with known exposure and processing |
| RGB approximation | RGB result against spectral reference on held-out spectra, including metameric variation |
| Implementation | Optimized CPU/GPU result against the reference calculation |
| LUT export | Read-back LUT result against the same fixed RGB calculation |

Neutral fits and test-spectrum fits using the test patch's own coefficients
are not independent material tests.

Record spectral errors, color differences, percentiles, worst cases, neutral
balance, hue/chroma behavior and clipping. Color metrics require the same
observer, adaptation and display conditions. Include measurement uncertainty
when available.

Test neutral ramps, exposure brackets, saturated reflectances, metamers and
illumination changes. Add licensed skin and sky scenes when available; neither
is validated by the present eight-scene set. Check units, curve direction,
missing bands, finite values, saved settings and rejection of mismatched inputs.


## Metal implementation checks, 2026-10-28

The three pointwise image routes now have a Metal float32 implementation.
Original-size image export and LUT baking share the renderer; float64 remains
the reference. The [GPU checks](metal-pipeline.zh-CN.md) cover source spectra,
characterized RGB, four VISION3 negatives, four reversal stocks, optional papers,
18 display/target combinations, exposure brackets and concurrent tile/program
lifetime. A real camera RAW verifies 2048-pixel previews and original-size PNG
readback. This demonstrates numerical implementation and file consistency,
not new material or camera color measurements. Other GPU hardware and source
materials still require their own validation.

The RAW efficiency follow-up also checks read-only TIFF mapping, per-file identity
validation, viewer-before-export decode admission, cache corruption repair and
first-photo delivery during a delayed batch import. On this Mac, the complete
Python suite has 304 passing tests, the browser-independent JS suite 64, and
CMake/CTest 2. Browser checks use the bundled Playwright with installed Chrome
because no Browser plugin is available. Local evidence is under
`artifacts/metal-preview/`; no test asset is published by these checks.
