# Zwoop Trail Studio V1.0 — Architecture & Baseline Audit

**Repository:** `https://github.com/Defients/zwoop`
**Baseline Reference SHA:** `3568f85b9d808c9731a6191f30398e3e46a3be71` (`main`)
**Target Platform:** Windows 10 / 11 (Python 3.15, NumPy 2.5.4, pure `ctypes` Win32 + `tkinter` UI)

---

## 1. Repository State & Baseline Audit

### 1.1 Verified Repository State
- **HEAD SHA:** `3568f85b9d808c9731a6191f30398e3e46a3be71`
- **Active Branch:** `main`
- **Working Tree:** Clean at start of audit
- **Entry Points:**
  - `python -m zwoop` (`zwoop/__main__.py`)
  - `pythonw run_zwoop.pyw` (self-locating Windows GUI launcher used by `HKCU\...\Run`)
- **Existing Test Suite:** `tests/test_zwoop.py` (21 tests covering soft-body invariants, brain transitions, multi-monitor union regions, maneuver registry, and deterministic replays)
- **Existing Benchmark Tooling:** `tools/bench.py`

### 1.2 Empirical Baseline Measurements
Measured on the target Windows 10/11 4-monitor workstation (`2560×1440` primary + 3 secondary displays, negative virtual coordinates `(-1080, -1080)` to `(4480, 1727)`):
- **Fixed-step simulation (`120 Hz`):** `~0.83 – 1.27 ms/step`
- **Creature rasterizer (`320×320` window, `res_scale=4`):**
  - `trail=False` (idle/moving): **`2.84 ms/frame`**
  - `trail=True` (14 metaball trail samples active): **`3.33 ms/frame`** (`+0.49 ms` delta)
- **`UpdateLayeredWindow` compositor cost by surface size:**
  - `320×320` (`400 KB`): **`0.156 ms/call`**
  - `640×640` (`1,600 KB`): **`0.248 ms/call`**
  - `960×960` (`3,600 KB`): **`0.435 ms/call`**
  - `1280×1280` (`6,400 KB`): **`0.682 ms/call`**
  - `1920×1920` (`14,400 KB`): **`2.625 ms/call`**
  - Sub-rectangle `UpdateLayeredWindow` on a persistent `1440×1440` backing DIB:
    - `256×256`: **`0.136 ms/call`**
    - `640×480`: **`0.204 ms/call`**
    - `1200×800`: **`0.557 ms/call`**

---

## 2. Reproduction & Characterization of the Existing Trail

The legacy built-in trail resides in `zwoop/render/rasterizer.py` (lines 62, 108–120):

```python
self.trail = deque(maxlen=14)          # (x,y) recent centers
...
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
```

### 2.1 Observed Defects & Failure Modes
1. **Hard 160 px Moving-Window Clipping:**
   Zwoop's overlay window (`320×320`) centers itself on `snap["center"]` every frame. Any trail geometry more than `160 px` from Zwoop's current center is outside the window bounds and cannot exist. At `700 px/s`, `160 px` is crossed in `0.22 seconds`.
2. **Frame-Rate-Dependent Lifespan & Sampling:**
   Samples are appended once per `render()` call with `maxlen=14`. At `30 FPS`, 14 samples span `467 ms`; at `120 FPS`, 14 samples span only `117 ms` and bunch tightly behind the core.
3. **Stale Sample Retention (`len(self.trail) > 3` bug):**
   When Zwoop slows below `280 px/s`, `self.trail.popleft()` stops when `len(self.trail) == 3`. Those 3 world-space coordinates remain in the deque indefinitely until the next high-speed burst, causing phantom field distortion when Zwoop later passes near those coordinates or next exceeds `280 px/s`.
4. **Hard Speed Gate (`speed > 280`):**
   Normal wandering (`p50 ~ 140–194 px/s`) produces zero trail; crossing `280 px/s` abruptly snaps the trail on.
5. **Hidden Coupling to `render.effects_level >= 2`:**
   Even when `render.trail` is `True`, setting `effects_level` to `0` or `1` silently disables the trail.
6. **Inability to Render Independent Colors, Layers, or Geometry:**
   Because trail points add scalar values into `self.field` prior to the `thr = 1.25` smoothstep, the trail cannot have its own palette, gradient, blend mode, or particle physics. Furthermore, a single trail sample contributes at most `0.055 * 2100 / 400 = 0.289` to the field—well below the visible alpha threshold (`1.25 - 0.42 = 0.83`), so isolated trail samples don't even appear unless stacked near the body's own field tail.
