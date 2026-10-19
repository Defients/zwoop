"""Behavior and motion reactivity controller with attack/release smoothing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class ReactiveModulation:
    """Bounded, smoothed reactive multipliers for the current frame."""

    intensity_mult: float = 1.0
    length_mult: float = 1.0
    width_mult: float = 1.0
    glow_mult: float = 1.0
    spiral_mult: float = 1.0
    particle_rate_mult: float = 1.0
    burst_factor: float = 0.0
    norm_speed: float = 0.0
    norm_accel: float = 0.0
    norm_curvature: float = 0.0
    state: str = "WANDER"
    maneuver: str = ""


class ReactiveController:
    """Maps Zwoop simulation snapshots to smooth, bounded trail modulations."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self._intensity = 0.85
        self._length = 1.0
        self._width = 1.0
        self._glow = 1.0
        self._spiral = 1.0
        self._p_rate = 1.0
        self._prev_state = "WANDER"
        self._prev_maneuver = ""
        self._prev_speed = 0.0
        self._prev_heading = 0.0
        self._burst_cooldown = 0.0

    @staticmethod
    def _smooth(curr: float, target: float, dt: float, attack_s: float, release_s: float) -> float:
        tau = max(0.015, attack_s if target >= curr else release_s)
        alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
        return curr + (target - curr) * alpha

    def update(
        self,
        dt: float,
        snap: dict[str, Any],
        beh_cfg: dict[str, Any],
        speed_reactivity: float = 0.8,
        reduced_motion: bool = False,
        disable_bursts: bool = False,
    ) -> ReactiveModulation:
        """Compute smoothed reactive modifiers from the latest snapshot."""
        dt = float(np.clip(dt if math.isfinite(dt) else 1 / 60, 0.0, 0.25))
        self._burst_cooldown = max(0.0, self._burst_cooldown - dt)

        state = str(snap.get("state", "WANDER")).upper()
        maneuver_raw = str(snap.get("maneuver") or "").lower()
        maneuver = maneuver_raw.split(":")[0] if maneuver_raw else ""
        is_windup = ":windup" in maneuver_raw

        vel = snap.get("vel")
        if vel is not None and len(vel) > 0:
            vx, vy = float(vel[0][0]), float(vel[0][1])
        else:
            vx = vy = 0.0
        speed = float(snap.get("speed", math.hypot(vx, vy)))
        if not math.isfinite(speed):
            speed = 0.0

        safe_dt = max(dt, 1 / 240.0)
        accel = (speed - self._prev_speed) / safe_dt
        heading = math.atan2(vy, vx) if speed > 2.0 else self._prev_heading
        dtheta = abs((heading - self._prev_heading + math.pi) % (2 * math.pi) - math.pi)
        turn_rate = dtheta / safe_dt if speed > 15.0 else 0.0

        self._prev_speed = speed
        self._prev_heading = heading

        norm_speed = float(np.clip(speed / 550.0, 0.0, 1.6))
        norm_accel = float(np.clip(max(0.0, accel) / 1800.0, 0.0, 1.5))
        norm_curv = float(np.clip(turn_rate / 6.0, 0.0, 1.5))

        if not beh_cfg.get("enabled", True):
            return ReactiveModulation(
                intensity_mult=1.0,
                length_mult=1.0,
                width_mult=1.0,
                glow_mult=1.0,
                spiral_mult=1.0,
                particle_rate_mult=1.0,
                burst_factor=0.0,
                norm_speed=norm_speed,
                norm_accel=norm_accel,
                norm_curvature=norm_curv,
                state=state,
                maneuver=maneuver,
            )

        idle_em = float(beh_cfg.get("idle_emission", 0.35))
        w_int = float(beh_cfg.get("wander_intensity", 0.75))
        c_int = float(beh_cfg.get("curious_intensity", 1.05))
        p_int = float(beh_cfg.get("perform_intensity", 1.40))
        sw_int = float(beh_cfg.get("swoop_intensity", 1.35))
        dv_int = float(beh_cfg.get("dive_intensity", 1.60))
        rec_int = float(beh_cfg.get("recover_intensity", 0.70))
        st_burst = float(beh_cfg.get("startle_burst", 1.50))
        rest_fade = float(beh_cfg.get("resting_fade", 0.10))

        spd_to_len = float(beh_cfg.get("speed_to_length", 0.85)) * float(speed_reactivity)
        acc_to_burst = float(beh_cfg.get("accel_to_burst", 0.70))
        curv_to_spir = float(beh_cfg.get("curvature_to_spiral", 0.60))
        state_to_glow = float(beh_cfg.get("state_to_glow", 0.75))

        # Target state intensity
        if state == "REST":
            t_int = rest_fade
            t_len = 0.45
            t_wid = 0.75
            t_glow = 0.50
            t_prate = rest_fade * 0.5
        elif state == "RECOVER":
            t_int = rec_int
            t_len = 0.75
            t_wid = 0.90
            t_glow = 0.80
            t_prate = rec_int * 0.8
        elif state in ("STARTLE", "EVADE"):
            t_int = min(2.0, max(1.15, st_burst))
            t_len = 1.25
            t_wid = 0.90
            t_glow = 1.35
            t_prate = 1.65
        elif state == "PERFORM":
            if is_windup:
                t_int = 0.85
                t_len = 0.70
                t_wid = 1.15
                t_glow = 1.20
                t_prate = 0.90
            elif maneuver in ("dive", "dart"):
                t_int = dv_int
                t_len = 1.45
                t_wid = 0.78  # sleek high-speed streak
                t_glow = 1.45
                t_prate = 1.65
            elif maneuver in ("swoop", "arc", "figure8", "corkscrew", "orbit"):
                t_int = max(p_int, sw_int)
                t_len = 1.30
                t_wid = 1.12
                t_glow = 1.30
                t_prate = 1.40
            else:
                t_int = p_int
                t_len = 1.20
                t_wid = 1.05
                t_glow = 1.25
                t_prate = 1.30
        elif state == "CURIOUS":
            t_int = c_int
            t_len = 1.05
            t_wid = 1.02
            t_glow = 1.12
            t_prate = 1.15
        else:  # WANDER
            t_int = w_int
            t_len = 0.95
            t_wid = 1.0
            t_glow = 0.95
            t_prate = 0.90

        # Blend with idle emission floor when speed is very low
        move_blend = float(np.clip(speed / 140.0, 0.0, 1.0))
        t_int = idle_em + (t_int - idle_em) * (0.25 + 0.75 * move_blend)

        # Apply continuous motion couplings (additive / bounded, never runaway)
        t_len = float(np.clip(t_len + spd_to_len * (norm_speed - 0.35) * 0.55, 0.30, 1.85))
        t_glow = float(np.clip(1.0 + (t_glow - 1.0) * state_to_glow + 0.25 * norm_speed, 0.35, 1.90))
        t_spiral = float(np.clip(1.0 + curv_to_spir * norm_curv * 0.65, 0.5, 2.0))
        t_prate = float(
            np.clip(t_prate + acc_to_burst * norm_accel * 0.65 + 0.35 * norm_speed, 0.0, 2.2)
        )
        t_int = float(np.clip(t_int, 0.05, 1.85))
        t_wid = float(np.clip(t_wid, 0.55, 1.45))

        if reduced_motion:
            t_spiral = min(t_spiral, 1.0)
            t_prate = min(t_prate, 0.9)

        attack_s = float(beh_cfg.get("attack_time_s", 0.18))
        release_s = float(beh_cfg.get("release_time_s", 0.65))

        self._intensity = self._smooth(self._intensity, t_int, dt, attack_s, release_s)
        self._length = self._smooth(self._length, t_len, dt, attack_s, release_s)
        self._width = self._smooth(self._width, t_wid, dt, attack_s, release_s)
        self._glow = self._smooth(self._glow, t_glow, dt, attack_s, release_s)
        self._spiral = self._smooth(self._spiral, t_spiral, dt, attack_s, release_s)
        self._p_rate = self._smooth(self._p_rate, t_prate, dt, attack_s, release_s)

        # Evaluate transient burst trigger (startle/evade entry, dive launch, or edge bounce)
        burst = 0.0
        if not disable_bursts and not reduced_motion and self._burst_cooldown <= 0.0:
            entered_startle = state in ("STARTLE", "EVADE") and self._prev_state not in ("STARTLE", "EVADE")
            entered_dive = (
                state == "PERFORM"
                and not is_windup
                and maneuver in ("dive", "dart")
                and self._prev_maneuver != maneuver
            )
            accel_spike = norm_accel > 1.15 and speed > 360.0
            edge_bounce = bool(snap.get("edge_hit")) and speed > 280.0

            if entered_startle:
                burst = float(np.clip(st_burst, 0.0, 2.0))
                self._burst_cooldown = 0.45
            elif entered_dive:
                burst = float(np.clip(dv_int * 0.75, 0.0, 1.8))
                self._burst_cooldown = 0.55
            elif accel_spike or edge_bounce:
                burst = float(np.clip(acc_to_burst * 0.85, 0.0, 1.5))
                self._burst_cooldown = 0.50

        self._prev_state = state
        self._prev_maneuver = "" if is_windup else maneuver

        return ReactiveModulation(
            intensity_mult=float(self._intensity),
            length_mult=float(self._length),
            width_mult=float(self._width),
            glow_mult=float(self._glow),
            spiral_mult=float(self._spiral),
            particle_rate_mult=float(self._p_rate),
            burst_factor=burst,
            norm_speed=norm_speed,
            norm_accel=norm_accel,
            norm_curvature=norm_curv,
            state=state,
            maneuver=maneuver,
        )
