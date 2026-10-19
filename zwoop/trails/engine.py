"""TrailEngine, TrailProfiler, and AutoQuality controller for Zwoop Trail Studio."""

from __future__ import annotations

from collections import deque
import copy
import math
import time
from typing import Any

import numpy as np

from .geometry import LayerRenderer, _box_blur_2d
from .history import TrailHistory
from .particles import ParticleSystem
from .presets import BUNDLED_PRESETS, PresetStore
from .reactive import ReactiveController, ReactiveModulation
from .schema import (
    QUALITY_BUDGETS,
    default_trails_config,
    validate_preset_dict,
    validate_trails_config,
)


class TrailProfiler:
    """Rolling frame-time and resource profiler with auto-quality hysteresis."""

    _TIERS = ("eco", "balanced", "high", "ultra")

    def __init__(self):
        self.render_ms_window: deque[float] = deque(maxlen=45)
        self.step_ms_window: deque[float] = deque(maxlen=45)
        self.last_render_ms: float = 0.0
        self.last_step_ms: float = 0.0
        self.active_samples: int = 0
        self.active_particles: int = 0
        self.active_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
        self.effective_tier: str = "balanced"
        self._last_tier_change_t: float = -999.0
        self._high_load_accum: float = 0.0
        self._low_load_accum: float = 0.0

    @property
    def avg_render_ms(self) -> float:
        if not self.render_ms_window:
            return 0.0
        return float(sum(self.render_ms_window) / len(self.render_ms_window))

    @property
    def p95_render_ms(self) -> float:
        if not self.render_ms_window:
            return 0.0
        s = sorted(self.render_ms_window)
        return float(s[min(len(s) - 1, int(len(s) * 0.95))])

    def update_auto_quality(
        self,
        dt: float,
        now_t: float,
        requested_preset: str,
        auto_enabled: bool,
        target_fps: int = 60,
    ) -> dict[str, Any]:
        """Return effective quality budget dict with hysteresis protection."""
        if requested_preset in QUALITY_BUDGETS and not (
            requested_preset == "auto" or auto_enabled
        ):
            self.effective_tier = requested_preset
            return copy.deepcopy(QUALITY_BUDGETS[self.effective_tier])

        if requested_preset in self._TIERS and self.effective_tier not in self._TIERS:
            self.effective_tier = requested_preset

        frame_budget_ms = 1000.0 / max(30, int(target_fps))
        trail_budget_ms = frame_budget_ms * 0.48  # leave >50% of frame for creature + OS
        avg = self.avg_render_ms

        if len(self.render_ms_window) >= 12:
            if avg > trail_budget_ms * 1.15:
                self._high_load_accum += dt
                self._low_load_accum = 0.0
            elif avg < trail_budget_ms * 0.45:
                self._low_load_accum += dt
                self._high_load_accum = 0.0
            else:
                self._high_load_accum = max(0.0, self._high_load_accum - dt * 0.5)
                self._low_load_accum = max(0.0, self._low_load_accum - dt * 0.5)

            idx = self._TIERS.index(self.effective_tier) if self.effective_tier in self._TIERS else 1
            max_idx = (
                self._TIERS.index(requested_preset)
                if requested_preset in self._TIERS
                else 2  # cap auto at 'high' unless 'ultra' explicitly chosen
            )
            # Step down after 1.2s of sustained high load (min 1.5s between changes)
            if (
                self._high_load_accum > 1.2
                and idx > 0
                and (now_t - self._last_tier_change_t) > 1.5
            ):
                self.effective_tier = self._TIERS[idx - 1]
                self._last_tier_change_t = now_t
                self._high_load_accum = 0.0
            # Step up only after 4.0s of sustained low load (strong hysteresis)
            elif (
                self._low_load_accum > 4.0
                and idx < max_idx
                and (now_t - self._last_tier_change_t) > 4.0
            ):
                self.effective_tier = self._TIERS[idx + 1]
                self._last_tier_change_t = now_t
                self._low_load_accum = 0.0
        elif requested_preset in self._TIERS:
            self.effective_tier = requested_preset

        return copy.deepcopy(QUALITY_BUDGETS[self.effective_tier])


