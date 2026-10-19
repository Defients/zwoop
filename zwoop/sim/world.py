"""Sim — wires Region + SoftBody + Brain into one deterministic creature.

    sim = Sim(region, params, seed=7)
    sim.step(dt, percept)         # fixed-step update
    snap = sim.snapshot(alpha)    # interpolated render state

Everything here is platform-free: percept inputs come from a CursorTracker
fed by Win32 code in production, or by scripted paths in tests/replays.
"""

from __future__ import annotations

import numpy as np

from .body import SoftBody, BodyParams
from .brain import Brain, Params, Percept, State
from .region import Region
from .perception import CursorTracker


class Sim:
    def __init__(self, region: Region, params: Params | None = None,
                 body_params: BodyParams | None = None,
                 center=None, seed: int | None = None):
        self.rng = np.random.default_rng(seed)
        self.region = region
        self.p = params or Params()
        bp = body_params or BodyParams()
        if self.p.size_scale != 1.0:
            bp.ring_radius *= self.p.size_scale
            bp.core_radius *= self.p.size_scale
            bp.outer_radius *= self.p.size_scale
        if center is None:
            host = region.rects[0]
            center = (host.cx, host.cy)
        self.body = SoftBody(bp, center=center, rng=self.rng)
        self.brain = Brain(region, self.p, rng=self.rng)
        self.tracker = CursorTracker()
        self.cursor_ok = True
        self.last_percept = Percept()
        self.t = 0.0

    def feed_cursor(self, pos):
        """Feed a raw cursor sample (or None) at the current sim time."""
        frag = self.tracker.update(self.t, pos) if pos is not None else None
        c = self.body.center
        if frag is None:
            self.last_percept = Percept(user_idle_s=self.last_percept.user_idle_s)
            return
        d = float(np.linalg.norm(frag["pos"] - c))
        self.last_percept = Percept(
            cursor_pos=frag["pos"], cursor_vel=frag["vel"],
            cursor_speed=frag["speed"], dist_cursor=d,
            cursor_sudden=frag["sudden"],
            user_idle_s=self.last_percept.user_idle_s)

    def set_user_idle(self, seconds: float):
        self.last_percept.user_idle_s = seconds

    def step(self, dt):
        out = self.brain.update(dt, self.body, self.last_percept)
        self.body.step(dt, drive=out.drive, region=self.region,
                       extra_damping=out.extra_damping, brace=out.brace)
        self.t += dt
        self._last_out = out
        return out

    def snapshot(self):
        """Render-facing state (positions are fixed-step; caller may
        interpolate between successive snapshots)."""
        return {
            "pos": self.body.pos.copy(),
            "radius": self.body.radius.copy(),
            "vel": self.body.vel.copy(),
            "center": self.body.center.copy(),
            "speed": self.body.speed,
            "deform": self.body.deformation(),
            "energy": self.body.kinetic_energy(),
            "state": self.brain.state.name,
            "maneuver": getattr(self, "_last_out", None) and
                        self._last_out.maneuver,
            "waypoint": None if self.brain.waypoint is None else
                        self.brain.waypoint.copy(),
            "edge_hit": self.body.edge_hit,
            "t": self.t,
        }
