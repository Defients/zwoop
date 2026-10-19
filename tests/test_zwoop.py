"""Zwoop test suite — physics invariants, brain behavior, replays.

Run:  python -m unittest discover -s tests -v   (from repo root)
"""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zwoop.sim.region import Region, Rect
from zwoop.sim.world import Sim
from zwoop.sim.brain import Params, State
from zwoop.sim.body import SoftBody, BodyParams
from zwoop.sim import steering

DT = 1.0 / 120.0
DESKTOP = Region([Rect(0, 0, 2560, 1440)])


def make_sim(seed=7, **kw):
    return Sim(DESKTOP, Params(**kw), seed=seed)


def run(sim, seconds, cursor=None, idle=0.0):
    """cursor: None, (x,y), or callable t->pos"""
    for i in range(int(seconds / DT)):
        t = i * DT
        pos = cursor(t) if callable(cursor) else cursor
        sim.feed_cursor(pos)
        sim.set_user_idle(idle)
        sim.step(DT)


class TestBody(unittest.TestCase):
    def test_long_run_finite(self):
        sim = make_sim()
        run(sim, 90.0)
        self.assertTrue(np.isfinite(sim.body.pos).all())
        self.assertTrue(np.isfinite(sim.body.vel).all())

    def test_stays_in_region(self):
        sim = make_sim()
        run(sim, 60.0)
        for p in sim.body.pos:
            self.assertTrue(
                sim.region.contains(p[0], p[1], -sim.body.radius[0]),
                f"particle escaped region: {p}")

    def test_deformation_bounded(self):
        sim = make_sim()
        worst = 0.0
        for i in range(int(60 / DT)):
            sim.feed_cursor(None)
            sim.step(DT)
            worst = max(worst, sim.body.deformation())
        self.assertLess(worst, 1.2)

    def test_recovers_from_extreme_impulse(self):
        sim = make_sim()
        run(sim, 2.0)
        sim.body.impulse((4000.0, -3000.0))
        run(sim, 8.0)
        self.assertTrue(np.isfinite(sim.body.pos).all())
        self.assertLess(sim.body.speed, 1500.0)
        c = sim.body.center
        self.assertTrue(sim.region.contains(c[0], c[1], 0))

    def test_no_static_equilibrium(self):
        """The creature must not sit perfectly still (aliveness)."""
        sim = make_sim()
        run(sim, 5.0)
        c0 = sim.body.center.copy()
        run(sim, 20.0)
        moved = np.linalg.norm(sim.body.center - c0)
        self.assertGreater(moved, 30.0)

    def test_edge_bounce_recovers(self):
        sim = make_sim()
        run(sim, 2.0)
        # slam toward the left edge
        sim.body.vel[:, 0] = -2500.0
        run(sim, 6.0)
        self.assertTrue(np.isfinite(sim.body.pos).all())
        self.assertTrue(sim.region.contains(*sim.body.center, 0))

    def test_determinism(self):
        a = make_sim(seed=42)
        b = make_sim(seed=42)
        run(a, 10.0)
        run(b, 10.0)
        np.testing.assert_allclose(a.body.pos, b.body.pos)


