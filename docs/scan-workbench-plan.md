# Scan calibration and one-click positive workbench

2026-10-29. Issue #12, branch `codex/scan-negative-calibration`. User authorizes
implementation, verification and normal restart. Execute inline, preserve edits.

## Contract

Add a separate “负片正相” tab to the existing AppKit/WebKit application. A first-time
dialog imports target RAW, actual transmission CSV and flat RAW. Four clicks on
A1, A6, D6, D1 patch centres define a projective 4×6 grid; inspect 24 sample markers
before fitting. CSV is explicitly transmission, wavelength nm, fractional values,
columns A1..D6; no reflection-card substitution. Save an immutable joint-response
profile. Import roll RAWs, select one unexposed border rectangle, choose negative
stock and viewing EV, click once to bake a frozen 65-cube and process the roll.
Current validated default is 5207 / Status M material / APD / ACES 2.0 / sRGB.

All data and processing temporaries stay on configured T7. Reuse `ScanRaw` half
and full stages, including already retained experiment stages; no refit, restart,
image switching, rendition eviction or repeated export may decode a third time.
Spatial flat correction remains outside the pointwise LUT. Full PNG export uses
existing region planning, mapped sources, codecs, readback and atomic publication.
No second scene exposure/development simulation. Fail closed on malformed sources,
mismatched capture metadata, unavailable storage or incompatible calibration.

## Tasks and ownership

- [x] `scanning/targets.py`: strict reference CSV, homography, independent patch
  extraction with saturation checks; test malformed units, rotated/projective
  grids and known analytic camera fields.
- [x] `scanning/assets.py`: bounded streaming upload, immutable source identity,
  metadata matching, persisted source index; no pixel algorithms in HTTP/UI.
- [x] `scanning/imaging.py`: native selection preview, flat-corrected mapped
  full source, positive preview/export using existing renderer/codecs; pointwise
  transforms with global coordinates, resampling owned by imaging module.
- [x] `scanning/service.py`: one-worker jobs, immutable profiles/LUT identities,
  persistent roll/border/results, verified resources/downloads; reuse calibrated
  material, float64 bake, Metal lookup and independent error checks.
- [x] HTTP/Application: exact scan API and streamed upload allowlists, safe local
  origin, bounded data; no change to ordinary scene-RAW endpoints/workspaces.
- [x] `design/gui-v2/scanning.js` and CSS: guided calibration, source grid preview,
  independent profile selection, filmstrip, border selection, one-click roll
  rendering, LUT download and full-resolution export; block normal quit during
  active upload/development to protect retained stages.
- [x] Test end-to-end synthetic inputs and real 000003/5207 retained inputs,
  restart, metadata failures, cache regeneration and repeated full export.
- [x] Run Python/JS/native checks, browser interaction and native application
  startup; save local evidence, document inputs/limits and show the working app.

Routine implementation choices follow this contract; no additional design
approval ceremony. The target and roll border are consequential measured inputs
and must be explicitly selected, never inferred from an arbitrary filename.

## Verification

2026-10-29: 385 Python tests, 69 JS tests and 2 CTest tests pass. Actual
000003 target and 37 scan RAWs were imported through the UI; 65-cube positive
rendering completed. A 9566×6374 PNG passed streaming pixel/ICC readback and
repeated export. Native restart restored the roll; all 40 retained RAW decode
ledgers were unchanged. The reference 5207 material was preserved. Numerical
results and limitations are recorded in scan-workbench.zh-CN.md.
