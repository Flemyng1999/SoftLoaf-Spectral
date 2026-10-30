# alpha.2 candidate validation

These results identify local candidate checks, not a published installer. Final
signing, installed-byte checks, source/tag CI and public download readback remain
separate gates. Tests used an owner-authorized scientific pack that is not a
release asset. No camera photograph or measured scan calibration is published.

The public Mac check run passed 3 native tests, 79 JavaScript tests and 145 Python
tests without skips. The latest Windows native build passed 5 tests, including
command-line argument roundtripping, per-monitor DPI and embedded branding.

A frozen Mac service ran with the checkout, developer Python, Homebrew and the
installed RawTherapee application denied by a read sandbox. It loaded Metal,
read a real Sony A7R V source, rendered the full 9556 × 6366 image in 1061 blocks
with a 64 MiB working budget, and read the exported PNG back exactly. All three
65³ pipeline exports passed their reference/file checks and downloaded hashes.
The first native window's complete first paint, without manual resizing, was
confirmed by the owner. A one-time drawing-area resize is retained at first
navigation; it does not change the outer window geometry.

Packaging originally missed the RT platform `options` file and then
`rtengine/camconst.json`. The resource installer now follows upstream's separate
camera-constant installation and tests both cases. A missing camera-constant
table produced a two-pixel width discrepancy; the corrected package restored the
9556-pixel active width. Absolute upstream macOS RT resource constants are
relocated, and the integrated engine builds with `OSX_DEV_BUILD=ON`.

The Mac X-Trans compatibility reader was compared with the official RT 5.12
reader's original native dependency closure. With the same RAW, PP3, white
balance and ICC handoffs, AP1 and encoded sRGB float32 arrays matched exactly on
the tested X-T30 source. Replacing dependencies is therefore recorded separately
from retaining the official numerical executable. This one source is not a
universal camera-accuracy result.

Earlier Windows frozen-service candidates completed real D750 RAW preview,
6024 × 4024 PNG export (403 blocks), three 65³ LUT exports and file readback on
D3D12 and CPU. Their export times were about 17 and 107 seconds respectively on
the tested host. These timings include the candidate's surrounding I/O and do
not predict other cameras or computers. The final Windows installer still needs
its own dependency-source audit and installed-candidate verification; those
prior candidate results do not substitute for that gate.

Retained RAW stages were reused on image switches and subsequent tests. Resource
or frozen-calibration changes have distinct identities; a completed development
is not silently deleted by rendition-cache cleanup. A test-only stage that had
failed before RAW input parsing was explicitly archived with its diagnostic
record before repair. It was not a completed retained development.

Native dependency notices preserve exact provider versions, build recipes,
source URLs and checksums. The public scientific payload remains excluded.
Implementation agreement, neutral fits and output readback do not establish
independent film, paper or real-negative color accuracy.