7. **No Discontinuity / Lifecycle Clearing:**
   Pausing, hiding, fullscreen auto-hide, or monitor changes do not clear `self.trail`.

---

## 3. World-Space Compositing Options Evaluated

To render persistent world-space trails (up to 5+ seconds or 1000+ pixels across multiple monitors) without enlarging the creature's tight `320×320` overlay to span the entire virtual desktop (`5560×2807` on the test rig = `62.4 MB` per frame buffer):

| Option | Description | Pros | Cons / Why Rejected or Adopted |
|---|---|---|---|
| **Option A — Full-Desktop Static Trail Overlay** | One giant `WS_EX_LAYERED` window spanning the entire virtual desktop union. | Simple world-to-window coordinate offset. | On a 4-monitor layout (`5560×2807`), a single 32-bit DIB is `62.4 MB`, and `UpdateLayeredWindow` takes `>15 ms/frame` just in kernel/DWM copy overhead. Rejected in pure form. |
| **Option B — Tiled Sparse Compositor** | Grid of fixed-size `WS_EX_LAYERED` tile windows across the desktop. | Bounds memory to active tiles. | Creating/showing/hiding multiple top-level layered HWNDs per second causes DWM window-list churn and seam artifacts across tile boundaries during blur/glow passes. |
| **Option C — Dynamic Bounded Trail Surface (with Persistent Backing DIB)** | Dedicated click-through `WS_EX_LAYERED` trail window (`ZwoopTrailSurface`) backed by a pre-allocated `MAX_W × MAX_H` DIB (`1600×1200`), dynamically positioned and sized each frame via `UpdateLayeredWindow(..., pptDst, psize)` to the tight quantized bounding box of active trail geometry + particles. | Zero DIB reallocation; `UpdateLayeredWindow` cost scales strictly with active trail bounding box (`0.13 ms` when compact, `0.55 ms` when spanning `1200×800`); auto-hides when trail is empty or disabled (`0.00 ms` overhead); supports multi-monitor negative coordinates seamlessly. | **Selected** as primary world-space compositor, combined with multi-scale internal rasterization (`res_scale` 2/3/4 per quality mode). |
| **Option D — GPU / OpenGL / DirectComposition Backend** | Hardware-accelerated shader overlay. | High fill-rate for full-screen particles. | Legacy Kovy failed in the field specifically due to OpenGL/driver/pywin32 fragility on transparent layered windows; adds binary dependencies and complicates headless deterministic testing. Rejected for V1.0. |

### 3.1 Selected Hybrid Architecture
1. **Two Layered Windows in Deterministic Z-Order:**
   - **`ZwoopTrailSurface` (`TrailOverlayWindow`):** Click-through `WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW` window positioned immediately *below* the creature window (`ZwoopSurface`).
   - **`ZwoopSurface` (`OverlayWindow`):** Existing `320×320` creature window on top, ensuring Zwoop's body is never buried under its own wake (while supporting optional `Legacy Zwoop` metaball-field coupling when the `legacy_zwoop` preset is active).
2. **Dynamic Bounding Box & Quantized Viewport:**
   - Every frame, `TrailEngine` computes the active world-space bounding box of all live trail samples, ribbons, echoes, and particles, plus glow padding.
   - The bounding box is quantized to `16 px` steps (preventing sub-pixel resampling shimmer) and clamped to the quality mode's maximum surface dimensions (up to `1600×1200`), anchored around the creature's recent trajectory.
   - Only the active `(w, h)` sub-slice of the backing DIB is cleared, shaded, and uploaded via `UpdateLayeredWindow`.
   - When `trails.enabled == False` or no samples/particles are alive, `TrailOverlayWindow` calls `set_visible(False)` and performs zero work.

---

## 4. Target Composition Order & Blending Mathematics

### 4.1 Logical Layer Ordering (Back to Front)
1. **Desktop background** (OS DWM)
2. **Older fading trail segments & wide glow halos** (drawn in `ZwoopTrailSurface`)
3. **Ordered Trail Layers (`Layer 1 .. Layer N`, up to 4 layers):**
   - Within each layer: wide outer glow pass $\rightarrow$ core geometry / ribbon / beam / mist / spiral / echo / segmented marks $\rightarrow$ layer particle / spark pass
