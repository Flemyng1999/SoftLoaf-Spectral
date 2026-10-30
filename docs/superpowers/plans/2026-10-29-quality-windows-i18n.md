# Diagnostics, checks, language and Windows implementation plan

Issue: #13. Execute inline; repository guidance does not authorize subagents.

Goal: produce bounded diagnostics, reproducible checks, persistent language settings,
C++23 native builds, and a Windows development path with D3D12 and CPU fallback.

Architecture: application-owned services handle diagnostics and preferences;
independent test tooling selects declared suites and records outcomes. Native
backends share bounded dispatch contracts while retaining the float64 oracle.

Constraints: preserve existing edits, frozen scientific settings and the two-stage
RAW rule. Pixels and processing temporaries stay on the configured external volume.
Do not copy private reference-product code, profiles, credentials or instructions.
Missing capabilities must not masquerade as verified integration coverage.

- [x] Add structured rotating diagnostic records, job IDs, elapsed times, startup
      and shutdown records. Test rotation, concurrent events, failures and redaction.
- [x] Declare portable/integration suites, produce JUnit/coverage/check summaries,
      require dependencies for strict integration, and add CI with failure artifacts.
- [x] Upgrade owned native targets to C++23; build and run CTest and numerical tests.
- [x] Add validated machine preferences and Settings language choice (system,
      Simplified Chinese, English), source-key catalogs and dynamic UI translation.
      Verify switching, restart, material/user names and persisted preferences.
- [x] Probe 303mini, build native Windows targets in an independent directory and
      record compiler, GPU and runtime identities. Do not alter other products.
- [x] Add a bounded D3D12 compute backend and exercise it against float64/CPU,
      including unavailable-device and dispatch-failure fallback behavior.
- [x] Attempt the Windows development application; document any remaining platform,
      RAW runtime, data permission, hardware or release limitations precisely.
- [x] Run the relevant full local checks and actual UI workflows; read saved reports
      and leave the application usable. No publication or signed release is implied.

Reference review: Alcedo's public cpp-ci workflow and logging tests; SoftLoaf
Negative's diagnostics, CI separation and Settings language selection. These are
architectural references, not implementation imports.

Final readback: `artifacts/quality/verified/summary.json` records 432 Python,
77 JavaScript and 2 native cases, with no required skips. Windows has 99 public
Python cases, 13 D3D12 hardware cases and a passing WebView2 desktop self-test.
Browser language switching and reload persistence were exercised against the
running service. Native macOS capture was unavailable; menu appearance was not
visually verified. Hosted CI has not been pushed or observed, and Windows real
RAW/runtime/material installation was still outside that initial verified shell;
the follow-up below records the later native application results.
See `docs/quality-and-windows.md` for commands, evidence and limits.


## Windows RAW follow-up, 2026-10-30

Continue Issue 13 on the same task branch. Preserve the two retained RAW stages
and use the owner-authorized D-drive test exception on 303mini.

- [x] Compare the Nikon failure with complete retained macOS pixels and the
  official Windows 5.12 executable; retain maxima as well as acceptance fraction.
- [x] Copy owner-approved scientific runtime assets and verify every hash.
- [x] Resolve integrated/reference RT paths and LCMS2 dependencies per platform.
- [x] Replace POSIX-only automatic memory detection on Windows.
- [x] Bind native ready files to the launcher process tree, including the
  Windows Python virtual-environment redirector.
- [x] Exercise Bayer and X-Trans import, preview, recipe changes and full export
  through the actual Windows native window; inspect PNG/ICC readback.
- [x] Compare actual-image GPU values with float64 and official RT handoffs;
  exercise CPU fallback and retained-stage reuse after restart.
- [x] Run regression gates, read logs, update the recorded limits and remove
  temporary desktop test launch tasks.


Follow-up readback: actual Bayer CR3 and X-Trans RAF imports, all three material
routes, sRGB/Display P3 full-size PNGs and a 65³ CUBE passed file checks. Five
exports were compared with the independent float64 model (551 points each,
maximum one 8-bit code). Actual-RAW CPU dispatch recovery and normal restart
reused unchanged retained stages. The final public Windows report records 108
Python, 78 JavaScript and two native cases; macOS targeted regressions passed
32 cases, with three native and three browser cases also passing. The English
native UI audit covered 49 node/tab states with no visible Chinese. E100 full
export remains slow on 303mini (398.754 seconds for 17.1 MP); spectral RGB
approximation and independent real-film color accuracy remain separate limits.
Temporary Windows desktop test tasks and debug listener were removed normally.
Evidence: `artifacts/quality/windows/raw-followup/` and
`docs/quality-and-windows.md`.
