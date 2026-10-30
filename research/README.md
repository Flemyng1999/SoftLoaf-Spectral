# Earlier experiments

For the new implementation's local E100/simulated-RAW/LUT comparison, see
[the separate experiment](hsi-raw-lut-comparison.md). The results below belong
to the earlier programs.

The new [IT8 data and LUT trial](it8-lut-trial.md) audits a measured reflective
target and tests a first IT8-derived spectral prior for LUT construction.
The [sampling-database study](sampling-database-study.md) compares color-space
feasibility and measured-spectra selection, with bounded synthetic metamer tests.
The [database build](sampling-database-build.md) implements separate local
reversal/negative input banks, independent model selection and readback checks.

These experiments were run before this repository was created. The results
below were transcribed from saved reports on 2026-10-26.
[baseline.json](baseline.json) records selected results and report hashes.
The full reports, data and programs are not included in the public repository,
so the experiments cannot be reproduced from this record alone.

All experiments used the same eight Manchester spectral scenes. These were
development data, not an independent test set.

A complete local copy is now recorded in [Local archive](local-archive.md).
It is excluded from public distribution pending data and asset review.

## 5207 digitization

The simulated negatives were captured under a measured narrow-band light and
standard D50, each paired with its earlier matrix. A limited-band APD result
provided another comparison. Whole-roll Dmin/Dmax fitting and display processing
ran in a separate application.

Readback checks passed for 16 CCM images, 24 display images, 18 DNGs, 18 float
TIFFs and three calibration rolls. The material model used original Status M
curves. Its neutral fitting error was about 1.06e-8 D; this does not validate
colored-film response.

GH7 measurements did not retain relative channel gains. The matrix calculations
used a stated coordinate convention, whose match to real hardware remains
unverified. These results do not rank the lamps or cameras by color accuracy.
The limited APD band omitted about 0.30% of blue response weight.

## 5207 printed on Ultra Endura

E-4020-generation curves and finished-print measurements were used to fit a
white envelope and three effective reflection-density components. The white
was fitted rather than measured from unexposed paper.

217 patches were used for fitting and 71 new-color patches were held out.
Held-out reflectance RMS was 0.0098308573, mean ΔE76 was 3.97555, and the 95th
percentile was 14.98995. Test-patch coefficients were fitted from each test
spectrum, so these values describe spectral representation, not independent
prediction from known paper exposure.

A simulated 3200 K lamp and ideal filters were balanced with neutral gray and
shared across eight photographs. The observation calculation covered
380–780 nm at 10 nm intervals. Paired exposure/print measurements are still needed.

## E100 reversal

All three curve families came from E-4000, revised 8-18. The characteristic
plot specified Status A. Effective CMY coefficients were fitted and constrained
to be nonincreasing with exposure. Maximum neutral density error was 0.000868824 D.

Eight scenes at three exposures produced 24 spectral images and 56 individual
PNGs. Independent numerical readback passed, with at most one 8-bit PNG code
value of difference.

Exposure integration covered 400–720 nm at 10 nm intervals; viewing covered
400–700 nm at 2 nm intervals. Simulated 18% gray was assigned to D50 visual
transmission Y=0.1, with optional shared viewing gain 1.8. This exposure anchor
was chosen for the simulation. Base absorption was not measured separately.
Real E100 color/exposure measurements have not yet been used for validation.

## Reproduction

Reproducing these calculations requires accessible inputs, permission to use
them and the recorded settings. The standalone implementation needs its own
tests; the checks above apply only to the earlier programs.
