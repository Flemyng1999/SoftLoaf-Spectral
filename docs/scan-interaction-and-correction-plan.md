# Scan calibration and correction interaction

2026-10-29, Issue #12, current task branch. User requests a clear calibration
flow, corrected viewer and thumbnails after flat/lens changes, a bottom progress
bar, and actual desktop/browser/log testing with usability fixes. Existing edits,
RT-only development and two retained source stages remain in force.

Calibration becomes three steps: choose a measured target and photo, check or
place sampling points, then name/save. Offer already imported target references
by card number. Hide positioning until both inputs are ready. Reuse coordinates
only for the identical immutable chart, reference and RT contract. Rotate/mirror
the displayed photo, invert that transform for measurement coordinates, retain
undo/reset and require checking all 24 points. Keep actions visible in a fixed
footer even at compact window sizes.

Move preview processing into its own module. Cache corrected RT previews with
profile/flat, geometry and renderer identity; thumbnails share each corrected
rendition. Keep an unmodified RT chart/sampling view in source coordinates.
Positive preview/export continue applying native-camera flat before the scan LUT.
Negative display flat is separately defined and fitted from the retained RT flat
in linear sRGB, central-normalized; it is a display-space correction, not a claim
of inversion of RT's DCP. Record this domain and its limits. Never apply native
camera gains directly to encoded sRGB. Flat/lens changes refresh the whole roll,
reusing retained stages; partial results publish with matching identities only.

Use measured job progress and phases in a single bottom bar. Unknown work stays
indeterminate, uploads use actual bytes, image work uses completed images/rows.
Include calibration, flat fitting, preview refresh, geometry, LUT and export.
Ignore stale geometry responses and disable incompatible actions while working.

Verify synthetic flat/geometry results against float64 and Metal, cache/version
and RAW ledgers, wizard source-point transforms and blockers, progress/errors,
then operate the native APP and the same service in a browser, inspect logs,
and record additional usability findings. All pixels and browser artifacts T7.

## Numbered chart and two-point placement

Use the usual ColorChecker 24 arrangement: 1 dark skin at upper left, 24 black
at lower right; row-major 6×4. The UI convention follows X-Rite's ColorData-1p
and colour's BabelColor ordering. These define IDs and arrangement only, never
replace the measured transmission data with reflective chart values.

New transmission CSV /2 uses wavelength_nm and unique patch IDs 1–24 as column
headers. Columns may be permuted; the reader orders by explicit ID. Keep /1
available solely to reproduce saved calibrations. Do not reinterpret A1..D6.
For the reviewed local card, write a separately identified numbered reference
with the verified reverse mapping. Retain old frozen results. Offer an existing
layout for a new numbered reference only when all wavelengths and each patch
spectrum match exactly, and the remapped full grid agrees with its four corners.

Default positioning asks for centres 1 and 24 in an upright photo. Construct an
axis-aligned 6×4 grid in displayed-photo coordinates and invert display rotation
and mirror for sampling. Two points do not determine a homography; optional
corner dragging adjusts perspective after placement. Always show all 24 sample
positions and require confirmation. Verify IDs, input rejection, exact spectrum
permutation, all display orientations, point placement and actual browser flow.

## Native colour patch keys

Bare ordinal IDs were rejected by the user. Use colour's exact Classic sample
keys as CSV /3 identities and UI prompts. No invented CC24 numeric prefix.
Reject unknown, missing, duplicate and misspelled keys with field-specific errors.
Column permutation is valid because matching is by key. /1 and /2 keep their
original semantics for existing calibration reproduction; do not rewrite them.
The reviewed local /3 reference changes headers only. Verify identical wavelengths
and spectra before offering its saved layout; retain existing frozen results.


## Final user-selected IDs

The user explicitly selects CC01 through CC24. Use those fixed, zero-padded IDs
in UI prompts, the diagram and the current /3 CSV template. Match by ID; reject
CC00, CC1, missing or repeated IDs. Keep colour's native names as the internal
semantic correspondence only. Previously imported formats retain their original
meaning; the local CC-labelled reference changes headers without changing any
measured values, frozen calibration or positive image.
