# References

## Related software

- [Lensfun](https://lensfun.github.io/), public lens database and image-coordinate
  correction library. The scan adapter loads an installed 0.3.4 database, freezes
  a selected distortion map and compares it with the library's coordinate output.
  Its [modifier documentation](https://lensfun.github.io/manual/latest/structlfModifier.html)
  separates coordinate transformations from pixel interpolation. Sampling and
  source-space flat correction here are independent implementations.

- [Spectral Film LUT](https://github.com/JanLohse/spectral_film_lut), Jan Lohse.
  Generates film-emulation LUTs from material data; supports negative, print and
  slide workflows. The repository identifies MIT licensing.
- [Spektrafilm](https://github.com/andreavolpato/spektrafilm), Andrea Volpato.
  Continuation of agx-emulsion, for spectral simulation of photographic processes.
  The repository identifies GPL-3.0 and includes further project-specific notices.

No code or data from these projects is included here. Before reusing either,
check the exact version, file licenses and data permissions.

## Color management and display rendering

- [DCamProf](https://rawtherapee.com/mirror/dcamprof/dcamprof.html), Anders Torger.
  Camera profiling from measured targets or spectral sensitivities; its
  documentation covers DCP matrices, color tables, white balance and neutral
  input profiles. The documented v1.0.6 release dates to 2018.
- [Adobe DNG specification 1.6](https://helpx.adobe.com/content/dam/help/en/photoshop/pdf/dng_spec_1_6_0_0.pdf),
  chapter 6, for camera-to-XYZ conversion and profile table application.
- [OpenColorIO](https://opencolorio.org/), for fixed color conversions and execution
  of the display configuration. See the [configuration guide](https://opencolorio.readthedocs.io/en/stable/guides/authoring/authoring.html).
- [Open Display Transform / OpenDRT](https://github.com/jedypod/open-display-transform),
  Jed Smith, for display rendering. The official v1.0.0 OCIO mini-config revision 2
  was inspected; its configuration, transfer tables and display LUTs carry an MIT
  license. The repository's main license is GPL-3.0. These are separate records.

No third-party implementation or configuration is bundled yet. Package identity,
hash and input/output requirements are in [Color management](color-management.zh-CN.md) (Chinese).

## Data and standards

- [Kodak E100, E-4000, revised 8-18](https://www.kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/e4000_ektachrome_100.pdf).
- [Wolf Faust test data](https://www.colorreference.de/testdata/index.html), including measured target spectra used in the Ultra Endura study.
- [Foster, Amano and Nascimento, fifty hyperspectral outdoor scenes](https://doi.org/10.48420/14877285.v3).
- [CIE datasets](https://cie.co.at/data-tables), with release-specific metadata and licensing.
- [ACES CLF implementation guide](https://docs.acescentral.com/clf/guides/), for transform export and ACES interchange.

Links checked on 2026-10-26. Redistribution terms must be checked for each source.

## Additional user-selected reference

[Spektrafilm](https://github.com/andreavolpato/spektrafilm) was explicitly added
on 2026-10-26. The [pinned data review](../research/spektrafilm-review.md) records
250D, Ultra Endura and Ektachrome profiles, processed-density conventions,
missing bands and separate code/profile license records. It has not replaced
the current runtime model.

## RAW development and photo-workspace architecture

- [RawTherapee 5.12](https://github.com/RawTherapee/RawTherapee/tree/a8a3d1bc7b419ed1c974c39276c97e618a4f9a1b): CLI precedence, ProcParams, camera-profile selection, float output and ICC handoff. Runtime is local; no engine source copied into this repository.
- [AlcedoStudio](https://github.com/zidage/AlcedoStudio/tree/18c863702565e4be7cba5d889314b555b6fb6037): thumbnail service, versioned disk cache, bounded decode work and export queue. Source inspected as an architectural reference; no source or Qt framework imported.

Both were explicitly selected by the user. This addition extends the earlier pre-2021 reference scope for these named projects.
