# Photo caching and two RAW developments

Issue #9, branch `codex/raw-superpixel-preview`, 2026-10-28.

The user establishes a permanent project rule: develop a RAW once for the half-size
preview, then once at full resolution for export. Switching images, editing film
recipes, repeated exports, restart and rendition eviction reuse those developments.
The count refers to RAW sensor decoding/development; import copying and integrity
checks are file I/O and are not claimed to be two operating-system reads.

Use the existing RT source and its Lab-to-output ICC operations to generate both
sRGB D65 and linear AP1/D60 from one development. Preserve half-size Bayer gathering,
WB, DCP and camera calibration. Full-size export reuses pinned full float data.
The official compatibility reader for unsupported sensors must also decode once;
its AP1-to-sRGB bridge needs independent comparison, explicit provenance and no
claim of native Bayer quartet processing. Do not roll out a failed color comparison.

Reference AlcedoStudio 18c86370's separate source/rendition stages, composite version
keys, bounded decode admission, single-flight requests, generation cancellation,
LRU memory/disk renditions and off-thread lookup. Do not copy its framework/code.
Our stronger user contract pins decoded RAW data; Alcedo's disposable thumbnail
policy cannot be applied to those stages. All pixel data remain on configured T7.

- [x] Add failing one-decode/two-output and two-phase-reuse tests; add RT shared-Lab
  output and per-development instrumentation. Compare both outputs with original RT.
- [x] Pin source-stage records atomically with cross-process admission. Never evict
  RAW developments for disk budget. Reject incomplete/corrupt committed stages;
  rebuild disposable previews from retained floats without reopening RAW.
- [x] Use float32 preview arrays with a bounded memory budget capable of holding
  neighboring 2048-short-edge images; retain float64 scientific references.
- [x] Add memory/disk rendition cache, keys including frozen recipe/input/exposure/
  display/selection/renderer identity, single-flight and verified atomic writes.
  Serve versioned binary preview assets instead of large base64 JSON for UI.
- [x] Add bounded frontend frame reuse and neighbor prefetch, foreground priority,
  immediate selection, stale-result protection and no wrong-photo placeholder.
- [x] Test restart, concurrency, eviction, corruption, disk-offline handling, cache
  invalidation and original-size export. Measure real alternating image switches,
  RAW decoder invocations and encoded payload sizes. Preserve user workspace.

The existing application preview NPZ/NPY snapshots remain valid frozen inputs;
upgrading the executable alone must not trigger another RAW preview decode.
Scientific/export verification remains separate from interactive rendition caching.

Acceptance: 328 Python tests, 67 JS tests and two CTest checks passed.
Application import/edit/repeated-export/restart test counted exactly two RAW
decodes. Independent full-output comparison on four camera files had maximum
absolute difference 2.3842e-7. Browser warmed switching had a median near 32 ms (final range 31–71 ms), with no
additional evaluation requests; first-use and native-compositor timings are
not claimed to have that latency.
