# Zwoop — Legacy Audit (Kovy / Kovrycha)

Audit of the original codebase preserved under `legacy/`.
Evidence level legend: **[verified]** = demonstrated by execution or certain static proof;
**[strong]** = high-confidence static analysis; **[provisional]** = inferred, needs runtime check.

---

## 1. Project inventory and execution paths

| File | Role | Status in the main app |
|------|------|------------------------|
| `legacy/main.py` | CLI entry point (`--config`, `--debug`, `--log`, `--minimize`, `--version`) | Canonical entry: `main() -> Kovrycha.start()` |
| `legacy/kovrycha.py` | App coordinator: config, threads (physics/monitor/pulse), mood | Core of the "full" build |
| `legacy/motion.py` | `PhysicsEngine` — 16-particle soft body (1 core + 15 ring), radial+ring+cross springs | Used by full build |
| `legacy/renderer.py` | Win32 layered window + OpenGL metaball shader | Used by full build |
| `legacy/interaction.py` | `SystemMonitor` — 4 threads (window/activity/cursor/session), cursor pattern detection, `EventSystem` (duplicate) | Used by full build; its `EventSystem` is dead code |
| `legacy/utils.py` | `ScreenManager`, `ConfigManager`, `PerformanceTracker`, `EventSystem` | Used by full build |
| `legacy/overlay_kovrycha.py` | Standalone Tkinter overlay (`-transparentcolor` black + WS_EX_TRANSPARENT), own copy of physics | Independent alternative — run directly |
| `legacy/minimal_kovrycha.py` | Standalone Tkinter window (NOT click-through, NOT transparent color key — just `-alpha` on whole window), own physics copy | Independent alternative — debug toy |
| `legacy/basic_screen.py` | `ScreenManager` without `EnumDisplayMonitors` (GetSystemMetrics primary only) | Drop-in replacement for `utils.ScreenManager`; not wired in by default |
| `legacy/bas0c_renderer.py` | Tkinter `SlimeRenderer` with same interface as the GL renderer | Drop-in replacement for `renderer.SlimeRenderer`; not wired in by default |

Orphaned bytecode in `__pycache__/` (Python 3.8): `blob.py` + `ui.py` — a *different, earlier* creature:
a PyQt6 window titled "Kovrycha - The Sentient Slime" containing a perimeter-point blob
(`rest_points`, `velocities`, `damping`, cohesion toward rest shape) drawn with
`QPainterPath.quadTo` smooth curve, `QRadialGradient` glow, and `mousePressEvent`/
`mouseMoveEvent` -> `apply_force_to_nearest_point` direct poking. Sources are lost;
only `.pyc` strings remain. This predates the "Kovrycha" multi-file architecture and is
the only legacy artifact with *direct mouse poking* — plausible source of the remembered
"creature reacts to the mouse" impression.

## 2. What actually ran — dependency graph (full build)

```
main.py
 └─ kovrycha.Kovrycha
      ├─ utils.ConfigManager         (json, ~/.kovrycha/config.json)
      ├─ utils.ScreenManager         (win32gui.EnumDisplayMonitors  ← BUG, see 4.1)
      ├─ utils.PerformanceTracker    (psutil, optional)
      ├─ utils.EventSystem           (sync emit, no locks)
      ├─ interaction.SystemMonitor   (4 daemon threads, started INSIDE __init__)
      ├─ motion.PhysicsEngine        (numpy particle/spring soft body)
      └─ renderer.SlimeRenderer      (Win32 layered window + WGL OpenGL)
           run() on main thread; physics/monitor/pulse on worker threads
```

Threads created in `Kovrycha.__init__` (start during construction):
`PhysicsThread` (90 Hz), `MonitorThread` (1 Hz), `PulseThread` (20 Hz),
plus SystemMonitor's own `window`/`activity`/`cursor`/`session` threads (also
started inside `SystemMonitor.__init__`).

## 3. Movement DNA — what the original engine actually does

`motion.py` structure (preserved as the conceptual seed for Zwoop):
- 1 heavy core (mass 2.5, radius 45) + 15 outer particles (mass 1, radius ~29)
  on an r=90 ring; springs: core→outer (k=elasticity), ring neighbors (0.75k),
  opposite cross-springs (0.4k); spring damping 0.2 along the spring axis.
