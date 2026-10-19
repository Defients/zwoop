"""Numpy metaball rasterizer -> premultiplied BGRA frame.

Field:  F(p) = sum_i  R_i^2 / (|p - p_i|^2 + eps)
Silhouette from a smooth threshold; layered gradients for depth;
velocity/deformation tint; optional fading trail of past centers.

Performance: the entire shading pipeline runs on a quarter-resolution
grid (the metaball kernel's long tail makes bounding boxes useless, and
every feature of the visual — field, glow, plasma — is far smoother
than the 4px sampling).  Only the final premultiplied BGRA conversion
happens at output resolution, where a single tent-filter pass on the
upsampled alpha keeps the silhouette edge soft.  ~10x faster than
full-resolution evaluation.

All writes go straight into the overlay's DIB-backed numpy buffer —
zero-copy presentation.
"""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from .theme import THEMES


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _tent(f):
    """One 3x3 tent-filter pass, in place (interior only)."""
    f[1:-1, 1:-1] = (f[1:-1, 1:-1] * 4 +
                     f[:-2, 1:-1] + f[2:, 1:-1] +
                     f[1:-1, :-2] + f[1:-1, 2:]) * 0.125
    return f


class Rasterizer:
    def __init__(self, size: int, theme="cosmos", effects=2, opacity=0.92,
                 trail=True, res_scale=4):
        self.size = size
        self.effects = effects
        self.opacity = opacity
        self.trail_on = trail

        # internal : output resolution ratio
        self.rs = res_scale if size % res_scale == 0 else 1
        self.isize = size // self.rs

        self.set_theme(theme)

        # internal-res pixel grid (window coords, pixel centers)
        g = np.arange(self.isize, dtype=np.float32) * self.rs + self.rs * 0.5
        self.gy, self.gx = np.meshgrid(g, g, indexing="ij")

        self.field = np.zeros((self.isize, self.isize), np.float32)
        self.obuf = np.zeros((self.isize, self.isize, 4), np.uint8)
        self.trail = deque(maxlen=14)          # (x,y) recent centers

        # flowing interior texture clock
        self.t = 0.0

    def set_theme(self, name):
        th = THEMES.get(name, THEMES["cosmos"])
        self.c_deep = np.array(th["deep"], np.float32)
        self.c_mid = np.array(th["mid"], np.float32)
        self.c_core = np.array(th["core"], np.float32)
        self.c_rim = np.array(th["rim"], np.float32)
        self.c_spark = np.array(th["spark"], np.float32)

    def render(self, frame, snap, window_origin, dt=1 / 60, debug=False):
        """Fill `frame` (H,W,4 uint8 BGRA premul) for this snapshot.

        window_origin: (x,y) desktop coords of frame's top-left.
        """
        ox, oy = window_origin
        rs = self.rs
        self.t += dt
        pos = snap["pos"]
        rad = snap["radius"]
        n = len(pos)
        gx, gy = self.gx, self.gy

        frame.fill(0)

        # ---- metaball field -------------------------------------------
        # Calibrated: eps=800 gives each ball ~0.85 field at its own
        # center; ring surface sums to ~2.4; field falls to ~1.1 around
        # 75px from center -> silhouette ~150px diameter.
        field = self.field
        field.fill(0.0)
        wx = pos[:, 0] - ox
        wy = pos[:, 1] - oy
        # kernel constants were calibrated for a 30px core ball — scale
        # them with the actual body so the silhouette scales too
        self.scale = float(rad[0]) / 30.0 if rad[0] > 0 else 1.0
        eps = 800.0 * self.scale * self.scale
        R = np.where(np.arange(n) == 0, rad * 1.4, rad * 1.2)
        for i in range(n):
            dx = gx - wx[i]
            dy = gy - wy[i]
            field += (R[i] * R[i]) / (dx * dx + dy * dy + eps)

        # ---- trail (only at speed: a fast swoosh, not a wake) ----------
        if (self.trail_on and self.effects >= 2 and snap["speed"] > 280):
            self.trail.append((snap["center"][0], snap["center"][1]))
            k = len(self.trail)
            for j, (tx, ty) in enumerate(self.trail):
                w = (j / max(1, k - 1)) ** 2 * 0.055
                dx = gx - (tx - ox)
                dy = gy - (ty - oy)
                s2 = self.scale * self.scale
                field += w * 2100.0 * s2 / (dx * dx + dy * dy + 400.0 * s2)
        elif len(self.trail) > 3:
            self.trail.popleft()

        _tent(field)     # hide raster steps before thresholding

        # ---- silhouette ------------------------------------------------
        thr = 1.25
        alpha = _smoothstep(thr - 0.42, thr + 0.30, field) \
            * self.opacity * 0.88
        inner = _smoothstep(thr, thr + 1.4, field)       # 0 rim ->1 core

        if self.effects >= 1:
            depth = np.clip(field * 0.33, 0, 1)
            rgb = self.c_deep[None, None] + \
                (self.c_mid - self.c_deep)[None, None] * depth[..., None]
            core_mask = _smoothstep(2.0, 3.4, field)
            rgb += (self.c_core[None, None] - rgb) * core_mask[..., None]
        else:
            rgb = np.broadcast_to(self.c_mid, (*field.shape, 3)).copy()

        if self.effects >= 2:
            # rim light, brighter toward travel direction
            rim = _smoothstep(0.9, 1.25, field) * \
                (1 - _smoothstep(1.25, 1.7, field))
            v = snap["vel"][0]
            vn = math.hypot(v[0], v[1])
            if vn > 1:
                lit = ((gx - (snap["center"][0] - ox)) * (v[0] / vn) +
                       (gy - (snap["center"][1] - oy)) * (v[1] / vn))
                rim *= 0.75 + 0.5 * np.clip(lit / (90.0 * self.scale),
                                            -1, 1)
            rgb += rim[..., None] * self.c_rim[None, None] * 0.85

            # interior flow: world-anchored plasma so it slides under the skin
            pxt = gx + ox
            pyt = gy + oy
            flow = (np.sin(pxt * 0.021 + self.t * 1.1) *
                    np.cos(pyt * 0.017 - self.t * 0.9) +
                    np.sin((pxt + pyt) * 0.013 + self.t * 0.5)) * 0.5 + 0.5
            rgb += (flow[..., None] - 0.5) * self.c_spark[None, None] \
                * 0.28 * inner[..., None]

            # top-light: the body reads as a volume, not a flat disc
            top_l = np.clip(
                (gy - (snap["center"][1] - oy)) / (-130.0 * self.scale),
                -1.0, 1.0) * 0.10
            rgb += top_l[..., None] * inner[..., None] * \
                self.c_rim[None, None]

            # speed tint: hot spark toward violet-white when fast
            heat = min(1.0, snap["speed"] / 850.0) * 0.35 + \
                min(1.0, snap["deform"] * 1.6) * 0.25
            hi = heat * inner
            rgb += (self.c_spark[None, None] - rgb) * hi[..., None]

            # gentle breathing pulse
            rgb *= 1.0 + 0.05 * math.sin(self.t * 2.2)

        # ---- debug overlays --------------------------------------------
        if debug:
            self._debug_overlay(rgb, alpha, snap, ox, oy)

        # ---- to premultiplied BGRA -------------------------------------
        np.clip(rgb, 0.0, 1.0, out=rgb)
        a255 = alpha * 255.0
        out = self.obuf
        out[..., 0] = (rgb[..., 2] * a255).astype(np.uint8)   # B
        out[..., 1] = (rgb[..., 1] * a255).astype(np.uint8)   # G
        out[..., 2] = (rgb[..., 0] * a255).astype(np.uint8)   # R
        out[..., 3] = a255.astype(np.uint8)
        frame[:] = np.repeat(np.repeat(out, rs, 0), rs, 1)

    def _debug_overlay(self, rgb, alpha, snap, ox, oy):
        """Particle dots, core marker, waypoint X."""
        rs = self.rs

        def dot(x, y, color, rr=3):
            x0, y0 = int(x / rs), int(y / rs)
            rr = max(1, rr // rs)
            h, w = alpha.shape
            for dy in range(-rr, rr + 1):
                for dx in range(-rr, rr + 1):
                    if dx * dx + dy * dy > rr * rr:
                        continue
                    xx, yy = x0 + dx, y0 + dy
                    if 0 <= xx < w and 0 <= yy < h:
                        rgb[yy, xx] = color
                        alpha[yy, xx] = 1.0
        for i, p in enumerate(snap["pos"]):
            dot(p[0] - ox, p[1] - oy, (1, 1, 1), 2 if i else 4)
        if snap.get("waypoint") is not None:
            w = snap["waypoint"]
            dot(w[0] - ox, w[1] - oy, (0, 1, 0.3), 4)
