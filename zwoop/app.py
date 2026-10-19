"""ZwoopApp — lifecycle and the main loop.

One thread owns everything: the Win32 message pump, the fixed-step
simulation accumulator, the rasterizer, and window compositing. That is the
root fix for the legacy threading hazards — there is nothing to race.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import traceback

import numpy as np

from .config import Config
from .sim.brain import Params
from .sim.body import BodyParams
from .sim.world import Sim
from .render.rasterizer import Rasterizer
from .platform_win.defs import set_dpi_awareness
from .platform_win.monitors import build_region, Awareness, enum_monitors
from .platform_win.overlay import OverlayWindow, pump_messages, \
    wait_or_messages
from .platform_win.input import cursor_pos, idle_seconds, left_button_down
from .platform_win.tray import TrayIcon, SEP
from .platform_win import autostart

log = logging.getLogger("zwoop.app")

# tray command ids
CMD_PAUSE = 1
CMD_EXIT = 2
CMD_HIDDEN = 3
CMD_DEBUG = 4
CMD_OPENCFG = 5
CMD_AUTOSTART = 6
CMD_BENCH = 7
CMD_PERS = 200
CMD_THEME = 300
CMD_FPS = 400
CMD_FX = 500
CMD_MON = 600
PERS_NAMES = ["chill", "playful", "hyper", "shy"]
THEME_NAMES = ["cosmos", "orchid", "lagoon", "ember"]
FPS_NAMES = [30, 60, 120]
FX_NAMES = [0, 1, 2]


class ZwoopApp:
    def __init__(self, config: Config):
        self.cfg = config
        self.running = False
        self.paused = False
        self.hidden = False
        self.debug = bool(config.get("debug", False))
        self.region = None
        self.sim = None
        self.overlay = None
        self.raster = None
        self.tray = None
        self.awareness = None
        self._prev_snap = None
        self._acc = 0.0
        self._last_frame_t = None
        self._fps_target = int(config.get("render.fps", 60))
        self._sim_h = 1.0 / int(config.get("sim.hz", 120))
        self._click_prev = False
        self._monitor_sig = None
        self._monitor_next = 0.0
        self._bench = None   # (frames, start) when benchmark mode on
        self._hidden_since = None

    # ------------------------------------------------------------ setup
    def _build_params(self) -> Params:
        b = self.cfg.data["behavior"]
        return Params(
            activity=b["activity"], curiosity=b["curiosity"],
            shyness=b["shyness"], expressiveness=b["expressiveness"],
            preferred_distance=b["preferred_distance"],
            interest_radius=b["interest_radius"],
            scare_radius=b["scare_radius"],
            rest_after_idle=b["rest_after_idle"],
            maneuver_cooldown=b["maneuver_cooldown"],
            size_scale=self.cfg.get("creature.size", 1.0))

    def _build_region(self):
        pref = self.cfg.get("platform.monitor", "auto")
        if not self.cfg.get("platform.roam_monitors", True) and \
                pref == "auto":
            pref = 0
        self.region = build_region(pref)

    def setup(self):
        set_dpi_awareness()
        self._build_region()
        p = self._build_params()
        bp = BodyParams(
            n_outer=max(6, int(self.cfg.get("creature.particle_count", 13)) - 1),
            ring_radius=self.cfg.get("creature.base_radius", 46.0) * 1.13,
            core_radius=self.cfg.get("creature.base_radius", 46.0) * 0.65,
            outer_radius=self.cfg.get("creature.base_radius", 46.0) * 0.48)
        self.sim = Sim(self.region, p, body_params=bp)

        win = int(self.cfg.get("render.window_size", 420))
        self.overlay = OverlayWindow(win)
        self.overlay.create()
        self.raster = Rasterizer(
            win, theme=self.cfg.get("render.theme", "cosmos"),
            effects=int(self.cfg.get("render.effects_level", 2)),
            opacity=float(self.cfg.get("render.opacity", 0.92)),
            trail=bool(self.cfg.get("render.trail", True)))
        self.awareness = Awareness(
            enabled=bool(self.cfg.get("platform.hide_on_fullscreen", True)))
        self.tray = TrayIcon("Zwoop", on_command=self._on_command)
        self.tray.create()
        self._monitor_sig = tuple((r.left, r.top, r.right, r.bottom)
                                  for r in enum_monitors())
        log.info("setup complete")

    # ------------------------------------------------------------ loop
    def run(self):
        self.running = True
        log.info("Zwoop running")
        last = time.perf_counter()
        try:
            while self.running:
                if not pump_messages():
                    break
                now = time.perf_counter()
                dt_frame = min(now - last, 0.25)
                last = now

                if self.paused or self.hidden or self.awareness.poll(now):
                    self._sleep_step(now)
                    continue
                elif not self.overlay.visible:
                    self.overlay.set_visible(True)

                # ---- perception --------------------------------------
                self.sim.feed_cursor(cursor_pos())
                self.sim.set_user_idle(idle_seconds())
                down = left_button_down()
                if down and not self._click_prev:
                    self.sim.last_percept.cursor_sudden = True   # click = jab
                self._click_prev = down

                # ---- fixed-step simulation ---------------------------
                self._acc += dt_frame
                n_steps = 0
                while self._acc >= self._sim_h and n_steps < 30:
                    self._prev_snap = self.sim.snapshot()
                    self.sim.step(self._sim_h)
                    self._acc -= self._sim_h
                    n_steps += 1
                if self._acc > self._sim_h * 30:
                    self._acc = 0.0       # long stall: drop backlog

                # ---- render ------------------------------------------
                snap = self.sim.snapshot()
                frame = self.overlay.frame
                w = self.overlay.size
                cx, cy = snap["center"]
                origin = (cx - w / 2, cy - w / 2)
                try:
                    self.raster.render(frame, snap, origin,
                                       dt=dt_frame, debug=self.debug)
                    self.overlay.present(cx, cy)
                except Exception:
                    log.error("render failed:\n%s", traceback.format_exc())
                    time.sleep(0.1)

                self._tick_bench()

                # ---- pacing ------------------------------------------
                spent = time.perf_counter() - now
                budget = 1.0 / self._fps_target
                wait_ms = max(1, int((budget - spent) * 1000))
                if not wait_or_messages(wait_ms):
                    break
        finally:
            self.shutdown()

    def _sleep_step(self, now):
        """Paused/hidden/suppressed: keep the process cheap and responsive."""
        if self.overlay.visible:
            self.overlay.set_visible(False)
        # keep the cursor tracker warm so resuming doesn't fake a "jerk"
        self.sim.feed_cursor(cursor_pos())
        wait_or_messages(120)

    # ------------------------------------------------------------- tray
    def menu_spec(self):
        cfg = self.cfg
        spec = [
            (f"Zwoop — {self.sim.brain.state.name}"
             + (f" ·{self.sim._last_out.maneuver}" if getattr(self.sim, '_last_out', None) and self.sim._last_out.maneuver else "")
             + (" [paused]" if self.paused else ""), None, None),
            SEP,
            ("Hide creature" if not self.hidden else "Show creature",
             CMD_HIDDEN, self.hidden),
            ("Pause" if not self.paused else "Resume", CMD_PAUSE, self.paused),
            SEP,
            ("Personality", [
                (n.capitalize(), CMD_PERS + i,
                 cfg.get("personality") == n) for i, n in
                enumerate(PERS_NAMES)], None),
            ("Theme", [(n.capitalize(), CMD_THEME + i,
                        cfg.get("render.theme") == n) for i, n in
                       enumerate(THEME_NAMES)], None),
            ("Frame rate", [(f"{f} fps", CMD_FPS + i,
                             self._fps_target == f) for i, f in
                            enumerate(FPS_NAMES)], None),
            ("Effects", [(f"Level {i}", CMD_FX + i,
                          self.raster.effects == i) for i in FX_NAMES],
             None),
            ("Monitor", [("Roam all", CMD_MON,
                          cfg.get("platform.monitor") == "auto")] +
                        [(f"Display {i}", CMD_MON + 1 + i,
                          cfg.get("platform.monitor") == i)
                         for i in range(len(self.region.rects))], None),
            SEP,
            ("Debug overlay", CMD_DEBUG, self.debug),
            ("Launch on login", CMD_AUTOSTART, autostart.is_enabled()),
            ("Open config folder", CMD_OPENCFG, False),
            SEP,
            ("Exit Zwoop", CMD_EXIT, False),
        ]
        return spec

    def _on_command(self, cid):
        cfg = self.cfg
        if cid == CMD_EXIT:
            self.running = False
        elif cid == CMD_PAUSE:
            self.paused = not self.paused
            log.info("paused=%s", self.paused)
        elif cid == CMD_HIDDEN:
            self.hidden = not self.hidden   # loop owns actual visibility
            log.info("hidden=%s", self.hidden)
        elif cid == CMD_DEBUG:
            self.debug = not self.debug
        elif cid == CMD_AUTOSTART:
            autostart.set_enabled(not autostart.is_enabled())
        elif cid == CMD_OPENCFG:
            folder = os.path.dirname(cfg.path)
            os.makedirs(folder, exist_ok=True)
            subprocess.Popen(["explorer", folder])
        elif CMD_PERS <= cid < CMD_PERS + len(PERS_NAMES):
            name = PERS_NAMES[cid - CMD_PERS]
            cfg.apply_personality(name)
            self.sim.brain.p = self._build_params()
            cfg.save()
            log.info("personality=%s", name)
        elif CMD_THEME <= cid < CMD_THEME + len(THEME_NAMES):
            name = THEME_NAMES[cid - CMD_THEME]
            cfg.set("render.theme", name)
            self.raster.set_theme(name)
            cfg.save()
        elif CMD_FPS <= cid < CMD_FPS + len(FPS_NAMES):
            self._fps_target = FPS_NAMES[cid - CMD_FPS]
            cfg.set("render.fps", self._fps_target)
            cfg.save()
        elif CMD_FX <= cid < CMD_FX + len(FX_NAMES):
            lvl = FX_NAMES[cid - CMD_FX]
            self.raster.effects = lvl
            cfg.set("render.effects_level", lvl)
            cfg.save()
        elif CMD_MON <= cid < CMD_MON + 16:
            sel = "auto" if cid == CMD_MON else cid - CMD_MON - 1
            cfg.set("platform.monitor", sel)
            cfg.save()
            self._build_region()
            self.sim.region = self.region
            self.sim.brain.region = self.region
            self.sim.brain.waypoint = None

    # ------------------------------------------------------------ utils
    def _tick_bench(self):
        if self._bench is None:
            return
        n, t0 = self._bench
        self._bench = (n + 1, t0)
        if n and n % 600 == 0:
            log.info("bench: %d frames in %.1fs (%.1f fps)",
                     n, time.perf_counter() - t0, n / (time.perf_counter() - t0))

    def shutdown(self):
        log.info("shutting down")
        try:
            self.cfg.save()
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.destroy()
        except Exception as e:
            log.warning("tray cleanup: %s", e)
        try:
            if self.overlay:
                self.overlay.destroy()
        except Exception as e:
            log.warning("overlay cleanup: %s", e)
