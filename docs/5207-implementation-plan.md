# 5207 calculation and pipeline audit (Issue #2)

Historical /1 plan. The current /3 implementation follows the
[direct Status M fitting plan](5207-status-m-refit-plan.md) and its
[validation record](5207-status-m-validation.zh-CN.md); APD is output-only.

Implement the already selected APD and optical-printing routes. Retain the
existing E100 calculation and all user recipes. No recapture equipment enters
the APD route; Status M compatibility is automatic and stock-specific.

1. Extract 5207 H-1-5207t (July 2015) and Ultra Endura E-4020 (July 2003)
   directly from the published vector plots. Retain points, axes, clipping,
   source hashes and model assumptions in ignored local assets. Do not import
   the historical private program or its profiles.
2. Independently implement float64 APD integration, automatic Status M target
   conversion, Dmin handling, ADX scaling and the complete ACES v1.2 ADX16
   transform. Check matrix orientation and toe behavior against OCIO's separate
   implementation. Do not quantize internal densities.
3. Fit effective negative dye amounts to the converted neutral densities,
   keeping the measured/published base spectrum. Document short-wave dye-tail
   assumptions and quantify APD weighting there. Do not claim normative SMPTE
   conformance or measured full-color accuracy.
4. Implement independent printing and viewing illumination, pointwise filter
   densities, paper sensitometry and a reflection-density approximation.
   Fit only the declared neutral calibration. Test against held-out finished
   print spectra where applicable; those do not validate exposure response.
5. Connect all nodes to actual intermediates, controls, CSV replacement, preview,
   image export and the existing selectable LUT builder. Preserve old drafts
   and old recipe files; attach current material identities on validation.
6. Test black/gray/color ramps, energy and density conservation, exposure signs,
   branch isolation, source mismatch and custom materials. Compare float64 and
   C++ intermediates. Read exported LUTs back independently. Measure RGB-prior
   approximation separately from interpolation against measured spectra.
7. Inspect the rendered application and record remaining physical/model limits.
   Update current owning docs and supply a concrete audit report with results.
