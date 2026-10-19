"""Benchmark the Zwoop pipeline: sim step, rasterize, composite.

    python tools/bench.py [seconds]

Measures CPU-side costs only (the DIB upload is driver-internal).
Reports per-stage ms and projected frame cost at 30/60/120 fps.
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, ".")
from zwoop.sim.region import Region, Rect
from zwoop.sim.world import Sim
from zwoop.sim.brain import Params
from zwoop.render.rasterizer import Rasterizer

SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
W = 420

region = Region([Rect(0, 0, 2560, 1440)])
sim = Sim(region, Params(), seed=5)
rast = Rasterizer(W, effects=2)
frame = np.zeros((W, W, 4), np.uint8)

# ---- sim step benchmark --------------------------------------------
h = 1.0 / 120.0
n = int(SECS * 120)
t0 = time.perf_counter()
for i in range(n):
    sim.feed_cursor((1280 + 300 * np.sin(i * h), 700))
    sim.step(h)
sim_t = (time.perf_counter() - t0) / n * 1000

# ---- raster benchmark (at several speeds) ---------------------------
snap = sim.snapshot()
c = snap["center"]
origin = (c[0] - W / 2, c[1] - W / 2)

for label, speed in (("idle", 0), ("moving", 600)):
    snap2 = dict(snap)
    snap2["vel"] = snap["vel"].copy()
    snap2["vel"][0] = [speed, speed * 0.3]
    snap2["speed"] = float(speed)
    t0 = time.perf_counter()
    reps = 240
    for _ in range(reps):
        rast.render(frame, snap2, origin, dt=1 / 60)
    ms = (time.perf_counter() - t0) / reps * 1000
    print(f"raster[{label:6s}]: {ms:6.2f} ms/frame")

print(f"sim step : {sim_t:6.3f} ms/step  ({n} steps)")
print()
print("projected per-frame cost (sim share = steps_per_frame * sim_t):")
for fps in (30, 60, 120):
    # measure raster once more for the table
    t0 = time.perf_counter()
    for _ in range(60):
        rast.render(frame, snap, origin, dt=1 / fps)
    r_ms = (time.perf_counter() - t0) / 60 * 1000
    s_ms = (120.0 / fps) * sim_t
    print(f"  @{fps:3d}fps: raster {r_ms:5.2f} + sim {s_ms:5.2f} = "
          f"{r_ms + s_ms:5.2f} ms  ({(r_ms + s_ms) / (1000 / fps) * 100:4.1f}% "
          f"of frame)")
