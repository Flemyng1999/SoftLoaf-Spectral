# Earlier experiments

The following results were read from saved reports on 2026-10-26. The calculations
precede this repository. [baseline.json](baseline.json) contains selected results
and hashes of the reports. Full reports, data and implementations are not bundled,
so this record alone is not a reproducible benchmark.

The same eight Manchester spectral scenes were used throughout. They are
development scenes rather than a new independent test set.

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

The standalone implementation will need source permissions, accessible inputs,
recorded settings and new tests. Passing checks in the earlier programs does
not establish that the new implementation is correct.
