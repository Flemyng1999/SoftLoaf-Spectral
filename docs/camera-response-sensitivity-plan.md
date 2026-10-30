# Camera-response sensitivity comparison

Issue #12, continuation on `codex/scan-negative-calibration`, 2026-10-29.
The user authorizes comparing A7R V predictions, A7R IV and other camera curves
with the current joint target fit on the same 37-frame 5207 roll. Execute inline.

The frozen material, measured border, RAW handoff, flat field, APD/ADX and ACES 2.0
remain unchanged. Per-response border gains are recalculated once to match that
same observed border, never independently per image. No additional RAW decoding.
All numerical data, pixels, caches and outputs stay on T7.

- [x] Retrieve source JSONs and licence; retain file hashes and measurement metadata.
  A7R V is a 400–700 nm, 10 nm prediction; Weta IV/III/II are 380–780 nm,
  5 nm relative responses. They do not become measurements of the user's A7R V.
- [x] Add tested response loading without extrapolation, common effective-light
  fitting, border alignment and display-difference summaries.
- [x] Use a shared 400–700 nm comparison band. Separate current full-band joint
  response, cropped joint response and full 391–730 nm A7R IV controls.
- [x] Fit a nonnegative common energy/optics spectrum for each fixed response,
  with a predeclared 10 nm Gaussian basis and ridge 0.1. Estimate channel scales
  on training patches; six physical-column holdouts assess same-card prediction.
  This is an estimated effective illuminant, never measured lamp SPD.
- [x] A second arm freezes the A7R V-derived effective illuminant and changes
  only response shape (and the one common-border alignment). Retain both arms.
- [x] Recompute 65³ tables from float64 spectral inverses; sample direct inverses
  on every frame so lookup error cannot masquerade as camera sensitivity.
- [x] Render full 2048-short-edge images for the primary recalibrated arm and
  controls; representative fixed-light full images plus complete-roll comparisons.
  Use the same global +2 EV viewing for readable images and also report 0 EV
  sample differences; no per-image white balance or automatic exposure.
- [x] Produce contact sheets, source/response/light plots, per-frame metrics and
  a factual report. Display ΔE00 is relative to the current result, not ground
  truth. Include invalid solutions, domain bounds and clipped/noisy regions.
- [x] Verify readback, Metal/float64 interpolation, retained RAW records, scientific
  synthetic tests and relevant regression; inspect the comparison images.

Unknown optical transmission, original camera-response measurement units/lenses,
green-flat extrapolation and same-roll Dmin remain limitations. Interpret source
relative responses as effective energy response under the rawtoaces/DNG forward
model convention, without treating them as absolute QE. Restrict the prediction
to its provided support rather than inventing spectral tails. The result cannot
select the physically correct camera/lamp pair without independent measurements.

Completed: ten 65-cubes, 271 full PNGs, 37 frames / 15,725 direct samples,
no real-source RAW development; all pixel readbacks and source/LUT hashes verified.
Python 380 passed, eight existing warnings. Browser mode/frame transitions and
five loaded images verified; scientific reference panel visually inspected.
