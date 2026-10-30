# Standalone installer work

Issue #16; branch codex/standalone-installers. The source-only alpha.1 tag stays
immutable. The next candidate is alpha.2, with macOS Apple Silicon and Windows
x64 packages. The owner authorized publication and the existing Apple identity
and Keychain profile; no secret is copied into this project or its packages.

The native shell launches a bundled, directory-based frozen Python service.
Program code, UI, shaders, native libraries, RAW readers and their public
resources are read-only installation resources. Per-user settings, logs and
workspace metadata live in the platform's application-support location. RAW,
hyperspectral pixels, retained stages and temporaries stay on the selected data
volume. A scientific-data directory is a separate user-provided input; pending
data are not silently embedded in a public installer. First launch selects the
data inputs and volume, rather than failing because a developer checkout is absent.

1. Test and implement resource/state/scientific-data path ownership. Preserve
   development defaults and retained RAW-stage rules.
2. Freeze the service with its public resources and both RAW reader roles.
   Verify native loads, imports and startup with the developer paths hidden.
3. Connect native startup and first-launch directory selection to the same
   configuration. Produce a local scientific verification pack without RAW
   photos, private target measurements or scan calibrations.
4. Build macOS and Windows candidates; audit native dependencies, licences and
   the actual deployment floor. Test cold startup, RAW two-stage reuse, GPU/CPU,
   full-size export and LUT readback on the exact candidate.
5. Sign/notarize/staple and assess the Mac package. State the Windows signature
   status explicitly. Verify installers, final hashes, immutable source/tag and
   downloaded release assets before declaring publication complete.

PyInstaller's official documentation describes native dependency relocation,
codesigning and hardened-runtime behavior. Those mechanisms do not establish a
deployment-floor promise or clear scientific-data distribution rights.
