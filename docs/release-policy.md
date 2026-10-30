# Releases

面包光谱 (SoftLoaf Spectral) distributes source prereleases and separately
verified platform packages. A successful development build is not an
installable release. Alpha.2 publication is macOS-first; a Windows installer
must pass its own dependency and installed-candidate checks before being added.

For 0.1.0-alpha.1 the owner explicitly selected a source-only prerelease without
unreviewed data. This channel publishes an audited immutable source archive,
inventory, checksums, build/test instructions and an explicit missing-input
list. It does not publish development binaries as installers. Binary launch,
signing and notarization gates below apply when binary packages are published;
source-only publication must not imply those gates passed. The full scientific
payload gate may remain blocked: those data are excluded, not marked approved.

A release must identify an immutable source commit, version and channel. Test
releases are marked prerelease and describe known scientific and performance
limits. Never move or reuse a published tag. Preserve unrelated working changes.

Each bundled scientific asset needs its exact original source, version, file
hash, quantity, units, coverage, extraction method, adaptation and distribution
permission. Obtain original manufacturer or measurement data directly. Curves
copied from another repository are excluded unless an original source cannot be
found and the exception documents the search, reason, source and limitations.
Code licences do not establish rights to scientific data. Pending permission is
a publication blocker, including for derived models with unresolved inputs.

Public payloads exclude user photographs, camera/scan calibrations, workspaces,
local paths, credentials, standards PDFs and unapproved manufacturer documents.
Packaging uses an explicit inventory; never recursively publish local/ or
artifacts/. Do not change pending records to approved to pass a gate.

The installed application must start without this checkout, developer Python,
Homebrew, MSYS2 or development configuration. Mutable settings, logs, caches and
RAW stages use their owning locations. Retained RAW stages must survive restart
and cache maintenance. Distribute required notices, dependency inventory and the
corresponding source/build instructions required by component licences.

Verify each final installer/archive, cold launch, a real RAW preview/export,
LUT readback, supported language and icon states, and CPU/GPU reference behavior.
Record exact-candidate evidence and performance limits. macOS public artifacts
must pass the selected Developer ID signing, hardened runtime, notarization,
stapling and Gatekeeper checks. Windows channel, signature status and runtime
prerequisites must be explicit; do not imply Microsoft Store certification.

Generate SHA-256 sums after all signing/packaging. Publication consumes those
verified bytes. Read back the tag, release flags, complete assets and their
checksums before calling the release published.
