#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include "../../desktop/windows/dpi_window.h"
#include <fstream>

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int) {
    const auto context = GetThreadDpiAwarenessContext();
    const bool per_monitor_v2 = AreDpiAwarenessContextsEqual(
        context, DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
    USEROBJECTFLAGS flags{};
    DWORD needed=0;
    if (!GetUserObjectInformationW(GetProcessWindowStation(), UOI_FLAGS,
        &flags, sizeof(flags), &needed)) return 4;
    const bool interactive = (flags.dwFlags & WSF_VISIBLE) != 0;
    wchar_t policy[128]{};
    SIZE_T length=0;
    const bool manifest_ok=QueryActCtxSettingsW(0, nullptr,
        L"http://schemas.microsoft.com/SMI/2016/WindowsSettings", L"dpiAwareness",
        policy, std::size(policy), &length) && std::wstring(policy)==L"PerMonitorV2";
    std::ofstream("windows-dpi-test.json") << "{\"per_monitor_v2\":" << (per_monitor_v2 ? "true" : "false")
              << ",\"interactive\":" << (interactive ? "true" : "false")
              << ",\"embedded_policy\":" << (manifest_ok ? "true" : "false")
              << ",\"awareness\":" << GetAwarenessFromDpiAwarenessContext(context) << "}\n";
    // A noninteractive SSH/service window station exposes PMv1 even for PMv2
    // manifests. Verify the activated policy there; require actual PMv2 in RDP.
    if (!manifest_ok || (interactive && !per_monitor_v2)) return 1;
    // A 200% window on a smaller RDP work area must remain fully accessible,
    // including when a secondary monitor has negative desktop coordinates.
    const RECT work{-1920, 0, 0, 1040};
    const auto fitted = softloaf::fit_window_rect({-1800, 50, 840, 1850}, work);
    if (fitted.left != -1920 || fitted.top != 0 ||
        fitted.right != 0 || fitted.bottom != 1040) return 2;
    const auto small = softloaf::fit_window_rect({100, 100, 900, 700}, {0, 0, 1920, 1040});
    if (small.left != 100 || small.top != 100 || small.right != 900 || small.bottom != 700) return 3;
    return 0;
}
