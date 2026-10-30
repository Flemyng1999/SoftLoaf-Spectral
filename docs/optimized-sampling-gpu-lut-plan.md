# Optimized sampling and bounded GPU LUT production

Issue #11. User authorizes direct upgrade of current recipes without backup.
Retain the float64 prior implementations and explicit legacy mode as numerical
references; do not create user backup documents. Preserve all other edits.

- [x] Pin and load the existing local_512_128 reversal prior and independently
  selected source-balanced root3 negative prior. Validate family, source grid,
  model/report/database hashes and selected-model metadata. Record scope: E100
  development selection versus negative input reconstruction, not APD accuracy.
- [x] Add a recipe input-model identity, migrate untagged recipes once, and use
  matching CPU float64 and fused GPU reconstruction in preview, image export and
  LUT production. Keep measured-spectrum calculations independent of this prior.
- [x] Implement exact-neighbor local regularized solves and signed root features
  in Metal; verify reconstruction/exposure and all three material/display routes
  against the retained CPU oracle, including dark/negative/HDR/boundary inputs.
- [x] Add export-owned CUBE block generation, mapped storage, streaming text I/O,
  independent readback and atomic publication. Eliminate full meshgrid and Python
  list-of-rows parsing from the application's LUT path.
- [x] Use GPU blocks for continuous truth, tetrahedral interpolation, display and
  spectral-vs-RGB verification. CPU remains the bounded independent float64/OCIO
  checker and statistical reducer, not a hidden production fallback.
- [x] Validate dataset-held-out records with separate approximation/interpolation/
  total errors; do not use validation records to fit. Re-evaluate material labels
  from current recipes instead of reusing historical E100/unfinished APD labels.
- [x] Test selected grid sizes including 129, final file execution, mismatch and
  failure paths, actual GPU dispatch and memory. Check app workspace upgrade and
  normal restart. Keep all spectral/LUT pixel data and staging on T7.

Verification: Python 364, JavaScript 68, CTest 2; 26 material combinations /
156 cases with float64, APD and independent colorimetric checks. Current-family
audit means improve on all three routes. Final 129³ exports: reversal 384.9 MiB
/ 15.59 s; negative 380.1 MiB / 13.33 s, including the model and independent
verification. Browser flow reaches a verified downloadable CUBE without console
errors. User requested direct workspace upgrade, no backup creation.
