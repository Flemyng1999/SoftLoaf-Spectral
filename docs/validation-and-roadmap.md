# Development

## 1. E100 reference program

Start with E100 because the original E-4000 characteristic plot specifies
Status A and the curves are available as vectors. Implement curve extraction,
exposure integration, density fitting and viewing in a standalone Python program.
Use float64 as the numerical reference.

Required checks:

- Document how to obtain each input and review its permitted use.
- Reproduce eight scenes at three exposures without another application's code,
  binaries, installed profiles or local absolute paths.
- Save source hashes, settings, spectra, XYZ and linear RGB. Read the saved PNGs
  back and compare them with the reference values.
- Keep transmission positive and at most one; neutral transmission must not
  decrease with exposure. Reproduce neutral Status A curves within 0.001 D.
- Compare with the earlier calculation and explain any differences.

The 0.001 D check concerns neutral-curve fitting. Real E100 exposure/color
measurements are still needed before reporting material accuracy.

## 2. RGB processing and the first LUT

Compare direct RGB fitting and a specified spectral prior. Use whole unseen
scenes for validation; random pixels from training photographs are not a separate
test set. Keep repeated patches and exposure variants within one split. The
earlier eight scenes are development data.

The first export is planned as ACEScct input to fixed sRGB display output. Record
the supported domain, exposure range, negative-value handling, shaper and
interpolation. Test `.cube` serialization in an independent implementation or host.
Compare 33, 65 and 129 point grids before selecting a default.

An initial interpolation-error target is 95th-percentile ΔE00 at most 0.5 and
maximum at most 2.0 against the RGB program under the same specified display
conditions. These are proposed LUT-export tolerances, not measured results or
film-accuracy targets. Check dark ramps and domain boundaries separately.

Publish the settings, inputs, build instructions, licenses, revision and results
with each LUT. Pending data rights prevent distribution of the affected assets.

## 3. 5207 and optical printing

Implement 5207 independently from documented methods. Separate calibration fit,
saved state and fixed application. Check capture units and profile compatibility
before treating a light/camera pair as a usable preset.

For optical printing, retain separate enlarger and viewing lights. Improve the
paper spectrum fit and obtain paired exposure/print measurements. The existing
paper result has large errors for some colors and needs further work.

Compare all three routes on common scenes with declared viewing conditions.
State any differences in tone or display processing that remain in the comparison.

## 4. Filters and host support

Add CLF/OCIO output and GPU processing after the fixed reference is tested.
Compare optimized output with the float64 reference, then measure runtime,
precision and memory on named hardware. Select a host plugin when there is a
specific requirement. Grain and halation are separate tasks.

## Measurements

Keep four errors separate:

| Error | Comparison |
| --- | --- |
| Material model | Prediction against independently measured film/print output with known exposure and processing |
| RGB approximation | RGB result against spectral reference on held-out spectra, including metameric variation |
| Implementation | Optimized CPU/GPU result against the reference calculation |
| LUT export | Read-back LUT result against the same fixed RGB calculation |

Neutral fits and test-spectrum fits using the test patch's own coefficients
are not independent material tests.

Record spectral errors, color differences, percentiles, worst cases, neutral
balance, hue/chroma behavior and clipping. Color metrics require the same
observer, adaptation and display conditions. Include measurement uncertainty
when available.

Test neutral ramps, exposure brackets, saturated reflectances, metamers and
illumination changes. Add licensed skin and sky scenes when available; neither
is validated by the present eight-scene set. Check units, curve direction,
missing bands, finite values, saved settings and rejection of mismatched inputs.
