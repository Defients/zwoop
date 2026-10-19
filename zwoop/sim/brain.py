"""Zwoop's behavioral brain.

A lightweight utility-driven state machine. One owner of intent; it outputs
steering accelerations consumed by SoftBody. Deterministic given the rng.

States
    WANDER   — self-directed roaming between waypoints (default)
    CURIOUS  — investigate the cursor: follow at a standoff, lead it, orbit it
    EVADE    — active retreat from a close/fast cursor
    STARTLE  — instant recoil from a sudden nearby cursor move
    PERFORM  — execute a maneuver (swoop/dive/orbit/dart/peek/figure8/...)
    RECOVER  — settle after vigorous motion
    REST     — low-energy hover when the user is long gone

Personality scales every threshold; anti-repetition history keeps the show
varied. Transitions are evaluated on a decision cadence with dwell times,
cooldowns and hysteresis — not every frame.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np

from . import steering as st
from .region import Region


class State(Enum):
    WANDER = auto()
    CURIOUS = auto()
    EVADE = auto()
    STARTLE = auto()
    PERFORM = auto()
    RECOVER = auto()
    REST = auto()


@dataclass
class Params:
    activity: float = 0.6
    curiosity: float = 0.6
    shyness: float = 0.3
    expressiveness: float = 0.7
    preferred_distance: float = 160.0
    interest_radius: float = 460.0
    scare_radius: float = 170.0
    rest_after_idle: float = 240.0
    maneuver_cooldown: float = 6.0
    size_scale: float = 1.0


@dataclass
class Percept:
    """Snapshot of the world for one sim step."""
    cursor_pos: np.ndarray | None = None
    cursor_vel: np.ndarray | None = None
    cursor_speed: float = 0.0
    dist_cursor: float = 1e9
    cursor_sudden: bool = False       # jerk event this step
    user_idle_s: float = 0.0


@dataclass
class Output:
    drive: np.ndarray = field(default_factory=lambda: np.zeros(2))
    brace: float = 0.0
    extra_damping: float = 0.0
    state: State = State.WANDER
    maneuver: str | None = None


class Brain:
    DECISION_DT = 0.12          # s between transition evaluations
    MIN_DWELL = 0.5             # s minimum in a state (except reflexes)

    def __init__(self, region: Region, params: Params,
                 rng: np.random.Generator | None = None):
        self.region = region
        self.p = params
        self.rng = rng or np.random.default_rng()

        self.state = State.WANDER
        self.t_state = 0.0
        self.t_since_decision = 0.0
        self.t_since_maneuver = 999.0
        self.t_since_perform_end = 999.0
        self.attention_left = 0.0
        self.evade_until = 0.0
        self.startle_hold = 0.0
        self.energy_debt = 0.0           # grows with maneuvers -> REST pressure
        self.waypoint = None
        self.wp_deadline = 0.0
        self.orbit_side = 1.0
        self.maneuver: st.Maneuver | None = None
        self.maneuver_t = 0.0
        self.history = deque(maxlen=14)  # recent maneuver names
        self.log: list[tuple[float, str]] = []
        self.t = 0.0
        self._sudden_t = -999.0          # last jerk event time (latched)

    # ================= transitions =====================================
    def _enter(self, s: State, **kw):
        if s != self.state:
            self.log.append((self.t, f"{self.state.name}->{s.name}"))
        self.state = s
        self.t_state = 0.0
        if s == State.CURIOUS:
            self.attention_left = self.rng.uniform(6, 14)
            self.orbit_side = self.rng.choice([-1.0, 1.0])
        if s == State.PERFORM:
            self.maneuver = kw.get("maneuver")
            self.maneuver_t = 0.0

    def _pick_maneuver(self, pos, perc: Percept):
        """Weighted choice with anti-repetition and context gating."""
        host = self.region.host(*pos)
        room_below = host.bottom - pos[1]
        room = min(pos[0] - host.left, host.right - pos[0])

        table = {
            "swoop":     1.0,
            "arc":       1.2,
            "dart":      1.1,
            "orbit":     0.8 if perc.cursor_pos is not None and
                         perc.dist_cursor < self.p.interest_radius else 0.45,
            "peek":      0.9 if perc.cursor_pos is not None and
                         perc.dist_cursor < self.p.interest_radius * 1.3 else 0.15,
            "dive":      0.9 if room_below > 420 else 0.0,
            "figure8":   0.5 if min(room_below, room) > 240 else 0.0,
            "corkscrew": 0.6 if room > 320 else 0.0,
        }
        # anti-repetition: the previous maneuver is banned outright,
        # earlier recents are exponentially suppressed
        for name in list(table):
            recent = sum(1 for h in self.history if h == name)
            table[name] *= 0.28 ** recent
            if self.history and self.history[-1] == name:
                table[name] = 0.0
        names = [k for k, w in table.items() if w > 0]
        if not names:
            return None
        weights = np.array([table[k] for k in names])
        weights /= weights.sum()
        name = self.rng.choice(names, p=weights)

        kw = {"scale": self.p.size_scale}
        if name == "orbit" and perc.cursor_pos is not None and \
                self.rng.random() < 0.7:
            center = perc.cursor_pos.astype(float)
        elif name == "peek" and perc.cursor_pos is not None:
            center = perc.cursor_pos.astype(float)
        else:
            center = pos
        if name == "orbit":
            m0 = st.REGISTRY["orbit"](pos, self.rng, self.region,
                                      scale=self.p.size_scale)
            m = st.Maneuver("orbit", m0.duration, 0.0, m0.cruise,
                            m0.max_accel, self._orbit_fn(center))
        elif name == "peek":
            m = st.REGISTRY["peek"](pos, self.rng, self.region,
                                    scale=self.p.size_scale,
                                    at=perc.cursor_pos)
        else:
            m = st.REGISTRY[name](pos, self.rng, self.region, **kw)
        return m

    def _orbit_fn(self, center):
        rng = self.rng
        r = rng.uniform(110, 170) * self.p.size_scale
        turns = rng.choice([1.0, 1.5])
        phase0 = rng.uniform(0, 2 * math.pi)
        sign = rng.choice([-1, 1])

        def fn(t):
            a = phase0 + sign * 2 * math.pi * turns * t
            rr = r * math.sin(math.pi * min(1.0, t * 1.15))
            return np.asarray(center) + rr * np.array([math.cos(a), math.sin(a)])
        return fn

    def _try_perform(self, pos, perc):
        m = self._pick_maneuver(pos, perc)
        if m is not None:
            self.t_since_maneuver = 0.0
            self.energy_debt += 1.0
            self.history.append(m.name)
            self._enter(State.PERFORM, maneuver=m)
            return True
        return False

    # ================= per-step update =================================
    def update(self, dt, body, perc: Percept) -> Output:
        self.t += dt
        self.t_state += dt
        self.t_since_decision += dt
        self.t_since_maneuver += dt
        self.t_since_perform_end += dt
        self.energy_debt = max(0.0, self.energy_debt - dt * 0.03)
        pos = body.center

        if perc.cursor_sudden:
            self._sudden_t = self.t

        if self.t_since_decision >= self.DECISION_DT:
            self.t_since_decision = 0.0
            self._decide(body, perc)

        return self._steer(dt, body, perc, pos)

    # ---- transitions ---------------------------------------------------
    def _decide(self, body, perc: Percept):
        p = self.p
        pos = body.center
        s = self.state

        # --- reflexes: startle & evade interrupt almost anything --------
        cursor_near = perc.cursor_pos is not None and \
            perc.dist_cursor < p.scare_radius
        cursor_fast = perc.cursor_speed > 900.0
        sudden = (self.t - self._sudden_t < 0.4) and \
            perc.dist_cursor < p.interest_radius

        if s not in (State.STARTLE, State.PERFORM) and sudden and \
                self.rng.random() < 0.45 + p.shyness * 0.4:
            away = pos - perc.cursor_pos
            n = np.linalg.norm(away)
            d = away / n if n > 1 else np.array([0.0, -1.0])
            body.impulse(d * self.rng.uniform(220, 330) * (0.6 + p.shyness))
            self.startle_hold = 0.28
            return self._enter(State.STARTLE)

        if s in (State.WANDER, State.CURIOUS, State.REST, State.RECOVER) and \
                cursor_near and cursor_fast and \
                self.rng.random() < 0.35 + p.shyness * 0.55:
            self.evade_until = self.t + self.rng.uniform(0.7, 1.3)
            return self._enter(State.EVADE)

        if s == State.STARTLE:
            return  # hold time handled in _steer
        if s == State.PERFORM:
            return  # maneuvers run to completion (short)
        if self.t_state < self.MIN_DWELL:
            return

        # --- normal utility transitions ---------------------------------
        if s == State.EVADE:
            if self.t > self.evade_until and \
                    (perc.cursor_pos is None or
                     perc.dist_cursor > p.scare_radius * 1.6):
                self._enter(State.RECOVER if body.speed > 320 else State.WANDER)
            return

        if s == State.RECOVER:
            if body.speed < 240 or self.t_state > 1.6:
                self._enter(State.WANDER)
            return

        if s == State.REST:
            curious_pull = perc.cursor_pos is not None and \
                perc.dist_cursor < p.interest_radius * 0.8 and \
                perc.cursor_speed > 40
            if curious_pull and self.rng.random() < p.curiosity:
                self._enter(State.CURIOUS)
            elif perc.user_idle_s < p.rest_after_idle * 0.5:
                self._enter(State.WANDER)
            elif self.t_state > self.rng.uniform(20, 45):
                self._enter(State.WANDER)
            return

        # curiosity — a moving cursor is magnetic; a still one is still
        # worth an occasional look (that's how the peek happens)
        if perc.cursor_pos is not None and s != State.CURIOUS:
            engaged = perc.dist_cursor < p.interest_radius
            moving = 30 < perc.cursor_speed < 1400
            chance = p.curiosity * (0.5 if moving else 0.05)
            if perc.dist_cursor < p.preferred_distance * 1.5:
                chance += p.curiosity * 0.10       # it got close: interesting
            if engaged and self.rng.random() < chance:
                return self._enter(State.CURIOUS)

        if s == State.CURIOUS:
            gone = perc.cursor_pos is None or \
                perc.dist_cursor > p.interest_radius * 1.4
            if self.t_state > self.attention_left or gone:
                return self._enter(State.WANDER)

        # rest when the user is long idle (and we're not mid-interaction)
        if perc.user_idle_s > p.rest_after_idle and s == State.WANDER and \
                self.energy_debt > 0.4:
            return self._enter(State.REST)
        if perc.user_idle_s > p.rest_after_idle * 1.5 and s == State.WANDER:
            return self._enter(State.REST)

        # spontaneous performance — the heart of "alive when idle".
        # eagerness ramps in over ~9s after the cooldown, so maneuvers are
        # spaced but not metronomic.
        if s in (State.WANDER, State.CURIOUS) and \
                self.t_since_maneuver > p.maneuver_cooldown:
            ramp = min(1.0, (self.t_since_maneuver - p.maneuver_cooldown) / 9.0)
            idle_boost = 1.35 if perc.user_idle_s > 8 else 1.0
            eager = (0.05 + 0.30 * p.expressiveness) * ramp * idle_boost
            if self.rng.random() < eager:
                if self._try_perform(pos, perc):
                    return

        # wandering: pick new waypoint on arrival or when stale
        if s == State.WANDER:
            if self.waypoint is None:
                self._new_waypoint(pos)
            elif np.linalg.norm(self.waypoint - pos) < 90 or \
                    self.t > self.wp_deadline:
                self._new_waypoint(pos)

    def _new_waypoint(self, pos):
        near_r = self.rng.uniform(380, 1100) * (0.7 + self.p.activity)
        self.waypoint = np.array(self.region.random_point(
            self.rng, margin=130, near=pos, radius=near_r))
        self.wp_deadline = self.t + self.rng.uniform(7, 13)

    # ---- steering ------------------------------------------------------
    def _steer(self, dt, body, perc, pos) -> Output:
        out = Output(state=self.state)
        p = self.p
        cruise_base = 90 + 190 * p.activity        # px/s wander cruise
        speed = body.speed

        if self.state == State.STARTLE:
            self.startle_hold -= dt
            out.extra_damping = 6.0
            if self.startle_hold <= 0:
                self._enter(State.EVADE if perc.cursor_pos is not None and
                            perc.dist_cursor < p.scare_radius * 1.8
                            else State.RECOVER)
            return out

        if self.state == State.WANDER:
            if self.waypoint is None:
                self._new_waypoint(pos)
            out.drive = st.arrive(pos, body.vel[0], self.waypoint,
                                  cruise=cruise_base,
                                  slow_radius=220, gain=4.2, max_accel=3200)

        elif self.state == State.CURIOUS and perc.cursor_pos is not None:
            # standoff target: beside/behind cursor, biased by its motion,
            # slowly circling so it looks like inspection
            to_c = pos - perc.cursor_pos
            d = np.linalg.norm(to_c) or 1.0
            side = np.array([-to_c[1], to_c[0]]) / d * self.orbit_side
            self.orbit_side = float(np.clip(
                self.orbit_side + dt * 0.3 * self.rng.choice([-1, 1]),
                -1.0, 1.0))
            lead = perc.cursor_vel * 0.38 if perc.cursor_vel is not None else 0
            target = perc.cursor_pos + lead + \
                to_c / d * p.preferred_distance + side * 55
            eagerness = 1.0 + p.curiosity * 0.9
            out.drive = st.arrive(pos, body.vel[0], target,
                                  cruise=340 * eagerness + perc.cursor_speed * 0.5,
                                  slow_radius=160, gain=5.2, max_accel=5200)
            # overshoot flavor: slight velocity matching with the cursor
            if perc.cursor_vel is not None:
                out.drive += perc.cursor_vel * 2.2

        elif self.state == State.EVADE and perc.cursor_pos is not None:
            away = pos - perc.cursor_pos
            d = np.linalg.norm(away) or 1.0
            perp = np.array([-away[1], away[0]]) / d * self.orbit_side * 0.6
            target = pos + (away / d + perp) * 260
            target = np.array(self.region.project_inside(*target, 90))
            out.drive = st.arrive(pos, body.vel[0], target,
                                  cruise=760, slow_radius=400,
                                  gain=7.0, max_accel=6800)

        elif self.state == State.PERFORM and self.maneuver is not None:
            m = self.maneuver
            t = self.maneuver_t
            self.maneuver_t += dt
            if t < m.windup:
                out.brace = t / m.windup          # compress, lean in
                out.extra_damping = 5.0
                out.maneuver = m.name + ":windup"
            else:
                tau = (t - m.windup) / m.duration
                if tau >= 1.0:
                    self.t_since_perform_end = 0.0
                    self._enter(State.RECOVER)
                    return out
                target = m.target(tau)
                target = np.array(self.region.project_inside(*target, 40))
                out.drive = st.arrive(pos, body.vel[0], target,
                                      cruise=m.cruise, slow_radius=150,
                                      gain=7.5, max_accel=m.max_accel)
                out.maneuver = m.name

        elif self.state == State.RECOVER:
            out.drive = st.arrive(pos, body.vel[0], pos + np.array([0, -30]),
                                  cruise=140, slow_radius=240,
                                  gain=3.2, max_accel=2200)
            out.extra_damping = 2.6

        elif self.state == State.REST:
            if self.waypoint is None or self.t_state < 0.1:
                self.waypoint = pos.copy()
            out.drive = st.arrive(pos, body.vel[0], self.waypoint,
                                  cruise=45, slow_radius=60,
                                  gain=2.4, max_accel=900)
            out.extra_damping = 3.2

        return out
