# Diagnostics, checks and Windows development

Implementation work is tracked in [Issue 13](https://github.com/Flemyng1999/SoftLoaf-Spectral/issues/13).
This document describes the development checkout, not a signed release.

## Diagnostics

The service writes rotating JSON lines to `artifacts/application/logs/events.jsonl`.
Each record has a UTC time, session identifier and monotonic elapsed time. Jobs
record admission, start, changed progress, failure and terminal state. Terminal
records include elapsed milliseconds. Request failures, uncaught exceptions and
D3D12 recovery record stable codes and exception locations.

The default limit is five files of approximately 2 MiB each. Structured fields
are allowlisted and string lengths are bounded. Exception messages, local paths,
image pixels, request bodies, credentials and user-entered names are excluded.
These records stay local. The native launch log remains a separate startup aid.
There is no remote telemetry service or crash-dump uploader.

Rotation, concurrent writes, job failures, HTTP failures and redaction have tests.
An actual 13-image preview preparation was also read back from the application:
one job reached 13/13 and recorded a complete terminal state and elapsed time.
This observation is not a RAW-decoding benchmark.

## Reproducible checks

Install `requirements-quality.txt`, build the native targets, then run:

```sh
python scripts/run_checks.py --profile public
python scripts/run_checks.py --profile integration
```

`--build` and `--report` select the native build and report directories. The
public suite is declared in `quality/suites.json`; it uses synthetic inputs and
independent numerical and contract tests. The integration suite requires the
licensed local materials, reference assets, optimized sampling models and
platform runtime. It does not download substitutes for missing inputs.

The runner checks generated HLSL against its Metal source, runs CTest, JavaScript
tests and pytest, and saves logs, JUnit, coverage and a summary even on failure.
A successful process with zero tests, skipped required checks or failed test
cases is rejected. Statement coverage currently measures `spectral_app` and
`spectral_lut`; it is not a measure of scientific accuracy or whole-repository
coverage.

The CI workflow builds C++23 and runs the public checks on Linux, macOS and
Windows. A separate Chromium job tests language switching and failure rollback.
Reports are retained when a job fails. The workflow has been checked through
local clean-source execution and 303mini execution; it has not yet been pushed
and observed running on GitHub Actions.

Actual GPU validation is separate from hosted CI. On Windows, run:

```powershell
$env:SOFTLOAF_CORE = "D:\SoftLoaf-Spectral\build\Release\softloaf_core.dll"
python -m pytest tests/test_d3d12_backend.py -q --junitxml=d3d12.xml
```

This is a mandatory hardware check on Windows: a missing D3D12 device is a
failure. The Windows-only suite is excluded explicitly from macOS integration;
its absence there does not certify Windows GPU behavior. No hosted GPU runner
has been registered as part of this work.

## Compute backends

Owned native targets require C++23, without compiler language extensions. The
float64 C ABI remains version 1. Upstream RawTherapee is built as a separate
project with its upstream compiler settings.

macOS uses Metal. Windows uses a D3D12 hardware adapter and bounded float32
compute dispatches. HLSL kernels are generated from the owned spectral and scan
kernels; the generator covers a deliberately limited source subset, checked by
source hashes and hardware comparisons. Shader hashes are recorded by the renderer. LUT baking,
image rendering and scan geometry share the backend transport.

OCIO's original 1D/2D/3D textures are bound directly. HLSL uses float32 loads and
interpolation for those tables; hardware sampler fractional precision did not
meet the texture comparison budget. ACES 2.0 uses the pinned official CG config
v4.0.0. There is no additional display LUT bake. The local spectral prior uses
an LDL solve of its positive-definite regularized Gram matrix, avoiding the
unstable determinant inverse.

CPU processing remains selectable with `--compute cpu`. Windows defaults to
`--compute auto`: unavailable devices or libraries select CPU, while compilation
or dispatch failure disables the GPU and retries the frozen operation once on
CPU. Validation errors stay errors. The selected calibration, retained RAW stage
and pointwise transform are preserved; rendition identity changes on recovery.
Strict hardware checks use `--require-gpu` and never pass through CPU fallback.

The backend retains bounded buffers and waits on a fence before reuse. A timed-out
command context is quarantined rather than freeing resources still in flight.
Device release happens explicitly before DLL unloading. Reported GPU duration
comes from timestamp queries; wall time additionally includes transfers and
host work. Fault tests inject compilation and dispatch failure; they do not
simulate every display-driver failure or physically remove a device.

## Settings language

Settings contains System, Simplified Chinese and English. The choice is stored
atomically in `local/ui-settings.json`, separately from recipes and calibration.
Main controls, scan calibration steps, cache settings and dynamic status text
switch without rebuilding the scientific model. Recipe names, filenames and
material data are preserved. Untranslated source strings retain their Chinese
text; the catalog is extendable. Native menus receive the effective language
through the local UI bridge.

Tests cover switching both ways, dynamic updates, user values and failed writes.
The running application's settings were also exercised through its browser UI:
English persisted after reload, and Simplified Chinese was restored afterward.
The macOS native capture service was unavailable during the final readback, so
native-menu appearance was compiled but not visually verified.

The 2026-10-30 follow-up expanded the English catalogue for plot labels, SVG
axes, pipeline formulas, units, material explanations, built-in image names and
dynamic status/error messages. User-authored recipe and file names remain
excluded. The actual Windows WebView2 page was traversed through 49 material
node/tab states: no visible Chinese remained in English mode. The language
menu retains the autonym “简体中文”. Three isolated Chromium tests check live
updates, SVG labels, dynamic counters, preference failure rollback and a
Chinese/English round trip without changing user content. The Browser plugin
was unavailable; Chromium and the real Windows WebView2 were driven through
Playwright in separate test workspaces.

## Windows development window

The independent 303mini build lives in `D:\SoftLoaf-Spectral`; it does not modify
other applications. It uses MSVC 19.44.35228, SDK 10.0.26100.0, an AMD Radeon
hardware adapter, and the official WebView2 SDK 1.0.4191.47. libpng and zlib are
installed in that build's own vcpkg directory.

Configure with `SOFTLOAF_RAWTHERAPEE=OFF`, a Python environment installed from
`requirements-quality.txt`, and `SOFTLOAF_WEBVIEW2_SDK` pointing to the extracted
official SDK. Set `SOFTLOAF_WEBVIEW2_CACHE` on the configured external pixel-data
volume for actual image work; production startup also requires external storage
settings. A build-directory browser profile is allowed only by the fixed,
pixel-free shell check. `SOFTLOAF_DESKTOP=ON` builds `SoftLoaf Spectral.exe`; a generated
`runtime.ini` locates the checkout, Python, native library and browser cache.
The window starts its own loopback service and accepts only its local origin.
Close requests flush the session and respect pending edits and work.

`--shell-check --report <path>` hosts a fixed synthetic page, checks its DOM with
WebView2 and exits. It does not load scientific data or claim the complete RAW
application works. This check passed in the account's desktop session with exit
code 0. An SSH-only session did not provide the same controller behavior. The
temporary desktop self-test task was removed afterward.

On 2026-10-30, the user authorized copying the T7 camera RAW test dataset onto
303mini's D drive for Windows testing. This is a machine-specific storage
exception; macOS pixel data and processing temporaries remain on T7. The copy
contains 1,274 files (47,028,134,375 bytes), including 1,272 RAW sources and two
LUT companions. All destination sizes and SHA-256 hashes match the source
manifest. Originals remain on T7. The local verification report is
`artifacts/quality/windows/raw-transfer/verification.json`; no RAW dataset is
bundled with the repository.

The vendored RT 5.12 CLI builds with its bundled reentrant LibRaw and OpenMP in
an independent MSYS2 UCRT64 environment. A pre-main startup crash was traced to
an unused global `ProcParams` in upstream highlight reconstruction: it read
`Options` before construction. Removing that unused object allows CLI startup.
Runtime assembly must install `rtengine/camconst.json` and rename the platform
`options.win` file to `options`, as upstream's install rules specify. Copying
the `rtdata` directory alone does not provide a complete runtime.

Five real sources were exercised: Canon EOS R6 CR3, Nikon D850 NEF, Sony A7S
ARW, Fujifilm X-S10 RAF and rotated Nikon 1 S2 NEF. Ten retained stages each
record one RAW load and two float32 ICC handoffs from shared Lab. A restarted
probe reused all ten stages without development. The four Bayer previews are
half-size; X-S10 is X-Trans and the integrated probe falls back to full demosaic.
That initial probe did not validate the separate official X-Trans compatibility
reader or application preview reduction; the native-application follow-up does.

Each stage's 3,149 sampled points was compared with an independent
colour-science ACEScg D60 to sRGB D65 Bradford/IEC conversion. Display values
were clipped to [0,1] for comparison; the largest error was 0.103 in 8-bit code
units. Both embedded ICC profiles, float32 type and finite values were checked.
These checks validate the handoff, not camera spectral accuracy.

Full-stage point grids from three previously retained macOS developments were
also compared. Canon R6 and D850 had all 527 sampled pixels within two code
units; maxima were 1.04 and 1.29. Nikon 1 S2 had 98.29% within two units, P99
2.46 and maximum 10.37. It fails the sampled-grid 99% reference gate. The cause was unresolved;
the Windows RAW color comparison was therefore not fully accepted at that stage. The complete-image follow-up below resolves this gate without changing its tolerance. The report
`artifacts/quality/windows/raw-transfer/raw-acceptance.json` separates successful
reading/handoffs from this failed reference comparison. Sony and Fujifilm did
not have retained macOS references available and were not decoded again on
macOS merely to create them. Earlier probes with an incomplete Windows runtime
remain in a separate directory and do not count as accepted results.

At that initial probe, licensed material installation and a real-image end-to-end
Windows desktop run had not been verified; the follow-up below covers them. The existing directory named `T7 Touch` on the internal D
drive is not treated as the macOS external data volume. No installer, signing
or release has been performed.

## Recorded checks

Reports remain under `artifacts/quality/`; they are local artifacts, not shipped
material data. The 2026-10-29 checks include:

- The final strict macOS integration run passed 432 Python, 77 JavaScript and
  2 CTest cases without skipped required checks. Statement coverage of
  `spectral_app` and `spectral_lut` is approximately 90%.
- A fresh 25-case Metal comparison after the LDL change, against float64 and
  official OCIO CPU output.
- Clean-source public checks without `local/` or material assets: 99 Python,
  77 JavaScript and 2 native cases on macOS; Windows has one native CTest case.
- Two real Chromium language tests.
- Thirteen real D3D12 checks on 303mini: material routes, APD/ADX to XYZ, local
  and root spectral priors, original OCIO textures, ACES 2.0 sRGB and Display P3,
  plus compile and dispatch failure recovery. Complete-route float32 tolerance
  is 3e-4, matching the existing Metal gate; primitive and texture tests use
  tighter 3e-6 limits.
- The Windows native window/WebView2/script/exit self-test.

These are implementation and numerical checks. They do not establish independent
real-film color accuracy, exhaustive hardware compatibility or complete test
coverage. Independent material and real-capture validation remain necessary.

## References used

The review considered AlcedoStudio's public CI and diagnostics tests, and the
separation of diagnostics, settings and release checks in SoftLoaf Negative.
Private implementation code, profiles and project instructions were not imported.
Windows interfaces follow Microsoft's D3D12 and WebView2 SDKs.


## Windows RAW application follow-up

The full application exposed issues absent from the synthetic native-shell
check. Automatic cache sizing used POSIX `sysconf`; Windows now queries
`GlobalMemoryStatusEx`, with a conservative bounded budget if unavailable.
The Windows virtual-environment Python launcher delegates to a child process;
ready-file ownership now accepts only the launch process or its descendants
from a process snapshot. The stale ready file is removed before launch, and
malformed, unrelated and cyclic process chains are rejected. These paths have
platform and native regression checks.

`local/raw-runtime.json` (schema 1) declares the integrated and official RT
executables and an optional dependency `dll_directory`. macOS keeps its bundle
layout; Windows uses native executable locations and adjacent resources.
`SOFTLOAF_RAWTHERAPEE_REFERENCE` may override the official compatibility reader.
CLI environments prepend their dependency directories, ICC paths use forward
slashes inside PP3, and RT settings/cache stay beside the retained stage.
LCMS2 resolves the Windows DLL explicitly, including an optional
`SOFTLOAF_LCMS2_LIBRARY` override. This is a development runtime, not a packaged
installer.

Ordinary Windows accounts may lack symbolic-link privileges. A typed RAW
staging path now falls back to a hash-verified copy for that specific error;
other filesystem errors still propagate. The decode-attempt ledger is written
only after source staging and settings are prepared, immediately before the
CLI invocation. The earlier failure was traced to source staging before any
full-resolution RAW decoding; its record was archived separately.

Nikon 1 S2 was also compared using all 14,122,000 retained macOS pixels.
99.0327% were within two code units, P99 was 1.9525 and the maximum was 35.675.
Thus the full-image comparison passes the declared 99% / two-code criterion,
while isolated pixels still differ substantially. The original 527-point grid
is retained as a failing diagnostic, not deleted or relabeled. The integrated
Windows output agrees with the unmodified official Windows RT 5.12 AP1 output
within 0.0000542 across the full image. Existing official and current macOS
references agree at the sampled coordinates. The observed differences also
exist between the official platform implementations; their precise internal
cause has not been established. No tolerance was increased.

The unmodified official Windows 5.12 installer was downloaded from RawTherapee
and checked against its published SHA-256
`fe0ab7e0e647130641a13cfaf54543c63efcc62a8da97acb9cde92c1bc255b8c`.
It was extracted into a private test runtime without installing over another
application. The integrated X-S10 probe and official Windows output differ
mostly at rare pixels: AP1 P99 is zero, maximum 0.004486. The production
X-Trans path continues to use the official executable and a single-decode
float AP1 → LCMS2 sRGB handoff, then reduces the preview without another RAW
decode.


## Native application and exported images, 2026-10-30

After the owner approved the test-only scientific runtime copy, 132 material,
model, display and icon files (71,411,550 bytes) were copied and hash checked.
The required ACES and spektrafilm license records were also installed. No user
session or scanning calibration was copied.

The actual Win32/WebView2 application imported a Canon R5 Bayer CR3 and Fujifilm
X-E1 X-Trans RAF through its file input. Both filmstrip and main preview loaded.
The R5 full image is 5079 × 3374; the X-E1 is 4938 × 3274. Both exported APD PNGs;
the R5 also exported E100 reversal, 5207/Ultra Endura optical printing and
Display P3 APD PNGs. The hardware backend was AMD Radeon D3D12. All five files
passed streaming pixel/ICC/frozen-fingerprint readback and file SHA-256 checks.

A separate Python model with the native core disabled computed 551 sample
points per exported image in float64. All sampled results were within two
8-bit codes; the maximum was one code for E100 and zero for the other four.
The retained RAW AP1/sRGB handoffs were also checked with colour-science's
ACEScg D60 → Bradford → sRGB D65/IEC conversion: sampled maxima were 0.0285
codes for R5 and 0.0346 for X-E1. Injected D3D12 dispatch failure with actual
RAW samples retried on CPU and matched the same float64 calculation, preserving
the frozen input and recipe.

A Display P3 APD 65³ CUBE passed parsed-file integrity, exact readback and
independent execution checks. Its 27,098 interpolation conditions were all
within two codes (continuous maximum 1.566 codes). This is an implementation
and interpolation result. Against the separate historical spectral audit,
only 50.65% of 16,128 exposure-variant conditions were within two codes; the
RGB spectrum approximation remains a source of error. Neither test establishes
independent real-film accuracy.

A normal native application restart followed by preview switches and two more
full-size exports left all four retained half/full RAW manifests and ledgers
unchanged. The new service session recorded no RAW-development start and no
uncaught exceptions or browser errors. Actual RAW starts and terminal records
now have stage, hashed source ID and elapsed time, without source paths.

The R5 optical-printing export took 9.319 seconds in this run. E100 took
398.754 seconds: 256.002 GPU seconds and 392.280 renderer wall seconds, using
the frozen local_512_128 prior and 4,218 bounded dispatches. This is a significant
remaining performance limitation on 303mini; it was not a hang or a second RAW
decode. APD GPU time was about 2.2 seconds. These are single-run observations,
not a general benchmark; encoding, readback and contention affect total time.

The final public Windows gate passed 108 Python, 78 JavaScript and two native
cases with no required skips. The targeted macOS RAW/cache regressions passed 32 cases, with three native
cases and three independent browser cases also passing. Local evidence is
under `artifacts/quality/windows/raw-followup/`; pixel screenshots remain on the
configured external test storage. Temporary desktop launch tasks and the remote
browser-debug session were removed after testing. The dataset and retained RAW
stages remain available on D:. No installer, signing or publication is implied.

## RDP interaction check, 2026-10-30

The Windows executable was also launched manually inside the owner's open
303mini RDP session. Canon R5 and Fujifilm X-E1 retained photographs switched
through the filmstrip, and 5207 APD and Ultra Endura previews rendered visibly.
This session used D3D12 and reached service readiness in 3.801 seconds. It
recorded no RAW-development starts or request failures.

A fresh RDP-triggered 5079 × 3374 Display P3 APD PNG passed streaming pixel,
ICC and frozen-recipe readback in 16.188 seconds, including 2.234 GPU seconds.
Decoder bytes were zero. A fresh 65³ APD CUBE also passed parsed-file integrity
and exact readback; all 27,098 interpolation conditions were within two codes,
with continuous maximum 1.566 codes. These checks retain the scientific limits
described above. Numerical evidence is in
`artifacts/quality/windows/rdp/export-and-session.json`.

The actual LUT generation progress and interpolation summary exposed two
additional untranslated dynamic strings. Both were fixed and deployed to the
Windows source tree. Following the owner's approval to refresh the unsaved
test window, a second generation visibly displayed “Generating 65³ LUT…” and
“Interpolation: 100.00% within 2/255 · Max 1.57 codes”. The updated JavaScript
suite passed 79 cases, and the independent browser suite passed three cases.

Fresh import was not completed in this manual run: the native file chooser
opened, but the computer-control tool lost its mouse target and the chooser
was cancelled. The earlier native file-input import checks remain separate
evidence. RDP coordinate control recovered in full-screen mode. Smaller-window
comparison headers can wrap differently and leave unequal A/B image areas;
the initial native window can also extend beyond the remote work area until
maximized. The comparison-layout issue remains open; initial window bounds
were subsequently fixed below. The application was left running.

## Windows high DPI rendering, 2026-10-30

The original executable's extracted manifest contained only `asInvoker`; it
declared no DPI awareness, and the window procedure did not handle
`WM_DPICHANGED`. The application now embeds `PerMonitorV2` with the older
`true/pm` fallback, follows the suggested physical window rectangle on DPI
changes, and resizes the WebView2 client bounds. WebView2 retains its default
automatic rasterization-scale tracking. Initial window dimensions are scaled
from logical units and constrained to the monitor work area, including negative
secondary-monitor coordinates. No global Windows or RDP scaling preference was
changed.

The DPI test checks the activated manifest policy and work-area layout. It
also requires the actual PMv2 thread context when running on a visible window
station. An SSH/service window station on 303mini reported PMv1 even with the
correct manifest; that is recorded as a noninteractive result, not an
interactive rendering measurement. The same executable launched manually in
RDP reported PMv2. A controlled executable with the old manifest failed the
policy test. The three Windows native tests passed after the fix.
Numerical records and native test output are retained in
`artifacts/quality/windows/rdp/dpi-verification.json` and
`artifacts/quality/windows/rdp/windows-dpi-native.xml`.

The old application exited normally through its session-save path. The new
build was launched manually in RDP, restored 5207 APD and rendered visibly
sharper text, controls and SVG curves. It remained open in
`D:\SoftLoaf-Spectral\build-dpi\Release`; the usual `build\Release` executable
was also rebuilt with the same fix. The new service selected D3D12. Moving
between physical monitors with different scaling factors has not been tested.

The implementation follows Microsoft's
[process DPI manifest guidance](https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process),
[WM_DPICHANGED contract](https://learn.microsoft.com/en-us/windows/win32/hidpi/wm-dpichanged)
and [WebView2 scale tracking](https://github.com/MicrosoftEdge/WebView2Feedback/blob/main/specs/RasterizationScale.md).
