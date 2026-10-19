"""Benchmark the Zwoop + Trail Studio V1.0 pipeline across the Section 12.6 matrix.

    python tools/bench.py [frames_per_case]

Measures:
  1. Core simulation step (120 Hz)
  2. Creature rasterizer (320x320)
  3. Trail Studio Benchmark Matrix (mean, p50, p95 ms/frame + active bbox):
     - Trails disabled
     - Legacy trail (legacy_zwoop)
     - Single beam/ribbon (laser_thread)
     - Single particle stream (stardust)
     - Balanced multi-layer preset (nebula_silk)
     - 4-layer heavy preset (Cosmic Comet 4L: smoke + ribbon + spiral + sparks)
     - High-speed long trail (hyperdrive @ 780 px/s)
     - Idle state with lingering trail
     - Multi-monitor seam crossing
     - Quality modes: eco, balanced, high, ultra
"""

from __future__ import annotations

import copy
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from zwoop.sim.region import Region, Rect
from zwoop.sim.world import Sim
from zwoop.sim.brain import Params
from zwoop.sim.body import BodyParams
from zwoop.render.rasterizer import Rasterizer
from zwoop.trails import BUNDLED_PRESETS, TrailEngine
from zwoop.trails.schema import QUALITY_BUDGETS, default_layer

FRAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 90
W_CREATURE = 320

region = Region([Rect(0, 0, 2560, 1440), Rect(2560, 180, 4480, 1260)])
bp = BodyParams(n_outer=12, ring_radius=31 * 1.13, core_radius=31 * 0.65, outer_radius=31 * 0.48)
sim = Sim(region, Params(), body_params=bp, seed=5)
rast = Rasterizer(W_CREATURE, effects=2, trail=False)
c_frame = np.zeros((W_CREATURE, W_CREATURE, 4), np.uint8)

# 1. Core simulation step benchmark
h = 1.0 / 120.0
n_sim = 360
t0 = time.perf_counter()
for i in range(n_sim):
    sim.feed_cursor((1280 + 300 * np.sin(i * h), 700))
    sim.step(h)
sim_ms = (time.perf_counter() - t0) / n_sim * 1000.0

# 2. Creature rasterizer benchmark
snap = sim.snapshot()
c = snap["center"]
origin = (c[0] - W_CREATURE / 2, c[1] - W_CREATURE / 2)
t0 = time.perf_counter()
for _ in range(120):
    rast.render(c_frame, snap, origin, dt=1 / 60)
creature_ms = (time.perf_counter() - t0) / 120 * 1000.0

print(f"Core sim step (120Hz) : {sim_ms:6.3f} ms/step")
print(f"Creature raster (320) : {creature_ms:6.2f} ms/frame")
print("-" * 78)
print(f"{'Scenario':<34s} | {'Mean ms':>7s} | {'p50 ms':>6s} | {'p95 ms':>6s} | {'Avg BBox':>11s}")
print("-" * 78)

t_backing = np.zeros((1200, 1600, 4), dtype=np.uint8)


