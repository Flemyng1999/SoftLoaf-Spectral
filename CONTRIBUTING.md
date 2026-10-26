# Contributing

Please open an Issue before substantial code or model changes. Include the
intended result, the relevant measurements, and a way to test the change.
Use a separate branch for the work.

Useful contributions include film transmission spectra with known exposure,
paper exposure/print measurements, sensor responses with relative channel scales,
and independently held-out spectral scenes.

For measurements, record stock/batch, process, instrument, geometry, units,
wavelength grid, reference, and uncertainty where known. Leave unknown fields
marked as unknown. For digitized curves, include the document revision, page,
axes, original points and extraction method.

Read [Methods](docs/science-and-pipelines.md) and [Data and licensing](docs/data-and-licensing.md)
before adding material data. Do not submit private code or data without the
right to distribute them. Original contributions use AGPL-3.0-only; third-party
material keeps its reviewed terms. Copyright transfer is not required.

Tests should distinguish model fitting, independent measurements, RGB
approximation, implementation consistency and LUT readback. Retain a numerical
reference when optimizing the calculation.

## Documentation

Describe what the program does, show how to use it when that code exists, and
state the remaining limitations. Prefer ordinary words and concrete quantities.
Do not add slogans, unsupported comparisons or duplicate summaries.

Writing references are [rawpy v0.15.0](https://github.com/letmaik/rawpy/blob/v0.15.0/README.md)
(8 August 2020) and [Colour v0.3.15](https://github.com/colour-science/colour/blob/v0.3.15/README.rst)
(25 January 2020). Their documentation structure is the reference, not wording
to copy. License and standard text remain unchanged.
