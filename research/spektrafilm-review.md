# Spektrafilm source review

The user explicitly added [Spektrafilm](https://github.com/andreavolpato/spektrafilm)
as a reference on 2026-10-26. This is an explicit addition to the earlier
pre-2021 reference preference. The inspected tree is pinned to commit
`3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`; this is not a dependency on its moving
main branch. No upstream runtime or profile has replaced this application's
current material calculation.

## Relevant data found

| Profile | Declared metric / illumination | Grid |
| --- | --- | --- |
| `kodak_vision3_250d.json` | Status M; sensitivity criterion 0.2 D above minimum; D55 | 380–780 nm, 5 nm |
| `kodak_ultra_endura.json` | Status A; sensitivity criterion 1.0 D above minimum; TH-KG3 printing reference; D50 viewing | 380–780 nm, 5 nm |
| `kodak_ektachrome_100.json` | Read the individual profile's metadata before use | 380–780 nm, 5 nm |

The profiles contain log sensitivity, channel-density spectra, base and midscale
neutral spectra, fitted characteristic curves, layer-density curves and model
parameters. They are processed model data rather than interchangeable raw
manufacturer measurements. In particular:

- The 250D channel-density table has 15 null cells and 45 negative cells;
  minimum −0.06827 D. Its base has four null cells below 400 nm.
- Ultra Endura channel density has 65 null cells. Its base is a processed
  profile quantity; it does not establish a new measurement of unexposed paper.
- Small negative characteristic densities also occur in both processed
  profiles. They cannot be silently clipped and then called the original model.
- The 380 nm lower grid boundary does not supply our APD branch's 360–380 nm
  material data. Existing missing-band assumptions are therefore not resolved.

Negative channel-density contributions may participate in masking/coupler and
unmixing conventions. Our current nonnegative effective-CMY plus fixed-base
model cannot accept them as isolated nonnegative dye spectra. Determine and
reproduce the complete upstream interpretation before importing those fields;
do not fill nulls with zero or treat already-unmixed curves as raw Status M.
Likewise, log sensitivity in a prepared profile may carry calibration and
normalization; matching its array shape is not proof of matching units.

## Useful comparisons

The separation of scene exposure, layer development, printing and viewing is
relevant. The project discusses masking and inhibitor couplers, which the
current application does not model. These are plausible material-model
limitations to investigate, not demonstrated causes or a validated correction
for our output. Its printing filters, reference illuminants and processed curves
are useful independent comparisons against the newly extracted Kodak curves.

Its scan stage is a separate design choice. The user's APD branch remains
standard APD/ADX→ACES, without importing a scanner/recapture stage. Grain,
halation and other spatial effects remain outside a fixed pointwise LUT.

## Provenance and reuse

The inspected profile metadata identifies Andrea Volpato and CC BY-SA 4.0;
source data retain their original owners. The root `SPEKTRAFILM_LICENSE.txt`
explicitly covers profiles and direct derivatives, including encoded LUTs. The
README contains conflicting older LUT wording; retain and cite the pinned
actual license and each file's metadata rather than relying on a summary.
The code is separately GPLv3, as stated by the repository.

The three unmodified profiles, inspected license files and SHA-256 records are
stored under ignored local reference assets. Their metadata and nulls are
preserved. No upstream LUT, private ICC profile or runtime code is imported.
Any later derived profile must carry its attribution, license and modification
record; publishing our independently extracted Kodak materials still requires
its own source-rights review.

## 2026-10-27 expansion

The same pinned tree has now been surveyed in full: 28 profiles, comprising
16 camera negatives, four camera positives, six papers and two movie print
films. All 28 local originals were checked against their Git blob identities.
See [the machine-readable survey](../data/film-source-survey.json).

Six processed sensitivity tables now enter explicitly provisional local
negative materials (Gold 200, 5219, Ultramax 400, C200, Pro 400H and Superia
X-TRA 400). Only log sensitivity is linearized and resampled; a single common
amplitude scale preserves channel ratios. No upstream processed or unmixed
density curve is treated as an original Status M measurement. Andrea Volpato,
CC BY-SA 4.0, the pinned source and the modifications are recorded in each
material and exported LUT. This supersedes the earlier statement that no
profile field was used at runtime; full upstream profiles and code remain
unintegrated. The [recipe notes](../docs/film-presets.zh-CN.md) identify every
5207 substitution and distinguish C-41, ECN-2, E-6, paper and movie print film.


## 2026-10-28 printing optics

Individual KG3, Edmund dichroic and optional reference-lens transmittances are
now used by an independently implemented spectral-v2 printing path. The processed
Ultra Endura profile contributes only its minimum-density shape, with a recorded
common Dmin-origin alignment; original Status A characteristic data remain our
separate source. No upstream runtime or whole paper model is imported. These
additions supersede the earlier integration scope, not the source limitations.
Old recipes retain legacy-v1 numerical output. See the [printing implementation
and external integration comparison](../docs/printing-optics.zh-CN.md) and
[optical identity manifest](../data/printing-optics-manifest.json).


## 2026-10-28 paper provenance check

The inspected profile metadata explicitly describes processing measurements from
manufacturer data sheets and scientific papers; it does not identify a new
per-paper exposure/spectrophotometer campaign by the project author. The
`printing.py` stage turns prepared log sensitivities into energy responses,
multiplies filtered enlarger light by modeled negative transmittance, projects
onto paper responses, normalizes to a virtual midgray, adds preflash, and
applies a prepared parametric paper development model. `scanning.py` reconstructs
a spectral density from processed channel/base curves and integrates reflected
viewing light with the standard observer. Those computations are modeling,
not new measurements of physical prints.

The author describes the goal as using manufacturer data sheets in the
[README](https://github.com/andreavolpato/spektrafilm), asks for PDFs in the
[2026 digitization campaign](https://discuss.pixls.us/t/2026-q2-data-sheets-digitization-campaign/58032),
and states in the [technical discussion, post 44](https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512/44)
that the model generalizes from limited densitometric data and is not accurate
to a particular realization of the analog process. This is not evidence that
no contributor ever measured any component; original manufacturers and other
cited researchers did measure source data. No complete stock-specific paper
white / fluorescence / exposure-to-print validation record was found in the
reviewed profile metadata and public runtime. A processed profile containing
base and density arrays does not resolve a missing original measurement.

The local paper-audit runtime sources retain the same pinned commit as above;
no upstream runtime or processed paper model is integrated by the four new
Kodak paper presets. Their independent manufacturer extraction and limits
are recorded in the [printing notes](../docs/printing-optics.zh-CN.md).
