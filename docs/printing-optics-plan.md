# Optical printing update

Issue #2, 2026-10-28. Retain Status M negative fitting and the independent APD
branch. Implement the requested printing refinements using separately identified
optical data, not paper dyes relabelled as filters.

1. Add hash-pinned local KG3 and Edmund CMY transmittances, optional lens data,
   source/licence records and explicit source-tail assumptions. Independently
   implement partial-insertion dichroic filtering; do not copy upstream runtime.
2. Add versioned printing settings. Existing recipes remain on legacy-v1;
   new printing recipes use spectral-v2. Switching is explicit and undoable.
   New optical settings do not change negative material fitting or APD.
3. Support optional optical transmission CSVs, a frozen optional preflash
   spectrum and wavelength-dependent paper minimum-density data. Retain source
   identity and distinguish processed model data from original measurements.
4. Preserve the legacy calculation, frozen exposure denominators and display
   contracts. Perform the modern exposure sum before the existing float64 C++
   material kernel; compare it with independent NumPy integration.
5. Update the workbench, curve viewer and CSV imports without new sidebar nodes.
   Group optical configuration under the enlarger. Expose paper base at paper.
6. Test old recipe stability, filter boundary conditions, no double filtering of
   composite imported light, preflash additivity, material/route independence,
   source identity, paper density fits and independent exported CUBE execution.
   Compare colored patches and scene output; do not claim real-film accuracy.
