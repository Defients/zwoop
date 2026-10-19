"""Zwoop soft body — particle/spring model in real units (px, seconds).

Topology preserved from the legacy creature: one heavy core + a ring of
lighter outer particles, joined by radial spokes, ring chords and a few
cross springs. Forces are px/s^2 * mass; velocities px/s. Damping uses
exp(-c*dt) so it is frame-rate independent (fixes legacy bug §4.3).

Deterministic: all randomness flows through an injected
numpy.random.Generator, so seeded replays reproduce exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .region import Region


@dataclass
class BodyParams:
    n_outer: int = 12            # ring particles (total = n_outer + 1)
    core_mass: float = 2.4
    outer_mass: float = 1.0
    core_radius: float = 30.0    # px — render/collision radius of core
    ring_radius: float = 52.0    # px — rest distance core->outer
    outer_radius: float = 22.0   # px — render radius of outer particle
    k_radial: float = 340.0      # spring stiffness (px/s^2 per px of stretch)
    k_ring: float = 210.0
    k_cross: float = 90.0
    c_spring: float = 16.0       # axial damping (px/s^2 per px/s)
    cohesion: float = 60.0       # weak pull of outers toward core (px/s^2)
    drag: float = 0.9            # linear drag coefficient (1/s)
    buoyancy: float = 26.0       # px/s^2 upward bias — ethereal float
    wobble: float = 8.0          # idle micro-jiggle amplitude (px/s^2)
    edge_restitution: float = 0.55
    edge_friction: float = 0.82  # tangential velocity retained on bounce
    max_speed: float = 1100.0    # px/s hard clamp
    max_stretch: float = 2.1     # max (dist to core)/ring_radius before clamp


class SoftBody:
    """One creature. Deterministic given the injected rng."""

    def __init__(self, params: BodyParams | None = None,
                 center=(960.0, 540.0), rng: np.random.Generator | None = None):
        self.p = params or BodyParams()
        self.rng = rng or np.random.default_rng()
        n = self.p.n_outer + 1
        self.n = n

        self.pos = np.zeros((n, 2), dtype=np.float64)
        self.vel = np.zeros((n, 2), dtype=np.float64)
        self.force = np.zeros((n, 2), dtype=np.float64)
        self.mass = np.full(n, self.p.outer_mass)
        self.mass[0] = self.p.core_mass
        self.radius = np.full(n, self.p.outer_radius)
        self.radius[0] = self.p.core_radius
        self.phase = self.rng.uniform(0, 2 * math.pi, n)   # idle jiggle phase

        # Lay out ring with slight organic variance
        self.pos[0] = center
        for i in range(1, n):
            a = (i - 1) * 2 * math.pi / self.p.n_outer
            r = self.p.ring_radius * self.rng.uniform(0.94, 1.06)
            self.pos[i] = center + r * np.array(
                [math.cos(a), math.sin(a)]) + self.rng.uniform(-4, 4, 2)

        # Springs: (i, j, rest, k, c)
        sp = []
        chord = 2 * self.p.ring_radius * math.sin(math.pi / self.p.n_outer)
        for i in range(1, n):
            sp.append((0, i, self.p.ring_radius, self.p.k_radial, self.p.c_spring))
            nxt = 1 + (i % self.p.n_outer)
            sp.append((i, nxt, chord, self.p.k_ring, self.p.c_spring))
            opp = i + self.p.n_outer // 2
            if opp < n:
                sp.append((i, opp, 2 * self.p.ring_radius,
                           self.p.k_cross, self.p.c_spring))
        self.springs = np.array(
            [(i, j, r, k, c) for i, j, r, k, c in sp], dtype=np.float64)

        self.noise_t = 0.0
        self.edge_hit = None       # set after step: "left"|"right"|"top"|"bottom"
        self._spawn_center = np.array(center, dtype=np.float64)

    # ---- queries ------------------------------------------------------
    @property
    def center(self):
        """Visual center: mean of all particles (smoother than raw core)."""
        return self.pos.mean(axis=0)

    @property
    def core(self):
        return self.pos[0]

    @property
    def core_vel(self):
        return self.vel[0]

    @property
    def speed(self):
        return float(np.linalg.norm(self.vel[0]))

    def deformation(self):
        """0 = perfect ring; grows as the body squashes/stretches."""
        d = np.linalg.norm(self.pos[1:] - self.pos[0], axis=1)
        return float(np.abs(d - self.p.ring_radius).mean() / self.p.ring_radius)

    def kinetic_energy(self):
        return float(0.5 * np.sum(self.mass * np.sum(self.vel ** 2, axis=1)))

    # ---- stepping -----------------------------------------------------
    def step(self, dt: float, drive: np.ndarray | None = None,
             region: Region | None = None, edge_margin=90.0,
             edge_strength=2600.0, extra_damping=0.0, brace=0.0):
        """Advance one fixed step.

        drive: (2,) px/s^2 acceleration applied by the brain to the body
        brace: 0..1 — wind-up compression (springs stiffen, rest shrinks)
        """
        p = self.p
        self.force.fill(0.0)
        self.noise_t += dt

        # --- springs ---------------------------------------------------
        si = self.springs[:, 0].astype(int)
        sj = self.springs[:, 1].astype(int)
        rest = self.springs[:, 2] * (1.0 - 0.22 * brace)
        k = self.springs[:, 3] * (1.0 + 0.6 * brace)
        c = self.springs[:, 4]

        dvec = self.pos[sj] - self.pos[si]
        dist = np.linalg.norm(dvec, axis=1)
        safe = np.maximum(dist, 1e-6)
        dirv = dvec / safe[:, None]
        relv = (self.vel[sj] - self.vel[si])
        axial = np.einsum("ij,ij->i", relv, dirv)
        fm = (dist - rest) * k + axial * c          # >0 pulls together
        fvec = dirv * fm[:, None]
        np.add.at(self.force, si, fvec)
        np.add.at(self.force, sj, -fvec)

        # --- cohesion: outers drift back toward the core ---------------
        to_core = self.pos[0] - self.pos[1:]
        dcore = np.linalg.norm(to_core, axis=1)
        dir_core = to_core / np.maximum(dcore, 1e-6)[:, None]
        cf = dir_core * (p.cohesion * (0.55 + dcore / p.ring_radius))[:, None]
        self.force[1:] += cf * self.mass[1:, None]

        # --- buoyancy + idle wobble (keeps it alive at rest) -----------
        self.force[:, 1] -= p.buoyancy * self.mass
        wob = p.wobble * (1.0 + 0.6 * brace)
        s = np.sin(self.noise_t * 1.9 + self.phase)
        t = np.cos(self.noise_t * 1.3 + self.phase * 1.7)
        self.force[:, 0] += wob * s * self.mass
        self.force[:, 1] += wob * t * self.mass

        # --- behavioral drive ------------------------------------------
        if drive is not None:
            self.force[0] += drive * self.mass[0]
            # outers follow at reduced authority -> natural lag deformation
            self.force[1:] += drive[None, :] * self.mass[1:, None] * 0.55

        # --- region edges ----------------------------------------------
        if region is not None:
            for i in range(self.n):
                fx, fy = region.soft_edge_force(
                    self.pos[i, 0], self.pos[i, 1],
                    self.radius[i] * 0.5, edge_margin, edge_strength)
                self.force[i, 0] += fx * self.mass[i]
                self.force[i, 1] += fy * self.mass[i]

        # --- integrate (semi-implicit Euler, exponential damping) ------
        damp = math.exp(-(p.drag + extra_damping) * dt)
        acc = self.force / self.mass[:, None]
        self.vel = (self.vel + acc * dt) * damp
        spd = np.linalg.norm(self.vel, axis=1)
        over = spd > p.max_speed
        if np.any(over):
            self.vel[over] *= (p.max_speed / spd[over])[:, None]
        self.pos += self.vel * dt

        # --- hard edge projection + bounce ------------------------------
        self.edge_hit = None
        if region is not None:
            for i in range(self.n):
                x, y = self.pos[i]
                r = self.radius[i] * 0.5
                if not region.contains(x, y, r):
                    nx, ny = region.project_inside(x, y, r)
                    # bounce off the axis that moved most
                    if abs(nx - x) > abs(ny - y):
                        self.vel[i, 0] = -self.vel[i, 0] * p.edge_restitution
                        self.vel[i, 1] *= p.edge_friction
                        self.edge_hit = "left" if nx < x else "right"
                    else:
                        self.vel[i, 1] = -self.vel[i, 1] * p.edge_restitution
                        self.vel[i, 0] *= p.edge_friction
                        self.edge_hit = "top" if ny < y else "bottom"
                    self.pos[i] = (nx, ny)

        # --- particle-particle separation -------------------------------
        for i in range(self.n):
            for j in range(i + 1, self.n):
                d = self.pos[j] - self.pos[i]
                dist = np.linalg.norm(d)
                mind = (self.radius[i] + self.radius[j]) * 0.55
                if 1e-6 < dist < mind:
                    nrm = d / dist
                    overlap = (mind - dist) * 0.5
                    w_i = self.mass[j] / (self.mass[i] + self.mass[j])
                    w_j = self.mass[i] / (self.mass[i] + self.mass[j])
                    self.pos[i] -= nrm * overlap * w_i
                    self.pos[j] += nrm * overlap * w_j

        # --- coherence clamp: nobody leaves the body --------------------
        rel = self.pos[1:] - self.pos[0]
        drel = np.linalg.norm(rel, axis=1)
        maxr = p.ring_radius * p.max_stretch
        too_far = drel > maxr
        if np.any(too_far):
            idx = np.nonzero(too_far)[0] + 1
            scale = maxr / drel[too_far]
            self.pos[idx] = self.pos[0] + rel[too_far] * scale[:, None]
            # bleed the excess radial velocity
            n = rel[too_far] / drel[too_far][:, None]
            vr = np.einsum("ij,ij->i", self.vel[idx] - self.vel[0], n)
            out = vr > 0
            if np.any(out):
                self.vel[idx[out]] -= n[out] * vr[out][:, None] * 0.8

        # NaN guard — never emit non-finite state
        if not np.isfinite(self.pos).all() or not np.isfinite(self.vel).all():
            bad = ~np.isfinite(self.pos).all(axis=1)
            self.pos[bad] = self._spawn_center
            self.vel[~np.isfinite(self.vel).all(axis=1)] = 0.0

    def impulse(self, dv, spread=0.45):
        """Impulse velocity change: full on core, jittered on outers."""
        dv = np.asarray(dv, dtype=np.float64)
        self.vel[0] += dv
        jit = self.rng.normal(0.0, spread, (self.n - 1, 2))
        self.vel[1:] += dv[None, :] * (0.55 + jit)
