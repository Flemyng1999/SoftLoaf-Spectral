# Scan exposure and speed follow-up

2026-10-29, Issue #12, existing task branch. Preserve current calibrations, source
stages and explicit exposure choices. No additional approval or delegation needed.

Measured baseline on the retained first real frame: 4.88 s preview, 4.10 s source
preparation, 0.76 s render/PNG/readback, about 0.13 s Metal dispatch. Repeated
external NPY creation/mapping/flush dominates. 4096 float64 material inversions
take 0.32 s. The model's declared camera-stops-zero neutral produces ACES Y
0.24254, so +2 EV is not a missing fourfold pipeline normalization. It was an
explicit experiment-wide viewing choice; neither Dmin nor the transmission
target determines the real photographed scene's exposure.

Work:

- Test and implement a halo-aware resampled region source in the imaging module;
  use it for scan previews without a full-frame temporary NPY. Preserve the
  original bilinear/global-coordinate phase and float32 handoff. Bound source
  halo memory as well as output pixels. Keep the full-size source unchanged.
- Cache the frozen camera-density-to-linear-ACES grid separately from display
  exposure. Verify its hashes/domains/order, preserve a float64 direct oracle,
  and keep per-export direct sampling plus independent CLF readback. An EV edit
  must not repeat all material inversions. Store all data on T7.
- Make new-roll exposure compensation start at 0 EV, preserve existing explicit
  +2 EV results, and describe it as compensation rather than a required standard.
  Do not invent per-photo auto exposure or call model neutrality real accuracy.
- Render the selected photo first; show completed photos while the roll continues.
  Cache hits should avoid reprocessing source pixels and repeated full hash reads,
  while changes to original/retained files must still be detected.
- Measure cold/warm paths on the same real sources and frozen colors. Compare
  streamed output with the previous preparation and float64, verify cache clear,
  original-size output, persistent RAW ledgers, Python/JS/native regressions and
  the actual AppKit/WebKit workbench before completion.


Implemented extension: combine radial lens distortion, quarter turns, normalized
crop and resampling in one halo-aware source lookup. Flat correction is evaluated
at each original source neighbour before sampling; Metal executes sampling,
camera density and the LUT together. Preview and full export share the sampler.
Public Lensfun provides an independent coordinate oracle; no private code or
profile is imported. New central-normalized flat grids are independent assets;
changing the flat refits the transmission target before applying the roll.
Geometry is excluded from 3D color LUTs. Tool entry buttons are inline SVG icons.

Verification and measured limits are recorded in docs/scan-workbench.zh-CN.md.

2026-10-29 import follow-up: actual roll-02 native import is fully serial, about
5 seconds/frame. File timestamps show 2.3–2.5 seconds in RAW development,
0.65 seconds for the 1024 preview and 0.17 seconds for its thumbnail, plus
copy/upload and request polling. Preserve the live import. Add a bounded pair
of preview preparation workers, pipeline one file upload with preparation,
register each frame before preview completion, and publish completed frames
immediately. Keep calibration/LUT/full export on their existing single worker.
No redecode for benchmarking; retain every immutable stage and decode ledger.
Native restart must wait for the current batch to finish and use normal session
flush. Then verify SVG tools and the reference drawer in the actual native window.

Additional interface requests: replace A1/A6/D6/D1 instructions with a 24-patch
orientation aid derived from the imported transmission measurements. Rotate or
mirror the aid, preserve the measured patch order and source coordinates, and
highlight each next corner. The chart photo uses RawTherapee sRGB from retained
native pixels and metadata, never display RGB as calibration samples. Move the
calibration entry to the first vector tool and remove the sidebar RMS summary.
Use embedded camera previews for immediate scan browsing, with native-channel
sampling remaining an explicit separate view. Extracting embedded JPEG is not
RAW pixel development. Successful test runs must remove their own generated
pixels so UUID test directories cannot accumulate indefinitely on T7.
