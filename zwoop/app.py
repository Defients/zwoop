"""ZwoopApp — lifecycle and the main loop.

One thread owns everything: the Win32 message pump, the fixed-step
simulation accumulator, the TrailEngine, the rasterizer, window compositing,
and the non-blocking Trail Studio UI pump.
"""

from __future__ import annotations

import copy
import logging
import os
import subprocess
import time
import traceback

from .config import Config
from .sim.brain import Params
from .sim.body import BodyParams
from .sim.world import Sim
from .render.rasterizer import Rasterizer
from .trails.engine import TrailEngine
from .trails.presets import BUNDLED_PRESETS, PresetStore
from .trails.schema import QUALITY_BUDGETS, QUALITY_LEVELS
from .ui.trail_studio import TrailStudio
from .platform_win.defs import set_dpi_awareness
from .platform_win.monitors import build_region, Awareness, enum_monitors
from .platform_win.overlay import (
    OverlayWindow,
    TrailOverlayWindow,
    pump_messages,
    wait_or_messages,
)
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
CMD_TRAIL_TOGGLE = 10
CMD_TRAIL_STUDIO = 11
CMD_TRAIL_CLEAR = 12
CMD_PERS = 200
CMD_THEME = 300
CMD_FPS = 400
CMD_FX = 500
CMD_MON = 600
CMD_TRAIL_QUAL = 700
CMD_TRAIL_INT = 720
CMD_TRAIL_PRESET = 800

PERS_NAMES = ["chill", "playful", "hyper", "shy"]
THEME_NAMES = ["cosmos", "orchid", "lagoon", "ember"]
FPS_NAMES = [30, 60, 120]
FX_NAMES = [0, 1, 2]
INTENSITY_LEVELS = [("Low", 0.45), ("Medium", 0.85), ("High", 1.25)]
PRESET_IDS_ORDERED = list(BUNDLED_PRESETS.keys())


