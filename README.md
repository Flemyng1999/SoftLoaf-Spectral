# SoftLoaf Spectral

[中文说明](README.zh-CN.md)

**The desktop runtime and scientific inputs are distributed separately.**
Alpha.1 is source-only; alpha.2 adds standalone macOS arm64 packaging; alpha.3
adds the Windows x64 runtime preview. See [Releases](https://github.com/Flemyng1999/SoftLoaf-Spectral/releases)
for published downloads and platform requirements. Neither channel includes film/paper curves, frozen
spectral models, photographs or scan calibrations.
Public core checks run without those inputs; the application needs a prepared
scientific-data directory. See [source build inputs](docs/source-release.md)
and [installer setup and packaging](docs/installer-setup.md).

The Windows preview is unsigned and requires WebView2 Evergreen. Its installed
runtime passed RAW preview/export, D3D12 and CPU execution, LUT file readback,
cache retention and uninstall/reinstall checks. Numerical and physical accuracy
limits remain; see the release's `Windows-Validation.json` and `Known-Limits.md`.

The workspace opens Film emulation, followed by Negative conversion and Spectra.
New recipes, stock changes and reopened saved recipes use the film's reference
capture light, shown as a note. RAW white balance, enlarger light and viewing
light remain separate. Upgrading a saved capture condition increments the
recipe revision once; subsequent openings retain that revision.

SoftLoaf Spectral is a project for calculating film-emulation LUTs from spectral
data. Its planned desktop application will combine illuminants, film sensitivity,
characteristic curves, dye spectra and other material data, with controls for
process settings, image preview and LUT export.

Users will be able to apply the generated LUTs to ordinary camera RAW files,
adjust the recipe and export the resulting images. RawTherapee will handle RAW
development; a matching DCP or matrix profile and a verified output conversion
will bring camera colors into the LUT's input space.
Users will not need hyperspectral images or camera spectral sensitivities;
spectral data will come from reviewed material presets or user imports. The
application is not intended to be a full RAW editor.

The first three processes are:

- Kodak 5207 negative film, using standard Academy Printing Density (APD) and a pinned film-to-ACES transform.
- The same negative printed on Kodak Ultra Endura photographic paper.
- Kodak E100 reversal film viewed by transmitted light.

The calculations include the light sources and materials used for exposure,
printing and viewing. The negative output branch uses standard APD rather than
simulated recapture lighting, sensor responses or camera calibration. A spectral reference will be used to test an RGB
approximation for ordinary images. Once its settings are fixed, the RGB
transform can be exported as a LUT. Grain and halation use separate image filters.

Film LUTs will be generated from the chosen spectral-node settings. The desktop
application will let users change lights, materials and process settings, compare
the results on their RAW images and save their own recipes. The internal film
LUT and OpenDRT display rendering will remain separate.

Fixed color conversions use OpenColorIO with the official ACES 2.0 CG config
v4.0.0. Display rendering offers ACES 2.0 and separate OpenDRT views.
Reversal and paper viewing default to colorimetric display conversion; negative
APD output defaults to ACES 2.0. See the [external comparisons and remaining
errors](docs/pipeline-default-verification.zh-CN.md) (Chinese).

## RAW development and caching

Each immutable RAW and frozen camera calibration has two retained development
stages: one half-size preview, then one full-resolution development for export.
Both color handoffs share one decode. Switching photographs, film edits, repeated
exports and restart reuse these stages; disposable display-cache eviction never
reopens RAW. See [cache architecture and measured switching](docs/photo-cache.zh-CN.md).
All RAW/hyperspectral pixel data and processing temporaries use the configured
external T7 storage.

## Status

The separate [negative scan workbench](docs/scan-workbench.zh-CN.md) imports a
measured transmission target and its RAW capture, with optional spatial flat-field
correction, then builds a
frozen calibration. A once-per-roll border selection allows one-click scan LUT
generation and batch positive rendering. RawTherapee directly develops each source once per half/full stage, retaining
both native camera channels and sRGB. Filmstrip and viewer share RT sRGB.
Preview and full-size PNG export reuse protected half/full RAW stages. Lens distortion, quarter turns, crop and output
scaling now share one Metal sampling pass; preview and export use the same map.
Output currently uses APD/ADX and ACES 2.0 SDR
sRGB. The target estimates a joint acquisition response; independent real-negative
color accuracy is not established.

This repository contains design notes, a source catalog, historical records and
a [local E100 RAW/LUT comparison](research/hsi-raw-lut-comparison.md). The experiment
generates LUTs and compares them with direct spectral calculations.
A [local desktop version 0.1](docs/application-v0.1.zh-CN.md) now uses a C++23
float64 calculation library and a macOS AppKit / WebKit window. It supports E100
node editing, RGB image trials, full-size PNG export and verified LUT export.
The development bundle requires the configured checkout, Python environment and
local material assets. The separate alpha.2 runtime candidate removes the
checkout/Python requirement, while scientific inputs remain user-provided.

On macOS, image pixels now use an independent Metal float32 implementation of
all three spectral routes and the native OCIO display graphs. Previews have a
2048-pixel short-edge limit; full-resolution exports and LUT baking share the
same renderer. RawTherapee, material fitting and the float64 reference remain
separate. See [implementation, timings and precision checks](docs/metal-pipeline.zh-CN.md).


A [local recipe workbench](docs/gui-design.zh-CN.md) now connects the E100
reference to image preview, same-input recipe comparison, JSON saving and
selectable LUT sizes with measured interpolation errors and an OCIO/CTF display package. The application now also computes the 5207 APD and Ultra Endura printing routes;
see the [pipeline audit](docs/5207-pipeline-audit.zh-CN.md) for numerical results and material assumptions. RAW input now uses two RawTherapee 5.12 handoffs: sRGB for the original preview and float linear ACEScg for film processing, with ACEScct coordinates for exported LUTs. Multi-image import, a filmstrip and background batch export are available locally; see the [implementation and validation limits](docs/raw-handoff-and-batch.zh-CN.md) (Chinese). Source assets and generated outputs remain local pending data-rights review.

5207 defaults to 5500 K camera illumination and fits Kodak's original Status M curves directly.
APD is calculated only at negative output before ADX and the ACES input transform;
optical printing uses the transmittance directly. See the [source and pipeline checks](docs/5207-status-m-validation.zh-CN.md).
Paper processing, measurement and viewing use their own [documented conditions](docs/5207-d55-and-paper-conditions.zh-CN.md).
New printing recipes use a [separate optical path](docs/printing-optics.zh-CN.md)
with KG3, dichroic-filter transmittances, optional lens transmission and preflash.
Existing recipes retain their legacy calculation until explicitly switched.
The paper node and photo edit bar also offer independently extracted Endura Premier,
Ektacolor EDGE, ROYAL Digital and Premier Metallic materials. Paper choice is
independent of the negative. Original RA-4 / Status A conditions, missing paper-white
measurements and the omitted metallic appearance are recorded per material.

The local [material catalog](docs/film-presets.zh-CN.md) exposes E100, Velvia 100, Velvia 50 and Provia 100F
for E-6 reversal, and VISION3 5203, 5207, 5213 and 5219 for negatives.
The added Fujifilm stocks use independently extracted manufacturer Status A,
sensitivity and dye curves, with declared source-reading limits, relative exposure
calibration and assumed curve tails. No E100 curves substitute for their components.
Negative materials and APD or optical-printing rendering can be selected
independently. Incomplete C-41 models are hidden from built-in choices; existing
user documents remain usable. Borrowed components and source credits are recorded
per material and in LUT headers.

A separate [Kodak source survey](data/kodak-motion-harvest-manifest.json) collects
curves for four VISION3 stocks from user-supplied motion-picture PDFs.
VERITA 200D is excluded from the selected materials.
The four VISION3 choices now use their own manufacturer curves and frozen
relative exposure references. 5203 uses its complete 2015 document; 5219 retains
an explicit Status M inference. Existing user recipes keep their material
snapshots. See the [integration and independent checks](docs/film-presets.zh-CN.md).

The E100 reference still needs the complete source-acquisition and curve-extraction
workflow. The local experiment rebuilds the numerical calculation from archived
data without importing the historical programs or private application code.

## Documentation

- [Diagnostics, checks, language settings and Windows development](docs/quality-and-windows.md) — C++23, D3D12 with CPU recovery, measured checks and remaining platform limits.

- [External data storage](docs/external-data-storage.zh-CN.md) — local T7 policy for RAW, hyperspectral data, caches and processing temporaries (Chinese).

- [Build and use desktop version 0.1](docs/application-v0.1.zh-CN.md) (Chinese).
- [Project description](docs/project-brief.zh-CN.md) — scope and initial design.
- [System design](docs/system-design.zh-CN.md) — spectral reference, LUT generation and ordinary RAW use (Chinese).
- [APD, ADX and Status M conversion](docs/apd-adx.zh-CN.md) — source notes and automatic material handling (Chinese).
- [RAW input and camera profiles](docs/raw-input-and-dcp.zh-CN.md) (Chinese).
- [Methods](docs/science-and-pipelines.md) — calculations and approximations.
- [Spectral nodes and desktop interface](docs/spectral-nodes.zh-CN.md) (Chinese).
- [GUI design and interactive prototype](docs/gui-design.zh-CN.md) (Chinese).
- [Required LUT-generation inputs](docs/lut-generation-inputs.zh-CN.md) (Chinese).
- [Spectral sampling database design](docs/spectral-sampling-database.zh-CN.md) — color coverage, physical feasibility and metamer diversity (Chinese).
- [Local database build and tests](research/sampling-database-build.md) — separate reversal and negative input banks, fitted models and measured errors (Chinese).
- [Color management and display output](docs/color-management.zh-CN.md) (Chinese).
- [Data](data/registry.json) — source documents and measurement records.
- [Earlier experiments](research/README.md) — results and known limitations.
- [IT8 data and LUT trial](research/it8-lut-trial.md) — measured-target audit and first IT8-derived spectral prior (Chinese).
- [Local archive](research/local-archive.md).
- [Development](docs/validation-and-roadmap.md) — work order and tests.
- [References](docs/prior-art.md).

## Limitations

Different spectra can have the same RGB values and produce different film
responses. The RGB approximation will be tested against measured spectral
scenes, with its input conditions and spectral assumptions recorded.

Neutral characteristic curves do not determine the response to every color.
The material models still need independent film and print measurements.

Roll calibration depends on the supplied images. Calibration, exposure and
viewing settings must be fixed before LUT export and recorded with each file.

## License

Original code and documentation: **AGPL-3.0-only**. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). External data retain their own terms; see [data and licensing](docs/data-and-licensing.md).

## Contributing

Measurements, test images, and code are welcome. Please include the source,
units, processing conditions, and permission to distribute any data you submit.
See [CONTRIBUTING](CONTRIBUTING.md).

See [分块处理与缓存设置](docs/streaming-io-cache-settings.zh-CN.md) for the current
image/export modules, settings behavior, measurements and limits.

The selected separate reversal and negative sampling models now drive the
application, with bounded GPU LUT baking and verification. See
[optimized sampling integration and measurements](docs/optimized-sampling-gpu-lut.zh-CN.md).

A separate [real-negative scan experiment](docs/scan-negative-experiment.zh-CN.md)
now uses owner-supplied transmission-target measurements, flat field and a real
37-frame 5207 roll. It produces local positive images with held-out chart and
implementation checks, while recording unresolved scan-response and material
errors. Frozen experimental CUBE/CLF export and a
[camera-response sensitivity comparison](docs/camera-response-sensitivity.zh-CN.md)
are available as local commands. They are not integrated into the desktop UI.
