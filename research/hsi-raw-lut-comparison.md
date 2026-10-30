# E100: hyperspectral reference and simulated RAW through a LUT

Local experiment for [Issue #2](https://github.com/Flemyng1999/SoftLoaf-Spectral/issues/2).
The implementation is independent of the historical Python programs and other
applications' private code. It reuses local numeric source data and density
measurement weights. Restricted inputs and generated LUTs remain outside Git.

## Method

The same Manchester reflectance image is multiplied by D65 and sent down two
paths. The reference integrates that spectrum with E100's layer sensitivities,
calculates dye amounts and transmittance, then integrates D50 through the film
to observed XYZ. The camera path integrates the original scene spectrum with
R5 or D850 responses, quantizes a synthetic RAW, applies a matching DCP subset,
converts to ACEScg/ACEScct and applies the spectral-derived LUT.

An ideal RGB control calculates the scene's CIE XYZ without a camera profile,
then uses the same RGB approximation. A continuous, non-LUT version of the
approximation separates its error from interpolation. All final images use
the same OpenDRT processor and standard sRGB file encoding. Pre-render XYZ
errors are retained too; the display transform can compress visible differences.

## Results, 2026-10-26

The complete run produced 144 frame/camera/exposure/grid comparisons and 48
synthetic DNGs. Each camera's pooled statistics contain 1,972,545 pixel/exposure
samples. Display errors below use delta E00 after the same OpenDRT and sRGB
conversion, including final display-range clipping.

| Camera response and matching DCP | 65-edge LUT total mean | Total 95th percentile | Total maximum | LUT-only 95th percentile |
| --- | ---: | ---: | ---: | ---: |
| Canon EOS R5 | 1.773 | 8.794 | 21.823 | 0.204 |
| Nikon D850 | 1.625 | 7.147 | 19.433 | 0.204 |

Total error compares the simulated RAW/DCP/LUT path with direct spectral E100
integration. LUT-only error compares the read-back LUT with the same continuous
RGB-prior calculation, holding the camera input fixed. These errors are not
additive: profile and prior deviations can reinforce or cancel each other.

| LUT edge size | R5 LUT-only 95th percentile / maximum | D850 LUT-only 95th percentile / maximum |
| --- | ---: | ---: |
| 33 | 0.781 / 1.780 | 0.777 / 1.806 |
| 65 | 0.204 / 0.892 | 0.204 / 0.871 |
| 129 | 0.062 / 0.355 | 0.063 / 0.363 |

The 65-edge LUT meets the earlier delta E00 interpolation proposal on these
scene samples and the revised 99% code-value criterion below for pooled samples.
Neither result certifies the full LUT domain or a general release.
Increasing the edge size to 129 changes total mean error only from 1.773 to
1.773 for R5 and from 1.625 to 1.619 for D850. The current spectral prior and
camera characterization need more work; grid density is not the main limit.
Purple flowers and other colors show substantial residual differences. The
table cannot rank the cameras: each result includes a separate profile and
unverified measurement-to-profile gain compatibility.

### Acceptance: at least 99% of pixels within 2/255 per RGB channel

The user revised this limit to require at least 99% of pixels to pass in the
final bounded, standard-encoded sRGB image, with the display transform held
fixed. A pixel passes only when all three channels differ by at most 2/255.
The report records both continuous differences multiplied by 255 and differences
after rounding each output to 8-bit, exactly as for PNG export. The strict
verdict requires both checks to reach 99%. Maxima remain diagnostics.
This threshold is a code difference, not delta E00 = 2.

| LUT edge | Camera | Total maximum, 8-bit codes | Total pixels within 2 codes | LUT-only maximum, 8-bit codes | LUT-only pixels within 2 codes |
| --- | --- | ---: | ---: | ---: | ---: |
| 33 | R5 | 96 | 61.921% | 22 | 98.210% |
| 33 | D850 | 89 | 54.961% | 21 | 98.146% |
| 65 | R5 | 96 | 62.288% | 10 | 99.952% |
| 65 | D850 | 88 | 57.498% | 9 | 99.954% |
| 129 | R5 | 96 | 61.821% | 4 | 99.9975% |
| 129 | D850 | 88 | 57.799% | 4 | 99.9981% |

The pooled LUT-only results pass the revised limit at 65 and 129 edges for both
cameras, including the continuous-code check (at least 99.9336% at 65 edges and
99.9934% at 129 edges). The 33-edge results fail. None of the total-error results
passes. At both 65 and 129 edges, all 48 camera/exposure/scene combinations
also pass separately. The worst 65-edge frame has 99.3372% of pixels within the
continuous-code limit. This per-frame check is separate from the pooled verdict.
At 129 edges the LUT-only
continuous maxima are 3.825 and 3.895 codes for R5 and D850; 50 and 38 rounded
pixels exceed two codes respectively. Total continuous maxima remain 95.629
and 87.990 codes. The total-error checks therefore still fail. These are
results for the declared development scenes, cameras and exposure settings,
not bounds over all possible inputs. Improving grid interpolation alone cannot
resolve the much larger total deviation in this experiment. The RGB spectral
prior and camera/profile compatibility require separate investigation.

The neutral-density fit error was 0.000868824 D. Independently refitted dye
amounts differed from the archived fit by at most 1.61e-13. No tested RAW channel
clipped and no evaluated camera pixel exceeded the LUT domain. Our float64 LUT
evaluation and OCIO differed by at most 7.32e-7 in XYZ. PNG pixel readback passed;
the complete test suite, including code-limit checks, reported 29 passed.
ExifTool validation of a generated
DNG, with large-array decoding enabled, reported OK. DNGs contain the selected
D65 technical matrix and base table as well as the CFA mosaic.

These checks establish a working model-comparison experiment. They do not
establish measured E100 color accuracy, a complete RAW developer or broad LUT
validity. All generated LUTs and images remain local.

The RGB approximation minimizes first differences of a 33-band spectrum subject
to three color constraints, with L2 regularization 1e-8. Negative reconstructed
bands are then projected to zero. This projection can change the reconstructed
input color. It is an explicit first prior, not a unique spectrum recovery or
a demonstrated best method. It is not fitted to any of the test photographs.

The LUT samples ACEScct over [-0.25, 0.75] on each channel and outputs relative
viewed XYZ D65 before OpenDRT. The experiment compares 33, 65 and 129 edge sizes,
with tetrahedral interpolation. Files are read back by our float64 evaluator and
independently by OpenColorIO. The input/output definitions must accompany these
experimental CUBE files; their output is not ordinary display RGB.

A [33-edge sampling follow-up](lut-sampling-33.md) compares trilinear
interpolation, coefficient fitting and a smaller domain. Its fitted table
passes pooled scene percentages but fails some frames and guard checks;
it does not replace the 65-edge control.

## Conditions

- Eight existing development scenes: 1, 5, 6, 16, 31, 38, 43 and 50. All run at
  -1, 0 and +1 EV. These scenes have been used historically and are not a new
  independent final evaluation set. Example views 16 and 43 were chosen before
  looking at the errors.
- Scene/camera/film exposure integration: 400–720 nm, 10 nm trapezoidal weights,
  D65 relative energy SPD, no invented scene tails. The camera responses are used
  in the energy-domain relative convention; no electron count or physical ISO
  calibration is inferred.
- E100 E-4000 revised 8-18: original extracted sensitivity, characteristic and
  dye curves. CMY amounts are independently refitted using the archived numeric
  finite-band Status A weights, then projected to be nonincreasing with exposure.
  No separate base is added. The historical program is not imported.
- Each layer's exposure origin uses flat 18% gray under D65. The anchor is chosen
  from neutral D50 visual transmission Y=0.1. Viewing gain is fixed at 1.8 for
  every image and exposure. This differs from the historical D55 exposure lamp.
- Viewing: D50, 400–700 nm at 2 nm, CIE1931 2°, finite-band white adapted to D65
  with Bradford. All reference calculations are float64.
- DCP: D65 ForwardMatrix2 and linear, value-independent HueSatMap2, synthetic
  AnalogBalance/CameraCalibration identity. Tone, look and baseline exposure
  offsets are not applied. This is a narrow, declared subset, not a complete
  DCP engine. The camera responses and DCPs were not measured together.
- RAW: 16-bit RGGB DNG, black 512, white 65535, fixed two-stop headroom. Each HSI
  pixel becomes one constant 2×2 spectral patch. Numerical comparisons recover
  the co-located channels from those patches, retaining quantization but excluding
  ordinary demosaicing artifacts. No noise, lens model or spatial resolution
  claim is included. A DNG readback checks the mosaic and CFA tags.
- Display: unchanged official OpenDRT v1.0.0 mini-config revision 2, Default
  appearance. Its `sRGB Encoding` colorspace models a nonstandard display EOTF,
  so it is not used as the file encoder. Our adapter uses the encoding table in
  its forward direction and is tested against independent IEC sRGB math; see
  [Color management](../docs/color-management.zh-CN.md).

## Inputs and local outputs

The default archive is the research data copy described in
[Local archive](local-archive.md). No measurement or profile is copied into the
source package. Source filenames and SHA-256 values are saved in the report.

- [Manchester scenes](https://doi.org/10.48420/14877285.v3), Foster, Amano and
  Nascimento; archived release metadata identifies CC BY 4.0.
- [RAW to ACES camera data](https://github.com/AcademySoftwareFoundation/rawtoaces-data),
  Canon EOS R5 and Nikon D850 files, measured by Weta Digital; file headers
  identify Apache-2.0. The records do not establish this experiment's physical
  exposure or compatibility with another source's DCP gains.
- RawTherapee-distributed matching DCPs in the local research archive. Their
  internal copyright field says public domain; that field is preserved as a
  source record, not a general redistribution decision.
- Kodak E100 extracted curves, finite-band density weights and CIE tables have
  the review status recorded in [Data and licensing](../docs/data-and-licensing.md)
  and [registry.json](../data/registry.json). Model/LUT distribution remains pending.
- [OpenDRT official package](https://github.com/jedypod/open-display-transform/releases/download/v1.0.0/OpenDRT_v1.0.0_mini-config_v2.zip),
  SHA-256 `c1a60bb4bd77bc2ae9c897143f9036229d816a9009aed58cfd4c5933fe9f6cc1`.

Outputs go to ignored `artifacts/hsi-raw-lut/`: `report.json`, CUBE files,
synthetic DNGs, sample XYZ/channel arrays, PNG comparisons and exact dependency
versions. The report separates input-profile, prior, interpolation and total
errors. No observed difference is a measurement of real E100 accuracy.

## Run

Use Python 3.12 in a project environment and install
`requirements-experiment.txt`. Supply the local research archive and official
OpenDRT zip; no installed private application or absolute source path is required.

```sh
python -m pytest -q
python -m experiments.hsi_raw_lut \
  --archive local/film-color-slides/hyperspectral-demo \
  --opendrt local/reference-assets/OpenDRT_v1.0.0_mini-config_v2.zip \
  --output artifacts/hsi-raw-lut
```

`--scenes 16 43 --grids 33 65` runs a smaller diagnostic. The optional display
integration test skips when the official zip is not supplied; numerical tests
do not require the restricted material or scene files. This experiment does not
complete the source-acquisition/vector-extraction work in Issue #1.
