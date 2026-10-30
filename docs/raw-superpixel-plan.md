# RAW superpixel preview

The user requests a 2×2 Bayer preview without demosaicing, then proportional
resampling only when the short edge exceeds 2048. Keep smaller decoded previews
at native size. Full-resolution export continues to develop the original with
the existing full-quality settings. No embedded JPEG substitutes for either
color handoff. This replaces the previous 2048 long-edge preview policy.

Use pinned RawTherapee 5.12 source. A small, separately recorded engine patch
adds a preview-only Bayer quartet gather before its existing white balance,
DCP/ICC and output transforms. Select it explicitly only for preview. Both sRGB
and AP1 outputs come from the same settings and retain float32 encoding. CFA
colors and active bounds determine quartet membership, not assumed RGGB order.
Unsupported geometries and other sensor types retain an explicit RT path.

- [x] Add failing tests for short-edge sizing, native smaller sources, preview/full
  cache separation, original dimensions and the Bayer quartet gather.
- [x] Build the patched local RT CLI and retain its upstream license, revision,
  patch and reproducible build instructions. Do not import private application code.
- [x] Route import/cache migration through preview development; defer full-size
  development to export. Freeze and identify both processing modes independently.
- [x] Check Bayer layouts, two-green averaging, odd crop boundaries and rotations;
  compare real RAW preview with independently reduced full-quality output,
  reporting color/detail differences instead of claiming identical pixels.
- [x] Check real cold import timing, original-size image readback, unchanged GPU
  calculation precision, UI selection/preview/cache restoration, then open APP.

The user further authorized vendoring the official RT CLI source directly. It
now lives in `third_party/rawtherapee` and builds as an isolated root CMake
ExternalProject. This supersedes the initial plan to keep only a patch outside
the source tree. Reentrant LibRaw and explicit Apple OpenMP are both built and
verified. LibRaw's native half-size API is an independent raw-quartet reference;
RT still needs a small adapter because it consumes the unpacked CFA before the
LibRaw postprocessing stage. Do not claim the RT production path simply invokes
`dcraw_process(half_size)`.

Acceptance completed on this Mac with 318 Python tests, 64 JS tests and two CTest checks.
Rendered RAW imports retain 1698×1131 for R6 and produce 3076×2048 for D850;
reload preserves selection and exposure. A 3396×2262 Metal export reads back
exactly with matching ICC. All data files and test temporaries use the configured
T7 volume. X-Trans deliberately retains the official reader because the candidate
reader failed independent edge-pixel comparisons; limiting threads was not a fix.
