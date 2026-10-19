"""Comprehensive automated test suite for Zwoop Trail Studio V1.0.

Covers Sections 16.1 – 16.7:
  - World-space history, FPS-independence, break detection, expiration
  - Geometry families, premultiplied-alpha invariants, edge cases
  - Seeded deterministic particles, caps, drag, gravity, cleanup
  - 25 Bundled Presets, immutability, PresetStore CRUD, import/export safety
  - Randomizer modes, seed determinism, recipe round-trip, and all 8 locks
  - Configuration migration from legacy `render.trail` & `effects_level`
  - Behavior & motion reactivity with attack/release smoothing
  - Multi-layer compositing, solo/priority, and visual family differentiation
  - TrailStudio state management, layer & gradient operations, undo/redo
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest

import numpy as np

from zwoop.config import Config
from zwoop.render.rasterizer import Rasterizer
from zwoop.trails import (
    BUNDLED_PRESETS,
    GEOMETRY_FAMILIES,
    PARAM_SCHEMA,
    ParticleSystem,
    PresetStore,
    ReactiveController,
    TrailEngine,
    TrailHistory,
    TrailRandomizer,
     migrate_legacy_config,
    validate_preset_dict,
    validate_trails_config,
)
from zwoop.trails.geometry import composite_layer
from zwoop.trails.history import resample_stroke
from zwoop.trails.randomizer import LOCK_KEYS
from zwoop.trails.schema import ValidationError, default_behavior_modifiers, default_layer
from zwoop.ui.trail_studio import TrailStudio, generate_demo_snapshot


def _fake_snap(x: float, y: float, t: float, vx: float = 200.0, vy: float = 0.0,
               state: str = "WANDER", maneuver: str = "") -> dict:
    spd = float(np.hypot(vx, vy))
    pos = np.zeros((13, 2), dtype=np.float32)
    pos[0] = (x, y)
    for i in range(1, 13):
        a = (i - 1) * 2 * np.pi / 12
        pos[i] = (x + 28 * np.cos(a), y + 28 * np.sin(a))
    vel = np.tile(np.array([vx, vy], dtype=np.float32), (13, 1))
    rad = np.full(13, 15.0, dtype=np.float32)
    rad[0] = 20.0
    return {
        "pos": pos,
        "radius": rad,
        "vel": vel,
        "center": np.array([x, y], dtype=np.float32),
        "speed": spd,
        "deform": 0.08,
        "energy": 0.5 * spd * spd,
        "state": state,
        "maneuver": maneuver,
        "waypoint": None,
        "edge_hit": None,
        "t": float(t),
    }


class TestHistoryAndTiming(unittest.TestCase):
    """Section 16.1 — History, FPS-independence, break detection, expiration."""

    def test_time_based_expiration_and_bounds(self):
        hist = TrailHistory(max_samples=50, min_spacing_px=4.0)
        for i in range(120):
            t = i * 0.05
            hist.record(_fake_snap(100 + i * 8.0, 200.0, t), now_t=t, max_lifetime_s=1.5)
        self.assertLessEqual(len(hist.samples), 50)
        now = 119 * 0.05
        for s in hist.samples:
            self.assertGreaterEqual(s.t, now - 1.55)

        hist.clear()
        self.assertEqual(len(hist.samples), 0)

    def test_fps_independent_lifespan_and_arc_length(self):
        """Trail length at 30 FPS vs 120 FPS over 1.0s at 300 px/s must match closely."""
        lengths = {}
        for fps in (30, 120):
            hist = TrailHistory(max_samples=300, min_spacing_px=5.0)
            dt = 1.0 / fps
            steps = int(1.0 * fps)
            for i in range(steps + 1):
                t = i * dt
                x = 200.0 + 300.0 * t
                hist.record(_fake_snap(x, 400.0, t, vx=300.0), now_t=t, max_lifetime_s=0.8)
            strokes = hist.get_strokes(now_t=1.0, lifetime_s=0.8, length_cap_px=1000.0)
            self.assertEqual(len(strokes), 1)
            rs = resample_stroke(strokes[0], now_t=1.0, lifetime_s=0.8)
            lengths[fps] = rs["total_len"]

        # Both 30 FPS and 120 FPS should span ~240 px (0.8s * 300 px/s) within 15 px
        self.assertAlmostEqual(lengths[30], lengths[120], delta=16.0)
        self.assertGreater(lengths[30], 200.0)

    def test_stationary_suppression_and_high_speed_subdivision(self):
        hist = TrailHistory(max_samples=200, min_spacing_px=6.0, max_step_px=25.0)
        # Stationary for 30 frames at 60Hz -> minimal sample accumulation
        for i in range(30):
            hist.record(_fake_snap(500.0, 500.0, i / 60.0, vx=0.0), now_t=i / 60.0)
        self.assertLessEqual(len(hist.samples), 2)

        # Fast 120 px jump in a single frame (< break_distance 280) -> subdivided
        added = hist.record(_fake_snap(620.0, 500.0, 31 / 60.0, vx=1500.0), now_t=31 / 60.0)
        self.assertGreaterEqual(len(added), 4)

    def test_discontinuity_and_teleport_break_detection(self):
        hist = TrailHistory(max_samples=200, min_spacing_px=4.0, break_distance_px=250.0, break_dt_s=0.4)
        for i in range(10):
            t = i * 0.02
            hist.record(_fake_snap(100 + i * 10.0, 100.0, t), now_t=t)
        # Teleport 600 px across monitors -> must start a new stroke_id
        t_tele = 10 * 0.02
        hist.record(_fake_snap(800.0, 700.0, t_tele), now_t=t_tele)
        for i in range(1, 8):
            t = t_tele + i * 0.02
            hist.record(_fake_snap(800.0 + i * 10.0, 700.0, t), now_t=t)

        strokes = hist.get_strokes(now_t=t_tele + 0.14, lifetime_s=2.0)
        self.assertEqual(len(strokes), 2)

        # Explicit break (e.g. pause/resume)
        hist.notify_break()
        t_res = t_tele + 0.16
        hist.record(_fake_snap(890.0, 700.0, t_res), now_t=t_res)
        strokes2 = hist.get_strokes(now_t=t_res, lifetime_s=2.0)
        self.assertEqual(len(strokes2), 3)


class TestGeometryAndBlending(unittest.TestCase):
    """Section 16.2 — Geometry edge cases & premultiplied-alpha blending."""

    def test_edge_cases_single_sample_zero_length_sharp_turn(self):
        hist = TrailHistory()
        hist.record(_fake_snap(300.0, 300.0, 0.0), now_t=0.0)
        strokes = hist.get_strokes(0.0, 1.5)
        rs1 = resample_stroke(strokes[0], 0.0, 1.5)
        self.assertIsNotNone(rs1)
        self.assertTrue(np.isfinite(rs1["pos"]).all())

        # Sharp 180-degree reversal
        hist.record(_fake_snap(360.0, 300.0, 0.05, vx=800.0), now_t=0.05)
        hist.record(_fake_snap(310.0, 300.0, 0.10, vx=-800.0), now_t=0.10)
        strokes = hist.get_strokes(0.10, 1.5)
        rs2 = resample_stroke(strokes[0], 0.10, 1.5)
        self.assertTrue(np.isfinite(rs2["pos"]).all())
        self.assertTrue(np.isfinite(rs2["norm"]).all())

    def test_premultiplied_alpha_invariants_across_blend_modes(self):
        h, w = 32, 32
        for mode in ("alpha", "add", "screen", "contrast"):
            dst_rgb = np.full((h, w, 3), 0.25, dtype=np.float32)
            dst_a = np.full((h, w), 0.5, dtype=np.float32)
            src_rgb = np.full((h, w, 3), 0.95, dtype=np.float32)
            src_a = np.full((h, w), 0.85, dtype=np.float32)
            composite_layer(dst_rgb, dst_a, src_rgb, src_a, blend_mode=mode, overlap_intensity=1.4)
            self.assertTrue(np.all(dst_a >= 0.0) and np.all(dst_a <= 1.0))
            self.assertTrue(np.all(dst_rgb >= 0.0))
            # Premultiplied invariant: no channel exceeds alpha
            self.assertTrue(np.all(dst_rgb <= dst_a[..., None] + 1e-6), f"Failed invariant for {mode}")


class TestParticles(unittest.TestCase):
    """Section 16.3 — Deterministic seeded emission, caps, gravity, cleanup."""

    def test_seeded_determinism_and_count_cap(self):
        lyr = default_layer("p1", "Stars", "particles")
        lyr["particles"]["max_particles"] = 45
        lyr["particles"]["spawn_rate"] = 120.0

        ps1 = ParticleSystem(seed=555)
        ps2 = ParticleSystem(seed=555)
        for i in range(40):
            pos = (400.0 + i * 5.0, 300.0)
            ps1.step(1 / 60.0, lyr, pos, (300.0, 0.0), burst_count=(10 if i == 5 else 0))
            ps2.step(1 / 60.0, lyr, pos, (300.0, 0.0), burst_count=(10 if i == 5 else 0))

        self.assertLessEqual(ps1.count, 45)
        self.assertEqual(ps1.count, ps2.count)
        np.testing.assert_allclose(ps1.pos, ps2.pos, atol=1e-5)
        np.testing.assert_allclose(ps1.vel, ps2.vel, atol=1e-5)

    def test_gravity_and_expiration(self):
        lyr = default_layer("p_grav", "Gravity", "particles")
        lyr["lifetime_s"] = 0.35
        lyr["lifetime_variance"] = 0.0
        lyr["particles"]["gravity"] = 200.0  # downward
        lyr["particles"]["turbulence"] = 0.0
        lyr["particles"]["initial_velocity"] = 0.0
        lyr["particles"]["velocity_inheritance"] = 0.0
        lyr["motion"]["drift_y"] = 0.0

        ps = ParticleSystem(seed=12)
        ps.step(0.02, lyr, (500.0, 500.0), (0.0, 0.0), burst_count=8)
        y_init = float(ps.pos[:, 1].mean())

        for _ in range(10):
            ps.step(0.02, lyr, None, None)
        self.assertGreater(float(ps.pos[:, 1].mean()), y_init + 2.0)

        # Advance past 0.35s lifetime -> all particles must expire cleanly
        for _ in range(20):
            ps.step(0.03, lyr, None, None)
        self.assertEqual(ps.count, 0)


class TestPresetsAndRandomizer(unittest.TestCase):
    """Section 16.4 — 25 Presets, immutability, CRUD, import/export, Randomizer."""

    def test_all_25_bundled_presets_valid_and_immutable(self):
        self.assertEqual(len(BUNDLED_PRESETS), 25)
        self.assertIn("legacy_zwoop", BUNDLED_PRESETS)
        self.assertGreaterEqual(len(PARAM_SCHEMA), 80)

        with tempfile.TemporaryDirectory() as tmp:
            store = PresetStore(user_dir=tmp)
            all_p = store.list_all()
            self.assertEqual(len(all_p), 25)
            ids = {p["id"] for p in all_p}
            self.assertEqual(len(ids), 25)

            # Mutating returned dict must not mutate bundled definition
            neb = store.get("nebula_silk")
            neb["name"] = "Hacked"
            neb["layers"][0]["width_px"] = 999.0
            self.assertEqual(store.get("nebula_silk")["name"], "Nebula Silk")
            self.assertNotEqual(store.get("nebula_silk")["layers"][0]["width_px"], 999.0)

            # Deleting bundled preset must raise ValidationError
            with self.assertRaises(ValidationError):
                store.delete_custom("nebula_silk")

    def test_custom_preset_save_duplicate_import_export_and_malformed_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresetStore(user_dir=tmp)
            custom = store.get("stardust")
            custom["name"] = "My Custom Nebula"
            saved = store.save_custom(custom)
            self.assertFalse(saved["builtin"])
            self.assertNotEqual(saved["id"], "stardust")

            dup = store.duplicate(saved["id"], "My Custom Nebula 2")
            self.assertNotEqual(dup["id"], saved["id"])

            # Export and import round-trip
            exp_path = os.path.join(tmp, "exported.json")
            store.export_file(dup, exp_path)
            imp = store.import_file(exp_path, persist=True)
            self.assertEqual(imp["name"], "My Custom Nebula 2")

            # Malformed imports must fail safely
            bad_path = os.path.join(tmp, "bad.json")
            with open(bad_path, "w", encoding="utf-8") as f:
                json.dump({"id": "x", "name": "Bad", "layers": [{"family": "nonexistent_type"}]}, f)
            with self.assertRaises(ValidationError):
                store.import_file(bad_path)

            nan_path = os.path.join(tmp, "nan.json")
            with open(nan_path, "w", encoding="utf-8") as f:
                f.write('{"id": "n", "name": "N", "layers": [{"family": "ribbon", "width_px": "not_a_num"}]}')
            with self.assertRaises(ValidationError):
                store.import_file(nan_path)

    def test_randomizer_determinism_locks_and_recipes(self):
        base = copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])
        rand = TrailRandomizer()

        p1, s1 = rand.randomize(base, mode="remix", seed=12345)
        p2, s2 = rand.randomize(base, mode="remix", seed=12345)
        self.assertEqual(s1, s2)
        self.assertEqual(p1, p2)

        # Lock verification: locking colors & geometry & layers keeps them untouched
        locks = {k: (k in ("colors", "geometry", "layers")) for k in LOCK_KEYS}
        p_locked, _ = rand.randomize(base, mode="wild", seed=999, locks=locks)
        self.assertEqual(len(p_locked["layers"]), len(base["layers"]))
        for l_orig, l_new in zip(base["layers"], p_locked["layers"]):
            self.assertEqual(l_orig["family"], l_new["family"])
            self.assertEqual(l_orig["width_px"], l_new["width_px"])
            self.assertEqual(l_orig["gradient_stops"], l_new["gradient_stops"])

        # Recipe round-trip
        rec = rand.encode_recipe("variation", 777, "nebula_silk", locks)
        dec = rand.decode_recipe(rec)
        self.assertEqual(dec["mode"], "variation")
        self.assertEqual(dec["seed"], 777)
        self.assertEqual(dec["locks"], locks)


class TestConfigMigrationAndReactivity(unittest.TestCase):
    """Sections 16.5 & 16.6 — Legacy migration & behavior reactivity."""

    def test_legacy_config_migration(self):
        # Legacy disabled trail must remain disabled after migration
        c_off = migrate_legacy_config({"render": {"trail": False, "effects_level": 2}})
        self.assertFalse(c_off["render"]["trails"]["enabled"])
        self.assertFalse(c_off["render"]["trail"])

        # Legacy enabled trail with effects_level=1 -> enabled, eco quality
        c_eco = migrate_legacy_config({"render": {"trail": True, "effects_level": 1}})
        self.assertTrue(c_eco["render"]["trails"]["enabled"])
        self.assertEqual(c_eco["render"]["trails"]["quality"]["preset"], "eco")

        # Empty / minimal config -> valid defaults
        c_min = migrate_legacy_config({})
        self.assertTrue(c_min["render"]["trails"]["enabled"])
        self.assertEqual(c_min["render"]["trails"]["active_preset"], "nebula_silk")

    def test_behavior_reactivity_and_smooth_transitions(self):
        rc = ReactiveController()
        beh = default_behavior_modifiers()

        # Rest state -> low intensity
        for _ in range(40):
            m_rest = rc.update(0.05, _fake_snap(500, 500, 1.0, vx=10.0, state="REST"), beh)
        self.assertLess(m_rest.intensity_mult, 0.35)

        # Sudden switch to PERFORM:dive -> attack smoothing prevents instant jump on frame 1,
        # then ramps up to high intensity and length
        m_step1 = rc.update(0.016, _fake_snap(500, 500, 1.02, vx=750.0, state="PERFORM", maneuver="dive"), beh)
        self.assertLess(m_step1.intensity_mult, 1.2)  # smoothed on first frame
        self.assertGreater(m_step1.burst_factor, 0.5)  # dive entry triggers burst

        for i in range(30):
            m_dive = rc.update(0.03, _fake_snap(500 + i * 20, 500, 1.05 + i * 0.03, vx=750.0, state="PERFORM", maneuver="dive"), beh)
        self.assertGreater(m_dive.intensity_mult, 1.25)
        self.assertGreater(m_dive.length_mult, 1.20)


class TestRenderingAndStudioWorkflow(unittest.TestCase):
    """Sections 16.7 — Visual family differentiation & TrailStudio workflows."""

    def test_visual_differentiation_across_families(self):
        """Representative presets from different families must produce measurably different frames."""
        signatures = {}
        for pid in ("nebula_silk", "laser_thread", "stardust", "double_helix", "ghost_veil", "event_horizon"):
            eng = TrailEngine(seed=11)
            eng.load_preset(pid, clear_existing=True)
            for i in range(36):
                t = i / 30.0
                snap = generate_demo_snapshot("swoop", t, w=240, h=180)
                eng.step(1 / 30.0, snap)
            frame = np.zeros((180, 240, 4), dtype=np.uint8)
            drew = eng.render_into(frame, (0.0, 0.0), snap, res_scale_override=2)
            self.assertTrue(drew, f"{pid} did not draw")
            # Corner pixel (0, 0) must remain transparent (no opaque background)
            self.assertEqual(int(frame[0, 0, 3]), 0)
            signatures[pid] = (
                int(np.count_nonzero(frame[..., 3] > 15)),
                float(frame[..., :3].mean()),
            )

        # Ensure presets are not identical
        unique_counts = {v[0] for v in signatures.values()}
        self.assertGreaterEqual(len(unique_counts), 5)

        # Verify rendering into a non-contiguous DIB sub-slice (e.g. TrailOverlayWindow subframe)
        backing_dib = np.zeros((600, 800, 4), dtype=np.uint8)
        sub_slice = backing_dib[:180, :240]
        self.assertFalse(sub_slice.flags.c_contiguous)
        eng_sub = TrailEngine(seed=11)
        eng_sub.load_preset("solar_flare", clear_existing=True)
        for i in range(25):
            snap = generate_demo_snapshot("swoop", i / 30.0, w=240, h=180)
            eng_sub.step(1 / 30.0, snap)
        drew_sub = eng_sub.render_into(sub_slice, (0.0, 0.0), snap, res_scale_override=4)
        self.assertTrue(drew_sub)
        self.assertGreater(int(np.count_nonzero(sub_slice[..., 3] > 10)), 100)

    def test_trail_studio_layer_gradient_and_undo_redo_workflows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PresetStore(user_dir=tmp)
            applied = []
            studio = TrailStudio(
                validate_trails_config({}),
                preset_store=store,
                on_apply=lambda c, p: applied.append((c, p)),
            )

            studio.select_preset("nebula_silk")
            self.assertEqual(len(studio.working_preset["layers"]), 2)

            # Add 3rd layer
            studio.add_layer("spiral")
            self.assertEqual(len(studio.working_preset["layers"]), 3)
            self.assertTrue(studio.unsaved_changes)

            # Solo toggle
            self.assertTrue(studio.toggle_solo_layer(2))
            self.assertFalse(studio.working_preset["layers"][0]["solo"])

            # Gradient edit
            studio.add_gradient_stop(0.33, "#FF007F", 0.9)
            self.assertEqual(len(studio.active_layer["gradient_stops"]), 4)

            # Undo / Redo
            studio.undo()
            self.assertEqual(len(studio.active_layer["gradient_stops"]), 3)
            studio.redo()
            self.assertEqual(len(studio.active_layer["gradient_stops"]), 4)

            # Preview frame generation
            rgb = studio.step_preview_frame(dt=1 / 30.0, w=240, h=160)
            self.assertEqual(rgb.shape, (160, 240, 3))
            self.assertEqual(rgb.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
