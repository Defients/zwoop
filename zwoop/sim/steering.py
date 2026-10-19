"""Steering forces + the maneuver vocabulary.

Every expressive move (swoop, dive, orbit, dart, peek, figure-eight,
corkscrew, recoil) is a *target trajectory* played through arrive-style
steering — the body is always moved by forces, never teleported.

A maneuver has three phases:
    windup   — creature compresses (brace) and leans in
    flight   — target follows a parametric path
    (done)   — brain hands control to RECOVERING
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def _v(x, y):
    return np.array([float(x), float(y)])


def clamp_norm(v, m):
    n = np.linalg.norm(v)
    return v * (m / n) if n > m > 0 else v


def arrive(pos, vel, target, cruise, slow_radius=140.0, gain=7.0,
           max_accel=5200.0):
    """Desired-velocity steering with arrival slowdown. Returns accel (px/s^2)."""
    d = np.asarray(target) - pos
    dist = np.linalg.norm(d)
    if dist < 1e-3:
        return -vel * gain * 0.4
    desired = d / dist * cruise * min(1.0, dist / slow_radius)
    return clamp_norm((desired - vel) * gain, max_accel)


def bezier(p0, p1, p2, t):
    u = 1 - t
    return u * u * p0 + 2 * u * t * p1 + t * t * p2


@dataclass
class Maneuver:
    name: str
    duration: float              # flight seconds
    windup: float = 0.22         # compress/lean seconds before flight
    cruise: float = 700.0        # desired speed during flight
    max_accel: float = 5600.0
    _fn: object = field(repr=False, default=None)   # tau->(x,y)

    def target(self, tau):
        return self._fn(min(max(tau, 0.0), 1.0))


def _rand_dir(rng, upward_bias=0.0):
    a = rng.uniform(-math.pi, math.pi)
    return _v(math.cos(a), math.sin(a) - upward_bias)


# --- factories ---------------------------------------------------------
# Each takes (start: np.ndarray, rng, region, scale) and returns Maneuver.

def make_swoop(start, rng, region, scale=1.0):
    """Long curved burst — the signature move."""
    span = rng.uniform(340, 620) * scale
    d = _rand_dir(rng, upward_bias=0.25)
    end = start + d * span
    end = np.array(region.project_inside(end[0], end[1], 80.0))
    perp = _v(-d[1], d[0]) * rng.choice([-1, 1]) * span * rng.uniform(0.25, 0.4)
    ctrl = (start + end) / 2 + perp
    return Maneuver("swoop", duration=rng.uniform(0.9, 1.3), windup=0.26,
                    cruise=900, max_accel=6400,
                    _fn=lambda t: bezier(start, ctrl, end, t))


def make_dive(start, rng, region, scale=1.0):
    """Accelerate downward fast, pull out above the floor."""
    host = region.host(*start)
    depth = rng.uniform(0.55, 0.8) * (host.bottom - start[1])
    depth = max(depth, 180.0)
    end = _v(start[0] + rng.uniform(-140, 140) * scale,
             min(start[1] + depth, host.bottom - 130))
    ctrl = _v(start[0] + rng.uniform(-60, 60), start[1] + depth * 1.15)
    return Maneuver("dive", duration=rng.uniform(0.7, 1.0), windup=0.2,
                    cruise=1050, max_accel=7000,
                    _fn=lambda t: bezier(start, ctrl, end, t))


def make_arc(start, rng, region, scale=1.0):
    """Gentle lateral arc — casual travel with style."""
    span = rng.uniform(260, 420) * scale
    d = _rand_dir(rng, upward_bias=0.1)
    end = np.array(region.project_inside(*(start + d * span), 80.0))
    ctrl = (start + end) / 2 + _v(-d[1], d[0]) * rng.choice([-1, 1]) * span * 0.18
    return Maneuver("arc", duration=rng.uniform(0.9, 1.4), windup=0.16,
                    cruise=560, max_accel=4200,
                    _fn=lambda t: bezier(start, ctrl, end, t))


def make_dart(start, rng, region, scale=1.0):
    """Short, sharp displacement — sudden 'notice something' hop."""
    span = rng.uniform(150, 260) * scale
    d = _rand_dir(rng)
    end = np.array(region.project_inside(*(start + d * span), 70.0))
    return Maneuver("dart", duration=rng.uniform(0.32, 0.45), windup=0.14,
                    cruise=1150, max_accel=8200,
                    _fn=lambda t: bezier(start, (start + end) / 2, end, t))


def make_orbit(start, rng, region, scale=1.0):
    """Circle a point — around the cursor or an imagined attractor."""
    center = np.asarray(start, dtype=float).copy()
    r = rng.uniform(110, 170) * scale
    turns = rng.choice([1.0, 1.0, 1.5])
    phase0 = rng.uniform(0, 2 * math.pi)
    sign = rng.choice([-1, 1])
    dur = turns * rng.uniform(1.0, 1.35)

    def fn(t):
        a = phase0 + sign * 2 * math.pi * turns * t
        # ease radius in then out so entry/exit aren't abrupt
        rr = r * math.sin(math.pi * min(1.0, t * 1.15))
        return center + rr * _v(math.cos(a), math.sin(a))

    return Maneuver("orbit", duration=dur, windup=0.0,
                    cruise=760, max_accel=5600, _fn=fn)


def make_peek(start, rng, region, scale=1.0, at=None):
    """Cautiously approach a point, hold a beat, withdraw."""
    target = np.asarray(at) if at is not None else np.asarray(start)
    s = np.asarray(start, dtype=float)
    d = target - s
    dist = np.linalg.norm(d)
    if dist < 1:
        d = _rand_dir(rng)
        dist = 1.0
    approach = s + d / dist * min(dist, dist * rng.uniform(0.55, 0.7))
    back = s + _rand_dir(rng) * rng.uniform(30, 60)

    def fn(t):
        if t < 0.45:                      # slow approach
            return s + (approach - s) * (t / 0.45)
        if t < 0.7:                       # hold — the peek itself
            return approach + _v(0, -6) * math.sin((t - 0.45) / 0.25 * math.pi)
        return approach + (back - approach) * ((t - 0.7) / 0.3)

    return Maneuver("peek", duration=rng.uniform(1.6, 2.2), windup=0.3,
                    cruise=330, max_accel=2600, _fn=fn)


def make_figure8(start, rng, region, scale=1.0):
    """Full aerial figure-eight — the show-off move."""
    c = np.asarray(start, dtype=float)
    w = rng.uniform(140, 200) * scale
    h = w * rng.uniform(0.5, 0.65)
    rot = rng.uniform(0, math.pi)
    ca, sa = math.cos(rot), math.sin(rot)

    def fn(t):
        a = 2 * math.pi * t
        x, y = w * math.sin(a), h * math.sin(2 * a)
        return c + _v(x * ca - y * sa, x * sa + y * ca)

    return Maneuver("figure8", duration=rng.uniform(2.0, 2.6), windup=0.28,
                    cruise=820, max_accel=5600, _fn=fn)


def make_corkscrew(start, rng, region, scale=1.0):
    """Barrel-roll forward — fast linear travel with a twist."""
    span = rng.uniform(360, 560) * scale
    d = _rand_dir(rng, upward_bias=0.15)
    end = np.array(region.project_inside(*(start + d * span), 80.0))
    perp = _v(-d[1], d[0])
    amp = rng.uniform(45, 80)
    waves = rng.uniform(2.5, 3.5)

    def fn(t):
        base = start + (end - start) * t
        return base + perp * amp * math.sin(waves * 2 * math.pi * t) * \
            math.sin(math.pi * t)

    return Maneuver("corkscrew", duration=rng.uniform(0.9, 1.3), windup=0.2,
                    cruise=900, max_accel=6200, _fn=fn)


def make_recoil(start, rng, region, scale=1.0, away_from=None):
    """Startled hop away from a stimulus point."""
    s = np.asarray(start, dtype=float)
    src = np.asarray(away_from) if away_from is not None else s
    d = s - src
    if np.linalg.norm(d) < 1:
        d = _rand_dir(rng)
    else:
        d = d / np.linalg.norm(d)
    # add perpendicular jitter so it isn't a straight retreat
    d = d + _rand_dir(rng) * 0.5
    d = d / np.linalg.norm(d)
    end = np.array(region.project_inside(*(s + d * rng.uniform(160, 240)), 70.0))
    return Maneuver("recoil", duration=0.4, windup=0.05,
                    cruise=980, max_accel=7600,
                    _fn=lambda t: bezier(s, (s + end) / 2, end, t))


REGISTRY = {
    "swoop": make_swoop, "dive": make_dive, "arc": make_arc,
    "dart": make_dart, "orbit": make_orbit, "peek": make_peek,
    "figure8": make_figure8, "corkscrew": make_corkscrew,
    "recoil": make_recoil,
}
