"""Monitor-union region: where Zwoop may exist.

Models the usable desktop as a union of monitor rectangles in virtual
coordinates (may include negative coords). Provides:
  - containment checks
  - soft repulsion from edges that border the void
  - hard projection back into the nearest valid position
  - waypoint sampling inside the region

Replaces the legacy "combined bounding rect" which let the creature drift
into dead space between monitors and past the overlay window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self): return self.right - self.left
    @property
    def height(self): return self.bottom - self.top
    @property
    def cx(self): return (self.left + self.right) / 2
    @property
    def cy(self): return (self.top + self.bottom) / 2

    def contains(self, x, y, margin=0.0):
        return (self.left + margin <= x < self.right - margin and
                self.top + margin <= y < self.bottom - margin)

    def clamp(self, x, y, margin=0.0):
        return (min(max(x, self.left + margin), self.right - margin),
                min(max(y, self.top + margin), self.bottom - margin))


class Region:
    """Union of Rects representing all displays (or one selected display)."""

    def __init__(self, rects: list[Rect] | None = None):
        self.rects: list[Rect] = rects or [Rect(0, 0, 1920, 1080)]

    # ---- containment -------------------------------------------------
    def contains(self, x, y, margin=0.0):
        return any(r.contains(x, y, margin) for r in self.rects)

    def host(self, x, y) -> Rect:
        """Rect containing the point; nearest rect by distance if outside."""
        for r in self.rects:
            if r.contains(x, y):
                return r
        return min(self.rects, key=lambda r: self._dist_to_rect(r, x, y))

    @staticmethod
    def _dist_to_rect(r: Rect, x, y):
        cx = min(max(x, r.left), r.right)
        cy = min(max(y, r.top), r.bottom)
        return math.hypot(x - cx, y - cy)

    # ---- edge semantics ----------------------------------------------
    def _beyond_is_void(self, x, y):
        """Is a probe point (already outside its host) covered by ANY
        monitor?  If not, the edge it crossed borders empty space."""
        return not self.contains(x, y)

    def soft_edge_force(self, x, y, radius, margin, strength):
        """Repulsive (fx,fy) near edges that border empty space.

        Edges shared with an adjacent monitor produce no force, so the
        creature can cross seamlessly between displays.
        """
        fx = fy = 0.0
        host = self.host(x, y)
        m = margin + radius
        probe = 24.0
        # (edge distance, outward normal) for each side of the host rect
        edges = ((x - host.left, -1.0, 0.0), (host.right - x, 1.0, 0.0),
                 (y - host.top, 0.0, -1.0), (host.bottom - y, 0.0, 1.0))
        for d, nx, ny in edges:
            if d < m and self._beyond_is_void(
                    x + nx * (d + probe), y + ny * (d + probe)):
                push = (m - max(d, 0.0)) / m  # 0..1
                f = strength * push * push
                fx += -nx * f
                fy += -ny * f
        return fx, fy

    def project_inside(self, x, y, radius=0.0):
        """Nearest valid point accounting for body radius."""
        if self.contains(x, y, radius):
            return x, y
        best = min(self.rects, key=lambda r: self._dist_to_rect(r, x, y))
        return best.clamp(x, y, radius)

    # ---- waypoints ---------------------------------------------------
    def random_point(self, rng, margin=120.0, near=None, radius=None):
        """Uniform-ish random valid point; optionally within `radius` of `near`."""
        host = self.host(*near) if near is not None else None
        r = host or self.rects[rng.integers(len(self.rects))]
        for _ in range(24):
            x = rng.uniform(r.left + margin, r.right - margin)
            y = rng.uniform(r.top + margin, r.bottom - margin)
            if near is not None and radius:
                if math.hypot(x - near[0], y - near[1]) > radius:
                    continue
            if self.contains(x, y, margin * 0.5):
                return x, y
        return r.cx, r.cy
