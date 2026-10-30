# A7R V response search and 65-cube delivery

Continuation of Issue #12, 2026-10-29. The requested independent measured camera
response is an evidential requirement, not a label that can be assigned to an
estimate, DCP, matrix, other camera, or bare-sensor QE curve.

- [x] Search primary measurement repositories and A7R V laboratory reports;
  distinguish numeric measurements, graph-only reports, predictions and aliases.
- [x] Record the source audit and missing physical inputs. Do not substitute
  A7R IV curves or DNG-derived predicted sensitivities as A7R V measurements.
- [x] Recompute the existing conditional spectral inverse at all 65³ nodes.
  Export an explicitly estimated-joint-response CUBE while the requested measured
  version remains unavailable. Include the full input encoding, frozen settings,
  credits, limitations and file hashes; no private paths in portable files.
- [x] Include a self-contained CLF with the mathematical linear-camera-to-log
  input operation. Flat-field correction remains a separate image operation.
- [x] Verify every file node, independent OCIO execution, direct float64 samples,
  current real-frame samples and Metal interpolation. Run regression checks.

The deliverable must separate file/implementation accuracy from physical camera,
illumination and material accuracy. A usable experimental file does not satisfy
the unresolved requirement for independent measured A7R V response and matching
scan-light information.

Published local experimental output uses the frozen-material density domain,
after comparing it with the initial 0–4 D grid. Both real-frame and broad material
state errors are reported, including the remaining large extreme-state errors.
All 274,625 nodes were freshly evaluated. Final Python checks: 376 passed,
8 existing dependency warnings. No new real-source RAW development occurred.
The requested independent-measurement version remains unresolved.
