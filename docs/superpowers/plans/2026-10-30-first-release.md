# First 面包光谱 release preparation

Issue: #14. Branch: codex/first-release.

Current goal: publish 0.1.0-alpha.1 as a source-only test release, with the
selected owner-authorized logo and source-specific distribution records.

The owner requested a permissions review before a complete test release, and
original-source spectral acquisition instead of copying curves from another
repository. Existing unpublished work and private data must be preserved.

After reviewing the missing distribution records, the owner explicitly chose
"先发布源码测试版，不附未审数据，并明确运行所需资料". This supersedes the
initial installer scope for the first release. The complete scientific runtime
and standalone signed installers remain future work, not waived or certified.

## Source-only release

- [x] Record version, source-only scope, licences and missing runtime inputs.
- [x] Keep only source identities and fit summaries in the public VISION3 manifest.
- [x] Add source inventory, data/path/credential exclusions and regression checks.
- [x] Run local public native, JavaScript, Python and browser checks.
- [ ] Freeze the source commit; build and inspect an exact-byte source archive.
- [ ] Build/test the clean source and complete exact-commit CI.
- [ ] Publish an immutable prerelease with inventory and checksums; read back
      the online tag, flags and final asset bytes.

## Completed preparation and future binary work

- [x] Freeze the selected bread-cat source; generate and verify PNG/ICNS/ICO.
- [x] Embed Windows icon/version resources and verify the compiled PE resources.
- [ ] Audit every material, density function, illuminant, optical curve and
      sampling-model training source against its original source and licence.
      Obtain original optical data where available. Keep pending data local.
- [ ] Add a release inventory and executable gate that rejects unresolved rights,
      undocumented fallback curves, private paths and development-only bundles.
- [ ] Build relocatable macOS and Windows candidates with owned runtime locations,
      third-party notices, corresponding source and hashes. No checkout or
      developer Python dependency may remain.
- [ ] Run cold launch and UI/RAW/export tests with the declared data volume;
      verify float64/GPU comparisons and CPU recovery on the frozen candidate.
- [ ] Sign/notarize applicable artifacts, verify final-byte checksums and source
      commit, then create an immutable prerelease tag and read back publication.

The first source-only version is 0.1.0-alpha.1. No existing GitHub release was
found at initial preflight on 2026-10-30. A binary tag must not be created merely
to mark an incomplete development package.

The current desktop shells depend on a checkout, a separate Python environment,
local scientific assets and installed native libraries. Those are packaging
requirements to resolve, not a distributable application.

2026-10-30: original CIE CSV bytes match the official SHA-256 metadata and retain
CC-BY-SA-4.0 attribution. Original SCHOTT KG3 workbook and Edmund cyan source
have been located, but original availability does not clear distribution. The
source review and executable data gate are present; the gate correctly fails
for the remaining materials, optical components and sampling inputs. Full
payload inventory and standalone package checks are not yet implemented.
