# Data and licensing

## Project license

Original code and documentation use **AGPL-3.0-only**. The standard text is in
[LICENSE](../LICENSE); [NOTICE](../NOTICE) states the version choice. Section 13
covers modified programs used for network interaction. See the [SPDX text](https://spdx.org/licenses/AGPL-3.0-only.html).

External data and third-party code retain their own terms. Review compatibility
and keep their notices when importing them. A public download link does not
by itself grant redistribution rights.

Section 2 makes output coverage depend on the output's contents. Processing a
personal photograph does not automatically put that photograph under AGPL.
Published model and LUT packages need their own source and license records.
Recipes and build code authored here use AGPL; numerical output and upstream
asset obligations are checked separately.

## Source records

[data/registry.json](../data/registry.json) lists the earlier inputs. No raw
datasets are bundled at present. Each imported asset needs:

- Source URL/DOI, author, version and hashes.
- Quantity, units, wavelength grid, geometry and known uncertainty.
- Document page, original extraction points and processing for digitized curves.
- License and attribution, with permission checked for the proposed distribution.

Record whether the review covers raw files, extracted tables, models, examples
and exported LUTs. A decision about one of these may not cover the others.

Manufacturer PDFs, standards and extracted tables stay outside Git until their
reuse has been reviewed. Acquisition instructions may instead identify a
user-supplied document and checksum. A checksum is useful for identification;
reproduction still requires access to the actual input.

Check exact releases of CIE tables, spectral scenes and camera datasets. Keep
attribution and applicable share-alike terms. Noncommercial-only data are not a
default input for the planned general-use release.

## Earlier private inputs

The GH7 response, measured capture light and old CCM files have not been
contributed for public distribution. The sensor's missing relative channel gains
also need to be resolved before calibration claims can be made.

The earlier digitization program is separate proprietary software. Its code,
binaries, profiles and configuration are not part of this project. Any later
transfer needs specific authorization; an independent implementation can instead
use documented methods and appropriately licensed sources.

Check data rights and remove credentials, private reports and personal paths
before publishing. LUT/model releases retain the relevant upstream records.
