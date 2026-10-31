面包光谱 / SoftLoaf Spectral 0.1.1
Yangming Feng and contributors
https://github.com/Flemyng1999/SoftLoaf-Spectral

This experimental package includes the program, RAW runtime, public CIE tables
and Lensfun geometry database. It DOES NOT include film/paper curves, trained
spectral models, photographs, measured scan targets or scan calibrations.
Public availability of manufacturer documents is not a redistribution licence.

First launch asks for a scientific-data directory with runtime-science.json,
then a processing directory on a mounted data volume. On macOS use an external
volume under /Volumes; on Windows use a mounted non-system volume. All image
pixels, retained RAW stages and processing temporaries stay on that volume.
See docs/installer-setup.md in the matching source release for required files,
manifest fields and validation. An arbitrary directory of PDFs is insufficient.
Do not select another user's private data or copy unreviewed data into releases.

macOS: Apple Silicon, macOS 26 or newer. Tested on macOS 27.0.1 / Apple M2 Pro.
Windows: x64 Windows 11, Microsoft Edge WebView2 Evergreen Runtime required.
D3D12 is selected when available; CPU recovery is retained. This Windows
package is unsigned. No Microsoft Store certification is claimed.

Drag the Mac application into Applications. Run the Windows installer as the
current user; no administrator installation is needed. Close the application
normally before updating. Uninstalling the program preserves per-user settings
and the external volume, including retained RAW stages.

The RAW pipeline retains one half-size preview development and one full-size
export development per immutable source and frozen camera calibration. RAW
reader changes do not silently discard completed retained stages. RAW preview
uses a Bayer 2x2 gather where supported, with a 2048-pixel short-edge limit;
X-Trans uses the separate RT compatibility reader. Display and LUT-space
handoffs share the same decode. Large exports are written in bounded blocks.
These implementation checks do not establish color accuracy for every camera,
film or measurement setup. Film/paper models require independent validation.

Original code: AGPL-3.0-only. Component licences, source links, exact native
build recipes and Python metadata are in Notices. RawTherapee 5.12 is GPL-3.0;
its integrated engine changes are in the matching source archive. The official
compatibility reader has relocated load commands/resource strings and separate
native dependencies; its numerical processing code is retained. Shared-library
replacement/relinking is permitted under applicable component licences; macOS
code signing may require re-signing a locally modified application.

Keep the matching source archive, native-source supplement and SHA256SUMS
available with the binary release. Never reuse or move an already published tag.
