"""Capture the desktop region around Zwoop's window for visual validation."""

from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")
from zwoop.platform_win.defs import user32, gdi32, wintypes, RECT  # noqa
import ctypes
from PIL import Image


def grab(x, y, w, h) -> Image.Image:
    hdc_screen = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, bmp)
    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020)
    # read bits
    from zwoop.platform_win.defs import BITMAPINFO, DIB_RGB_COLORS
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(bmi.bmiHeader)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(hdc_mem, bmp, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)
    import numpy as np
    arr = np.frombuffer(buf, np.uint8).reshape(h, w, 4)
    return Image.fromarray(arr[..., :3][:, :, ::-1].copy(), "RGB")


if __name__ == "__main__":
    x = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 560
    h = int(sys.argv[4]) if len(sys.argv) > 4 else 560
    out = sys.argv[5] if len(sys.argv) > 5 else "shot.png"
    grab(x, y, w, h).save(out)
    print("saved", out)
