"""System tray icon + context menu — ctypes, no third-party deps.

Owns a hidden message-only window for icon callbacks; menus are built
fresh each time so checkmarks reflect live state.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

import numpy as np

from .defs import (ICONINFO, BITMAPINFO, DIB_RGB_COLORS, NOTIFYICONDATAW,
                   NIM_ADD, NIM_MODIFY, NIM_DELETE, NIF_ICON, NIF_MESSAGE,
                   NIF_TIP, NIF_SHOWTIP, WM_USER, WM_RBUTTONUP,
                   WM_LBUTTONDBLCLK, WM_DESTROY, WM_QUIT, WNDCLASSEXW,
                   MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_POPUP, MF_GRAYED,
                   TPM_LEFTALIGN, TPM_BOTTOMALIGN, TPM_RETURNCMD,
                   TPM_NONOTIFY, POINT, user32, gdi32, kernel32, shell32)

log = logging.getLogger("zwoop.tray")

WM_TRAY = WM_USER + 0x7A
HWND_MESSAGE = -3

WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT,
    wintypes.WPARAM, wintypes.LPARAM)

SEP = ("-", None, None)   # separator sentinel in menu specs


class TrayIcon:
    """NIF icon + right-click menu. `on_command(cmd_id)` dispatches."""

    def __init__(self, tooltip="Zwoop", on_command=None, on_double=None):
        self.tooltip = tooltip
        self.on_command = on_command or (lambda cid: None)
        self.on_double = on_double or (lambda: None)
        self.hwnd = None
        self.hicon = None
        self._wndproc = None
        self._menu_map = {}

    # ------------------------------------------------------------ setup
    def create(self, class_name="ZwoopTray"):
        self._register(class_name)
        self.hwnd = user32.CreateWindowExW(
            0, class_name, "ZwoopTray", 0, 0, 0, 0, 0,
            wintypes.HWND(HWND_MESSAGE), None,
            kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise OSError("tray window creation failed")
        self.hicon = self._make_orb_icon()
        self._notify(NIM_ADD)

    def _register(self, name):
        self._wndproc = WNDPROC(self._wnd_proc)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = name
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            if kernel32.GetLastError() != 1410:
                raise OSError("tray RegisterClassEx failed")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam == WM_RBUTTONUP:
                self.show_menu()
                return 0
            if lparam == WM_LBUTTONDBLCLK:
                self.on_double()
                return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _notify(self, op, tip=None):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_SHOWTIP
        nid.uCallbackMessage = WM_TRAY
        if self.hicon:
            nid.uFlags |= NIF_ICON
            nid.hIcon = self.hicon
        nid.szTip = (tip or self.tooltip)[:127]
        if tip is not None:
            nid.uFlags |= NIF_TIP
        else:
            nid.uFlags |= NIF_TIP
        if not shell32.Shell_NotifyIconW(op, ctypes.byref(nid)):
            log.warning("Shell_NotifyIconW op=%d failed", op)

    # ------------------------------------------------------------- icon
    def _make_orb_icon(self, px=32):
        """Procedural violet orb icon — a miniature Zwoop."""
        y, x = np.mgrid[0:px, 0:px]
        cx = cy = (px - 1) / 2
        r = np.hypot(x - cx, y - cy) / (px / 2 - 1)
        inside = np.clip(1 - r, 0, 1)
        glow = inside ** 1.6
        # violet->lavender radial
        rr = 96 + 120 * glow
        gg = 47 + 90 * glow
        bb = 247 * glow + 60 * inside
        aa = np.clip((inside * 1.4 - 0.08) * 255, 0, 255)

        color_bmp = self._bmp_from_rgba(px, px, rr, gg, bb, aa)
        mask = np.where(aa > 40, 0, 1).astype(np.uint8)
        mask_bmp = self._mask_bitmap(px, px, mask)

        ii = ICONINFO()
        ii.fIcon = True
        ii.hbmColor = color_bmp
        ii.hbmMask = mask_bmp
        icon = user32.CreateIconIndirect(ctypes.byref(ii))
        gdi32.DeleteObject(color_bmp)
        gdi32.DeleteObject(mask_bmp)
        return icon

    @staticmethod
    def _bmp_from_rgba(w, h, r, g, b, a):
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = wintypes.LPVOID()
        bmp = gdi32.CreateDIBSection(None, ctypes.byref(bmi), DIB_RGB_COLORS,
                                     ctypes.byref(bits), None, 0)
        arr = np.ctypeslib.as_array(
            (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value))
        arr = arr.reshape(h, w, 4)
        arr[..., 0] = b.astype(np.uint8)
        arr[..., 1] = g.astype(np.uint8)
        arr[..., 2] = r.astype(np.uint8)
        arr[..., 3] = a.astype(np.uint8)
        return bmp

    @staticmethod
    def _mask_bitmap(w, h, mask):
        row_bytes = (w + 31) // 32 * 4
        data = np.zeros(h * row_bytes, dtype=np.uint8)
        for y in range(h):
            for x in range(w):
                if mask[y, x]:
                    data[y * row_bytes + x // 8] |= 0x80 >> (x % 8)
        return gdi32.CreateBitmap(w, h, 1, 1, data.ctypes.data)

    # ------------------------------------------------------------- menu
    def build_menu(self, spec):
        """spec: list of (label, cmd_id|None|'sub', submenu|None)."""
        menu = user32.CreatePopupMenu()
        self._fill(menu, spec)
        return menu

    def _fill(self, menu, spec):
        for item in spec:
            if item == SEP:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, "")
                continue
            label, payload, extra = item
            flags = MF_STRING
            if extra:
                flags |= MF_CHECKED
            if isinstance(payload, list):           # submenu
                sub = user32.CreatePopupMenu()
                self._fill(sub, payload)
                user32.AppendMenuW(menu, flags | MF_POPUP, sub, label)
            elif payload is None:
                user32.AppendMenuW(menu, flags | MF_GRAYED, 0, label)
            else:
                user32.AppendMenuW(menu, flags, payload, label)

    def show_menu(self, spec=None):
        """Right-click menu; spec provided by the app's describe_menu()."""
        if spec is None:
            spec = getattr(self, "menu_spec", [])
        menu = self.build_menu(spec)
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)   # so the menu dismisses right
        cmd = user32.TrackPopupMenu(
            menu, TPM_RETURNCMD | TPM_NONOTIFY | TPM_LEFTALIGN |
            TPM_BOTTOMALIGN, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, 0, 0, 0)  # WM_NULL — menu cleanup
        user32.DestroyMenu(menu)
        if cmd:
            self.on_command(cmd)

    def set_tip(self, tip):
        self._notify(NIM_MODIFY, tip=tip)

    def destroy(self):
        try:
            self._notify(NIM_DELETE)
        except Exception:
            pass
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = None
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
