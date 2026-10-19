"""World-space trail history, discontinuity detection, and spline resampling."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class TrailSample:
    """Single immutable-style world-space trajectory sample."""

    sample_id: int
    stroke_id: int
    t: float
    x: float
    y: float
    vx: float
    vy: float
    speed: float
    heading: float
    curvature: float
    accel: float
    state: str
    maneuver: str
    deform: float
    energy: float
    body_rel: np.ndarray | None = None  # (N, 2) particle offsets from center for Echo
    body_rad: np.ndarray | None = None  # (N,) particle radii


class TrailHistory:
    """Bounded, FPS-independent world-space trajectory recorder."""

    def __init__(
        self,
        max_samples: int = 320,
        min_spacing_px: float = 5.0,
        max_step_px: float = 28.0,
        break_distance_px: float = 280.0,
        break_dt_s: float = 0.45,
    ):
        self.max_samples = max(16, int(max_samples))
        self.min_spacing_px = float(min_spacing_px)
        self.max_step_px = float(max_step_px)
        self.break_distance_px = float(break_distance_px)
        self.break_dt_s = float(break_dt_s)

        self.samples: deque[TrailSample] = deque(maxlen=self.max_samples)
        self._next_sample_id: int = 1
        self._stroke_id: int = 1
        self._pending_break: bool = False
        self._last_echo_t: float = -999.0

    def notify_break(self) -> None:
        """Mark a discontinuity so the next sample starts a fresh stroke."""
        self._pending_break = True
        self._stroke_id += 1

    def clear(self) -> None:
        """Remove all stored samples immediately."""
        self.samples.clear()
        self._pending_break = False
        self._stroke_id += 1
        self._last_echo_t = -999.0

    def prune(self, now_t: float, max_lifetime_s: float) -> None:
        """Expire samples older than `max_lifetime_s`."""
        cutoff = now_t - max(0.05, float(max_lifetime_s))
        while self.samples and self.samples[0].t < cutoff:
            self.samples.popleft()

    def record(
        self,
        snap: dict[str, Any],
        now_t: float | None = None,
        max_lifetime_s: float = 4.5,
    ) -> list[TrailSample]:
        """Record a simulation snapshot into world-space history.

        Returns the list of newly appended samples (0, 1, or interpolated >1).
        """
        c = snap.get("center")
        if c is None:
            return []
        cx, cy = float(c[0]), float(c[1])
        if not (math.isfinite(cx) and math.isfinite(cy)):
            self.notify_break()
            return []

        t = float(snap.get("t", 0.0) if now_t is None else now_t)
        vel_arr = snap.get("vel")
        if vel_arr is not None and len(vel_arr) > 0:
            vx, vy = float(vel_arr[0][0]), float(vel_arr[0][1])
        else:
            vx = vy = 0.0
        if not (math.isfinite(vx) and math.isfinite(vy)):
            vx = vy = 0.0

        speed = float(snap.get("speed", math.hypot(vx, vy)))
        if not math.isfinite(speed):
            speed = 0.0
        state = str(snap.get("state", "WANDER"))
        maneuver = str(snap.get("maneuver") or "")
        deform = float(snap.get("deform", 0.0))
        energy = float(snap.get("energy", 0.0))

        self.prune(t, max_lifetime_s)

        # Capture compact relative particle silhouette periodically for Echo family
        body_rel = None
        body_rad = None
        if t - self._last_echo_t >= 0.035 and "pos" in snap and "radius" in snap:
            pos = np.asarray(snap["pos"], dtype=np.float32)
            if pos.ndim == 2 and pos.shape[1] == 2 and np.isfinite(pos).all():
                body_rel = pos - np.array([cx, cy], dtype=np.float32)
                body_rad = np.asarray(snap["radius"], dtype=np.float32).copy()
                self._last_echo_t = t

        if not self.samples:
            heading = math.atan2(vy, vx) if speed > 1.0 else 0.0
            s = TrailSample(
                sample_id=self._next_sample_id,
                stroke_id=self._stroke_id,
                t=t,
                x=cx,
                y=cy,
                vx=vx,
                vy=vy,
                speed=speed,
                heading=heading,
                curvature=0.0,
                accel=0.0,
                state=state,
                maneuver=maneuver,
                deform=deform,
                energy=energy,
                body_rel=body_rel,
                body_rad=body_rad,
            )
            self._next_sample_id += 1
            self.samples.append(s)
            self._pending_break = False
            return [s]

        prev = self.samples[-1]
        dt = t - prev.t
        dx = cx - prev.x
        dy = cy - prev.y
        dist = math.hypot(dx, dy)

        # Check discontinuity conditions: time stall, time reversal, or teleport
        if (
            self._pending_break
            or dt < -1e-5
            or dt > self.break_dt_s
            or dist > self.break_distance_px
        ):
            self._stroke_id += 1
            self._pending_break = False
            heading = math.atan2(vy, vx) if speed > 1.0 else prev.heading
            s = TrailSample(
                sample_id=self._next_sample_id,
                stroke_id=self._stroke_id,
                t=t,
                x=cx,
                y=cy,
                vx=vx,
                vy=vy,
                speed=speed,
                heading=heading,
                curvature=0.0,
                accel=0.0,
                state=state,
                maneuver=maneuver,
                deform=deform,
                energy=energy,
                body_rel=body_rel,
                body_rad=body_rad,
            )
            self._next_sample_id += 1
            self.samples.append(s)
            return [s]

        # Stationary suppression: if barely moved since the last recorded sample
        # and little time has passed, wait until movement accumulates >= min_spacing_px
        if dist < self.min_spacing_px and (dist < 0.75 or dt < 0.08):
            return []

        safe_dt = max(dt, 1e-4)
        heading = math.atan2(dy, dx) if dist > 0.5 else (
            math.atan2(vy, vx) if speed > 1.0 else prev.heading
        )
        # Signed angular difference in [-pi, pi]
        dtheta = (heading - prev.heading + math.pi) % (2 * math.pi) - math.pi
        curvature = float(np.clip(abs(dtheta) / max(dist, 4.0), 0.0, 0.25))
        accel = float(np.clip((speed - prev.speed) / safe_dt, -4000.0, 4000.0))

        # High-speed subdivision: prevent undersampling at low FPS + high speed
        n_sub = max(1, min(8, int(math.ceil(dist / max(8.0, self.max_step_px)))))
        added: list[TrailSample] = []

        # Hermite / cubic velocity-aware interpolation when subdividing
        for k in range(1, n_sub + 1):
            alpha = k / n_sub
            if n_sub > 1 and dt > 1e-3:
                # Cubic Hermite between prev and current using velocities
                h00 = 2 * alpha ** 3 - 3 * alpha ** 2 + 1
                h10 = alpha ** 3 - 2 * alpha ** 2 + alpha
                h01 = -2 * alpha ** 3 + 3 * alpha ** 2
                h11 = alpha ** 3 - alpha ** 2
                ix = h00 * prev.x + h10 * (prev.vx * dt) + h01 * cx + h11 * (vx * dt)
                iy = h00 * prev.y + h10 * (prev.vy * dt) + h01 * cy + h11 * (vy * dt)
            else:
                ix = prev.x + (cx - prev.x) * alpha
                iy = prev.y + (cy - prev.y) * alpha

            it = prev.t + dt * alpha
            ivx = prev.vx + (vx - prev.vx) * alpha
            ivy = prev.vy + (vy - prev.vy) * alpha
            ispd = prev.speed + (speed - prev.speed) * alpha
            ihdg = prev.heading + dtheta * alpha

            s = TrailSample(
                sample_id=self._next_sample_id,
                stroke_id=self._stroke_id,
                t=it,
                x=float(ix),
                y=float(iy),
                vx=float(ivx),
                vy=float(ivy),
                speed=float(ispd),
                heading=float(ihdg),
                curvature=curvature,
                accel=accel,
                state=state,
                maneuver=maneuver,
                deform=deform,
                energy=energy,
                body_rel=body_rel if k == n_sub else None,
                body_rad=body_rad if k == n_sub else None,
            )
            self._next_sample_id += 1
            self.samples.append(s)
            added.append(s)

        return added

    def get_strokes(
        self,
        now_t: float,
        lifetime_s: float,
        spawn_delay_s: float = 0.0,
        length_cap_px: float = 1200.0,
    ) -> list[list[TrailSample]]:
        """Return contiguous strokes (newest-to-oldest trimmed by lifetime & length cap)."""
        if not self.samples:
            return []
        min_t = now_t - max(0.05, float(lifetime_s))
        max_t = now_t - max(0.0, float(spawn_delay_s))

        # Walk from newest to oldest so length_cap_px trims the oldest tail
        valid: list[TrailSample] = []
        acc_len = 0.0
        last_pt: tuple[float, float] | None = None
        last_stroke: int | None = None

        for s in reversed(self.samples):
            if s.t > max_t:
                continue
            if s.t < min_t:
                break
            if last_pt is not None and s.stroke_id == last_stroke:
                seg = math.hypot(s.x - last_pt[0], s.y - last_pt[1])
                if acc_len + seg > length_cap_px:
                    break
                acc_len += seg
            last_pt = (s.x, s.y)
            last_stroke = s.stroke_id
            valid.append(s)

        if not valid:
            return []
        valid.reverse()  # chronological order (oldest -> newest)

        strokes: list[list[TrailSample]] = []
        cur: list[TrailSample] = []
        cur_id: int | None = None
        for s in valid:
            if cur_id is None or s.stroke_id != cur_id:
                if cur:
                    strokes.append(cur)
                cur = [s]
                cur_id = s.stroke_id
            else:
                cur.append(s)
        if cur:
            strokes.append(cur)
        return strokes


def resample_stroke(
    stroke: list[TrailSample],
    now_t: float,
    lifetime_s: float,
    max_points: int = 96,
    smoothing: float = 0.5,
    tension: float = 0.5,
    drift_x: float = 0.0,
    drift_y: float = 0.0,
    curl_noise: float = 0.0,
) -> dict[str, np.ndarray] | None:
    """Convert a list of TrailSample (oldest -> newest) into vectorized arrays.

    Returns dict with keys:
      'pos': (M, 2) float32 world coords (oldest -> newest; index -1 is head)
      'tang': (M, 2) float32 unit tangents
      'norm': (M, 2) float32 unit normals
      'age_s': (M,) float32 age in seconds
      'u_age': (M,) float32 normalized age in [0, 1] (0=head, 1=tail)
      'u_arc': (M,) float32 normalized arc position in [0, 1] (0=head, 1=tail)
      'speed': (M,) float32
      'curvature': (M,) float32
      'accel': (M,) float32
      'deform': (M,) float32
      'total_len': float
    """
    n = len(stroke)
    if n == 0:
        return None

    raw_x = np.array([s.x for s in stroke], dtype=np.float32)
    raw_y = np.array([s.y for s in stroke], dtype=np.float32)
    raw_t = np.array([s.t for s in stroke], dtype=np.float32)
    raw_spd = np.array([s.speed for s in stroke], dtype=np.float32)
    raw_curv = np.array([s.curvature for s in stroke], dtype=np.float32)
    raw_acc = np.array([s.accel for s in stroke], dtype=np.float32)
    raw_def = np.array([s.deform for s in stroke], dtype=np.float32)

    age_raw = np.maximum(0.0, float(now_t) - raw_t)

    # Apply age-based wind drift and coherent world-space curl displacement
    if drift_x != 0.0 or drift_y != 0.0:
        raw_x = raw_x + age_raw * float(drift_x)
        raw_y = raw_y + age_raw * float(drift_y)
    if curl_noise > 0.05:
        amp = float(curl_noise) * np.minimum(1.5, age_raw * 0.85)
        raw_x = raw_x + amp * np.sin(raw_y * 0.018 + float(now_t) * 1.7)
        raw_y = raw_y + amp * np.cos(raw_x * 0.018 - float(now_t) * 1.4)

    if n == 1:
        pos = np.column_stack([raw_x, raw_y])
        hdg = stroke[0].heading
        tang = np.array([[math.cos(hdg), math.sin(hdg)]], dtype=np.float32)
        norm = np.array([[-tang[0, 1], tang[0, 0]]], dtype=np.float32)
        u_age = np.clip(age_raw / max(0.05, float(lifetime_s)), 0.0, 1.0)
        return {
            "pos": pos,
            "tang": tang,
            "norm": norm,
            "age_s": age_raw,
            "u_age": u_age,
            "u_arc": np.zeros(1, dtype=np.float32),
            "speed": raw_spd,
            "curvature": raw_curv,
            "accel": raw_acc,
            "deform": raw_def,
            "total_len": 0.0,
        }

    # Compute cumulative arc length
    dx = np.diff(raw_x)
    dy = np.diff(raw_y)
    seg_len = np.hypot(dx, dy)
    cum = np.concatenate([[0.0], np.cumsum(seg_len)]).astype(np.float32)
    total_len = float(cum[-1])

    if total_len < 1.0:
        pos = np.column_stack([raw_x[-1:], raw_y[-1:]])
        hdg = stroke[-1].heading
        tang = np.array([[math.cos(hdg), math.sin(hdg)]], dtype=np.float32)
        norm = np.array([[-tang[0, 1], tang[0, 0]]], dtype=np.float32)
        u_age = np.clip(age_raw[-1:] / max(0.05, float(lifetime_s)), 0.0, 1.0)
        return {
            "pos": pos,
            "tang": tang,
            "norm": norm,
            "age_s": age_raw[-1:],
            "u_age": u_age,
            "u_arc": np.zeros(1, dtype=np.float32),
            "speed": raw_spd[-1:],
            "curvature": raw_curv[-1:],
            "accel": raw_acc[-1:],
            "deform": raw_def[-1:],
            "total_len": total_len,
        }

    # Remove near-duplicate arc steps before interpolation
    keep = np.concatenate([[True], seg_len > 0.25])
    if keep.sum() < 2:
        keep[0] = True
        keep[-1] = True
    cum = cum[keep]
    raw_x = raw_x[keep]
    raw_y = raw_y[keep]
    age_raw = age_raw[keep]
    raw_spd = raw_spd[keep]
    raw_curv = raw_curv[keep]
    raw_acc = raw_acc[keep]
    raw_def = raw_def[keep]

    m = int(np.clip(int(total_len / 16.0) + 4, 4, max(6, int(max_points))))
    s_grid = np.linspace(0.0, total_len, m, dtype=np.float32)

    px = np.interp(s_grid, cum, raw_x).astype(np.float32)
    py = np.interp(s_grid, cum, raw_y).astype(np.float32)

    # Optional corner-relaxation smoothing pass (weighted by `smoothing` & `tension`)
    passes = int(round(float(smoothing) * 3 * (1.0 - 0.4 * float(tension))))
    for _ in range(passes):
        if len(px) >= 4:
            px[1:-1] = 0.25 * px[:-2] + 0.5 * px[1:-1] + 0.25 * px[2:]
            py[1:-1] = 0.25 * py[:-2] + 0.5 * py[1:-1] + 0.25 * py[2:]

    pos = np.column_stack([px, py])
    age_s = np.interp(s_grid, cum, age_raw).astype(np.float32)
    spd = np.interp(s_grid, cum, raw_spd).astype(np.float32)
    curv = np.interp(s_grid, cum, raw_curv).astype(np.float32)
    acc = np.interp(s_grid, cum, raw_acc).astype(np.float32)
    deform = np.interp(s_grid, cum, raw_def).astype(np.float32)

    # Compute smooth tangents and normals
    tx = np.gradient(px)
    ty = np.gradient(py)
    tnorm = np.maximum(np.hypot(tx, ty), 1e-5)
    tx /= tnorm
    ty /= tnorm
    tang = np.column_stack([tx, ty]).astype(np.float32)
    norm = np.column_stack([-ty, tx]).astype(np.float32)

    u_age = np.clip(age_s / max(0.05, float(lifetime_s)), 0.0, 1.0)
    # u_arc: 0.0 at newest head (end of array), 1.0 at oldest tail (start of array)
    u_arc = 1.0 - (s_grid / max(total_len, 1e-5))

    return {
        "pos": pos,
        "tang": tang,
        "norm": norm,
        "age_s": age_s,
        "u_age": u_age,
        "u_arc": u_arc,
        "speed": spd,
        "curvature": curv,
        "accel": acc,
        "deform": deform,
        "total_len": total_len,
    }