def run_case(
    label: str,
    preset_or_id,
    quality: str = "balanced",
    enabled: bool = True,
    speed_override: float | None = None,
    idle_halfway: bool = False,
    cross_monitors: bool = False,
):
    eng = TrailEngine(seed=17)
    eng.cfg["quality"]["preset"] = quality
    eng.cfg["quality"]["auto_quality"] = False
    if isinstance(preset_or_id, str):
        eng.load_preset(preset_or_id, clear_existing=True)
    else:
        eng.load_preset(preset_or_id, clear_existing=True)
    eng.set_enabled(enabled)

    q_bud = QUALITY_BUDGETS.get(quality, QUALITY_BUDGETS["balanced"])
    max_w, max_h = int(q_bud["max_surface_w"]), int(q_bud["max_surface_h"])

    times = []
    areas = []
    dt = 1.0 / 60.0

    for i in range(FRAMES):
        t = i * dt
        if cross_monitors:
            cx = 2200.0 + 700.0 * np.sin(t * 1.6)
            cy = 720.0 + 180.0 * np.cos(t * 2.2)
            vx = 700.0 * 1.6 * np.cos(t * 1.6)
            vy = -180.0 * 2.2 * np.sin(t * 2.2)
            state, man = "PERFORM", "swoop"
        elif idle_halfway and i > FRAMES // 2:
            cx = 1280.0 + 6.0 * np.sin(t * 1.2)
            cy = 720.0 + 5.0 * np.cos(t * 1.1)
            vx, vy = 5.0, 4.0
            state, man = "REST", ""
        else:
            r = 220.0 if (speed_override or 400.0) < 600 else 360.0
            w_ang = (speed_override or 420.0) / r
            cx = 1280.0 + r * np.cos(t * w_ang)
            cy = 720.0 + r * 0.75 * np.sin(2 * t * w_ang) * 0.5
            vx = -r * w_ang * np.sin(t * w_ang)
            vy = r * 0.75 * w_ang * np.cos(2 * t * w_ang)
            state, man = "PERFORM", "figure8"

        spd = float(speed_override if speed_override is not None and not (idle_halfway and i > FRAMES // 2) else np.hypot(vx, vy))
        s_i = dict(snap)
        s_i["center"] = np.array([cx, cy], dtype=np.float32)
        s_i["vel"] = np.tile(np.array([vx, vy], dtype=np.float32), (13, 1))
        s_i["speed"] = spd
        s_i["state"] = state
        s_i["maneuver"] = man
        s_i["t"] = t

        t_start = time.perf_counter()
        eng.step(dt, s_i, region=region, target_fps=60)
        bbox = eng.compute_active_bounds(s_i, max_w=max_w, max_h=max_h)
        if bbox is not None:
            bx, by, bw, bh = bbox
            sub = t_backing[:bh, :bw]
            eng.render_into(sub, (bx, by), s_i)
            areas.append((bw, bh))
        else:
            areas.append((0, 0))
        times.append((time.perf_counter() - t_start) * 1000.0)

    arr_t = np.array(times[10:])  # skip initial 10 warm-up frames
    mean_ms = float(arr_t.mean())
    p50_ms = float(np.percentile(arr_t, 50))
    p95_ms = float(np.percentile(arr_t, 95))
    avg_w = int(np.mean([a[0] for a in areas[10:]]))
    avg_h = int(np.mean([a[1] for a in areas[10:]]))
    print(f"{label:<34s} | {mean_ms:7.2f} | {p50_ms:6.2f} | {p95_ms:6.2f} | {avg_w:4d}x{avg_h:<4d}")


# Build 4-layer expensive preset ("Cosmic Comet 4L")
comet_4l = copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])
comet_4l["id"] = "cosmic_comet_4l"
comet_4l["name"] = "Cosmic Comet 4L"
comet_4l["layers"].append(default_layer("l3_spiral", "Helix", "spiral"))
comet_4l["layers"].append(default_layer("l4_sparks", "Sparks", "sparks"))

run_case("1. Trails disabled", "nebula_silk", enabled=False)
run_case("2. Legacy trail (legacy_zwoop)", "legacy_zwoop", quality="balanced")
run_case("3. Single beam (laser_thread)", "laser_thread", quality="balanced")
run_case("4. Particle stream (stardust)", "stardust", quality="balanced")
run_case("5. 2-layer balanced (nebula_silk)", "nebula_silk", quality="balanced")
run_case("6. 4-layer heavy (Cosmic Comet)", comet_4l, quality="balanced")
run_case("7. High-speed streak (hyperdrive)", "hyperdrive", quality="balanced", speed_override=780.0)
run_case("8. Idle decay after motion", "nebula_silk", quality="balanced", idle_halfway=True)
run_case("9. Multi-monitor crossing", "aurora_threads", quality="balanced", cross_monitors=True)
run_case("10. Quality: Eco", "nebula_silk", quality="eco")
run_case("11. Quality: Balanced", "nebula_silk", quality="balanced")
run_case("12. Quality: High", "nebula_silk", quality="high")
run_case("13. Quality: Ultra", "nebula_silk", quality="ultra")
