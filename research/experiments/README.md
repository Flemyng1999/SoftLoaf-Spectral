# Capture white normalization

This utility replays a local historical experiment. It is not the standalone
film engine. The supplied spectra, camera profiles, native inversion program
and viewing configuration remain external inputs and are not distributed here.
See [data and licensing](../../docs/data-and-licensing.md).

All five capture setups now use no-film illumination as unit white, (1, 1, 1).
Film-base absorption is retained. The original matrix convention is a linear
RGB row vector multiplied by the matrix on its right. Dividing input channel
`i` by its old white value requires multiplying matrix row `i` by that value.
This leaves the matrix output unchanged. It does not recover missing sensor
gains or establish a real camera/profile calibration.

Both sides of the matrix on/off comparison receive the same normalized capture
values. Each branch then repeats the eight-frame roll fit and display processing.
The result includes the fit's response to the changed channel transform.

## Run

Requires Python, NumPy, Pillow and Matplotlib. Supply the historical
`hyperspectral-demo` directory, original profile directory, external native
viewing configuration with its referenced LUTs, and a Chinese font. The archive
is read only; output must be outside it.

```sh
python -m unittest discover -s research/experiments -p 'test_capture_white.py'
python research/experiments/replay_capture_white.py \
  --archive "$EXPERIMENT_ARCHIVE" \
  --output "$EXPERIMENT_OUTPUT" \
  --profile-dir "$ORIGINAL_PROFILES" \
  --ocio "$REFERENCE_VIEW_CONFIG" \
  --font "$CHINESE_FONT"
```

The archive contains the historical native reference at
`tools/native_5207_reference`. Its executable dependencies must be available on
the machine. This recipe uses the already decoded synthetic RAW samples rather
than running RawTherapee again. Normalized previews are white-balanced camera
channel diagnostics with sRGB display encoding, not untouched RAW or calibrated
sRGB color. The retained XYZ previews use CIE 1931 2°, finite-band D50 or S_APD
illumination, Y=1 no-film white, no added viewing gain, and no white adaptation.

The program saves original input hashes, both matrix scales, float64 equivalence
checks, neutral checks, native roll models, floating-point images and PNG readback
checks in `report.json`. The local report includes source records and is not a
public data package.

## Check on 2026-10-26

All five white constraints, neutral ramps and output-equivalence checks passed.
Ten branches used eight frames each; all fits reported response model version 5.
PNG pixels and embedded sRGB profiles were read back. Float64 matrix-output
invariance error was at most 2.23e-16.

| Setup | Maximum native matrix-output difference | Maximum final sRGB difference |
| --- | ---: | ---: |
| GH7, RGB light | 1.79e-7 | 2.99e-6 |
| GH7, D50 | 1.20e-7 | 1.38e-6 |
| Color IMX273, RGB light | 1.20e-7 | 1.38e-6 |
| Color IMX273, D50 | 1.79e-7 | 6.17e-6 |
| Monochrome IMX273, three lights | 5.97e-8 | 1.52e-6 |

These are differences from the earlier matrix-on calculation after changing
units and rounding to float32. They are numerical checks, not errors against
measured film. Matrix-off results now start from the normalized white and
supersede the earlier off-branch comparison figures. The material model,
physical transmission previews, paper model and E100 experiment are unchanged.

## References used by the manuscript

- [ISO/CIE 11664-3:2019](https://www.iso.org/standard/74165.html): calculate color from spectral distributions.
- [ISO 5-3:2009](https://www.iso.org/standard/52915.html): spectral conditions for density measurement.
- [SMPTE ST 2065-2:2020](https://pub.smpte.org/latest/st2065-2/st2065-2-2020.pdf): APD printing-density definition.
- [SMPTE ST 2065-3:2020](https://pub.smpte.org/latest/st2065-3/st2065-3-2020.pdf): ADX density encoding.
- [ACES, IDTs: How Do They Work (2020)](https://acescentral.com/knowledge-base-2/idts-how-do-they-work/): established use of white balance and matrix transforms for camera input.

The APD target and ordinary camera-to-ACES input transform have different output
meanings. The local linear-channel matrix is an experiment, not an APD standard
formula. Neither RGB illumination nor this roll solver is mandated by these
references. Finite spectral coverage, missing GH7 gains and approximate material
models prevent a claim of full measurement-standard conformance.
