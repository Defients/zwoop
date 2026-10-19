"""Cursor perception — smoothing, velocity, jerk/sudden-move detection.

Platform code feeds raw samples; this produces the Percept the brain reads.
Pure logic: fully testable without Win32.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from .brain import Percept


class CursorTracker:
    """EMA-smoothed cursor position/velocity with jerk detection."""

    def __init__(self, vel_half_life=0.09, sudden_thresh=2600.0):
        self.pos = None
        self.vel = np.zeros(2)
        self.speed = 0.0
        self.vel_hl = vel_half_life          # s — velocity smoothing
        self.sudden_thresh = sudden_thresh   # px/s^2 of accel -> "sudden"
        self._last_raw = None
        self._last_vel = np.zeros(2)
        self._t = None
        self.history = deque(maxlen=40)

    def update(self, t: float, raw):
        """raw: (x,y) or None. Returns a fresh Percept fragment."""
        if raw is None:
            return None
        raw = np.asarray(raw, dtype=np.float64)
        sudden = False

        if self._t is None:
            self.pos = raw.copy()
            self._t = t
            self._last_raw = raw
        else:
            dt = max(t - self._t, 1e-4)
            inst_v = (raw - self._last_raw) / dt
            a = 1.0 - math.exp(-math.log(2) * dt / self.vel_hl)
            self.vel = self.vel * (1 - a) + inst_v * a
            accel = np.linalg.norm(self.vel - self._last_vel) / dt
            if accel > self.sudden_thresh and np.linalg.norm(inst_v) > 400:
                sudden = True
            self._last_vel = self.vel.copy()
            self.pos = raw
            self._t = t
            self._last_raw = raw
            self.speed = float(np.linalg.norm(self.vel))
            self.history.append((t, raw[0], raw[1]))

        return {"pos": self.pos, "vel": self.vel, "speed": self.speed,
                "sudden": sudden}
