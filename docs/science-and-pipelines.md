# Methods

These are the proposed calculations. The repository does not yet contain an
implementation. [Earlier results](../research/README.md) describe the starting point.

## Quantities

Spectra use wavelengths in nm and carry units, sampling intervals, coverage,
and measurement geometry. Integration includes the quadrature widths.

Film sensitivity gives a layer's exposure response as a function of wavelength.
A characteristic curve relates exposure to developed density. A dye-density
spectrum describes absorption after development. These are separate measurements.
CIE matching functions provide the colorimetric reference for viewing calculations.

Convert logarithmic sensitivity to linear values before integration. Keep
relative channel scales. With an energy SPD, quantum efficiency requires an
energy-to-photon conversion; a response already expressed per unit energy does not.

Density records state whether they include base/fog, whether base was subtracted,
and which geometry or spectral weighting was used. Status A, Status M and APD
are separate definitions. A finite-band calculation lists the omitted coverage
and does not claim full measurement-standard conformance.

## Film exposure and development

Scene reflectance factor and exposure illumination give the incident spectrum.
Integration with each layer response gives effective exposure. The material
model then produces developed spectral transmittance.

The initial model uses fixed CMY density spectra and effective coefficients
inferred along the neutral characteristic curves. Each layer exposure drives
the corresponding coefficient. This approximation leaves interimage effects,
masking chemistry, concentration-dependent dye spectra and process variation
unmeasured. A neutral fit cannot establish the response to arbitrary colors.

Retain the original curve points and document resampling, endpoint holding,
base alignment and monotonic constraints. Use one identified stock revision.
Missing spectral tails and chosen exposure anchors remain explicit assumptions.

## Negative digitization

The negative transmittance multiplies the capture illuminant. Sensor integration
produces linear capture channels, followed by a matching calibration transform,
a declared density conversion, inversion, and display processing.

A CCM specifies its input units, channel order, multiplication convention and
calibration conditions. It applies to those capture channels. Camera RGB is not
already display RGB or XYZ.

The earlier GH7 measurements lost relative channel gains. The fixed matrix pairs
therefore remain experimental; their compatibility with a real capture setup
needs measurement.

Roll fitting and fixed application are separate operations. A fitted calibration
can be saved, then applied pointwise. A LUT requires that saved state, fixed
exposure and fixed viewing settings. Re-estimating parameters from each supplied
image set belongs in a filter, outside the cube.

For a scene-to-film-effect LUT, negative capture and inversion are internal
steps. A LUT that accepts actual negative scan RGB has a different input and
must be named and tested separately. Blind inversion tests must not receive the
forward model's known base or dye amounts as answers.

## Optical printing

Negative transmittance, enlarger illumination and filtration determine paper
exposure. Paper sensitometry and the reflection model produce a finished-print
spectrum. The viewing illuminant and observer then give its color.

Printing light and viewing light are independent. Paper reflection includes
scattering; a film transmission model alone does not describe it. Paper white
must be measured or identified as a fitted parameter. Fluorescence needs its
own measurements and model.

The initial Ultra Endura fit describes finished-print spectra. It has no paired
known-exposure measurements, so its exposure-to-print predictions remain unvalidated.
The simulated 3200 K lamp and filters are ideal components, not a particular enlarger.

## Reversal viewing

Layer exposure gives developed CMY coefficients and transmittance. The viewing
light passes through that image before colorimetric integration. There is no
negative inversion stage.

The E100 model constrains effective dye amounts to decrease or remain constant
as exposure increases. The remaining neutral-curve error is retained in the
report. Residual base absorption is included in effective coefficients because
no separate base spectrum was available.

The earlier exposure convention places simulated 18% gray at D50 visual
transmission Y=0.1. The alternative shared viewing gain of 1.8 changes viewing
brightness. Neither setting is an absolute camera-exposure calibration.

## Viewing and RGB inputs

Initial viewing calculations use CIE 1931 2°, explicit illumination and band
coverage, and Bradford white adaptation where specified. Record the display
encoding, luminance convention, gamut handling and rendering transform. Keep
unclipped spectra and floating-point intermediate images.

Observed print or slide XYZ carries viewing conditions. Converting it to RGB
does not make it scene-referred, nor reproduce all human visual adaptation.

Ordinary RGB inputs require an approximation. Compare direct RGB fitting with a
specified spectral prior on the same held-out data. RGB does not identify a
unique spectrum. Reflectance reconstruction also needs a declared illuminant and
cannot represent all emissive, fluorescent or specular stimuli.

Use metamer pairs to measure the film-response variation hidden by matching
input RGB. Report this separately from numerical and LUT interpolation errors.
Test negative and out-of-range RGB, exposure limits and illuminant changes.

The first practical export is planned as ACEScct input to a fixed sRGB display
output. Later working-space looks require a separate output definition. An
ACES Look Transform uses the ACES2065-1 interchange convention even if it works
in another space internally; see the [CLF guide](https://docs.acescentral.com/clf/guides/).

## LUT settings

Store stock/process revisions, source hashes, wavelength grids, lights, exposure
origins, channel scale/profile, paper/filter settings, density definition,
calibration, viewing gain, observer, adaptation, gamut policy, input/output
encodings, shaper, domain, interpolation and software revision.

Exposure variants must recalculate the nonlinear film stage. Scaling a finished
sRGB image is not the same operation. Grain, halation, local effects and temporal
noise are outside a static color LUT.
