# Original CIE tables

These CSV and metadata files were obtained directly from the International
Commission on Illumination (CIE) on 2026-10-30. They retain the original bytes;
each CSV SHA-256 matches its accompanying official metadata. No other software
repository supplies these tables. `sources.json` records URLs, DOIs and hashes.

Copyright International Commission on Illumination (CIE). Each dataset's original
metadata declares **Creative Commons Attribution-ShareAlike 4.0 International**:
<https://creativecommons.org/licenses/by-sa/4.0/>. Legal code:
<https://creativecommons.org/licenses/by-sa/4.0/legalcode>.
This data licence is separate from the project's code licence. Preserve this
attribution, the source metadata and applicable share-alike terms for adaptations.
There are no modifications in these copies, and no endorsement by CIE is implied.

| Dataset | Citation DOI | Quantity and grid |
| --- | --- | --- |
| CIE 1931 standard colorimetric observer | 10.25039/CIE.DS.xvudnb9b | Relative x-bar, y-bar, z-bar; 2 degree observer; 360–830 nm, 1 nm |
| Standard illuminant D50 | 10.25039/CIE.DS.etgmuqt5 | Relative spectral power; 300–830 nm, 1 nm |
| Standard illuminant D65 | 10.25039/CIE.DS.hjfjmt59 | Relative spectral power; 300–830 nm, 1 nm |
| Illuminant D55 | 10.25039/CIE.DS.qewfb3kp | Relative spectral power; actual CSV 300–780 nm, 5 nm |
| Daylight components S0, S1, S2 | 10.25039/CIE.DS.w7zunnny | Relative daylight basis; actual CSV 300–830 nm, 5 nm |

The acquired D55 metadata description says 380–780 nm, while its hash-matched
CSV contains 97 rows from 300–780 nm. The daylight-component metadata description
says 360–830 nm at 1 nm, while its hash-matched CSV contains 107 rows from
300–830 nm at 5 nm. These original inconsistencies are preserved, not silently
corrected in the metadata. `sources.json` separately records the observed grid.
Treat the actual table grid as the input grid; do not infer extra measurements
from metadata wording or interpolation.

These are source acquisitions for release preparation. Runtime substitution and
its numerical comparisons have not yet been completed. They do not resolve film,
paper, density-response or training-model permissions.
