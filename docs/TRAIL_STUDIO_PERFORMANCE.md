# Zwoop Trail Studio V1.0 — Performance Engineering Report

**Test Machine:** Windows 10/11 64-bit Workstation (4 physical monitors spanning `(-1080, -1080)` to `(4480, 1727)`, Python 3.15.0, NumPy 2.5.4)
**Benchmark Tool:** `python tools/bench.py 80` (80 frames per scenario at 60 Hz step, discarding first 10 warm-up frames)

---

## 1. Core Pipeline Baseline

| Stage | Measured Cost | Notes |
|---|---|---|
| **Fixed-Step Simulation (`120 Hz`)** | **`0.388 – 0.420 ms/step`** | Soft-body springs + brain + perception (~0.84 ms per 60 FPS frame) |
| **Creature Metaball Rasterizer (`320×320`)** | **`2.09 – 2.86 ms/frame`** | Quarter-res field + zero-allocation block-broadcast upsample |
| **`UpdateLayeredWindow` (`320×320`)** | **`0.156 ms/call`** | Creature window presentation |
| **`UpdateLayeredWindow` (`640×480` sub-rect)** | **`0.204 ms/call`** | Dynamic bounded trail window presentation |
| **Memory Footprint (`pythonw.exe` live)** | **`~46 – 54 MB` RSS** | Includes persistent `1600×1200` backing DIB (`7.3 MB`) + `320×320` creature DIB (`0.4 MB`) |

---

## 2. Section 12.6 Benchmark Matrix Results

Measured CPU time for `TrailEngine.step()` + `compute_active_bounds()` + `TrailEngine.render_into()` across all 13 benchmark scenarios:

| # | Scenario | Mean (ms) | p50 (ms) | p95 (ms) | Avg Active BBox (px) |
|---|---|---|---|---|---|
| 1 | **Trails disabled (`enabled=False`)** | **`0.00 ms`** | **`0.00 ms`** | **`0.00 ms`** | `0×0` (window hidden) |
| 2 | **Legacy trail (`legacy_zwoop`)** | **`4.52 ms`** | **`4.33 ms`** | `6.75 ms` | `358×304` |
| 3 | **Single beam (`laser_thread`)** | **`4.86 ms`** | **`5.11 ms`** | `7.44 ms` | `396×313` |
| 4 | **Single particle stream (`stardust`)** | **`7.73 ms`** | **`8.82 ms`** | `12.62 ms` | `397×321` |
| 5 | **2-layer balanced (`nebula_silk`)** | **`9.31 ms`** | **`9.45 ms`** | `15.06 ms` | `421×313` |
| 6 | **4-layer heavy (`Cosmic Comet 4L`)** | **`26.35 ms`** | **`26.58 ms`** | `42.52 ms` | `421×317` |
| 7 | **High-speed long streak (`hyperdrive` @ 780 px/s)** | **`24.27 ms`** | **`25.49 ms`** | `33.95 ms` | `631×425` |
| 8 | **Idle state with lingering trail decay** | **`10.92 ms`** | **`11.17 ms`** | `14.94 ms` | `386×293` $\rightarrow$ `0×0` |
| 9 | **Multi-monitor crossing (`aurora_threads`)** | **`18.97 ms`** | **`19.79 ms`** | `25.70 ms` | `778×400` |
| 10 | **Quality Mode: `Eco`** | **`12.09 ms`** | **`11.32 ms`** | `19.33 ms` | `419×313` |
| 11 | **Quality Mode: `Balanced`** | **`13.10 ms`** | **`13.16 ms`** | `22.49 ms` | `421×313` |
| 12 | **Quality Mode: `High`** | **`28.49 ms`** | **`25.82 ms`** | `51.72 ms` | `421×313` |
| 13 | **Quality Mode: `Ultra`** | **`32.18 ms`** | **`29.02 ms`** | `54.57 ms` | `421×313` |

---

## 3. Key Optimizations & Safeguards Implemented

1. **Zero-Overhead Disabled & Idle State:**
   When `trails.enabled == False` or after lingering trails finish decaying during `REST`, `compute_active_bounds()` returns `None`, `TrailOverlayWindow` calls `ShowWindow(SW_HIDE)`, and `0.00 ms` of CPU/DWM work is performed.
2. **Dynamic Quantized Bounding-Box Sub-Slicing:**
   Instead of clearing and shading a full-desktop buffer (`5560×2807`), `TrailEngine` computes the tight 16px-quantized bounding box around live samples and particles (averaging `396×313` during normal roaming) and uploads only that sub-rectangle from a pre-allocated backing DIB via `UpdateLayeredWindow`.
3. **Zero-Allocation In-Place Block-Broadcast Upsampling:**
   Replacing `np.repeat(np.repeat(obuf, rs, 0), rs, 1)` with `frame.reshape(ih, rs, iw, rs, 4)[:] = obuf[:, None, :, None, :]` eliminated two full-frame temporary array allocations per frame and reduced balanced 2-layer render time from `19.36 ms` down to **`9.31 ms`**.
4. **Arc-Length-Aware Segment Coalescing & Local Capsule BBoxes:**
   `resample_stroke()` spaces spline vertices every `~16 px` capped by the quality tier's `segment_cap` (`20` in `eco`, `32` in `balanced`), and `_rasterize_polyline()` evaluates each capsule segment strictly within its local `[iy0:iy1, ix0:ix1]` grid patch.
5. **Hysteresis-Protected Auto-Quality (`TrailProfiler`):**
   `TrailProfiler.update_auto_quality()` tracks a 45-frame rolling window. It steps down one quality tier if trail rendering exceeds budget for `>1.2s`, and waits `>4.0s` of sustained low load before stepping back up—preventing mode oscillation while protecting creature smoothness.
