# Contributing

For substantial code or model changes, open an Issue describing the change,
the measurements it uses and how to test it. Work on a separate branch.

The project needs film transmission spectra with known exposure, paired paper
exposure and print measurements, sensor responses with relative channel scales,
and spectral scenes reserved for independent testing.

Include the stock and batch, process, instrument, geometry, units, wavelength
grid, reference and known uncertainty with each measurement. Mark unknown
fields as unknown. For curves extracted from a document, include its revision,
page, axes, original points and extraction method.

Read [Methods](docs/science-and-pipelines.md) and [Data and licensing](docs/data-and-licensing.md)
before adding material data. Do not submit private code or data without the
right to distribute them. Original contributions use AGPL-3.0-only; third-party
material keeps its reviewed terms. Copyright transfer is not required.

Report fitting errors separately from tests against independent measurements.
Test the RGB approximation, optimized calculations and exported LUTs against
their respective references. Keep the float64 reference when optimizing code.

## Documentation

Describe what the code does and give examples that run. Label planned work as
planned, and explain known limitations where they affect use. Use concrete
quantities for results; avoid slogans and unsupported comparisons.

Writing references are [rawpy v0.15.0](https://github.com/letmaik/rawpy/blob/v0.15.0/README.md)
(8 August 2020) and [Colour v0.3.15](https://github.com/colour-science/colour/blob/v0.3.15/README.rst)
(25 January 2020). Use the linked versions, both published before 2021, as
references for prose and structure. Do not copy their wording. Keep license
and standard text unchanged.
