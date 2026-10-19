# Changelog

All notable changes to **Zwoop — The Living Desktop Creature** are documented in this file.

## [1.1.0] — Trail Studio V1.0 (The Living Motion Effects Engine)

### Added
- **World-Space Trail Engine (`zwoop/trails/`):**
  - `TrailHistory` with virtual-desktop world coordinates, FPS-independent time/distance sampling, high-speed Hermite subdivision, and automatic teleport/stall/monitor-change discontinuity detection.
  - **10 Geometry Families (`zwoop/trails/geometry.py`):** `ribbon`, `beam`, `particles`, `smoke`, `sparks`, `segmented`, `spiral`, `echo` (deformation-preserving afterimage silhouettes), `branching` (procedural electric/fractal forks), and `legacy`.
  - **Multi-Layer Compositor:** Up to 4 independent layers per preset with per-layer priority, enable/disable, solo isolation, and explicit premultiplied-alpha blending (`alpha`, `add`, `screen`, `contrast`).
  - **Seeded Vectorized Particle Simulator (`zwoop/trails/particles.py`):** 7 particle shapes (`circle`, `star`, `diamond`, `streak`, `ring`, `puff`, `shard`), air drag, gravity/buoyancy, coherent curl turbulence, boundary bounce/fade, and shared global particle caps.
  - **Behavior & Motion Reactivity (`zwoop/trails/reactive.py`):** Maps speed, acceleration, turning curvature, behavioral state (`WANDER`, `CURIOUS`, `PERFORM`, `RECOVER`, `REST`, `STARTLE`, `EVADE`), and named maneuvers (`dive`, `dart`, `swoop`, `arc`, `figure8`, `corkscrew`) to smooth, attack/release-damped trail modulations and particle bursts.
  - **25 Bundled Presets (`zwoop/trails/presets.py`):** 24 distinct creative presets across 6 collections (*Cosmic*, *Elemental*, *Ethereal*, *Energetic*, *Playful*, *Experimental*) plus *Legacy Zwoop*, managed by `PresetStore` with atomic custom preset save/load, duplicate, rename, delete, favorites, and safe JSON import/export.
  - **Schema & Validation (`zwoop/trails/schema.py`):** Over 80 validated parameters across 9 groups with family applicability metadata and deterministic legacy configuration migration (`migrate_legacy_config`).
  - **Controlled Randomizer (`zwoop/trails/randomizer.py`):** 5 modes (`variation`, `remix`, `wild`, `palette_only`, `motion_only`), 8 lock categories, seeded determinism, undo history, and shareable recipe strings (`ZTS1:...`).
- **Dynamic Bounded Trail Overlay (`TrailOverlayWindow` in `zwoop/platform_win/overlay.py`):**
  - Dedicated click-through `WS_EX_LAYERED` surface positioned immediately behind Zwoop's creature window, updating only the quantized active bounding box of live trail effects and auto-hiding when empty or disabled.
- **Trail Studio UI (`zwoop/ui/trail_studio.py`):**
  - Full CosmoTech dark editor with Preset Gallery (cached real-engine thumbnails), Basic Mode, Advanced Mode (4-layer bar, interactive Multi-Stop Gradient Editor, 9 grouped parameter sub-tabs), Persistent Live Preview Dock across 8 demo flight paths, Management & Randomizer tab, and session Undo/Redo/Apply/Revert.
- **System Tray & CLI Integration:**
  - Added `Open Trail Studio...` and compact `Trails` submenu (Enable/Disable, Presets, Intensity, Quality, Clear) to the tray menu; double-clicking the tray icon opens Trail Studio.
  - Added `--studio` (`-s`) and `--preset` (`--trail-preset`) CLI flags.
- **Validation & Documentation:**
  - Added `tests/test_trail_studio.py` (15 comprehensive test suites; 36 total tests passing).
  - Added `docs/TRAIL_STUDIO_ARCHITECTURE.md`, `docs/TRAIL_STUDIO_USER_GUIDE.md`, `docs/TRAIL_STUDIO_PRESETS.md`, `docs/TRAIL_STUDIO_PERFORMANCE.md`, and `docs/shots/trail_showcase_25.png`.

## [1.0.0] — Resurrection of Kovy into Zwoop
- Replaced broken legacy pywin32/OpenGL stack with pure `ctypes` Win32 layered overlay, fixed-step `120 Hz` soft-body physics in real-time units, utility-driven behavioral brain, and quarter-res metaball rasterizer.
- Fixed tray menu callback wiring and calibrated default creature size to `31 px` base radius (`320×320` overlay).
