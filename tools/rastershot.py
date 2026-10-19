"""Headless rasterizer check: step the sim, render frames, dump PNGs.

    python tools/rastershot.py [seconds] [outdir]
"""

import sys
import numpy as np
from PIL import Image

sys.path.insert(0, ".")
from zwoop.sim.region import Region, Rect
from zwoop.sim.world import Sim
from zwoop.sim.brain import Params
from zwoop.render.rasterizer import Rasterizer

W = 420
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/shots"
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0

region = Region([Rect(0, 0, 2560, 1440)])
sim = Sim(region, Params(), seed=3)
rast = Rasterizer(W, theme="cosmos", effects=2)
frame = np.zeros((W, W, 4), np.uint8)

# let the cursor hover near the creature so CURIOUS behaviors show
cx, cy = 1280.0, 720.0

dt = 1 / 120
n = int(SECS * 120)
saved = 0
for i in range(n):
    t = i * dt
    # cursor slowly circles mid-screen
    sim.feed_cursor((cx + 300 * np.sin(t * 0.4), cy + 220 * np.cos(t * 0.33)))
    sim.step(dt)
    if i % 90 == 0:  # every 0.75s of sim
        snap = sim.snapshot()
        c = snap["center"]
        origin = (c[0] - W / 2, c[1] - W / 2)
        rast.render(frame, snap, origin, dt=0.75)
        img = Image.fromarray(frame[:, :, [2, 1, 0]], "RGB")
        # put alpha into a checkerboard-free dark bg for viewing
        img.putalpha(Image.fromarray(frame[:, :, 3], "L"))
        img.save(f"{OUT}/r{saved:02d}.png")
        print(f"r{saved:02d} t={t:5.1f} state={snap['state']:8s} "
              f"speed={snap['speed']:4.0f} deform={snap['deform']:.2f} "
              f"pos=({c[0]:.0f},{c[1]:.0f})")
        saved += 1
