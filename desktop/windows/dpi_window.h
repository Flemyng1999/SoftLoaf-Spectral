#pragma once
#include <windows.h>
#include <algorithm>

namespace softloaf {
// Coordinates and the work area are physical pixels in a PMv2 thread.
inline RECT fit_window_rect(RECT bounds, const RECT& work) {
    const LONG width = std::clamp<LONG>(bounds.right - bounds.left, 1,
        std::max<LONG>(1, work.right - work.left));
    const LONG height = std::clamp<LONG>(bounds.bottom - bounds.top, 1,
        std::max<LONG>(1, work.bottom - work.top));
    const LONG left = std::clamp(bounds.left, work.left, work.right - width);
    const LONG top = std::clamp(bounds.top, work.top, work.bottom - height);
    return {left, top, left + width, top + height};
}

inline void size_initial_window(HWND window) {
    const auto dpi = GetDpiForWindow(window);
    RECT frame{0, 0, MulDiv(1320, dpi, USER_DEFAULT_SCREEN_DPI),
                      MulDiv(900, dpi, USER_DEFAULT_SCREEN_DPI)};
    AdjustWindowRectExForDpi(&frame, WS_OVERLAPPEDWINDOW, TRUE, 0, dpi);
    RECT current{};
    GetWindowRect(window, &current);
    RECT desired{current.left, current.top, current.left + frame.right - frame.left,
        current.top + frame.bottom - frame.top};
    MONITORINFO monitor{sizeof(MONITORINFO)};
    if (GetMonitorInfoW(MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST), &monitor))
        desired = fit_window_rect(desired, monitor.rcWork);
    SetWindowPos(window, nullptr, desired.left, desired.top,
        desired.right - desired.left, desired.bottom - desired.top,
        SWP_NOACTIVATE | SWP_NOZORDER);
}
}
