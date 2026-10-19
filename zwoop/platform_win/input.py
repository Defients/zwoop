"""Cursor + input-idle observation. Read-only; nothing is hooked."""

from __future__ import annotations

import ctypes

from .defs import POINT, LASTINPUTINFO, user32, kernel32


def cursor_pos():
    """(x, y) in virtual desktop coords, or None on failure."""
    pt = POINT()
    return (pt.x, pt.y) if user32.GetCursorPos(ctypes.byref(pt)) else None


def idle_seconds() -> float:
    """Seconds since last user input (GetLastInputInfo)."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    tick = kernel32.GetTickCount()
    delta = tick - lii.dwTime
    if delta < 0:                      # 49-day tick wraparound
        delta += 2 ** 32
    return delta / 1000.0


def left_button_down() -> bool:
    return bool(user32.GetAsyncKeyState(0x01) & 0x8000)
