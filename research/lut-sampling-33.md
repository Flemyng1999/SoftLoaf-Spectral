# 33-edge LUT sampling and interpolation trial

Follow-up to [the E100 RAW/LUT comparison](hsi-raw-lut-comparison.md),
[Issue #2](https://github.com/Flemyng1999/SoftLoaf-Spectral/issues/2), 2026-10-26.
The objective is at least 99% of pixels within 2/255 in all three final sRGB
channels. This trial changes the approximation of the same continuous spectral
recipe; it does not improve camera characterization or recover missing spectra.

## Result

Fitting the nodes and using trilinear interpolation brings the full-range 33-edge
LUT above 99% on pooled development pixels. It passes only 35 of 48 frames
separately and regresses on boundary and monotonicity guards. Keep it as an
experiment, rather than replacing the 65-edge control. No further tuning was
attempted after these checks.

Both continuous-code and rounded 8-bit checks must reach 99%. The table reports
each camera's 1,972,545 pixel/exposure samples; a frame passes only if both checks
pass. Every fraction counts a pixel only when all three channels pass.

| Sampling / interpolation | R5 continuous / 8-bit | D850 continuous / 8-bit | Frames passing / 48 |
| --- | ---: | ---: | ---: |
| Original 33, tetrahedral | 96.071% / 98.210% | 96.033% / 98.146% | 11 |
| Original 33, trilinear | 97.441% / 98.344% | 97.368% / 98.296% | 27 |
| Fitted 33, trilinear, same domain | **99.140% / 99.463%** | **99.176% / 99.503%** | 35 |
| Fitted 33, tetrahedral control | 98.678% / 99.342% | 98.697% / 99.369% | 29 |
| 33, domain [0, 0.7], tetrahedral | 99.608% / 99.758% | 99.636% / 99.794% | 41 |
| Original 65, tetrahedral control | 99.935% / 99.952% | 99.934% / 99.954% | 48 |

The worst fitted/trilinear frame is scene 38, +1 EV, R5: 94.634% continuous
and 96.140% rounded pixels pass. Its pooled 8-bit maximum errors are 19 and
18 codes for R5 and D850. A passing pooled percentage does not make those
remaining errors small. The 65-edge control's worst frame is 99.337% continuous.

Total errors against direct HSI-to-E100 integration still fail: fitted 33 gives
61.194% and 57.363% rounded pixels within two codes for R5 and D850. These total
results include the existing spectral-prior and profile deviations, not just
LUT interpolation error. They are not measurements of real E100 accuracy.

## What changed

The original LUT evaluates the spectral recipe exactly at a uniform 33-edge
ACEScct grid. Its tetrahedral interpolation has 155,751 continuous-code failures
in the two cameras' pooled samples; failures occur above maximum-channel
ACEScct 0.3, rather than in the dark bins. Switching interpolation alone improves
the result but does not reach the target.

The fitted variant keeps the original ACEScct AP1/D60 domain [-0.25, 0.75] and
relative viewed XYZ D65 output before OpenDRT. There is no additional shaper or
hidden lookup table at application time:

1. Evaluate the unchanged float64 spectral recipe on a uniform 65³ grid,
   including the original nodes and their midpoints.
2. Fit 33³ XYZ coefficients by unweighted least squares to those analytic
   outputs, using a separable trilinear basis. The objective is XYZ error at
   the analytic grid, not perceptual error or photograph-specific error.
3. Project negative XYZ coefficients to zero. There were 83 negative component
   values before projection, with minimum -0.0508919. This projection is a
   declared safeguard, not a constrained least-squares optimum.
4. Write and read back a 33³ CUBE, then evaluate it using trilinear interpolation.
   The saved table contains 35,937 three-channel samples. It requires the stated
   input/output definitions and interpolation at the host; the current CUBE
   writer does not embed an interpolation setting.

The coefficients approximate the continuous recipe and are no longer exact
material evaluations at each node. They must not be shown as measured spectra.
The same table evaluated tetrahedrally fails the continuous 99% pooled check.
This interpolation choice is specific to this candidate, not a general ranking.

The smaller-domain control keeps exact material evaluations but spends all 33
samples per axis on [0, 0.7]. No development photo is outside it. Nevertheless,
this removes support for part of the old domain; it is not a full-range solution.
Its worst frame reaches only 96.478% continuous. It is not selected as a default.

Neither coefficients nor domains were fitted to photographs. Candidate choice
was informed by their development results. These eight scenes have been used
before; the trial has no independent final evaluation set.

## Guards and file checks

| Check | Original 33 tetrahedral | Fitted 33 trilinear | Original 65 tetrahedral |
| --- | ---: | ---: | ---: |
| 100,000 uniform-domain random samples, continuous pass | 93.556% | 96.517% | 99.395% |
| Same random samples, 8-bit pass | 95.527% | 97.607% | 99.508% |
| Domain-face grid, continuous pass | 100% | 93.523% | 100% |
| 4,097-point neutral ramp, continuous pass | 98.609% | 100% | 100% |
| Decreasing Y steps along that ramp | 0 | 708 | 0 |

The fitted ramp's largest Y drop is 9.72e-5 between adjacent samples. It passes
the output code threshold, but the monotonicity regression is a reason not to
promote it. The random-domain seed is 20261026; guard samples are not used in
fitting. The boundary probe contains 386 points on the faces of a 9³ grid.
These finite checks are not a proof over the whole domain.

All scene inputs remain inside the original domain and no synthetic RAW channel
clips. The 65-edge control also reproduces the earlier scene statistics.
Float64 LUT evaluation and independent OCIO CPU file evaluation differ by at
most 7.40e-7 XYZ across the trial; all per-frame acceptance verdicts agree.
The test suite reports 36 passed, including independent OCIO trilinear readback
and an independently solved small coefficient-fit example.

## Reproduce

Use the same Python environment, local inputs and pinned OpenDRT package as the
first experiment:

```sh
python -m pytest -q
python -m experiments.lut_sampling \
  --archive local/film-color-slides/hyperspectral-demo \
  --opendrt local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip \
  --output artifacts/lut-sampling
```

This run produces 288 frame/variant comparisons. Its ignored output directory
contains six CUBE files, source and implementation hashes, recipe, per-frame and
pooled measurements, guard results and explicit interpolation settings in
`report.json`. Inputs and generated assets remain local pending rights review.
No private application code is used.

The generation contract and required node inputs are summarized in
[生成胶片 LUT 需要哪些输入](../docs/lut-generation-inputs.zh-CN.md).
