# Data and licensing

## Project license

Original code and documentation use **AGPL-3.0-only**. The standard text is in
[LICENSE](../LICENSE); [NOTICE](../NOTICE) states the version choice. Section 13
covers modified programs used for network interaction. See the [SPDX text](https://spdx.org/licenses/AGPL-3.0-only.html).

External data and third-party code retain their own terms. Check compatibility
and keep their notices before importing them. Publicly available files may
still require permission for redistribution.

Section 2 makes output coverage depend on the output's contents. Processing a
personal photograph does not automatically put that photograph under AGPL.
Published model and LUT packages need their own source and license records.
Recipes and build code authored here use AGPL; numerical output and upstream
asset obligations are checked separately.

## Source records

[data/registry.json](../data/registry.json) lists the inputs used in earlier
experiments. Only the explicitly reviewed original CIE tables in
`assets/science/cie` are currently included as distributable source tables;
local film, paper, optical and training assets remain separate. For each imported asset,
record:

- Source URL/DOI, author, version and hashes.
- Quantity, units, wavelength grid, geometry and known uncertainty.
- Document page, original extraction points and processing for digitized curves.
- License and attribution, with permission checked for the proposed distribution.

Check the permitted use of raw files, extracted tables, models, examples and
exported LUTs separately, and record which uses have been reviewed.

The [first-release source review](release-source-audit.zh-CN.md) distinguishes
original acquisitions from the runtime's remaining borrowed optical curves.
Original manufacturer or measurement sources take priority. A repository curve
requires an unavoidable-source exception with the search, reason, limits and
licence recorded; none has been approved for the first release. The executable
scientific-source check currently blocks publication of the complete data set.

Keep manufacturer PDFs, standards and extracted tables outside Git until their
reuse has been reviewed. Where a document must be supplied by the user, give
acquisition instructions and a checksum. A checksum identifies the file but
does not provide access to the input needed for reproduction.

The user-supplied TB-2014-005 was read locally for APD/ADX and stock-specific
Status M conversion. Its file identity, hash and sections are recorded in the
registry and [source notes](apd-adx.zh-CN.md). The bulletin includes a historical
appendix superseded by SMPTE standards; it does not establish normative
conformance or provide the complete APD/ADX-to-ACES implementation. The PDF,
responsivity tables and film-matrix coefficients have not been bundled.
Local reference use does not authorize redistribution of the source or tables;
derived model and LUT distribution need a separate source-rights review.

For CIE tables, spectral scenes and camera datasets, check the exact release
being imported. Keep attribution and applicable share-alike terms. Do not use
noncommercial-only data as a default input for the planned general-use release.

## Earlier private inputs

The 2026-10-29 real-negative experiment uses owner-authorized local copies of
the 000003 transmission-card measurements and matching scan RAW files. The
original measurement exports, normalized transmittance and reference IT8 are
hash-checked on the configured external volume. No private runtime, scanner
profile or historical calibration code is imported. Measurement files, patch
maps, fitted scan responses, photographs and derived local lookup tables are
not bundled or authorized for public redistribution by this experiment.

The GH7 response, measured capture light and old CCM files have not been
contributed for public distribution. The sensor's missing relative channel gains
also need to be resolved before calibration claims can be made.

The earlier digitization program is separate proprietary software. Its code,
binaries, profiles and configuration are not part of this project. Any later
transfer needs specific authorization; an independent implementation can instead
use documented methods and appropriately licensed sources.

Before publishing, check data rights and remove credentials, private reports
and personal paths. Include the relevant source and license records with LUT
and model releases.

## Current 5207 reference implementation

The desktop application independently extracts published vector curves from
Kodak H-1-5207t (July 2015) and E-4020 (July 2003). Extracted tables, PDF files
and the bulletin's numeric APD/5207 compatibility data remain under ignored
local assets with source hashes. This does not grant redistribution rights.
No historical private application code, scanner profile or camera calibration
is used by these routes.

Model /3 uses a separately extracted ISO 5/3:1984 Table 4 Status M source,
cross-checked against ANSI/ISO 5-3:1995. The PDFs and numeric table remain local;
only the extractor and identity manifest are bundled. Access to a public scan
does not establish permission to redistribute the table or derived material.

The optional negative-preset survey retains 14 manufacturer PDFs and 28 pinned
spektrafilm profiles locally. Six processed sensitivity tables are used in
explicitly provisional materials; their source commit, hashes, Andrea Volpato
attribution, CC BY-SA 4.0 and modification records travel with the recipe and
LUT header. No upstream processed density curve is relabelled as raw Status M.
Manufacturer curves and borrowed 5207 components retain their separate rights.
The catalogs in `data/film-source-survey.json` and `data/film-presets-manifest.json`
contain identity and scope records, not the raw assets or a grant to publish.

The ACES v1.2 ADX16 algorithm is separately reproduced under its Academy 2015
license; retain third_party/aces-v1.2/LICENSE.md. Negative LUT packages include
the license alongside their numeric and recipe records. The upstream transform
identity and hash are recorded in the registry.


The printing-optics update retains pinned KG3, Edmund dichroic and optional
Canon lens curves locally, with the original manufacturer/source links and
separate redistribution status. A processed Ultra Endura base shape is an
explicit CC BY-SA 4.0 derivative, not a new measurement. Exported derived local
packages include the unmodified upstream profile licence, attribution and a
CHANGELOG.txt. Source identities and tail/resampling assumptions are recorded in
[data/printing-optics-manifest.json](../data/printing-optics-manifest.json) and
the [printing notes](printing-optics.zh-CN.md). No upstream runtime is imported.

The optional Velvia 100 material independently extracts original vectors from
Fujifilm AF3-202E (February 2005), page 8. The PDF, mapped original vertices,
Status A fit, sensitivity tails and derived material remain local pending rights
review. `data/reversal-presets-manifest.json` records source identities without
redistributing the curves. This does not adopt an upstream processed reversal
model or establish permission to publish derived LUTs. The application exposes
only E-6 reversal choices and VISION3 negatives; archived C-41 records remain
available to existing user documents.

Velvia 50 (AF3-0221E2, p8) and Provia 100F (AF3-036E, p6) now use their own
hash-pinned manufacturer charts, independently extracted without any E100 curve
substitution. Source raster masks/vectors, accepted points, rejected ink candidates
and derived tables stay local. Both have separately recorded extraction limits
and model-fit allowances. The original PDF and derived material/LUT redistribution
status remains pending; adding a local menu choice does not authorize publication.

The 2026-10-28 user-supplied Kodak motion-picture survey collects independent
curves for 5203, 5206, 5207, 5213 and 5219. The identity manifest is
`data/kodak-motion-harvest-manifest.json`; the PDFs, vector geometry, raster
readings, tables and source overlays remain ignored local assets. No upstream
profile or substitute material is used. Collection does not resolve the missing
VERITA dye components or the unconfirmed measurement conditions in the supplied
5203 and 5219 documents. The source-only survey remains separate from derived material versions. Source
availability does not establish permission to redistribute these assets or their
derived material/LUT outputs.

The selected survey now excludes VERITA 5206 at the user's request. Its collected
evidence is archived outside the active collection. Only the four VISION3 stocks
are rebuilt and verified by default; exclusion does not delete source evidence.

The selected four VISION3 materials are now integrated as `vision3-source/2`.
5203 uses its separately identified complete 2015 source. The other three use
the collected own-stock curves, and 5219 retains the accepted Status M inference.
Own endpoint spectral tails and relative exposure references are explicit; no
other stock supplies replacement components. Original assets, derived material
JSON, source plots, example images and LUTs remain ignored local files pending
rights review. Existing user recipe snapshots are not rewritten.


Four optional Kodak paper materials independently extract manufacturer vector
charts: E-4070 (December 2017), E-7020/E-7021 (April 2019), and E-4071 (March 2013).
`data/paper-presets-manifest.json` records PDF and derived identities, extraction
pages and model scope. Source PDFs, original traces, numerical materials, plots
and LUTs remain ignored local assets pending redistribution review. No processed
spektrafilm paper profile supplies these four materials or their assumed paper
white. Existing optical component sources and obligations remain separate.

## Integrated RAW source

The local camera-response sensitivity study uses the exact A7R V prediction from
Solomatov and Akkaynak (2023) and separately identified Sony A7R IV/III/II files
from rawtoaces-data. The latter declare wetadigital / lightsaber and Apache-2.0;
their source licence is retained externally. Prediction redistribution remains
unreviewed. Public identities and hashes are in
`data/camera-response-sensitivity-sources.json`. Curves, lamp estimates, target
readings, photo comparisons and derived LUTs remain local; other camera sources
are never relabelled as A7R V measurements.

The local 2026-10-29 scan export uses private target measurements and the existing
5207 material model. CUBE/CLF files, target response fits, frozen calibration and
real-image validation remain on the external data volume; no redistribution grant
is inferred. The A7R V source audit found an author-provided **prediction** file,
not an independently measured SSF. It is recorded locally and is not used in the
experimental LUT. See `docs/a7rv-response-source-audit.zh-CN.md`.

At the user's explicit request, the official RawTherapee 5.12 source snapshot
`a8a3d1bc7b419ed1c974c39276c97e618a4f9a1b` is vendored under
`third_party/rawtherapee`, including its bundled LibRaw and official resources.
The upstream GPL and each component/resource's notices are retained; root AGPL
licensing does not replace them. `softloaf-source.json` pins the source archive
and local changes. Generated build files, private calibration, other products'
code and agent instructions are excluded. This local source integration does
not publish camera test photos or authorize publication of film/paper assets.

The scan geometry adapter optionally loads the installed public Lensfun 0.3.4
database and library. No database XML or binary is added to this repository.
Frozen choices identify the public source XML by hash and name, with numerical
map coefficients and coordinate residuals. Library, program and database terms
remain upstream's; see NOTICE. The user-authorized review of another product's
flat/lens workflow did not import its implementation, private lens profiles,
calibration data or project instructions.
Standalone runtime dependency packaging and distribution review remain separate.
