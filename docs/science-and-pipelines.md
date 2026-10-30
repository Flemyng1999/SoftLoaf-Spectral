# Methods

This document describes the calculations planned for the standalone engine.
A [local E100 experiment](../research/hsi-raw-lut-comparison.md) implements a
limited numerical reference and RAW/LUT comparison. The [local application](application-v0.1.zh-CN.md)
now uses a C++23 float64 port for pointwise reversal calculations and LUT
interpolation, checked against the Python reference. Material fitting and
OCIO display processing retain their existing implementations. The desktop
application now computes negative APD and optical printing with separately
recorded material assumptions; see the [numerical audit](5207-pipeline-audit.zh-CN.md).
[Earlier experiments](../research/README.md) contain results from separate programs.

## Quantities

Wavelengths are in nm. Each spectrum records its units, sampling intervals,
coverage and measurement geometry. Integration includes the quadrature widths.

Film sensitivity describes a layer's exposure response by wavelength.
A characteristic curve relates exposure to developed density. A dye-density
spectrum describes absorption after development. These are separate measurements.
CIE matching functions provide the colorimetric reference for viewing calculations.

Convert logarithmic sensitivity to linear values before integration. Keep
relative channel scales. With an energy SPD, quantum efficiency requires an
energy-to-photon conversion; a response already expressed per unit energy does not.

Each density record identifies the measurement geometry and spectral weighting,
whether base/fog is included, and whether base was subtracted. Status A, Status M
and APD use different definitions. Calculations over a limited wavelength band
must list the omitted coverage; they do not establish full conformance with a
measurement standard.

## Film exposure and development

The film-emulation interface uses each material's reference capture illumination:
5500 K CIE daylight for the current daylight stocks, and a 3200 K Planck
approximation for VISION3 tungsten stocks. New recipes and film changes adopt
this condition automatically and show it as a read-only note. This is a film
model reference, not an estimate of the imported photograph's illumination or
its camera white balance. Printing and viewing lights remain independent.
The lower-level reference calculation still accepts explicit scene conditions
for scientific comparisons. The application upgrades saved recipes, including
workspace baselines and deletion-recovery records, to the declared film
reference when validating or restoring them. An actual scene change increments
the recipe revision once. Other nodes and RAW stages remain unchanged. Unknown
materials without a valid reference retain their conditions rather than borrow
another stock's light. External recipe files are only rewritten when saved.

The scene reflectance factor multiplied by the exposure illuminant gives the
incident spectrum. Integrating it with each layer response gives effective
exposure. The material model converts these exposures to developed spectral
transmittance.

The initial model uses fixed CMY density spectra. Effective coefficients are
fitted along the neutral characteristic curves; each layer exposure determines
the corresponding coefficient. The model does not measure interimage effects,
masking chemistry, changes in dye spectra with concentration or process
variation. Fitting neutral curves alone cannot validate colored-film response.

Retain the original curve points and document resampling, endpoint holding,
base alignment and monotonic constraints. Use one identified stock revision.
Missing spectral tails and chosen exposure anchors remain explicit assumptions.

## Negative APD and standard output

The selected negative route is scene input → exposure/development → negative
transmittance → standard Academy Printing Density (APD) → standard output →
display. It does not simulate a capture lamp, sensor or scanner calibration.
The separate optical-printing route still uses its enlarger light and paper.

