# SoftLoaf Spectral

[中文说明](README.zh-CN.md)

SoftLoaf Spectral is a project for simulating photographic film and generating
color LUTs. It uses film sensitivity, characteristic curves, dye absorption,
and the illumination used for printing, scanning, or viewing.

The project starts with three processes:

- Kodak 5207 negative film, digitized with a specified light source and camera.
- The same negative printed on Kodak Ultra Endura photographic paper.
- Kodak E100 reversal film viewed by transmitted light.

The spectral calculations serve as a reference for an RGB implementation.
Fixed color transforms can then be exported as LUTs. Grain and halation require
separate image filters.

## Status

This repository currently contains the design, source catalog, and results from
earlier experiments. The standalone engine and LUT exporter are not implemented
yet. There are no installation instructions or released LUTs at this stage.

The first development task is to reproduce the E100 calculation without any
other application's code or configuration.

## Documentation

- [Project description](docs/project-brief.zh-CN.md) — scope and initial design.
- [Methods](docs/science-and-pipelines.md) — calculations and approximations.
- [Data](data/registry.json) — source documents and measurement records.
- [Earlier experiments](research/README.md) — results and known limitations.
- [Development](docs/validation-and-roadmap.md) — work order and tests.
- [References](docs/prior-art.md).

## Limitations

RGB values do not specify a unique spectrum. An RGB film effect is therefore an
approximation whose error depends on the input, illumination, and spectral
prior. It will be tested against measured spectral scenes.

Neutral characteristic curves alone do not determine the response to every
color. The current models also need independent film and print measurements.

Automatic roll calibration depends on the supplied images. LUT export requires
a fixed calibration, exposure, and viewing setup. Those settings will accompany
each LUT.

## License

Original code and documentation: **AGPL-3.0-only**. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). External data retain their own terms; see [data and licensing](docs/data-and-licensing.md).

## Contributing

Measurements, test images, and code are welcome. Please include the source,
units, processing conditions, and permission to distribute any data you submit.
See [CONTRIBUTING](CONTRIBUTING.md).
