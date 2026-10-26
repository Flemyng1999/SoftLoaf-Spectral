# Working on SoftLoaf Spectral

Read README.md first. Methods are in docs/science-and-pipelines.md, data rules
in docs/data-and-licensing.md, and planned tests in docs/validation-and-roadmap.md.
research/ contains historical evidence, not the current implementation.

Use an Issue and a task branch, normally codex/<task>, for implementation.
Preserve existing edits. Keep this repository independent of other products;
do not import private code, profiles, credentials or project instructions.
Use subagents only when requested by the user or specifically assigned by
project guidance.

Record units, encodings, white points, observer, spectral coverage, exposure and
viewing settings for every transform. Keep camera channels, density, observed
XYZ and display RGB distinct. A neutral fit does not establish color accuracy.
Fixed LUT export requires frozen calibration and pointwise processing.

Keep a float64 reference and compare optimized CPU/GPU output with it. Review
data rights and verify exported files before publication. Preserve source and
license records; exclude private paths and assets with pending permissions.

Write ordinary project documentation. Use the pre-2021 README references in
CONTRIBUTING.md for tone and structure. Explain actual behavior, data and limits;
do not claim features, measurements or superiority that have not been demonstrated.
