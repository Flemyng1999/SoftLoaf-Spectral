# 2048 px and Metal implementation

Issue #8, branch `codex/metal-spectral-preview`, 2026-10-28.

The user authorized a 2048-pixel preview and full Metal pixel processing. The
long edge is capped at 2048 without inventing detail in smaller originals. RAW
development remains the established RawTherapee handoff. Material extraction,
float64 fitting and single-point diagnostic/reference calculations remain CPU
control/reference work; image-wide spectral and display calculations move to
Metal. PNG encoding and file I/O are CPU boundary operations.

## Architecture

An independent Objective-C++/Metal C ABI loads OCIO-generated MSL and binds its
original 1D/2D/3D textures. A fused pixel kernel reconstructs spectra for RGB
inputs, integrates film exposure, evaluates frozen material curves, and computes
reversal viewing, APD/ADX-to-ACES, or optical paper exposure/development/viewing.
It preserves the existing scientific definitions and applies the existing OCIO
display graph once. Float32 GPU arithmetic is compared with the retained
float64 model; there is no silent CPU or LUT approximation fallback.

Metal tiles, shared buffer reuse, bounded shader/recipe caches and a serialized
GPU queue bound working memory. The viewer coalesces requests and rejects stale
results. Preview, full-resolution export and LUT baking call the same pixel
renderer. Full-resolution exports use immutable sources and frozen recipes.
Old 384-pixel caches are rebuilt from their source with a versioned cache policy.
Hyperspectral inputs retain their actual source size, bounded by the same cap.

## Implementation and acceptance

- [x] Add failing tests for GPU availability, OCIO texture binding and reference
  agreement before implementing `core/metal`, `spectral_lut/metal.py` and
  `spectral_app/metal_renderer.py`.
- [x] Check all three routes, source spectra and characterized RGB, all display
  views/targets, exposure brackets, curve ends, negative RGB and custom papers.
  Compare pre-display XYZ and encoded RGB separately; initial encoded absolute
  error budget 3e-4, with observed maxima reported rather than assumed.
- [x] Connect preview/export/LUT baking and version 2048 preview caches. Rebuild
  reduced persisted previews without changing source files or recipe snapshots.
- [x] Bound concurrent requests, GPU buffers and per-pixel scratch. Test stale
  request rejection, source/recipe changes, partial failures and original-size
  export. Include GPU name, timings, actual dimensions and memory bounds.
- [x] Check generated LUT and image readback, independent OCIO execution and
  reference colorimetry; numerical agreement is not real-film accuracy.
- [x] Run CMake/CTest, relevant Python/JS tests and actual rendered UI checks;
  normal restart after workspace backup, with pending drafts protected.

## References and boundaries

Apple: [GPU calculations](https://developer.apple.com/documentation/metal/performing-calculations-on-a-gpu),
[threadgroups](https://developer.apple.com/documentation/metal/creating-threads-and-threadgroups),
[image processing on Apple silicon](https://developer.apple.com/videos/play/wwdc2021/10153/),
[resource synchronization](https://developer.apple.com/documentation/metal/resource-synchronization).
OCIO's installed public `GpuShaderDesc` MSL generator supplies the display code
and original texture values. Its identity and license remain recorded separately.

The user authorized architectural reference to SoftLoaf Negative's preview and
export implementation. Only lifecycle coalescing, fixed export snapshots and
bounded tiling principles are referenced; no private implementation, profiles,
credentials or project instructions are copied into this repository.

## RAW efficiency follow-up

The user additionally requested Alcedo's RAW loading efficiency principles. Preserve
the two existing RT color handoffs and full-quality demosaic. Use read-only TIFF
mappings, stream and memoize integrity checks while file identity is unchanged,
prioritize waiting interactive decodes over background exports, and publish the
first imported photo immediately. Cold decode and cached handoff timing are
measured separately; no embedded JPEG is substituted. See
[RAW handoff](raw-handoff-and-batch.zh-CN.md) for actual timing and remaining limits.
