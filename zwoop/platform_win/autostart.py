"""Launch-on-login via the standard HKCU\\...\\Run key. Opt-in only."""

from __future__ import annotations

import os
import sys
import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Zwoop"


def _command() -> str:
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
    # The Run key has no working dir / PYTHONPATH — launch the shim that
    # locates the package itself.
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "..", "run_zwoop.pyw")
    return f'"{exe}" "{os.path.normpath(script)}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, VALUE_NAME)
            return bool(val)
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    try:
        access = winreg.KEY_SET_VALUE if on else \
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            access) as k:
            if on:
                winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ,
                                  _command())
            else:
                try:
                    winreg.DeleteValue(k, VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
