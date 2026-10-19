"""Display enumeration + fullscreen/lock awareness — pure ctypes.

EnumDisplayMonitors is called via user32 directly (the legacy bug was asking
win32gui for it — it lives in a different module entirely).
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from .defs import (MONITORINFOEXW, MONITORINFOF_PRIMARY, RECT, POINT,
                   MONITOR_DEFAULTTONEAREST, user32, shell32, kernel32)
from ..sim.region import Rect, Region

log = logging.getLogger("zwoop.monitors")

MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
    ctypes.POINTER(RECT), wintypes.LPARAM)


def enum_monitors() -> list[Rect]:
    """All real display rectangles in virtual coords (may be negative)."""
    found = []

    @MONITORENUMPROC
    def cb(hmon, hdc, rect_ptr, data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            found.append((Rect(r.left, r.top, r.right, r.bottom),
                          bool(info.dwFlags & MONITORINFOF_PRIMARY)))
        return True

    try:
        if not user32.EnumDisplayMonitors(None, None, cb, 0):
            raise OSError("EnumDisplayMonitors failed")
    except Exception as e:
        log.warning("monitor enumeration failed: %s — using primary metrics", e)
        w = user32.GetSystemMetrics(0)   # SM_CXSCREEN
        h = user32.GetSystemMetrics(1)   # SM_CYSCREEN
        if w > 0 and h > 0:
            return [Rect(0, 0, w, h)]
        return [Rect(0, 0, 1920, 1080)]

    # keep primary first for deterministic indexing
    found.sort(key=lambda t: not t[1])
    return [r for r, _ in found] or [Rect(0, 0, 1920, 1080)]


def build_region(monitor_pref="auto") -> Region:
    """Region from all monitors, or just the selected one."""
    rects = enum_monitors()
    if monitor_pref != "auto":
        try:
            rects = [rects[int(monitor_pref)]]
        except (ValueError, IndexError):
            log.warning("monitor pref %r invalid; using all", monitor_pref)
    return Region(rects)


# ------------------------------------------------------------ awareness
def _quns_fullscreen() -> bool:
    """SHQueryUserNotificationState: is an app fullscreen/presenting?"""
    fn = getattr(shell32, "SHQueryUserNotificationState", None)
    if fn is None:
        return False
    state = ctypes.c_int(0)
    try:
        if fn(ctypes.byref(state)) != 0:   # S_OK
            return False
        # 2=QUNS_BUSY 3=QUNS_RUNNING_D3D_FULL_SCREEN 4=QUNS_PRESENTATION_MODE
        return state.value in (2, 3, 4)
    except Exception:
        return False


def _fg_covers_monitor() -> bool:
    """Heuristic: foreground window spans its whole monitor (games etc)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    try:
        rc = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return False
        mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(mon, ctypes.byref(info))
        m = info.rcMonitor
        covers = (rc.left <= m.left + 4 and rc.top <= m.top + 4 and
                  rc.right >= m.right - 4 and rc.bottom >= m.bottom - 4)
        # exclude the desktop shell itself from counting as "fullscreen app"
        if covers:
            import ctypes as _c
            name = _c.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, name, 64)
            if name.value in ("Progman", "WorkerW", "Shell_TrayWnd",
                              "Windows.UI.Core.CoreWindow"):
                return False
        return covers
    except Exception:
        return False


def _session_locked() -> bool:
    """Locked if we can't open the input desktop or it isn't 'Default'."""
    try:
        hdesk = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if not hdesk:
            return True
        try:
            needed = wintypes.DWORD(0)
            user32.GetUserObjectInformationW(
                hdesk, 2, None, 0, ctypes.byref(needed))  # UOI_NAME
            if needed.value:
                buf = ctypes.create_unicode_buffer(needed.value // 2 + 2)
                if user32.GetUserObjectInformationW(
                        hdesk, 2, buf, needed.value, ctypes.byref(needed)):
                    return buf.value.lower() != "default"
            return False
        finally:
            user32.CloseDesktop(hdesk)
    except Exception:
        return False


class Awareness:
    """Polled session awareness: fullscreen/lock -> auto-hide."""

    def __init__(self, enabled=True, interval=0.5):
        self.enabled = enabled
        self.interval = interval
        self._next = 0.0
        self.should_hide = False
        self.reason = ""

    def poll(self, now=None):
        now = time.perf_counter() if now is None else now
        if now < self._next:
            return self.should_hide
        self._next = now + self.interval
        if not self.enabled:
            self.should_hide = False
            return False
        if _session_locked():
            self.should_hide, self.reason = True, "locked"
        elif _quns_fullscreen() or _fg_covers_monitor():
            self.should_hide, self.reason = True, "fullscreen"
        else:
            self.should_hide, self.reason = False, ""
        return self.should_hide
