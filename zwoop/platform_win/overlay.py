"""Transparent click-through overlay window.

A small WS_EX_LAYERED window that follows the creature and is composited
each frame by UpdateLayeredWindow from a premultiplied-alpha DIB.
This gives true per-pixel translucency, exact click-through, and — because
the window travels with the creature — no multi-monitor spanning bugs.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

import numpy as np

from .defs import (BLENDFUNCTION, AC_SRC_OVER, AC_SRC_ALPHA, ULW_ALPHA,
                   BITMAPINFO, DIB_RGB_COLORS, MSG, PM_REMOVE, POINT,
                   QS_ALLINPUT, MWMO_INPUTAVAILABLE, SIZE, WNDCLASSEXW,
                   WS_POPUP, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOPMOST,
                   WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, SW_SHOWNOACTIVATE,
                   SW_HIDE, HWND_TOPMOST, SWP_NOACTIVATE, SWP_SHOWWINDOW,
                   SWP_NOSIZE, SWP_NOMOVE, WM_QUIT, WM_DESTROY, user32,
                   gdi32, kernel32)

log = logging.getLogger("zwoop.overlay")

WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM)


class OverlayWindow:
    """Owns the layered window + persistent DIB. Single-threaded use."""

    def __init__(self, size: int, class_name="ZwoopSurface"):
        self.size = size
        self.hwnd = None
        self.dc_mem = None
        self.dib = None
        self.dib_bits = None
        self.old_bmp = None
        self.visible = False
        self._class_name = class_name
        self._wndproc = None   # keep ref alive
        self._px = self._py = -10_000
        self._blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        # numpy view over the DIB bits: shape (size, size, 4), BGRA, top-down
        self.frame = None

    # ------------------------------------------------------------- setup
    def create(self):
        self._register_class()
        ex = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST |
              WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        self.hwnd = user32.CreateWindowExW(
            ex, self._class_name, "Zwoop", WS_POPUP,
            -32000, -32000, self.size, self.size,
            None, None, kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError(f"CreateWindowEx failed: {ctypes.get_last_error()}")
        self._create_dib()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self.visible = True
        log.info("overlay window created (%dx%d)", self.size, self.size)

    def _register_class(self):
        self._wndproc = WNDPROC(self._wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = None  # click-through window never sees the cursor
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = kernel32.GetLastError()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise OSError(f"RegisterClassEx failed: {err}")

    def _create_dib(self):
        hdc_screen = user32.GetDC(None)
        self.dc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFO().bmiHeader)
        bmi.bmiHeader.biWidth = self.size
        bmi.bmiHeader.biHeight = -self.size   # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0       # BI_RGB

        bits = wintypes.LPVOID()
        self.dib = gdi32.CreateDIBSection(
            hdc_screen, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(bits), None, 0)
        if not self.dib:
            raise OSError("CreateDIBSection failed")
        self.old_bmp = gdi32.SelectObject(self.dc_mem, self.dib)
        user32.ReleaseDC(None, hdc_screen)

        self.dib_bits = bits
        self.frame = np.ctypeslib.as_array(
            (ctypes.c_ubyte * (self.size * self.size * 4)
             ).from_address(bits.value))
        self.frame = self.frame.reshape(self.size, self.size, 4)
        self.frame[:] = 0

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------------------ present
    def present(self, cx: float, cy: float):
        """Write self.frame (already filled by the rasterizer) and move the
        window so it is centered on (cx, cy)."""
        if not self.hwnd:
            return
        px, py = int(cx - self.size / 2), int(cy - self.size / 2)
        src = POINT(0, 0)
        dst = POINT(px, py)
        sz = SIZE(self.size, self.size)
        if not user32.UpdateLayeredWindow(
                self.hwnd, None, ctypes.byref(dst), ctypes.byref(sz),
                self.dc_mem, ctypes.byref(src), 0,
                ctypes.byref(self._blend), ULW_ALPHA):
            err = kernel32.GetLastError()
            log.warning("UpdateLayeredWindow failed: %s", err)
        self._px, self._py = px, py

    def set_visible(self, on: bool):
        if on and not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True
        elif not on and self.visible:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def destroy(self):
        try:
            if self.dc_mem and self.dib:
                gdi32.SelectObject(self.dc_mem, self.old_bmp)
                gdi32.DeleteObject(self.dib)
                gdi32.DeleteDC(self.dc_mem)
        except Exception as e:
            log.warning("GDI cleanup: %s", e)
        try:
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
        except Exception as e:
            log.warning("DestroyWindow: %s", e)
        self.hwnd = None


class TrailOverlayWindow:
    """Dynamic bounded world-space trail surface backed by a persistent DIB.

    Click-through layered window positioned immediately behind Zwoop's main
    creature window. Only the active bounding box (w, h) of live trail effects
    is shaded and uploaded via UpdateLayeredWindow each frame.
    """

    def __init__(self, max_w: int = 1600, max_h: int = 1200,
                 class_name: str = "ZwoopTrailSurface"):
        self.max_w = int(max_w)
        self.max_h = int(max_h)
        self.hwnd = None
        self.dc_mem = None
        self.dib = None
        self.dib_bits = None
        self.old_bmp = None
        self.visible = False
        self._class_name = class_name
        self._wndproc = None
        self._blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        self.frame: np.ndarray | None = None
        self.last_rect: tuple[int, int, int, int] = (0, 0, 0, 0)

    def create(self):
        self._register_class()
        ex = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST |
              WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        self.hwnd = user32.CreateWindowExW(
            ex, self._class_name, "ZwoopTrail", WS_POPUP,
            -32000, -32000, 64, 64,
            None, None, kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError(f"Trail CreateWindowEx failed: {ctypes.get_last_error()}")
        self._create_dib()
        user32.ShowWindow(self.hwnd, SW_HIDE)
        self.visible = False
        log.info("trail overlay window created (backing DIB %dx%d)",
                 self.max_w, self.max_h)

    def _register_class(self):
        self._wndproc = WNDPROC(self._wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = None
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = kernel32.GetLastError()
            if err != 1410:
                raise OSError(f"Trail RegisterClassEx failed: {err}")

    def _create_dib(self):
        hdc_screen = user32.GetDC(None)
        self.dc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFO().bmiHeader)
        bmi.bmiHeader.biWidth = self.max_w
        bmi.bmiHeader.biHeight = -self.max_h   # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        bits = wintypes.LPVOID()
        self.dib = gdi32.CreateDIBSection(
            hdc_screen, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(bits), None, 0)
        if not self.dib:
            raise OSError("Trail CreateDIBSection failed")
        self.old_bmp = gdi32.SelectObject(self.dc_mem, self.dib)
        user32.ReleaseDC(None, hdc_screen)

        self.dib_bits = bits
        self.frame = np.ctypeslib.as_array(
            (ctypes.c_ubyte * (self.max_w * self.max_h * 4)).from_address(bits.value)
        ).reshape(self.max_h, self.max_w, 4)
        self.frame[:] = 0

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DESTROY:
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def subframe(self, w: int, h: int) -> np.ndarray:
        """Return a writable view of the top-left (h, w, 4) region of the DIB."""
        cw = max(16, min(self.max_w, int(w)))
        ch = max(16, min(self.max_h, int(h)))
        return self.frame[:ch, :cw]

    def present_rect(self, x: int, y: int, w: int, h: int, behind_hwnd=None):
        """Composite the active (w, h) sub-slice at desktop coordinates (x, y)."""
        if not self.hwnd:
            return
        cw = max(16, min(self.max_w, int(w)))
        ch = max(16, min(self.max_h, int(h)))
        if not self.visible:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True
            if behind_hwnd:
                user32.SetWindowPos(
                    self.hwnd, behind_hwnd, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        src = POINT(0, 0)
        dst = POINT(int(x), int(y))
        sz = SIZE(cw, ch)
        if not user32.UpdateLayeredWindow(
                self.hwnd, None, ctypes.byref(dst), ctypes.byref(sz),
                self.dc_mem, ctypes.byref(src), 0,
                ctypes.byref(self._blend), ULW_ALPHA):
            err = kernel32.GetLastError()
            log.warning("Trail UpdateLayeredWindow failed: %s", err)
        self.last_rect = (int(x), int(y), cw, ch)

    def set_visible(self, on: bool):
        if on and not self.visible and self.hwnd:
            user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
            self.visible = True
        elif not on and self.visible and self.hwnd:
            user32.ShowWindow(self.hwnd, SW_HIDE)
            self.visible = False

    def destroy(self):
        try:
            if self.dc_mem and self.dib:
                gdi32.SelectObject(self.dc_mem, self.old_bmp)
                gdi32.DeleteObject(self.dib)
                gdi32.DeleteDC(self.dc_mem)
        except Exception as e:
            log.warning("Trail GDI cleanup: %s", e)
        try:
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
        except Exception as e:
            log.warning("Trail DestroyWindow: %s", e)
        self.hwnd = None


# ------------------------------------------------------- message pump
def pump_messages():
    """Process all queued thread messages. Returns False on WM_QUIT."""
    msg = MSG()
    while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
        if msg.message == WM_QUIT:
            return False
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    return True


def wait_or_messages(timeout_ms: int):
    """Sleep until a message arrives or timeout. Returns False on WM_QUIT."""
    user32.MsgWaitForMultipleObjectsEx(
        0, None, timeout_ms, QS_ALLINPUT, MWMO_INPUTAVAILABLE)
    return pump_messages()
