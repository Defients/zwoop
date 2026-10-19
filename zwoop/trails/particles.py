"""Deterministic, vectorized particle & puff/spark simulator for Trail Studio."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


class ParticleSystem:
    """Bounded, seeded particle emitter and physics integrator for one layer."""

    def __init__(self, seed: int = 101):
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.reset()

    def reset(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.pos = np.zeros((0, 2), dtype=np.float32)
        self.vel = np.zeros((0, 2), dtype=np.float32)
        self.age = np.zeros(0, dtype=np.float32)
        self.life = np.zeros(0, dtype=np.float32)
        self.size0 = np.zeros(0, dtype=np.float32)
        self.size = np.zeros(0, dtype=np.float32)
        self.rot = np.zeros(0, dtype=np.float32)
        self.ang_vel = np.zeros(0, dtype=np.float32)
        self.hue_jit = np.zeros(0, dtype=np.float32)
        self.phase = np.zeros(0, dtype=np.float32)
        self.birth_speed = np.zeros(0, dtype=np.float32)
        self._spawn_acc: float = 0.0
        self._prev_emit_pos: np.ndarray | None = None
        self._t: float = 0.0

    @property
    def count(self) -> int:
        return int(len(self.age))

    def clear(self) -> None:
        self.pos = np.zeros((0, 2), dtype=np.float32)
        self.vel = np.zeros((0, 2), dtype=np.float32)
        self.age = np.zeros(0, dtype=np.float32)
        self.life = np.zeros(0, dtype=np.float32)
        self.size0 = np.zeros(0, dtype=np.float32)
        self.size = np.zeros(0, dtype=np.float32)
        self.rot = np.zeros(0, dtype=np.float32)
        self.ang_vel = np.zeros(0, dtype=np.float32)
        self.hue_jit = np.zeros(0, dtype=np.float32)
        self.phase = np.zeros(0, dtype=np.float32)
        self.birth_speed = np.zeros(0, dtype=np.float32)
        self._spawn_acc = 0.0
        self._prev_emit_pos = None

    def notify_break(self) -> None:
        self._prev_emit_pos = None

    def step(
        self,
        dt: float,
        layer: dict[str, Any],
        emit_pos: tuple[float, float] | np.ndarray | None,
        emit_vel: tuple[float, float] | np.ndarray | None,
        rate_mult: float = 1.0,
        burst_count: int = 0,
        cap_override: int | None = None,
        region: Any = None,
        reduced_motion: bool = False,
    ) -> None:
        """Advance existing particles by `dt` and spawn new particles."""
        if dt <= 0.0 or not math.isfinite(dt):
            return
        dt = min(float(dt), 0.25)
        self._t += dt

        pcfg = layer.get("particles", {})
        mcfg = layer.get("motion", {})
        fam = layer.get("family", "particles")

        # ---- 1. Advance existing particles ---------------------------------
        if len(self.age) > 0:
            self.age += dt
            alive = (self.age < self.life) & np.isfinite(self.pos).all(axis=1)
            if not np.all(alive):
                self._filter(alive)

        if len(self.age) > 0:
            drag = float(pcfg.get("drag", 1.6))
            if fam == "smoke":
                drag = max(drag, 2.2)
            damp = math.exp(-max(0.0, drag) * dt)

            grav = float(pcfg.get("gravity", -18.0))
            turb = float(pcfg.get("turbulence", 45.0))
            if reduced_motion:
                turb *= 0.25

            drift_x = float(mcfg.get("drift_x", 0.0))
            drift_y = float(mcfg.get("drift_y", -8.0))

            if turb > 0.1:
                px = self.pos[:, 0]
                py = self.pos[:, 1]
                ax = turb * np.sin(py * 0.022 + self._t * 2.1 + self.phase)
                ay = turb * np.cos(px * 0.022 - self._t * 1.8 + self.phase * 1.3)
                self.vel[:, 0] += ax * dt
                self.vel[:, 1] += ay * dt

            self.vel[:, 1] += grav * dt
            self.vel *= damp

            self.pos[:, 0] += (self.vel[:, 0] + drift_x) * dt
            self.pos[:, 1] += (self.vel[:, 1] + drift_y) * dt

            ang_v = float(pcfg.get("angular_velocity", 45.0))
            if reduced_motion:
                ang_v *= 0.2
            self.rot = (self.rot + self.ang_vel * dt) % 360.0

            growth = float(pcfg.get("growth_rate", 0.3))
            if fam == "smoke" and growth < 0.4:
                growth = max(growth, 0.65)
            elif fam == "sparks" and growth > -0.1:
                growth = -0.35
            u = np.clip(self.age / np.maximum(self.life, 1e-4), 0.0, 1.0)
            self.size = np.maximum(1.0, self.size0 * np.maximum(0.15, 1.0 + growth * u))

            # Optional boundary handling
            edge_mode = pcfg.get("edge_behavior", "fade")
            if region is not None and edge_mode in ("bounce", "fade"):
                for i in range(len(self.age)):
                    x, y = float(self.pos[i, 0]), float(self.pos[i, 1])
                    r = float(self.size[i])
                    if not region.contains(x, y, r):
                        if edge_mode == "bounce":
                            nx, ny = region.project_inside(x, y, r)
                            if abs(nx - x) > abs(ny - y):
                                self.vel[i, 0] = -self.vel[i, 0] * 0.6
                            else:
                                self.vel[i, 1] = -self.vel[i, 1] * 0.6
                            self.pos[i] = (nx, ny)
                        else:
                            self.age[i] = min(self.life[i], self.age[i] + dt * 3.0)

        # ---- 2. Determine emission count -----------------------------------
        if emit_pos is None or not layer.get("enabled", True):
            return

        ep = np.asarray(emit_pos, dtype=np.float32)
        if not np.isfinite(ep).all():
            return
        ev = (
            np.zeros(2, dtype=np.float32)
            if emit_vel is None
            else np.asarray(emit_vel, dtype=np.float32)
        )
        if not np.isfinite(ev).all():
            ev = np.zeros(2, dtype=np.float32)

        max_p = int(pcfg.get("max_particles", 120))
        if cap_override is not None:
            max_p = min(max_p, max(4, int(cap_override)))

        base_rate = float(pcfg.get("spawn_rate", 36.0))
        spd = float(np.linalg.norm(ev))
        spd_resp = float(mcfg.get("speed_response", 0.65))
        idle_em = float(layer.get("_idle_emission", 0.35))
        spd_factor = idle_em + (1.0 - idle_em) * min(1.5, spd / 260.0) * (0.4 + 0.6 * spd_resp)
        if fam == "sparks" and spd < 90.0 and burst_count <= 0:
            spd_factor *= 0.2

        eff_rate = max(0.0, base_rate * max(0.0, float(rate_mult)) * spd_factor)
        var = float(pcfg.get("spawn_variance", 0.25))
        if var > 0.0:
            eff_rate *= float(self.rng.uniform(max(0.2, 1.0 - var), 1.0 + var))

        self._spawn_acc += eff_rate * dt
        n_cont = int(self._spawn_acc)
        self._spawn_acc -= n_cont

        n_total = min(max_p, n_cont + max(0, int(burst_count)))
        if n_total > 0:
            self._spawn_batch(n_total, ep, ev, layer, max_p, is_burst=(burst_count > 0))

        self._prev_emit_pos = ep.copy()

    def _spawn_batch(
        self,
        n: int,
        ep: np.ndarray,
        ev: np.ndarray,
        layer: dict[str, Any],
        max_p: int,
        is_burst: bool = False,
    ) -> None:
        pcfg = layer.get("particles", {})
        mcfg = layer.get("motion", {})
        fam = layer.get("family", "particles")
        scale = float(layer.get("size_scale", 1.0))

        # Interpolate birth positions along current step segment
        p0 = ep if (self._prev_emit_pos is None or is_burst) else self._prev_emit_pos
        if np.linalg.norm(ep - p0) > 260.0:
            p0 = ep
        alphas = self.rng.uniform(0.0, 1.0, size=(n, 1)).astype(np.float32)
        b_pos = p0[None, :] + (ep - p0)[None, :] * alphas

        # Perpendicular offset + jitter
        spd = float(np.linalg.norm(ev))
        if spd > 2.0:
            tangent = ev / spd
            back_angle = math.atan2(-tangent[1], -tangent[0])
        else:
            back_angle = float(self.rng.uniform(0.0, 2.0 * math.pi))
            tangent = np.array([math.cos(back_angle + math.pi), math.sin(back_angle + math.pi)], dtype=np.float32)

        normal = np.array([-tangent[1], tangent[0]], dtype=np.float32)
        off_px = float(layer.get("offset_px", 0.0))
        jitter = float(mcfg.get("position_jitter", 0.0)) + (8.0 if fam == "smoke" else 3.0)
        b_pos += normal[None, :] * off_px
        b_pos += self.rng.normal(0.0, max(0.5, jitter), size=(n, 2)).astype(np.float32)

        # Emission cone angles around backward direction (or omnidirectional on burst)
        spread_deg = 360.0 if is_burst else float(pcfg.get("directional_spread", 120.0))
        half_rad = math.radians(spread_deg) * 0.5
        angles = back_angle + self.rng.uniform(-half_rad, half_rad, size=n).astype(np.float32)

        v_init = float(pcfg.get("initial_velocity", 55.0)) * (1.45 if is_burst else 1.0)
        speeds = v_init * self.rng.uniform(0.45, 1.35, size=n).astype(np.float32)
        inh = float(pcfg.get("velocity_inheritance", 0.25))
        b_vel = (
            ev[None, :] * inh
            + np.column_stack([np.cos(angles) * speeds, np.sin(angles) * speeds]).astype(np.float32)
        )

        # Lifetime with variance
        base_life = max(0.12, float(layer.get("lifetime_s", 1.5)))
        l_var = float(layer.get("lifetime_variance", 0.25))
        b_life = base_life * self.rng.uniform(max(0.25, 1.0 - l_var), 1.0 + l_var, size=n).astype(np.float32)
        b_age = np.zeros(n, dtype=np.float32)

        # Size with variation
        base_sz = max(1.5, float(pcfg.get("size_px", 9.0)) * scale)
        if fam == "smoke":
            base_sz = max(base_sz, 16.0 * scale)
        s_var = float(pcfg.get("size_variation", 0.35))
        b_sz0 = base_sz * self.rng.uniform(max(0.25, 1.0 - s_var), 1.0 + s_var, size=n).astype(np.float32)

        rot0 = float(pcfg.get("rotation_deg", 0.0))
        b_rot = (rot0 + self.rng.uniform(0.0, 360.0, size=n)).astype(np.float32)
        ang_v = float(pcfg.get("angular_velocity", 45.0))
        b_ang = self.rng.uniform(-abs(ang_v) - 15.0, abs(ang_v) + 15.0, size=n).astype(np.float32)

        h_var = float(layer.get("hue_variance", 0.08))
        b_hue = self.rng.uniform(-180.0 * h_var, 180.0 * h_var, size=n).astype(np.float32)
        b_phase = self.rng.uniform(0.0, 2.0 * math.pi, size=n).astype(np.float32)
        b_spd = np.full(n, spd, dtype=np.float32)

        self.pos = np.concatenate([self.pos, b_pos], axis=0)
        self.vel = np.concatenate([self.vel, b_vel], axis=0)
        self.age = np.concatenate([self.age, b_age], axis=0)
        self.life = np.concatenate([self.life, b_life], axis=0)
        self.size0 = np.concatenate([self.size0, b_sz0], axis=0)
        self.size = np.concatenate([self.size, b_sz0.copy()], axis=0)
        self.rot = np.concatenate([self.rot, b_rot], axis=0)
        self.ang_vel = np.concatenate([self.ang_vel, b_ang], axis=0)
        self.hue_jit = np.concatenate([self.hue_jit, b_hue], axis=0)
        self.phase = np.concatenate([self.phase, b_phase], axis=0)
        self.birth_speed = np.concatenate([self.birth_speed, b_spd], axis=0)

        # Enforce hard cap (keep newest particles)
        if len(self.age) > max_p:
            keep = slice(len(self.age) - max_p, len(self.age))
            self._slice(keep)

    def _filter(self, mask: np.ndarray) -> None:
        self.pos = self.pos[mask]
        self.vel = self.vel[mask]
        self.age = self.age[mask]
        self.life = self.life[mask]
        self.size0 = self.size0[mask]
        self.size = self.size[mask]
        self.rot = self.rot[mask]
        self.ang_vel = self.ang_vel[mask]
        self.hue_jit = self.hue_jit[mask]
        self.phase = self.phase[mask]
        self.birth_speed = self.birth_speed[mask]

    def _slice(self, sl: slice) -> None:
        self.pos = self.pos[sl]
        self.vel = self.vel[sl]
        self.age = self.age[sl]
        self.life = self.life[sl]
        self.size0 = self.size0[sl]
        self.size = self.size[sl]
        self.rot = self.rot[sl]
        self.ang_vel = self.ang_vel[sl]
        self.hue_jit = self.hue_jit[sl]
        self.phase = self.phase[sl]
        self.birth_speed = self.birth_speed[sl]
