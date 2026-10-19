"""Zwoop entry point — `python -m zwoop [options]`."""

import argparse
import logging
import logging.handlers
import os
import sys

from . import APP_NAME, __version__
from .config import Config, default_config_path


def _setup_logging(debug=False, quiet=False):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    if not quiet:
        h = logging.StreamHandler()
        h.setFormatter(fmt)
        h.setLevel(logging.DEBUG if debug else logging.INFO)
        root.addHandler(h)
    try:
        logdir = os.path.dirname(default_config_path())
        os.makedirs(logdir, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(logdir, "zwoop.log"), maxBytes=1 << 20, backupCount=3,
            encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        root.addHandler(fh)
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="zwoop", description="Zwoop — the living desktop creature.")
    ap.add_argument("--version", "-v", action="store_true")
    ap.add_argument("--config", "-c", help="path to config.json")
    ap.add_argument("--debug", "-d", action="store_true",
                    help="verbose logging + debug overlay")
    ap.add_argument("--personality", "-p",
                    choices=["chill", "playful", "hyper", "shy"])
    ap.add_argument("--fps", type=int, choices=[30, 60, 120])
    ap.add_argument("--monitor", type=str, help="'auto' or display index")
    ap.add_argument("--no-tray", action="store_true",
                    help="run without tray icon (console only)")
    ap.add_argument("--studio", "-s", action="store_true",
                    help="open Trail Studio configuration window on launch")
    ap.add_argument("--preset", "--trail-preset", dest="preset", type=str,
                    help="initial trail preset ID (e.g. nebula_silk, stardust, solar_flare)")
    args = ap.parse_args(argv)

    if args.version:
        print(f"{APP_NAME} v{__version__}")
        return 0

    _setup_logging(debug=args.debug)
    overrides = {}
    if args.personality:
        overrides["personality"] = args.personality
    if args.fps:
        overrides.setdefault("render", {})["fps"] = args.fps
    if args.monitor is not None:
        overrides.setdefault("platform", {})["monitor"] = args.monitor
    if args.debug:
        overrides["debug"] = True
    if args.preset:
        overrides.setdefault("render", {}).setdefault("trails", {})["active_preset"] = args.preset
        overrides["render"]["trails"]["custom_working"] = None

    cfg = Config(args.config, overrides=overrides)

    from .app import ZwoopApp
    app = ZwoopApp(cfg, open_studio_on_start=bool(args.studio))
    try:
        app.setup()
    except Exception as e:
        logging.critical("Zwoop failed to start: %s", e, exc_info=True)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, f"Zwoop could not start:\n\n{e}",
                "Zwoop", 0x10)
        except Exception:
            pass
        return 1
    if args.no_tray and app.tray:
        app.tray.destroy()
        app.tray = None
    return 0 if app.run() is None else 0


if __name__ == "__main__":
    sys.exit(main())