- Forces: Hooke springs + axial damping; gravity 0.08 with per-particle sinusoidal
  "hover" lift; quadratic drag 0.015; trig-noise wander; core-cohesion ("gather");
  random core impulses (upward-biased); cursor avoidance r<180 px with e^1.5
  falloff and a "ghost phase" gimmick; window-rect avoidance zones; soft boundary
  push (70 px margin); edge clamp+bounce (0.7) + probabilistic stickiness.
- Mood multipliers (calm/playful/sleepy/excited) retune wander/impulse/elasticity/
  hover/gather.
- Semi-implicit Euler (comment claims Verlet — wrong), velocity clamp 60,
  pairwise particle-circle collision with restitution, core-distance hard clamp.

**Cursor relationship: avoidance ONLY — there is no pursuit/follow code anywhere in
the surviving sources.** Verified by full-text search of all legacy modules: the only
cursor force is repulsive (`particle - cursor`). Any memory of following is emergent
wander near the cursor, or the lost PyQt6 blob's poke-by-drag.

## 4. Defect catalog (root causes)

### 4.1 ScreenManager — wrong module for EnumDisplayMonitors  [verified]
`utils.py:57` calls `win32gui.EnumDisplayMonitors`. In pywin32 the function lives in
`win32api`, not `win32gui` — `AttributeError` every launch (see `legacy/kovrycha.log`
line 4), leaving `monitors` empty; the fallback default monitor is then used
(1920×1080 assumption). `basic_screen.py` was written as the workaround.