4. **The living Zwoop organism** (`ZwoopSurface`, always crisp and legible above the trail)

### 4.2 Explicit Blending Mathematics (Premultiplied-Alpha Safe)
Windows `UpdateLayeredWindow` with `AC_SRC_OVER` and `AC_SRC_ALPHA` requires **premultiplied BGRA**:
$$\text{DIB pixel} = \lfloor 255 \cdot (B_{\text{pre}}, G_{\text{pre}}, R_{\text{pre}}, \alpha) \rfloor, \quad C_{\text{pre}} \le \alpha \in [0, 1]$$

When compositing Layer $L$ with straight color $C_s \in [0, 1]^3$ and effective opacity $\alpha_s \in [0, 1]$ onto the premultiplied accumulator $(C_d, \alpha_d)$:

1. **Normal (`alpha` / Porter-Duff Source-Over):**
   $$C_{\text{out}} = C_s \cdot \alpha_s + C_d \cdot (1 - \alpha_s)$$
   $$\alpha_{\text{out}} = \alpha_s + \alpha_d \cdot (1 - \alpha_s)$$

2. **Additive / Glow (`add` — Premultiplied-Alpha Safe):**
   In premultiplied space, increasing RGB while keeping $\alpha_{\text{out}}$ bounded produces true self-luminous emission over dark and light desktop backgrounds without dark halos:
   $$C_{\text{out}} = \min\!\big(1.0,\; C_d + C_s \cdot \alpha_s \cdot k_{\text{overlap}}\big)$$
   $$\alpha_{\text{out}} = \max\!\big(\alpha_d,\; \alpha_s + \alpha_d \cdot (1 - \alpha_s)\big), \quad C_{\text{out}} \le \alpha_{\text{out}}$$
   *(We enforce $C_{\text{out}} = \min(C_{\text{out}}, \alpha_{\text{out}})$ after accumulation or elevate $\alpha_{\text{out}} = \max(\alpha_{\text{out}}, \max_c C_{\text{out},c})$ so DWM never encounters invalid super-luminous premultiplied values on transparent pixels.)*

3. **Screen (`screen`):**
   $$C_{\text{out}} = C_d + C_s \cdot \alpha_s - C_d \odot (C_s \cdot \alpha_s)$$
   $$\alpha_{\text{out}} = \alpha_s + \alpha_d \cdot (1 - \alpha_s)$$

4. **Soft Contrast / Dark Core (`contrast` — used by *Event Horizon* & *Ink in Water*):**
   Allows a dark-centered wake with a bright rim by using high $\alpha_s$ with low $C_s$ in the core and luminous $C_s$ in the halo.

---

## 5. Subsystem Architecture

```
zwoop/
  trails/
    __init__.py
    schema.py        # 75+ validated parameters, LayerConfig, TrailConfig, Preset, migration
    history.py       # World-space TrailSample ring buffer, arc-length resampling, break detection
    particles.py     # Seeded deterministic particle & puff/spark/fragment simulator with caps
    reactive.py      # Snapshot signal extractor + attack/release smoothed behavior modifiers
    geometry.py      # Vectorized SDF & splat generators for all 9 geometry families
    presets.py       # 25 distinct presets (6 collections) + PresetStore (save/load/import/export)
    randomizer.py    # Controlled seeded randomizer (5 modes, 8 lock categories, undo stack)
    engine.py        # TrailEngine + TrailProfiler + AutoQuality hysteresis controller
  render/
    trail_overlay.py # Dynamic bounded premultiplied-BGRA compositor & multi-layer renderer
  ui/
    __init__.py
    trail_studio.py  # Full CosmoTech Trail Studio editor (Tkinter, non-blocking, live preview)
```

### 5.1 Threading & Lifecycle Contract
- `ZwoopApp` remains the single authoritative owner of simulation, rendering, and Win32 `UpdateLayeredWindow` calls.
- `TrailStudioWindow` runs inside the main thread via periodic non-blocking `root.update()` pumps integrated into `ZwoopApp`'s frame loop (with safe fallback standalone mode for `--studio` CLI), completely eliminating cross-thread GDI/Tkinter race conditions.
- When `paused`, `hidden`, or `awareness.should_hide` (fullscreen/lock) triggers, `TrailEngine.clear()` and `trail_overlay.set_visible(False)` execute immediately so no residual trail overlays ever linger over fullscreen games or locked sessions.
