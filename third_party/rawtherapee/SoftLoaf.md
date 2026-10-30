# SoftLoaf RAW engine

This is the official RawTherapee 5.12 source snapshot at
`a8a3d1bc7b419ed1c974c39276c97e618a4f9a1b`, with the small local changes listed
in `softloaf-source.json`. Upstream source and resource licenses are retained.
This is a separate CLI executable, not a copy of another product's private code.

The root project's default macOS build compiles the `rth-cli` target with
`cmake/RawTherapee.cmake` and installs it with the official `rtdata` resources into
`local/runtime/RawTherapeeEngine.app`. The application uses this engine for Bayer
preview and original-size export. X-Trans retains the verified official 5.12
reader and resources: the candidate integrated reader did not pass the
independent AP1 comparison at some bottom-edge pixels. `SOFTLOAF_RAWTHERAPEE` and
`SOFTLOAF_RAWTHERAPEE_PREVIEW` remain explicit development overrides. The runtime
needs the build machine's public library dependencies; it is not a standalone
signed or notarized distribution. The current hardware/runtime check is on
Apple M2 Pro and macOS 27; the installed Homebrew libraries do not establish
macOS 14.5 compatibility for this local RAW executable.

## Preview

`SOFTLOAF_RT_SUPERPIXEL=1` selects the CLI's preview mode. On ordinary three-color
Bayer sensors it skips demosaicing and gathers R, the average of the two G
samples, and B from each 2×2 quartet. RT's full-resolution black correction and
normalization precede gathering; its existing WB, DCP/ICC and output conversion
follow. There are no full-resolution demosaiced channel buffers. The `getImage`
path preserves the camera's crop, transforms and existing WB/gain behavior.
Other sensor/geometry types retain the explicit normal RT path. Full-quality
export clears this environment flag and uses the original demosaic method.

LibRaw's existing `params.half_size=1` + `raw2image()` is independently tested
against raw quartet values. It is not a parameter of `unpack()` and does not
change the `rawdata.raw_image` plane consumed by RT. Setting it alone in RT
would therefore not reduce this pipeline. The small RT adapter gathers its
already-corrected float values without quantizing them back to integer input
or replacing RT's black/WB/camera-profile processing with `dcraw_process()`.
There is no claim that the production RT path calls `dcraw_process(half_size)`.

## Threads

RT links its bundled LibRaw **reentrant** `libraw_r.a`, with OpenMP enabled.
For Apple Clang the configuration retains the frontend flags, explicitly links
libomp, and defines `LIBRAW_FORCE_OPENMP` consistently in RT and LibRaw. This
bypasses LibRaw's upstream Apple/reentrant default that otherwise disables
OpenMP. Static-only LibRaw avoids libtool dropping Apple Clang's `-Xclang` at
shared-library link time. The upstream RT unpack mutex is retained.

The application admits one expensive RAW pair at a time, gives waiting viewer
work priority over exports, and requests up to four OpenMP threads per CLI. The official X-Trans compatibility
reader is requested with two threads. Limiting the candidate reader's threads
did not reliably remove its border differences; no root cause is claimed.
Nested teams and dynamic team changes are disabled. The reentrant suffix does
not promise every decoder is parallel; actual speed depends on camera/format.
Native tests prove that the archive has OpenMP calls and its public half-size
API returns the expected quartet values. Real RAW checks cover NEF, CR3, RAF
and rotated images. Full-quality and preview caches have different signatures.

## Build

The Windows build removes an unused namespace-scope `ProcParams` from
`hilite_recon.cc`. Its constructor read `options.rtSettings.srgb` before the
global `Options` constructor on the tested MinGW build, crashing before `main`.
The object had no uses; its removal does not change highlight processing.

The X-Trans homogeneity sums now stay within the maps initialized by their
preceding loops. Upstream extended the final tile's bounds beyond those maps;
repeated official Windows developments produced different bottom-edge values.
The corrected path uses RT's existing raw-sample interpolation for the outer
11 sensor pixels. In the two tested X-T30 images this changes only the outer
four output pixels. The rest matches the original official CLI exactly when
both readers use the same complete upstream camera resources; the corrected
full output repeats exactly. This is a recorded boundary change, not a claim
of agreement with the original program's unstable edge values.

`scripts/build_windows_rt_reference.py` builds a compatibility CLI from the
hash-pinned official 5.12 source archive, with only those initialization and
X-Trans bounds fixes. It uses a generic x64 target and UCRT64 dependencies,
whose binary packages and corresponding source recipes are audited separately.
The independent comparison must include `dcraw.json`, `rt.json`,
`camconst.json` and `cammatrices.json` on both sides: the originally extracted
official Windows directory omitted additional camera tables and therefore
was not the same camera-calibration condition. No fitted color correction is
applied to make the readers agree.

From the repository root, configure and build with CMake. Required public
packages include GTKmm 3, LCMS2, Exiv2, TIFF, PNG, JPEG, FFTW3f, Lensfun,
libiptcdata, glibmm, librsvg, libomp, autoconf, automake and libtool. CMake's
`SOFTLOAF_RAWTHERAPEE` option can disable the integrated engine for CPU/core-only
builds. Build concurrency is bounded independently from runtime thread counts.

The integrated CLI exposes `--softloaf-identify <file>` using LibRaw metadata
without unpacking. The Python dispatcher uses `filters == 9` to select the
official X-Trans reader rather than assuming every RAF is X-Trans. Its actual
executable identity and compatibility reason remain in the returned metadata.
Executable changes during a running session require a restart before development.

## Two retained developments

The integrated pipeline now calls `lab2rgbOut` for the primary AP1 profile and
secondary sRGB profile from the same corrected Lab image. The secondary profile
and output path are explicit `SOFTLOAF_RT_SECONDARY_PROFILE` and
`SOFTLOAF_RT_SECONDARY_OUTPUT` environment variables. Each actual RAW data load
reports `SOFTLOAF_RAW_DECODE 1`; the Python handoff requires one such event and
the shared-Lab marker before committing the two TIFFs.

The official X-Trans compatibility executable develops once to float AP1. LCMS2
converts that result through its actual ICC to float sRGB without another RAW
decode. The full result is independently compared with original RT outputs.
For preview it is reduced after demosaicing, rather than pretending to support
the Bayer quartet path. See `docs/photo-cache.zh-CN.md` for cache ownership,
recovery and numerical checks.

## Scan handoffs

`SOFTLOAF_RT_NATIVE_OUTPUT` writes a separate native-camera uint16 TIFF before
WB, DCP/ICC or display conversion. The ordinary CLI sRGB output still follows
RT camera/as-shot color management. Both share one original RAW decode; native
highlight reconstruction is disabled. The log records sensor crop, preview
binning and rotation. This replaces the application's independent LibRaw scan
reader and the temporary LinearRaw DNG display adapter. It is not a neutral-fit
claim about real-negative color accuracy.