class TestBrain(unittest.TestCase):
    def _states(self, sim):
        return {n for _, m in sim.brain.log for n in m.split("->")}

    def test_cursor_approach(self):
        """Creature should approach a nearby cursor at some point."""
        sim = make_sim()
        cpos = np.array([1400.0, 700.0])
        run(sim, 1.0, cursor=cpos)
        d0 = np.linalg.norm(sim.body.center - cpos)
        dmin, saw_curious = 1e9, False
        for i in range(int(12.0 / DT)):
            sim.feed_cursor(cpos)
            sim.step(DT)
            dmin = min(dmin, np.linalg.norm(sim.body.center - cpos))
            saw_curious |= sim.brain.state == State.CURIOUS
        self.assertTrue(saw_curious)
        self.assertLess(dmin, d0)

    def test_sudden_cursor_startles(self):
        # disable spontaneous maneuvers so PERFORM can't block the reflex
        sim = make_sim(expressiveness=0.0, maneuver_cooldown=9999)
        run(sim, 3.0, cursor=(1500, 700))
        got_startle = False
        for i in range(int(2.0 / DT)):
            # teleport the cursor next to the creature = sudden
            c = sim.body.center
            sim.feed_cursor((c[0] + 60, c[1] + 10))
            sim.step(DT)
            if sim.brain.state in (State.STARTLE, State.EVADE):
                got_startle = True
                break
        self.assertTrue(got_startle)

    def test_evades_fast_close_cursor(self):
        sim = make_sim()
        run(sim, 2.0)
        evaded = False
        for i in range(int(4 / DT)):
            c = sim.body.center
            # whip the cursor back and forth right on top of the creature
            wob = math.sin(i * DT * 25) * 80
            sim.feed_cursor((c[0] + wob, c[1]))
            sim.step(DT)
            if sim.brain.state == State.EVADE:
                evaded = True
                break
        self.assertTrue(evaded)

    def test_rests_on_long_idle(self):
        sim = make_sim()
        run(sim, 8.0, idle=999.0)
        self.assertIn(sim.brain.state, (State.REST, State.WANDER))
        # give it time to settle into REST
        run(sim, 30.0, idle=999.0)
        self.assertEqual(sim.brain.state, State.REST)

    def test_performs_spontaneously(self):
        sim = make_sim()
        seen = set()
        for i in range(int(60 / DT)):
            sim.feed_cursor(None)
            sim.step(DT)
            if sim.brain.state == State.PERFORM:
                seen.add(sim.brain.maneuver.name)
        self.assertTrue(len(seen) >= 2, f"low variety: {seen}")

    def test_anti_repetition(self):
        """No maneuver should fire twice back-to-back."""
        sim = make_sim()
        run(sim, 120.0)
        hist = list(sim.brain.history)
        for a, b in zip(hist, hist[1:]):
            self.assertNotEqual(a, b)

    def test_disengages_from_cursor(self):
        """CURIOUS must end — it can't obsess forever."""
        sim = make_sim()
        run(sim, 30.0, cursor=(1280, 720))
        # after attention span, it should leave CURIOUS at some point
        left = any("CURIOUS->WANDER" in m for _, m in sim.brain.log)
        self.assertTrue(left or sim.brain.state != State.CURIOUS)


class TestRegion(unittest.TestCase):
    def test_multi_monitor(self):
        reg = Region([Rect(0, 0, 1920, 1080), Rect(1920, 0, 3840, 1080)])
        # seam between monitors is not a void edge
        fx, fy = reg.soft_edge_force(1900, 540, 20, 90, 2000)
        self.assertEqual((fx, fy), (0.0, 0.0))   # right edge shared -> free
        # but top edge still repels
        fx, fy = reg.soft_edge_force(960, 30, 20, 90, 2000)
        self.assertGreater(fy, 0)

    def test_project_inside(self):
        reg = Region([Rect(0, 0, 1920, 1080)])
        x, y = reg.project_inside(-50, 500, 10)
        self.assertTrue(reg.contains(x, y, 9))


class TestManeuvers(unittest.TestCase):
    def test_all_registered(self):
        rng = np.random.default_rng(0)
        start = np.array([960.0, 540.0])
        for name, factory in steering.REGISTRY.items():
            m = factory(start, rng, DESKTOP)
            self.assertGreater(m.duration, 0)
            for t in (0.0, 0.5, 1.0):
                tgt = m.target(t)
                self.assertTrue(np.isfinite(tgt).all(), f"{name} bad target")


class TestReplay(unittest.TestCase):
    """Scripted cursor-path replays (seeded, deterministic)."""

    def test_idle_scenario(self):
        sim = make_sim(seed=1)
        run(sim, 45.0, cursor=None, idle=60.0)
        self.assertTrue(np.isfinite(sim.body.pos).all())

    def test_circling_cursor(self):
        sim = make_sim(seed=2)
        c0 = np.array([1280.0, 720.0])
        run(sim, 30.0,
            cursor=lambda t: c0 + 150 * np.array(
                [math.cos(t * 1.4), math.sin(t * 1.4)]))
        self.assertTrue(np.isfinite(sim.body.pos).all())

    def test_stall_recovery(self):
        sim = make_sim(seed=3)
        run(sim, 5.0)
        # frame stall: giant dt via a single huge step is not allowed;
        # simulate bounded catch-up like the app does
        sim.step(0.033)
        self.assertTrue(np.isfinite(sim.body.pos).all())

    def test_display_change(self):
        """Lose a monitor mid-run -> creature must stay recoverable."""
        sim = make_sim(seed=4)
        run(sim, 5.0)
        sim.region = Region([Rect(0, 0, 1280, 720)])
        sim.brain.region = sim.region
        run(sim, 10.0)
        c = sim.body.center
        self.assertTrue(sim.region.contains(c[0], c[1], -40))


if __name__ == "__main__":
    unittest.main()