### 4.2 Initialization-order race: monitor threads outlive `self.physics`  [verified]
`interaction.py:99` starts 4 threads inside `SystemMonitor.__init__`, which runs at
`kovrycha.py:86` — **before** `self.physics` is assigned at line 92. The window-change
callback hits `self.physics.set_avoidance_zone` → `AttributeError`, logged in
`kovrycha.log` line 15 ("Error getting window info: 'Kovrycha' object has no
attribute 'physics'"). Same race applies to `self.events.emit("pulse")` handlers
touching the renderer before GL init.

### 4.3 Force/timestep unit mismatch — the creature is effectively frozen  [verified]
Forces were authored as *per-frame* magnitudes (impulse 1.5, wander 0.65…) but are
integrated in real seconds: `vel += (F/m)·dt; pos += vel·dt` — position response
scales with **dt²**. Measured headless at 90 Hz:
**core drifted 2.0 px in 10 s** of playful mood (≈0.2 px/s; ~8000× weaker than the
dt=1.0 regime the constants imply). Additionally the `vel *= 0.97` dampening is
per-step, so it silently strengthens with frame rate. This is the single biggest
reason the shipped app felt dead: the blob didn't roam.

### 4.4 OpenGL calls from threads that own no context  [strong]
`renderer.update_color`, `_on_pulse_event`, `_on_mood_change` call `glUseProgram`/
`glUniform*`. They are invoked from `PulseThread` (via `events.emit`) and
`PhysicsThread` (`Kovrycha._update_color_state` → `renderer.update_color`), while the
WGL context is current only on the main thread → undefined behavior / GL errors.
Same class of bug: `render_frame` iterates `physics.get_particles()` (list of dicts
holding numpy arrays) with zero synchronization while the physics thread mutates it.

### 4.5 Message-pump bug: PeekMessage without removal  [strong]
`renderer.py:674` `win32gui.PeekMessage(hwnd, 0, 0, 0)` peeks (PM_NOREMOVE) — the same
message is returned forever and re-dispatched in a hot loop until WM_DESTROY. Any
queued non-destroy message wedges the loop.

### 4.6 Window covers only the primary monitor; physics bounds cover all  [strong]
Overlay is created at the primary monitor's rect (`renderer.py:123-133`), but
boundary forces use `get_combined_bounds()` (all displays). On multi-monitor setups
the creature can be pushed outside the window and become invisible-but-alive.

### 4.7 `SetLayeredWindowAttributes` + `LWA_COLORKEY` ⇒ no real translucency  [strong]
The shader computes per-pixel alpha, but color-key transparency only makes *black*
pixels transparent — every drawn pixel is opaque. The "translucent slime" claim is
unrealized; any pixel rendered pure black would also punch a hole. Proper per-pixel
alpha requires `UpdateLayeredWindow` with a premultiplied DIB.

### 4.8 Shader `time` uniform = epoch seconds  [strong]
`glUniform1f(time, time.time())` — ~1.7e9 s exceeds fp32 precision; `sin(time*…)`
degenerates to noise → shimmering/flicker. Same for the Tk `time.time()*2` wobble
(fine — Python float64) but GL side is broken.

### 4.9 Mood multipliers compound destructively  [verified]
`_adjust_behavior()` mutates `self.gravity *= 0.7` etc. on every mood change; only
the `calm` branch restores defaults. Cycling excited↔playful multiplies gravity
repeatedly (0.7·0.5·0.7·0.5…) — parameters drift away from config over time.

### 4.10 Shader mood uniform always "calm" at init  [strong]
`mood_values.get("calm", 0)` — literal `"calm"` key instead of current mood
(`renderer.py:489`).

### 4.11 `ConfigManager.DEFAULT_CONFIG` shallow copy shares nested dicts  [verified]
`self.config = self.DEFAULT_CONFIG.copy()` — mutations via `set()` or `_update_dict`
write into the class-level defaults, leaking across instances.

### 4.12 Misc
- `autostart: true` default in config — a persistence flag that nothing reads;
  silent opt-out default is contrary to opt-in policy (dead key). [strong]
- `GetAsyncKeyState` click counting inflates `mouse_clicks` every 50 ms while held. [strong]
- `pfd` used before SetPixelFormat validation; `c_float` relied on via
  `from OpenGL.GL import *` namespace pollution — fragile. [provisional]
- `EventSystem` duplicated in `interaction.py` (with history) — dead code. [verified]
- `win32com.client`, `win32security`, `win32ts`, `pythoncom` imported for one
  lock-check that has a ctypes fallback — heavy deps for marginal value. [verified]

## 5. Legacy behavior profile (provisional, from code + headless sim)

Because of §4.3, the shipped binary's observable behavior was: **a static blob at
screen center** with imperceptible drift, spring jiggle from noise, and cursor
repulsion too weak to notice (≈dt²-scaled). The *intended* profile (dt=1 regime,
extrapolated): drift ≈15 px/s wander, impulses ~1×/s playful, velocities clamped at
60 px/step — i.e. very fast, twitchy roaming with bouncy edges. Zwoop targets a
middle ground: physics in real px/s units, peak ~900 px/s, cruise 60–250 px/s.

## 6. What is worth preserving

- The soft-body topology (core + ring + chord + cross springs) — recognizable DNA.
- Metaball field rendering concept (r²/(d²+ε) sum, threshold silhouette).
- Color ideas (purple base, stretch→green→pink shift) — retargeted to the V1
  violet/magenta/lavender palette.
- Idle⇄playful coupling, avoidance zones, pattern detection (circles/zigzag) as
  *concepts* — reimplemented cleanly.
- `basic_screen.py`'s instinct: don't depend on pywin32 at all. Zwoop uses **pure
  ctypes** for every Win32 call — zero third-party platform deps.

## 7. Architecture decision (evidence → choice)

Chosen: **Python 3.15 + numpy, single-threaded app core, ctypes Win32 layered
window (`UpdateLayeredWindow`, per-pixel alpha, click-through), metaball field
rasterized by numpy into a small window that follows the creature.**

| Candidate | Verdict | Evidence |
|-----------|---------|----------|
| A. Keep OpenGL fullscreen overlay | Rejected | §4.4/4.5/4.6/4.7/4.8 — the GL layer held most of the crash risk and couldn't even produce real translucency; PyOpenGL on py3.15 adds risk. |
| B. Tkinter transparentcolor overlay | Rejected | Whole-window `-alpha` + 1-bit color key only; can't do soft alpha edges; `overlay_kovrycha.py` proves the limits. |
| C. Native rewrite (C++/Rust) | Rejected | Loses the tuned spring DNA and iteration speed; no evidence the workload needs it (sim+draw ≈ ms-scale). |
| **D. ctypes layered window + numpy DIB (chosen)** | **Adopted** | True per-pixel alpha & click-through; window tracks creature → no multi-monitor spanning bug; single thread ⇒ classes 4.2/4.4/4.5 of defects vanish; deps = numpy only. |

Trade-off accepted: the creature's window is bounded (~440 px box). That is a
feature — it constrains visual footprint and makes click-through exact.
