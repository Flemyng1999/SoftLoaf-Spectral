# Streaming images and cache settings

2026-10-28. Branch `codex/streaming-io-cache-settings`.

The user authorizes bounded export and preview processing, functional modules,
and cache settings based on SoftLoaf Negative and Alcedo. Preserve the current
pointwise spectral models, float64 reference, ICC encodings and two retained RAW
developments. No additional source RAW decode for rendering, cleanup or relocation.
All pixel data, staging and caches remain on configured T7.

Architecture: independent sources → byte-budget block plan → frozen pointwise
renderer → scanline PNG codec → streaming verification → atomic publication.
Application remains a facade; single/batch export, image codecs, settings policy
and maintenance have separate owners. Read public Alcedo source and authorized
SoftLoaf Negative modules only for architecture, not code/profile reuse.

- [x] Add failing codec/block/streaming-equivalence tests. Implement a small libpng
  C++ ABI for row I/O with ICC/text, CRC and resource cleanup.
- [x] Add region sources, planner, quantization and renderer adapters. Map only
  export regions; preserve the documented bounded 8-bit raster decoder boundary.
- [x] Extract single/batch export and introduce streaming PNG verification and
  download I/O. Test cancellation, failure cleanup, frozen settings and seams.
- [x] Reuse the block pipeline for preview assets without full-frame float outputs.
  Keep scalar diagnostics separate, with exact selected-point values.
- [x] Add cache policy and maintenance modules, owned-root markers, inventory,
  automatic/custom/off policies, memory and reserve budgets, safe cleanup and
  verified retryable external relocation. Protect RAW stages and live work.
- [x] Add concise settings UI and native Settings shortcut; apply policies without
  changing recipe or input calibration. Browser-test save/restart/cleanup/move.
- [x] Compare all three routes and displays with the retained reference, verify a
  real full-size RAW export and decoder counts, measure peak working memory,
  then normally restart APP with user workspace preserved.

Full RAW development remains RT's own bounded-by-camera decoder job, not claimed
to have constant memory. JPEG/PNG import currently permits at most 12 MP/16 MiB;
its 8-bit decoder allocation is recorded separately from bounded float rendering.
Current effects are pointwise and need no halo. Future neighborhood/global effects
must declare their support/analysis instead of silently reusing this assumption.

Verification: core/desktop CTest 2/2; frontend Node tests 68/68; independent Chrome
settings flow at 1440×1000 and 960×650 without console errors; native Cmd+, and
folder chooser exercised, user recipe snapshots unchanged. D850 retained input
export and float64 sampled-row checks passed; measured RSS 268.1 versus 2106.7 MiB,
at the cost of 23.43 versus 11.91 seconds. Full Python regression results recorded
in the implementation document. Native App left running in cache settings.
