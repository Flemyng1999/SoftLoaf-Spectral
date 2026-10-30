# Real negative scan calibration experiment

2026-10-29. Implements the float64 reference in
[the scan-negative design](scan-negative-lut.zh-CN.md), using user-supplied
000003 transmission measurements, RGB flat field and 5207 scans. This is a
local research path, not a released calibration or a LUT-export UI.

## Scope and decisions

Keep the existing scene-RAW pipeline unchanged. A separate retained scan
development uses linear native camera channels, without DCP, white balance,
display curves or automatic exposure. Preview development is half size; a
future full-resolution export must use its own single retained full stage.
All pixels, measurements, caches and outputs remain on T7. Private measurement
data and profiles from other products are not redistributed or imported as code.

Fit combined illumination/optics/camera response from the actual measured
transmittances, not the target's D50 XYZ table. Retain an explicit, regularized
family of nonnegative response estimates. Test held-out chart patches and
compare alternate fits on 5207 spectra; do not claim uniquely measured lamp or
sensor spectra. Correct flat field before the pointwise spectral inverse.

Recover independent CMY coefficients in the existing Status M-fitted 5207
material, preserve signed net dye spectra and require passive absolute
transmittance. APD and ADX are used only after reconstruction, with ACES 2.0
for display. Do not perform scene-to-film exposure simulation a second time.
No image-specific white balance, percentile exposure or fitted contrast may
silently alter the scientific output. Optional viewing adjustments are named.

## Tasks

- [x] Add a native LibRaw linear scan handoff and protected half-stage retention;
  reserve a separate full-stage interface, without claiming full-export validation.
  Test synthetic CFA channel values, cache reuse and corruption; inspect clipping.
- [x] Add float64 calibration/inverse modules. Test independent analytic
  transmission models, known coefficients, bounded failures, nonuniform
  wavelength integration and held-out target prediction.
- [x] Inspect real RAW chart/flat before fitting; reject saturated calibration
  samples and verify physical patch orientation. Fit response family and record
  its predictive spread; scan-system response is not a film-scene illuminant.
- [x] Correct representative 5207 frames and then the supplied roll using one
  frozen calibration. Save comparison sheets, per-frame residual/bound/noise
  diagnostics and calibrated images. Preserve borders separately from picture.
- [x] Run appropriate complete regression checks; document external evidence,
  observable results and unresolved physical calibration errors.

## Acceptance

Deliver reviewable real-frame positives plus a reproducible report, or a precise
data-based explanation where the spectral inverse fails. Synthetic roundtrip
and chart training error are separate from held-out chart error and from
unavailable independent 5207 density/color ground truth. A visually attractive
result does not establish film color accuracy. This experiment does not promise
a production GPU scan path or scan-LUT export.

## Outcome

Issue #12, branch `codex/scan-negative-calibration`. The 37-frame roll has 74
3074×2048 PNGs with exact streamed pixel/ICC/fingerprint readback. Seven new
scan-domain tests and the complete final 371-test Python suite pass; the existing
68 JS and two native tests pass. The nested target prediction and real-frame
response-model sensitivity expose unresolved physical errors, detailed in the
experiment document. No independent real-negative accuracy claim is made.