class TrailEngine:
    """Platform-agnostic world-space trail simulation and rendering engine."""

    def __init__(
        self,
        trails_cfg: dict[str, Any] | None = None,
        preset_store: PresetStore | None = None,
        seed: int = 42,
    ):
        self.store = preset_store or PresetStore()
        self.seed = int(seed)
        self.cfg = validate_trails_config(trails_cfg or default_trails_config())
        self.history = TrailHistory(
            max_samples=320,
            min_spacing_px=float(self.cfg["quality"].get("sample_spacing_px", 6.0)),
        )
        self.reactive = ReactiveController()
        self.renderer = LayerRenderer()
        self.profiler = TrailProfiler()
        self.particle_systems: dict[str, ParticleSystem] = {}
        self.active_preset: dict[str, Any] = self._resolve_active_preset()
        self.last_modulation: ReactiveModulation = ReactiveModulation()
        self._sync_particle_systems()

    def _resolve_active_preset(self) -> dict[str, Any]:
        cw = self.cfg.get("custom_working")
        if isinstance(cw, dict):
            try:
                return validate_preset_dict(cw, strict=False)
            except Exception:
                pass
        pid = self.cfg.get("active_preset", "nebula_silk")
        p = self.store.get(pid)
        if p is None:
            p = copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])
        return p

    def _sync_particle_systems(self) -> None:
        layers = self.active_preset.get("layers", [])
        valid_ids = set()
        for i, lyr in enumerate(layers):
            lid = lyr["id"]
            valid_ids.add(lid)
            if lid not in self.particle_systems:
                self.particle_systems[lid] = ParticleSystem(seed=self.seed + (i + 1) * 97)
        for lid in list(self.particle_systems):
            if lid not in valid_ids:
                del self.particle_systems[lid]

    @property
    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", True))

    def set_enabled(self, on: bool) -> None:
        self.cfg["enabled"] = bool(on)
        if not on:
            self.clear()

    def load_preset(self, preset_id_or_dict: str | dict[str, Any], clear_existing: bool = False) -> dict[str, Any]:
        """Switch active preset by ID or validated preset dict."""
        if isinstance(preset_id_or_dict, str):
            p = self.store.get(preset_id_or_dict)
            if p is None:
                p = copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])
            self.cfg["active_preset"] = p["id"]
            self.cfg["custom_working"] = None
            rec = [x for x in self.cfg.get("recent_presets", []) if x != p["id"]]
            rec.insert(0, p["id"])
            self.cfg["recent_presets"] = rec[:10]
        else:
            p = validate_preset_dict(preset_id_or_dict, strict=False)
            self.cfg["active_preset"] = p["id"]
            self.cfg["custom_working"] = copy.deepcopy(p)

        self.active_preset = p
        self._sync_particle_systems()
        if clear_existing:
            self.clear()
        return copy.deepcopy(self.active_preset)

    def clear(self) -> None:
        """Clear all trail history and active particles immediately."""
        self.history.clear()
        for ps in self.particle_systems.values():
            ps.clear()
        self.profiler.active_samples = 0
        self.profiler.active_particles = 0
        self.profiler.active_bbox = (0, 0, 0, 0)

    def notify_discontinuity(self) -> None:
        """Break the current stroke (e.g. teleport, monitor change, unpause)."""
        self.history.notify_break()
        for ps in self.particle_systems.values():
            ps.notify_break()

    def has_active_visuals(self) -> bool:
        if not self.enabled:
            return False
        if len(self.history.samples) >= 2:
            return True
        return any(ps.count > 0 for ps in self.particle_systems.values())

    def max_configured_lifetime(self) -> float:
        q_max = float(self.cfg["quality"].get("max_lifetime_s", 4.5))
        layers = self.active_preset.get("layers", [])
        if not layers:
            return 1.5
        l_max = max(float(lyr.get("lifetime_s", 1.8)) for lyr in layers if lyr.get("enabled", True)) if any(lyr.get("enabled", True) for lyr in layers) else 1.0
        return min(q_max * 1.4, l_max * 1.5)

    def step(
        self,
        dt: float,
        snap: dict[str, Any],
        region: Any = None,
        target_fps: int = 60,
    ) -> None:
        """Advance trail history, reactivity, and particle physics by `dt`."""
        if not self.enabled:
            if self.history.samples or any(ps.count > 0 for ps in self.particle_systems.values()):
                self.clear()
            return

        t0 = time.perf_counter()
        now_t = float(snap.get("t", 0.0))
        q_cfg = self.cfg["quality"]
        q_budget = self.profiler.update_auto_quality(
            dt,
            now_t,
            q_cfg.get("preset", "balanced"),
            bool(q_cfg.get("auto_quality", True)),
            target_fps=target_fps,
        )

        self.history.min_spacing_px = float(q_budget.get("sample_spacing_px", 6.0))
        reduced_motion = bool(q_cfg.get("reduced_motion", False))
        disable_bursts = bool(q_cfg.get("disable_bursts", False))

        # Merge preset behavior rules with user behavior overrides
        beh_cfg = copy.deepcopy(self.active_preset.get("behavior", {}))
        if not beh_cfg.get("enabled", True):
            pass
        mod = self.reactive.update(
            dt,
            snap,
            beh_cfg,
            speed_reactivity=float(self.cfg.get("speed_reactivity", 0.8)),
            reduced_motion=reduced_motion,
            disable_bursts=disable_bursts,
        )
        self.last_modulation = mod

        max_life = min(float(q_budget["max_lifetime_s"]), self.max_configured_lifetime())
        self.history.record(snap, now_t=now_t, max_lifetime_s=max_life)

        # Step particle systems with shared global particle budget
        layers = self.active_preset.get("layers", [])
        any_solo = any(lyr.get("solo", False) and lyr.get("enabled", True) for lyr in layers)
        active_p_layers = [
            lyr for lyr in layers
            if lyr.get("enabled", True)
            and (not any_solo or lyr.get("solo", False))
            and lyr.get("family") in ("particles", "smoke", "sparks")
        ]
        global_p_cap = int(q_budget.get("particle_cap", 150))
        per_layer_cap = max(15, global_p_cap // max(1, len(active_p_layers)))

        c = snap.get("center")
        vel = snap.get("vel")
        ev = vel[0] if (vel is not None and len(vel) > 0) else (0.0, 0.0)
        idle_em = float(beh_cfg.get("idle_emission", 0.35))

        total_p = 0
        for lyr in layers:
            lid = lyr["id"]
            ps = self.particle_systems.get(lid)
            if ps is None:
                continue
            if lyr.get("family") not in ("particles", "smoke", "sparks") or not lyr.get("enabled", True) or (any_solo and not lyr.get("solo", False)):
                if ps.count > 0:
                    ps.clear()
                continue
            lyr["_idle_emission"] = idle_em
            burst_n = 0
            if mod.burst_factor > 0.05:
                burst_n = int(round(float(lyr.get("particles", {}).get("spawn_burst_size", 12)) * mod.burst_factor))
            ps.step(
                dt,
                lyr,
                emit_pos=c,
                emit_vel=ev,
                rate_mult=mod.particle_rate_mult,
                burst_count=burst_n,
                cap_override=per_layer_cap,
                region=region,
                reduced_motion=reduced_motion,
            )
            total_p += ps.count

        self.profiler.active_samples = len(self.history.samples)
        self.profiler.active_particles = total_p
        step_ms = (time.perf_counter() - t0) * 1000.0
        self.profiler.last_step_ms = step_ms
        self.profiler.step_ms_window.append(step_ms)

    def compute_active_bounds(
        self,
        snap: dict[str, Any],
        max_w: int = 1280,
        max_h: int = 960,
        quantize: int = 16,
    ) -> tuple[int, int, int, int] | None:
        """Compute quantized world-space bounding box (x0, y0, w, h) for active trail."""
        if not self.enabled:
            return None

        xs: list[float] = []
        ys: list[float] = []
        c = snap.get("center")
        if c is not None and math.isfinite(c[0]) and math.isfinite(c[1]):
            xs.append(float(c[0]))
            ys.append(float(c[1]))

        now_t = float(snap.get("t", 0.0))
        max_life = self.max_configured_lifetime()

        # Include live history points (plus drift allowance)
        for s in self.history.samples:
            age = max(0.0, now_t - s.t)
            if age <= max_life:
                xs.append(s.x)
                ys.append(s.y)

        # Include live particles
        for ps in self.particle_systems.values():
            if ps.count > 0:
                xs.append(float(ps.pos[:, 0].min()))
                xs.append(float(ps.pos[:, 0].max()))
                ys.append(float(ps.pos[:, 1].min()))
                ys.append(float(ps.pos[:, 1].max()))

        if len(xs) < 2 and all(ps.count == 0 for ps in self.particle_systems.values()):
            return None

        # Margin for ribbon width, spiral amplitude, drift, and glow radius
        pad = 96.0
        x_min = min(xs) - pad
        x_max = max(xs) + pad
        y_min = min(ys) - pad
        y_max = max(ys) + pad

        # Quantize outward to `quantize` pixel boundaries to avoid sub-frame jitter
        q = max(4, int(quantize))
        qx0 = int(math.floor(x_min / q) * q)
        qy0 = int(math.floor(y_min / q) * q)
        qx1 = int(math.ceil(x_max / q) * q)
        qy1 = int(math.ceil(y_max / q) * q)

        w = max(q * 4, qx1 - qx0)
        h = max(q * 4, qy1 - qy0)

        # If bbox exceeds max surface size, anchor box around creature's head
        if w > max_w:
            cx = int(c[0]) if c is not None else (qx0 + qx1) // 2
            qx0 = int(math.floor((cx - max_w * 0.5) / q) * q)
            w = max_w
        if h > max_h:
            cy = int(c[1]) if c is not None else (qy0 + qy1) // 2
            qy0 = int(math.floor((cy - max_h * 0.5) / q) * q)
            h = max_h

        self.profiler.active_bbox = (qx0, qy0, w, h)
        return (qx0, qy0, w, h)

    def render_into(
        self,
        frame: np.ndarray,
        window_origin: tuple[float, float],
        snap: dict[str, Any],
        theme_name: str = "cosmos",
        res_scale_override: int | None = None,
    ) -> bool:
        """Render all active layers into `frame` (H, W, 4 uint8 premultiplied BGRA).

        Returns True if any non-zero trail pixels were written.
        """
        if not self.enabled:
            frame.fill(0)
            return False

        t0 = time.perf_counter()
        fh, fw = frame.shape[:2]
        q_cfg = copy.deepcopy(self.cfg["quality"])
        eff_budget = QUALITY_BUDGETS.get(self.profiler.effective_tier, QUALITY_BUDGETS["balanced"])
        q_cfg["segment_cap"] = min(int(q_cfg.get("segment_cap", 120)), int(eff_budget["segment_cap"]))
        q_cfg["max_lifetime_s"] = min(float(q_cfg.get("max_lifetime_s", 4.5)), float(eff_budget["max_lifetime_s"]))

        rs = int(res_scale_override or eff_budget.get("res_scale", q_cfg.get("res_scale", 3)))
        rs = max(1, min(4, rs))
        # Ensure clean integer tiling
        while rs > 1 and (fh % rs != 0 or fw % rs != 0):
            rs -= 1

        ih = max(1, fh // rs)
        iw = max(1, fw // rs)
        ox, oy = float(window_origin[0]), float(window_origin[1])

        gx_1d = ox + np.arange(iw, dtype=np.float32) * rs + rs * 0.5
        gy_1d = oy + np.arange(ih, dtype=np.float32) * rs + rs * 0.5
        gy, gx = np.meshgrid(gy_1d, gx_1d, indexing="ij")

        dst_rgb_pre = np.zeros((ih, iw, 3), dtype=np.float32)
        dst_a = np.zeros((ih, iw), dtype=np.float32)

        layers = self.active_preset.get("layers", [])
        any_solo = any(lyr.get("solo", False) and lyr.get("enabled", True) for lyr in layers)
        # Sort by priority while preserving relative order
        ordered_layers = sorted(
            enumerate(layers),
            key=lambda iv: (int(iv[1].get("priority", 0)), iv[0]),
        )

        now_t = float(snap.get("t", 0.0))
        g_int = float(self.cfg.get("global_intensity", 0.85)) * float(
            self.active_preset.get("default_intensity", 0.85)
        )
        g_op = float(self.cfg.get("global_opacity", 0.90))

        for _, lyr in ordered_layers:
            if not lyr.get("enabled", True):
                continue
            if any_solo and not lyr.get("solo", False):
                continue
            ps = self.particle_systems.get(lyr["id"])
            self.renderer.render_layer(
                gx,
                gy,
                dst_rgb_pre,
                dst_a,
                lyr,
                self.history,
                ps,
                self.last_modulation,
                snap,
                now_t,
                q_cfg,
                global_intensity=g_int,
                global_opacity=g_op,
                theme_name=theme_name,
            )

        if not np.any(dst_a > 1e-3):
            frame.fill(0)
            render_ms = (time.perf_counter() - t0) * 1000.0
            self.profiler.last_render_ms = render_ms
            self.profiler.render_ms_window.append(render_ms)
            return False

        # Light tent filter to smooth low-res grid edges before upsampling
        if rs >= 2:
            _box_blur_2d(dst_rgb_pre, passes=1)
            _box_blur_2d(dst_a, passes=1)
            max_c = np.max(dst_rgb_pre, axis=-1)
            dst_a = np.clip(np.maximum(dst_a, max_c), 0.0, 1.0)
            np.minimum(dst_rgb_pre, dst_a[..., None], out=dst_rgb_pre)

        obuf = np.zeros((ih, iw, 4), dtype=np.uint8)
        obuf[..., 0] = (dst_rgb_pre[..., 2] * 255.0).astype(np.uint8)  # B
        obuf[..., 1] = (dst_rgb_pre[..., 1] * 255.0).astype(np.uint8)  # G
        obuf[..., 2] = (dst_rgb_pre[..., 0] * 255.0).astype(np.uint8)  # R
        obuf[..., 3] = (dst_a * 255.0).astype(np.uint8)                # A

        if rs == 1:
            frame[:] = obuf
        elif frame.flags.c_contiguous:
            # Fast zero-allocation in-place block broadcast when contiguous
            frame.reshape(ih, rs, iw, rs, 4)[:] = obuf[:, None, :, None, :]
        else:
            # Non-contiguous DIB sub-slice view: write via repeat into slice
            frame[:] = np.repeat(np.repeat(obuf, rs, axis=0), rs, axis=1)

        render_ms = (time.perf_counter() - t0) * 1000.0
        self.profiler.last_render_ms = render_ms
        self.profiler.render_ms_window.append(render_ms)
        return True