class ZwoopApp:
    def __init__(self, config: Config, open_studio_on_start: bool = False):
        self.cfg = config
        self.open_studio_on_start = open_studio_on_start
        self.running = False
        self.paused = False
        self.hidden = False
        self.debug = bool(config.get("debug", False))
        self.region = None
        self.sim = None
        self.overlay = None
        self.trail_overlay = None
        self.raster = None
        self.preset_store = None
        self.trail_engine = None
        self.studio = None
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
        self._bench = None
        self._hidden_since = None
        self._trail_error_count = 0

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
            ring_radius=self.cfg.get("creature.base_radius", 31.0) * 1.13,
            core_radius=self.cfg.get("creature.base_radius", 31.0) * 0.65,
            outer_radius=self.cfg.get("creature.base_radius", 31.0) * 0.48)
        self.sim = Sim(self.region, p, body_params=bp)

        # World-space trail engine + persistent bounded trail overlay
        user_preset_dir = os.path.join(os.path.dirname(self.cfg.path), "presets")
        self.preset_store = PresetStore(user_dir=user_preset_dir)
        self.trail_engine = TrailEngine(
            self.cfg.get("render.trails"), preset_store=self.preset_store
        )
        self.trail_overlay = TrailOverlayWindow(max_w=1600, max_h=1200)
        self.trail_overlay.create()

        win = int(self.cfg.get("render.window_size", 320))
        self.overlay = OverlayWindow(win)
        self.overlay.create()

        is_legacy_preset = (
            self.trail_engine.enabled
            and self.trail_engine.active_preset.get("id") == "legacy_zwoop"
        )
        self.raster = Rasterizer(
            win, theme=self.cfg.get("render.theme", "cosmos"),
            effects=int(self.cfg.get("render.effects_level", 2)),
            opacity=float(self.cfg.get("render.opacity", 0.92)),
            trail=is_legacy_preset)

        self.studio = TrailStudio(
            self.trail_engine.cfg,
            preset_store=self.preset_store,
            on_apply=self._on_studio_apply,
            on_clear_trails=self._on_clear_trails,
            theme_name=self.cfg.get("render.theme", "cosmos"),
        )
        self.awareness = Awareness(
            enabled=bool(self.cfg.get("platform.hide_on_fullscreen", True)))
        self.tray = TrayIcon(
            "Zwoop",
            on_command=self._on_command,
            on_double=self.open_trail_studio,
            get_spec=self.menu_spec,
        )
        self.tray.create()
        self._monitor_sig = tuple((r.left, r.top, r.right, r.bottom)
                                  for r in enum_monitors())
        if self.open_studio_on_start:
            self.open_trail_studio()
        log.info("setup complete")

    def open_trail_studio(self):
        if self.studio is not None:
            self.studio.open_window()

    def _on_studio_apply(self, new_trails_cfg: dict, new_preset: dict):
        self.cfg.data["render"]["trails"] = copy.deepcopy(new_trails_cfg)
        self.cfg.data["render"]["trail"] = bool(new_trails_cfg.get("enabled", True))
        self.trail_engine.cfg = copy.deepcopy(new_trails_cfg)
        self.trail_engine.load_preset(copy.deepcopy(new_preset), clear_existing=False)
        if not self.trail_engine.enabled and self.trail_overlay:
            self.trail_overlay.set_visible(False)
        if self.raster:
            self.raster.trail_on = (
                self.trail_engine.enabled
                and new_preset.get("id") == "legacy_zwoop"
            )
        self.cfg.save()

    def _on_clear_trails(self):
        if self.trail_engine:
            self.trail_engine.clear()
        if self.trail_overlay:
            self.trail_overlay.set_visible(False)

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

                if self.studio and self.studio.is_open:
                    self.studio.pump(now)

                # Monitor topology hotplug / resolution change check
                if now >= self._monitor_next:
                    self._monitor_next = now + 1.5
                    sig = tuple((r.left, r.top, r.right, r.bottom) for r in enum_monitors())
                    if sig != self._monitor_sig:
                        log.info("display layout changed -> rebuilding region")
                        self._monitor_sig = sig
                        self._build_region()
                        self.sim.region = self.region
                        self.sim.brain.region = self.region
                        self.sim.brain.waypoint = None
                        if self.trail_engine:
                            self.trail_engine.notify_discontinuity()

                if self.paused or self.hidden or self.awareness.poll(now):
                    self._sleep_step(now)
                    continue
                elif not self.overlay.visible:
                    self.overlay.set_visible(True)
                    if self.trail_engine:
                        self.trail_engine.notify_discontinuity()

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
                    if self.trail_engine:
                        self.trail_engine.notify_discontinuity()

                # ---- render trails + creature ------------------------
                snap = self.sim.snapshot()
                self._step_and_render_trails(dt_frame, snap)

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

    def _step_and_render_trails(self, dt_frame: float, snap: dict):
        if not self.trail_engine or not self.trail_overlay:
            return
        if not self.trail_engine.enabled:
            if self.trail_overlay.visible:
                self.trail_overlay.set_visible(False)
            return

        try:
            self.trail_engine.step(
                dt_frame, snap, region=self.region, target_fps=self._fps_target
            )
            eff_tier = self.trail_engine.profiler.effective_tier
            q_bud = QUALITY_BUDGETS.get(eff_tier, QUALITY_BUDGETS["balanced"])
            max_w = min(self.trail_overlay.max_w, int(q_bud["max_surface_w"]))
            max_h = min(self.trail_overlay.max_h, int(q_bud["max_surface_h"]))

            bbox = self.trail_engine.compute_active_bounds(snap, max_w=max_w, max_h=max_h)
            if bbox is None:
                if self.trail_overlay.visible:
                    self.trail_overlay.set_visible(False)
                return

            bx, by, bw, bh = bbox
            sub = self.trail_overlay.subframe(bw, bh)
            theme_name = self.cfg.get("render.theme", "cosmos")
            drew = self.trail_engine.render_into(sub, (bx, by), snap, theme_name=theme_name)
            if drew:
                self.trail_overlay.present_rect(
                    bx, by, bw, bh, behind_hwnd=self.overlay.hwnd
                )
            elif self.trail_overlay.visible:
                self.trail_overlay.set_visible(False)
            self._trail_error_count = 0
        except Exception:
            self._trail_error_count += 1
            log.error("trail subsystem error (#%d):\n%s",
                      self._trail_error_count, traceback.format_exc())
            if self.trail_overlay.visible:
                self.trail_overlay.set_visible(False)
            self.trail_engine.clear()
            if self._trail_error_count >= 5:
                log.warning("disabling trails after repeated errors to protect desktop")
                self.trail_engine.set_enabled(False)

    def _sleep_step(self, now):
        """Paused/hidden/suppressed: clear & hide overlays and keep process cheap."""
        if self.overlay.visible:
            self.overlay.set_visible(False)
        if self.trail_overlay and self.trail_overlay.visible:
            self.trail_overlay.set_visible(False)
        if self.trail_engine and self.trail_engine.has_active_visuals():
            self.trail_engine.clear()
        # keep the cursor tracker warm so resuming doesn't fake a "jerk"
        self.sim.feed_cursor(cursor_pos())
        wait_or_messages(120)

    # ------------------------------------------------------------- tray
    def _build_trails_submenu(self) -> list:
        te = self.trail_engine
        tcfg = te.cfg if te else self.cfg.get("render.trails", {})
        enabled = bool(tcfg.get("enabled", True))
        active_id = tcfg.get("active_preset", "nebula_silk")
        favs = tcfg.get("favorites", [])
        recents = tcfg.get("recent_presets", [])
        cur_qual = tcfg.get("quality", {}).get("preset", "balanced")
        cur_int = float(tcfg.get("global_intensity", 0.85))

        # Presets submenu: Recently used, Favorites, Featured Bundled
        recent_items = []
        for pid in recents[:5]:
            if pid in PRESET_IDS_ORDERED:
                idx = PRESET_IDS_ORDERED.index(pid)
                p = BUNDLED_PRESETS[pid]
                recent_items.append((p["name"], CMD_TRAIL_PRESET + idx, pid == active_id))

        fav_items = []
        for pid in favs[:8]:
            if pid in PRESET_IDS_ORDERED:
                idx = PRESET_IDS_ORDERED.index(pid)
                p = BUNDLED_PRESETS[pid]
                fav_items.append((p["name"], CMD_TRAIL_PRESET + idx, pid == active_id))

        featured_ids = [
            "nebula_silk", "stardust", "event_horizon", "solar_flare",
            "storm_arc", "ghost_veil", "aurora_threads", "plasma_jet",
            "hyperdrive", "pixie_dust", "double_helix", "legacy_zwoop",
        ]
        featured_items = [
            (BUNDLED_PRESETS[pid]["name"],
             CMD_TRAIL_PRESET + PRESET_IDS_ORDERED.index(pid),
             pid == active_id)
            for pid in featured_ids if pid in PRESET_IDS_ORDERED
        ]

        presets_sub = []
        if recent_items:
            presets_sub.append(("Recently Used", recent_items, None))
        if fav_items:
            presets_sub.append(("Favorites", fav_items, None))
        presets_sub.extend(featured_items)

        int_sub = [
            (f"{label} ({val:.2f})", CMD_TRAIL_INT + i, abs(cur_int - val) < 0.08)
            for i, (label, val) in enumerate(INTENSITY_LEVELS)
        ]
        int_sub.append(("Custom (Trail Studio)...", CMD_TRAIL_STUDIO, False))

        qual_sub = [
            (q.capitalize(), CMD_TRAIL_QUAL + i, cur_qual == q)
            for i, q in enumerate(QUALITY_LEVELS)
        ]

        return [
            ("Enable Trails" if not enabled else "Disable Trails",
             CMD_TRAIL_TOGGLE, enabled),
            ("Open Trail Studio...", CMD_TRAIL_STUDIO, False),
            SEP,
            ("Presets", presets_sub, None),
            ("Intensity", int_sub, None),
            ("Quality", qual_sub, None),
            SEP,
            ("Clear current trails", CMD_TRAIL_CLEAR, False),
        ]

    def menu_spec(self):
        cfg = self.cfg
        spec = [
            (f"Zwoop — {self.sim.brain.state.name}"
             + (f" ·{self.sim._last_out.maneuver}" if getattr(self.sim, '_last_out', None) and self.sim._last_out.maneuver else "")
             + (" [paused]" if self.paused else ""), None, None),
            SEP,
            ("Open Trail Studio...", CMD_TRAIL_STUDIO,
             bool(self.studio and self.studio.is_open)),
            ("Trails", self._build_trails_submenu(), None),
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
            self.hidden = not self.hidden
            log.info("hidden=%s", self.hidden)
        elif cid == CMD_DEBUG:
            self.debug = not self.debug
        elif cid == CMD_AUTOSTART:
            autostart.set_enabled(not autostart.is_enabled())
        elif cid == CMD_OPENCFG:
            folder = os.path.dirname(cfg.path)
            os.makedirs(folder, exist_ok=True)
            subprocess.Popen(["explorer", folder])
        elif cid == CMD_TRAIL_STUDIO:
            self.open_trail_studio()
        elif cid == CMD_TRAIL_TOGGLE:
            new_on = not self.trail_engine.enabled
            self.trail_engine.set_enabled(new_on)
            cfg.set("render.trails.enabled", new_on)
            if not new_on and self.trail_overlay:
                self.trail_overlay.set_visible(False)
            if self.studio:
                self.studio.working_cfg["enabled"] = new_on
                self.studio._sync_all_widgets()
            cfg.save()
        elif cid == CMD_TRAIL_CLEAR:
            self._on_clear_trails()
        elif CMD_TRAIL_QUAL <= cid < CMD_TRAIL_QUAL + len(QUALITY_LEVELS):
            q = QUALITY_LEVELS[cid - CMD_TRAIL_QUAL]
            self.trail_engine.cfg["quality"]["preset"] = q
            cfg.set("render.trails.quality.preset", q)
            if self.studio:
                self.studio.working_cfg["quality"]["preset"] = q
                self.studio._sync_all_widgets()
            cfg.save()
        elif CMD_TRAIL_INT <= cid < CMD_TRAIL_INT + len(INTENSITY_LEVELS):
            _, val = INTENSITY_LEVELS[cid - CMD_TRAIL_INT]
            self.trail_engine.cfg["global_intensity"] = val
            cfg.set("render.trails.global_intensity", val)
            if self.studio:
                self.studio.working_cfg["global_intensity"] = val
                self.studio._sync_all_widgets()
            cfg.save()
        elif CMD_TRAIL_PRESET <= cid < CMD_TRAIL_PRESET + len(PRESET_IDS_ORDERED):
            pid = PRESET_IDS_ORDERED[cid - CMD_TRAIL_PRESET]
            p = self.trail_engine.load_preset(pid, clear_existing=True)
            cfg.set("render.trails.active_preset", pid)
            cfg.set("render.trails.custom_working", None)
            cfg.set("render.trails.recent_presets", self.trail_engine.cfg["recent_presets"])
            self.raster.trail_on = (self.trail_engine.enabled and pid == "legacy_zwoop")
            if self.studio:
                self.studio.working_preset = copy.deepcopy(p)
                self.studio.working_cfg["active_preset"] = pid
                self.studio.working_cfg["custom_working"] = None
                self.studio._sync_all_widgets()
            cfg.save()
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
            if self.studio:
                self.studio.theme_name = name
                self.studio.preview_creature.set_theme(name)
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
            if self.trail_engine:
                self.trail_engine.notify_discontinuity()

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
            if self.studio and self.studio.is_open:
                self.studio.close_window()
        except Exception:
            pass
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
            if self.trail_overlay:
                self.trail_overlay.destroy()
        except Exception as e:
            log.warning("trail overlay cleanup: %s", e)
        try:
            if self.overlay:
                self.overlay.destroy()
        except Exception as e:
            log.warning("overlay cleanup: %s", e)