APD is the density metric specified by SMPTE ST 2065-2:2012. ADX is its exchange
encoding, specified by SMPTE ST 2065-3:2012; floating-point APD density is not an
ADX code value, camera RGB, XYZ or display RGB. The [Academy documentation
index](https://acescentral.com/aces-documentation-copy/) lists both standards
and informative bulletin TB-2014-005. The user-supplied bulletin has now been
read, including its historical S-2008-002 v1.1 appendix. The bulletin explicitly
defers conformance to the superseding SMPTE standards. Its source identity,
page references and implementation boundaries are recorded in
[APD and ADX](apd-adx.zh-CN.md) (Chinese); normative verification is still pending.

Integrate transmittance using the original standard spectral weights, complete
coverage and prescribed normalization. Freeze those definitions and source
hashes. A changed weighting is a custom density metric, not standard APD.
The standard responsivities already incorporate their defined printing influx;
do not multiply an additional capture/viewing lamp or the separate influx table.
Missing spectral bands must not be filled with zero while claiming conformance.
Record Dmin/base-density treatment, channel gains and any ADX encoding separately;
do not infer their values or processing order from the names alone.

5207 material calibration uses Kodak's original Status M characteristic curves
and Status M spectral products. Status M is the measurement definition of those
curves; APD is the negative-output density definition used before ADX encoding
and the film input transform into ACES. Neither is an RGB color space.
The original Status M targets are never converted to APD during material fitting.
The fitted transmittance is integrated as APD only by the negative-output branch;
optical printing uses the same transmittance directly, without APD or ADX.

Negative material and positive rendering are independent selections. ECN-2 and
C-41 retain their material source and Status M identity with either rendering
branch. Applying the current motion-picture input transform to C-41 is explicitly
experimental, not a validated stock-specific color transform. Changing rendering
does not refit the negative or change its spectral transmittance.

A separately proposed scan-negative input would recover negative material state
from calibrated camera channels before those same rendering branches. It is not
implemented by the current ordinary scene-RAW handoff. Its spectral inputs,
fixed calibration and external validation requirements are described in the
[scan-negative LUT design](scan-negative-lut.zh-CN.md) (Chinese).

A stock-specific 3×3 matrix and offset can estimate APD when only Status M
readings are available. This was used by models /1 and /2 and is retained as
historical reference, not as a production material or printing step in /3.
With a spectral transmittance model, direct integration avoids that additional
regression error. Neutral fits still cannot establish full-color accuracy.

The standard-output node contains the versioned APD/ADX-to-ACES conversion and
the bridge from its declared output to the application's XYZ interface. Use
the pre-2021 reference [aces-core v1.2 (2019)](https://github.com/aces-aswf/aces-core/tree/v1.2),
then lock the exact transform, dependencies and hashes after inspection. The
original CTL is now reproduced in float64: continuous ADX16 codes enter
channel-dependent/independent density matrices, the specified toe table and
linear log-exposure segment, then exponentiation and the exposure-to-AP0 matrix.
Matrix orientation and toe behavior are tested against OCIO's independent
ADX16 builtin. ACES AP0/D60 is adapted to the application's XYZ/D65 interface.
The reference is commit 518c27f577e99cdecfddf2ebcfaa53444b1f9343 and transform
a1.0.3; its Academy license is retained under third_party/aces-v1.2.

5207 uses directly extracted Kodak H-1-5207t July 2015 curves and ISO 5/3:1984
Table 4 Status M products, independently checked against ANSI/ISO 5-3:1995.
Log products are interpolated with the printed tail slopes and integrated over
360–730 nm / 2 nm using normalized trapezoidal weights. This is a recorded
finite-band approximation, not ISO 5-3:2009 computational conformance.
The published minimum-density shape is aligned to the lowest original Status M
exposure plateau to form a frozen modeled Dmin. This is not a measured
zero-exposure sample. Dye density below 400 nm uses endpoint extension
through 360 nm, explicitly recorded. The current result is an APD reference
calculation, not a normative SMPTE conformance claim or full-color validation.
Model `5207-paper-reference/4` retains signed, Dmin-subtracted CMY increments
from the hash-pinned original extraction rather than the clipped legacy CSV.
It checks that the resulting absolute density remains nonnegative across all
bounded layer combinations. The D55 gray exposure denominator now uses the same
photopic normalization as runtime illumination. See the [Status M recheck](5207-status-m-validation.zh-CN.md)
for source-curve back-calculation, independent outputs and remaining material errors.
The /4 default camera illuminant is CIE daylight at 5500 K, matching Kodak's
declared test illuminant approximately. Paper conditions remain separate:
Status A, RA-4 at 35°C for 45 s, and 0.5 s reference exposure. The document's
print evaluation uses 5000 K ±1000 K; the application's D50 is an approximation.
The simulated 3200 K lamp, ideal CMY filters and software gray balance are
model settings, not manufacturer specifications. See the [source conditions](5207-d55-and-paper-conditions.zh-CN.md).
Old recipes with configured capture equipment cannot silently become APD
recipes. Preserve them and explicitly
create a new draft. Per-image fitting and automatic exposure remain outside a
fixed pointwise LUT.

## Optical printing

Negative transmittance, enlarger illumination and filtration determine paper
exposure. Paper sensitometry and the reflection model produce a finished-print
spectrum. The viewing illuminant and observer then give its color.

Printing and viewing use separately specified lights. Paper reflection includes
scattering, which a film transmission model alone does not describe. Paper white
must be measured or marked as a fitted parameter. Fluorescence requires separate
measurements and a model.

The initial Ultra Endura fit describes finished-print spectra. There are no
paired measurements of known exposure and resulting print spectra to test its
exposure-to-print predictions. The simulated 3200 K lamp and filters are ideal
components and do not represent a measured enlarger.

## Reversal viewing

Layer exposure gives developed CMY coefficients and transmittance. The viewing
light passes through that image before colorimetric integration. There is no
negative inversion stage.

The E100 model constrains effective dye amounts to decrease or remain constant
as exposure increases. The remaining neutral-curve error is retained in the
report. Residual base absorption is included in effective coefficients because
no separate base spectrum was available.

The earlier simulation assigns 18% gray to D50 visual transmission Y=0.1.
An optional shared viewing gain of 1.8 changes brightness. These settings do
not provide an absolute camera-exposure calibration.

Reversal transmission and paper reflection produce observed XYZ under declared
viewing conditions. Their default output is an OCIO colorimetric conversion
from adapted XYZ D65 to the target RGB primaries and transfer function, with
explicit final clipping. No scene-rendering transform is added by default.
The APD route instead uses its pinned film input transform and the official
ACES 2.0 output view. OpenDRT remains an alternative creative view, applied
once. Coordinate conversion into ACES does not make observed print or slide
colorimetry into original scene radiance. Independent formulas, saved-reference
replays, remaining model discrepancies and export errors are recorded in
[the three-route verification](pipeline-default-verification.zh-CN.md).

## Viewing and RGB inputs

The application generates LUTs from spectral data and process settings. Ordinary
camera RAW files will support grading, preview and rendered-image export, and
are not a prerequisite for LUT generation. RawTherapee development and a matching
DCP or matrix profile provide characterized RGB. Verify the exported profile,
transfer function, white point, exposure scale and clipping before bridging to
the OCIO working space; do not assume an internal working profile describes
the exported TIFF or that OCIO automatically interprets arbitrary ICC profiles.
Camera spectral sensitivities are optional
research inputs, not a prerequisite for using the application. DCP transforms
do not identify sensor sensitivities or recover the scene spectrum. See
[RAW input and camera profiles](raw-input-and-dcp.zh-CN.md) (Chinese).

The input profile belongs only to the camera that took the digital photograph;
the selected negative APD route has no simulated capture camera. Profile
components, white balance, channel scales, baseline exposure and any clipping
must be recorded; removing a DCP look and tone curve alone does not establish a
neutral or exposure-linear input. Profile approximation error is tested before
the film stage.

Initial viewing calculations use CIE 1931 2°, explicit illumination and band
coverage, and Bradford white adaptation where specified. Record the display
encoding, luminance convention, gamut handling and rendering transform. Keep
unclipped spectra and floating-point intermediate images.

Observed print or slide XYZ carries viewing conditions. Converting it to RGB
does not make it scene-referred, nor reproduce all human visual adaptation.

Fixed color conversions will use OpenColorIO, with OpenDRT for display rendering
through a pinned OCIO configuration. The bridge from observed XYZ records its
white adaptation, luminance scale and chosen linear input space. The negative
standard-output conversion must likewise declare its output before this module.
Preview, image export and display-baked LUTs use the same saved processing recipe.

Material checks retain spectra and XYZ before display rendering. A separate
colorimetric check view uses OCIO without OpenDRT's appearance processing.
Display rendering does not validate the material model. The configuration and
encoding requirements are in [Color management](color-management.zh-CN.md) (Chinese).

Ordinary RGB inputs do not identify a unique spectrum. Two approximations will
be compared on the same held-out data: direct RGB fitting and reconstruction
with a specified spectral prior. Reflectance reconstruction requires a declared
illuminant and cannot represent all emissive, fluorescent or specular stimuli.

Both routes derive their film response from the selected spectral-node recipe.
An RGB fit accelerates that recipe and must be trained and tested against its
spectral outputs. It is not an independently authored color look. Changing a
material or light invalidates affected LUTs and any approximation not verified
for the new parameters.

The application will keep the internal film LUT separate from OpenDRT. Its
planned interface is ACEScct input to relative XYZ adapted to D65, with its Y
scale and viewing meaning saved in the recipe. Negative APD standard output
declares its ACES output and XYZ bridge before using this interface. Preview applies the LUT, then
OCIO's input bridge and OpenDRT. The source spectra and original observed XYZ
remain available before this interface conversion.

Use metamer pairs to measure the film-response variation hidden by matching
input RGB. Report this separately from numerical and LUT interpolation errors.
Test negative and out-of-range RGB, exposure limits and illuminant changes.

The proposed [spectral sampling database](spectral-sampling-database.zh-CN.md)
separates measured spectra, coverage subsets, constrained synthetic/metamer
samples and numerical-domain probes. Color-space uniformity requires a stated
coordinate measure, exposure and range; it does not imply uniform spectral
coverage or physically feasible reflectances. Record original grids and
source-group splits, including derived/illuminant/exposure variants, before
selecting samples. Keep the database design separate from the user's LUT size.
The [local 0.1 build](../research/sampling-database-build.md) now writes separate
reversal and negative input SQLite banks with independent selections and models.
The reversal model is tested against the local E100 reference; negative tuning
currently uses input-spectrum RMSE only and has no APD or display labels.
This does not establish real-film accuracy or a released production dataset.
The ordinary workbench still uses its previous default prior.

The first external display-baked export is planned as ACEScct input to a fixed
sRGB display output, combining the internal film LUT and display processing.
Working-space looks require a separate output definition. An
ACES Look Transform uses the ACES2065-1 interchange convention even if it works
in another space internally; see the [CLF guide](https://docs.acescentral.com/clf/guides/).

## LUT settings

Each LUT records its stock and process revisions, source hashes, wavelength
grids, lights, exposure origins, channel scale and profile, paper and filter
settings, density definition, calibration, viewing gain, observer, adaptation,
gamut policy, input/output encodings, shaper, domain, interpolation and software
revision.

Also record the OCIO version, configuration and dependency hashes, source space,
Display and View, OpenDRT version and preset, and actual output transfer function.
An upstream display name alone is not a complete file-encoding definition.

Exposure variants recalculate the nonlinear film stage; scaling the finished
sRGB image gives a different result. Grain, halation, local effects and temporal
noise require processing outside a static color LUT.

## Current RAW handoff

The local application calls RawTherapee 5.12 twice with shared technical settings: float sRGB/D65 for the original image, and float linear AP1/D60 for film processing. An exported LUT consumes ACEScct AP1/D60, encoded without an additional sRGB conversion. The continuous reference preview consumes the corresponding linear AP1 values. File encoding, ICC readback and an independent colorimetric comparison are checked; this is not a real-camera accuracy claim. See [implementation, settings and results](raw-handoff-and-batch.zh-CN.md) (Chinese).


## Versioned enlarger optics

New printing recipes use spectral-v2: separate lamp, KG3, optional lens and
partial-insertion dichroic transmittances, followed by a fixed optional preflash
added before paper development. Legacy recipes remain numerically unchanged.
Paper minimum density may have a declared wavelength-dependent spectrum;
processed upstream shape and fixed Dmin-origin alignment are recorded separately
from original Status A characteristic data. See the [implementation, source
coverage and external integration comparison](printing-optics.zh-CN.md).


## Metal pixel implementation

The macOS image renderer independently evaluates the existing pointwise model
in float32 Metal kernels. RGB prior reconstruction or measured spectral input,
film exposure/development, APD/ADX or optical paper exposure/development,
colorimetric integration and the existing OCIO-generated MSL display graph are
GPU operations. Material fitting and frozen kernel preparation remain float64;
RawTherapee development, input preparation, single-point reference diagnostics
and file I/O/encoding remain CPU boundaries. The GPU is an implementation of
the same model, not a new spectral prior or an additional baked display LUT.

Tiles bound GPU working storage without image-sized intermediate spectral
arrays. Preview, original-size export and LUT baking share this implementation;
file execution and float64 validation remain independent. Previews preserve
source resolution up to a 2048-pixel short edge, with versioned cache rebuilding.
GPU errors do not silently select a different backend. See the [measured
implementation errors and hardware scope](metal-pipeline.zh-CN.md).

## Retained RAW developments

The application develops each immutable RAW under a frozen camera calibration
once for half-size preview and once at full resolution for export. Both technical
output spaces share the same decode. Film recipes, display views and exposure
edits consume retained floats and do not invalidate camera development. Keep
these two stages across restarts and do not evict them with display renditions.
An incomplete or corrupted retained stage needs explicit recovery, not an
unrecorded additional decode. Import copying and file hashing are I/O; this rule
is not a claim that the operating system reads each byte exactly twice.
