# Installing the alpha.2 candidate

This prerelease packages the native window and its runtime. Scientific inputs
remain separate. It contains no film/paper curves, trained spectral models,
photographs, transmission-target measurements or scan calibrations. A normal
installation does not provide material presets until a prepared data directory
has been supplied. The public core tests remain usable without that directory.

## Systems and installation

The Mac candidate is arm64 and requires macOS 26 or newer; its bundled native
libraries establish that floor. Verification used macOS 27.0.1 and an Apple M2 Pro.
Copy the application from the disk image to Applications before opening it.

The Windows candidate is x64, tested on Windows 11. It requires Microsoft's
WebView2 Evergreen Runtime. The installer writes to the current user's Programs
directory. D3D12 is selected when available, with a CPU route retained. The
Windows candidate is unsigned; it is not a Microsoft Store package.

First launch selects a prepared scientific-data directory, then a processing
directory on the same mounted data volume. Mac data volumes must be under
`/Volumes`; Windows uses a non-system drive. The program may be installed on the
system drive; RAW/hyperspectral pixels, retained stages, previews and processing
temporaries stay on the selected volume. Per-user settings, workspace metadata
and logs use the operating system's application-support directory.

Updates require a normal application close. Uninstallation removes program
files and preserves settings and the external data volume.

## Prepared scientific directory

`runtime-science.json` uses schema `softloaf.runtime-science/1` and a `files`
array. Every record has a relative forward-slash `path` and its lowercase
64-character `sha256`. Files must stay inside the selected directory; absolute
paths, duplicate paths, path traversal and mismatching bytes are rejected.
For example, a record is `{ "path": "folder/input.csv", "sha256": "…" }`;
the ellipsis must be replaced with the actual SHA-256.

Required paths, relative to that directory:

- `local/film-color-slides/hyperspectral-demo/output/reversal-E100/data/E100_dye_density_CMY.csv`
- The same data directory's `E100_characteristic_RGB.csv` and `E100_linear_sensitivity_RGB.csv`.
- `local/film-color-slides/hyperspectral-demo/output/reversal-E100/intermediate/model.npz`.
- `local/film-color-slides/data/CIE_xyz_official.csv`, `CIE_std_illum_D50.csv` and `CIE_std_illum_D65.csv`.
- `local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip`.
- `artifacts/sampling-database/report.json`, `reversal.sqlite` and `negative.sqlite`.
- `artifacts/sampling-database/models/reversal.npz` and `negative.npz`.

These are calculation inputs, not arbitrary PDFs renamed as CSV/NPZ. Material
extraction, quantity conventions and model production are described in
[science and pipelines](science-and-pipelines.md),
[data and licensing](data-and-licensing.md) and
[the local sampling build](../research/sampling-database-build.md).
Additional negative, reversal, paper and optical assets require their matching
source records and original extraction files. The installer validates file
identity; that check does not establish measurement accuracy or redistribution
permission. The local test pack is not a public download.

## Building the runtime

Use the matching source tag, C++23 compiler and `requirements-packaging.txt`.
Build the native libraries and shell with `SOFTLOAF_PACKAGED_SERVICE=ON`.
The integrated pinned RT engine uses `cmake/RawTherapee.cmake`; its camera
resources include the platform-specific `options` file and
`rtengine/camconst.json`, following upstream's separate installation rules.

`scripts/build_service.py` freezes program code and public resources only.
`scripts/bundle_macos_raw.py` and `scripts/bundle_windows_raw.py` copy explicit
RAW reader dependency closures. The Mac compatibility reader retains the
original official RT numerical binary while relocating resource strings and
load commands. Its native libraries are identified separately. Library/provider
changes require a fresh independent RAW comparison, not just internal agreement.

`scripts/build_runtime_notices.py`, `scripts/build_native_notices.py` and
`scripts/fetch_native_sources.py` preserve Python notices and exact native source
locations, checksums and provider build recipes. The matching source archive
contains the integrated RT modifications. The native-source supplement preserves
redistributable dependency sources. Mac signing follows dependency order, then
Developer ID hardened-runtime signing, notarization, stapling and Gatekeeper
assessment. Generate final SHA-256 sums only after those operations.

`scripts/stage_installer.py` stages only explicit program/runtime inputs, rejects
missing RAW resources and inventories the payload. Windows packaging uses
`desktop/windows/installer.nsi`; data volumes are not included in its uninstall
rules. Never copy a local workspace, test pack or RAW corpus into a public stage.

For Windows MSYS2 inputs, `scripts/msys2_inventory.py` verifies each selected DLL
against its original cached binary package. It preserves `.PKGINFO`,
`.BUILDINFO`, package notices, source URLs and hashes. After fetching the source
archives, `--sources-manifest` also checks their `PKGBUILD` against the hash in
the binary's build record. A filename or a matching library version alone is
insufficient evidence. The audit includes both RAW roles and MSYS2 libraries
selected by the frozen-service analysis; other native providers need separate
records.

Staging rejects a missing executable in either RAW role before creating its
output directory. Install the role executables, DLL closures and resources
after freezing the service: a clean freeze replaces its output tree.
