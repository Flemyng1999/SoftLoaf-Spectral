# Source-only test release 0.1.0-alpha.1

面包光谱 / SoftLoaf Spectral is an experimental film-spectral calculation
application. This first prerelease supplies its source for review, development
and public numerical tests. **There is no ready-to-run installer or complete
scientific runtime in this release.**

The source contains the C++23 float64 reference, macOS Metal and Windows D3D12
implementations with CPU recovery, the desktop workbench, RAW handoff/cache and
streaming-export modules, tests, logo assets and the pinned modified RawTherapee
5.12 source. Film stock, positive rendering and paper are separate choices.
The local implementation supports four VISION3 negatives, four E-6 reversal
stocks and five Kodak RA-4 papers; their numerical materials are not included.

## Contents and licences

Original project code and documentation use AGPL-3.0-only. RawTherapee, LibRaw,
the Academy transform and other third-party components retain the notices in
`third_party/` and `NOTICE`. The unmodified original CIE tables in
`assets/science/cie` use CC-BY-SA-4.0, with source metadata and attribution.
The selected application logo is in `assets/branding`.

No manufacturer PDFs, extracted film/paper tables, processed optical curves,
Status A/M or APD source tables, frozen sampling models, hyperspectral scenes,
camera RAW photographs, private target measurements, scan calibrations,
workspaces, caches, credentials or compiled applications are included.
The VISION3 identity manifest contains source hashes and fit summaries rather
than sensitivity arrays. OpenDRT's runtime data package is also not included.

`release/scientific-sources.json` continues to record the unresolved full-data
review. A failed full-data gate does not mean the omitted files were cleared by
publishing this source. `release/source-policy.json` and
`scripts/source_release.py` audit the source archive separately.

## Build the public calculation core

Use Python 3.12, Node.js 22, CMake 3.20 or newer, a C++23 compiler and libpng.
The declared Python versions are in `requirements-quality.txt`. Work from the
extracted source root; no Git checkout or scientific dataset is required for
these public checks.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-quality.txt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DSOFTLOAF_DESKTOP=OFF -DSOFTLOAF_RAWTHERAPEE=OFF
cmake --build build --parallel 4
.venv/bin/python scripts/run_checks.py --profile public
```

Install libpng using the platform package manager (for example `brew install
libpng` on macOS or `apt install libpng-dev` on Ubuntu). On Windows use Visual
Studio 2022 with the C++ workload and a current Windows SDK, Python 3.12 and
Node.js 22. With vcpkg's libpng installed:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-quality.txt
vcpkg install libpng:x64-windows
cmake -S . -B build -A x64 `
  -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" `
  -DSOFTLOAF_DESKTOP=OFF -DSOFTLOAF_RAWTHERAPEE=OFF
cmake --build build --config Release --parallel 4
$env:SOFTLOAF_CORE = "$PWD/build/Release/softloaf_core.dll"
.venv\Scripts\python scripts/run_checks.py --profile public
```

Set `VCPKG_ROOT` to your vcpkg installation, or use the installed
`VCPKG_INSTALLATION_ROOT` value. The public profile checks deterministic
synthetic references and contracts; it does not certify the omitted materials,
real-film color accuracy or GPU hardware. It writes reports under
`artifacts/quality/latest`. No private data are downloaded by the tests.

Browser interaction checks are separate:

```sh
npm ci
npx playwright install chromium
npm run test:browser
```

## What the desktop application still requires

The application is not an empty workbench that starts solely with the public
CIE tables. Its current startup requires the identified local E100 reference
and frozen sampling inputs. Obtain or independently regenerate authorized
inputs before attempting desktop startup. They cannot be reconstructed from
the source archive's hashes alone; automated acquisition and complete public
reproduction of the frozen runtime are not delivered in this prerelease.

| Input group | Expected location / source record |
| --- | --- |
| E100 sensitivity, characteristic and CMY data | `local/film-color-slides/hyperspectral-demo/output/reversal-E100/data/`; original Kodak E-4000, see `data/registry.json` |
| Retained E100 fit, Status A weights and reconstruction/reference inputs | The same archive's `output/reversal-E100/intermediate/model.npz`; original reference assets must be supplied separately |
| Runtime CIE XYZ, D50 and D65 handoffs | `local/film-color-slides/data/`; unmodified public originals are separately supplied in `assets/science/cie`, but runtime mapping has not been substituted automatically |
| Frozen negative/reversal sampling inputs | `artifacts/sampling-database/`: `report.json`, both SQLite banks and both `models/*.npz`; see `data/sampling-priors-manifest.json` and the sampling-build documentation |
| OpenDRT runtime config | `local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip`; pinned source record in `data/registry.json` |
| 5207, Ultra Endura, APD and Status M | `local/materials/5207-v1/` and `local/materials/status-m-iso1984/`; identity manifests in `data/` |
| Additional VISION3, E-6 and RA-4 materials | `local/materials/film-presets-v1`, `vision3-source-v2`, `reversal-presets-v1`, `paper-presets-v1`; per-material manifests in `data/` |
| Optional printing optical components | `data/printing-optics-manifest.json` identifies the current local reference dependency; original-source replacement and review remain incomplete |
| Scan calibration | The user's own numbered transmission-target spectra, RAW chart capture and per-roll border selection; no private calibration is provided |

See `docs/data-and-licensing.md`, `docs/spectral-csv.zh-CN.md` and the extraction
scripts for quantities, source versions, hashes and documented assumptions.
Status M fits negative material; APD is a separate negative-output metric.
5219's Status M interpretation is inferred from cross-chart evidence. Paper
white is partly assumed, and metallic-paper angular appearance is not modeled.

## Local desktop development

Configure an external data volume before processing RAW or hyperspectral data.
Create your own ignored `local/storage-settings.json`, for example:

```json
{"volume":"/Volumes/YourDataDisk","data_root":"/Volumes/YourDataDisk/SoftLoaf-Spectral"}
```

On Windows use an actual mounted data drive and matching absolute paths.
Never copy another person's workspace, target measurements or credentials.
The application retains one preview development and one full-size development
per immutable RAW and frozen camera calibration. Disposable cache cleanup must
not remove those retained stages.

After the omitted inputs are prepared, macOS can build its development window
with `SOFTLOAF_DESKTOP=ON`; the default `SOFTLOAF_RAWTHERAPEE=ON` also builds the
vendored CLI and requires the packages listed in
`third_party/rawtherapee/SoftLoaf.md`. Select the intended interpreter with
`-DPython3_EXECUTABLE=/absolute/path/to/.venv/bin/python`. Windows desktop
development additionally requires the official WebView2 SDK and installed
WebView2 Runtime, `SOFTLOAF_WEBVIEW2_SDK` and an external
`SOFTLOAF_WEBVIEW2_CACHE`; configure the separate RAW executables and DLL search
directory via ignored `local/raw-runtime.json` as described in
`docs/quality-and-windows.md`. These development windows depend on their source
and Python environment. They are not portable installers.

Run `.venv/bin/python -m spectral_app --check` (Windows: the corresponding
`.venv\Scripts\python`) to list missing startup inputs. Public-test success
does not imply that this full-runtime check passes.

macOS 14.5 is the current development deployment target, not a verified binary
compatibility promise. The local macOS 27 / Apple Silicon and Windows 11 tests
do not replace a future packaged-release deployment-floor test. This source
release has no Developer ID signed or notarized application and no Windows
installer or Microsoft Store certification.
