# Scan RAW development through RawTherapee

2026-10-29, Issue #12, existing task branch. User explicitly requests replacing
LibRaw scan development with direct RT original-RAW development. The mixed
filmstrip comes from embedded JPEG being populated only for selected old items,
while other thumbnails still represent uncharacterized native camera channels.

Use the vendored RT 5.12 CLI. A native-camera output before WB/profile conversion
and the usual sRGB output share one RAW decode. Freeze half/full developments in
a new RT calibration contract; retain prior LibRaw stages without overwriting or
silently retrying them. Existing active calibration must be refitted from its
source chart and flat; map sample points through explicit sensor crop geometry,
not equal normalized coordinates. Rebuild existing previews from one RT sRGB
source, including every filmstrip thumbnail. Native values remain measurement
inputs. Avoid treating camera JPEG or temporary LinearRaw DNG as final RT output.

Check synthetic linear camera ratios, half/full ledger retention and restart;
compare sRGB with unmodified RT output, verify active real chart/roll, preserve
float64 inversion and full export checks. All pixels and temporary data stay T7.
