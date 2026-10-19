# ZWOOP — The Living Desktop Creature (+ Trail Studio V1.0)

One creature. Infinite motion.

Zwoop is a single autonomous soft-bodied organism that lives on your
Windows 10/11 desktop. It wanders, gets curious about your cursor, shies
away from sudden movement, rests when you idle, and throws itself into
spontaneous aerial maneuvers: darts, arcs, swoops, figure-eights, dives.

**New in v1.1.0 — Trail Studio V1.0 (The Living Motion Effects Engine):**
Zwoop now features a world-space, behavior-reactive, multi-layer trail
effects engine with **10 geometry families**, **25 bundled presets**, a
controlled **Randomizer**, and the **Trail Studio** interactive editor.

---

## Run It

Requires Windows 10/11 and Python 3.10+ with `numpy` (and `Pillow` for screenshot tools):

```bash
pip install numpy pillow
cd <this repo>
python -m zwoop
```

Open **Trail Studio** immediately on launch:

```bash
python -m zwoop --studio
# or launch with a specific trail preset:
python -m zwoop --preset solar_flare
```

Or run windowless from anywhere via the launcher shim:

```bash
pythonw run_zwoop.pyw
```

### System Tray Controls
- **Double-click** the Zwoop tray icon to open **Trail Studio**.
- **Right-click** the tray icon for:
  - **Open Trail Studio...**
  - **Trails** $\rightarrow$ Enable/Disable, Presets (Recently Used, Favorites, Featured), Intensity, Quality (`Eco` / `Balanced` / `High` / `Ultra` / `Auto`), Clear current trails
  - **Hide creature / Pause**
  - **Personality** (`chill` / `playful` / `hyper` / `shy`)
  - **Theme** (`cosmos` / `orchid` / `lagoon` / `ember`)
  - **Frame rate** (`30` / `60` / `120` fps)
  - **Monitor** (Roam all displays or pin to one)
  - **Debug overlay**, **Launch on login**, **Open config folder**, **Exit Zwoop**

---

## Trail Studio V1.0 Highlights

- **World-Space Persistent Trails:** Rendered on a dedicated click-through dynamic bounded `WS_EX_LAYERED` surface (`ZwoopTrailSurface`) positioned immediately behind Zwoop's body window—trails persist naturally across hundreds of pixels and multiple monitors without clipping at the creature's window boundary.
- **10 Geometry Families:** `ribbon`, `beam`, `particles`, `smoke`, `sparks`, `segmented`, `spiral`, `echo` (deformation-preserving afterimages), `branching` (electric/fractal forks), and `legacy`.
- **Up to 4 Independent Layers:** Reorder, solo, duplicate, copy/paste, and blend layers using premultiplied-alpha-safe `alpha`, `add`, `screen`, or `contrast` (dark-core) modes.
- **25 Bundled Presets across 7 Collections:**
  - *Cosmic:* `nebula_silk`, `astral_wake`, `stardust`, `event_horizon`
  - *Elemental:* `solar_flare`, `frostwake`, `storm_arc`, `ember_drift`
  - *Ethereal:* `ghost_veil`, `aurora_threads`, `moon_mist`, `spirit_ribbon`
  - *Energetic:* `plasma_jet`, `ion_pulse`, `laser_thread`, `hyperdrive`
  - *Playful:* `pixie_dust`, `bubble_pop`, `confetti_comet`, `candy_swirl`
  - *Experimental:* `double_helix`, `fractal_echo`, `quantum_scatter`, `ink_in_water`
  - *Legacy:* `legacy_zwoop`
- **Behavior & Motion Reactivity:** Trails respond smoothly (with independent attack/release damping) to speed, acceleration, turning curvature, behavioral states, and aerial maneuvers.
- **Controlled Randomizer:** 5 modes (`variation`, `remix`, `wild`, `palette_only`, `motion_only`), 8 lock categories, and shareable deterministic recipe codes (`ZTS1:...`).

---

## Documentation

- [`docs/TRAIL_STUDIO_ARCHITECTURE.md`](docs/TRAIL_STUDIO_ARCHITECTURE.md) — Baseline audit, compositor evaluation, blending math, and subsystem architecture
- [`docs/TRAIL_STUDIO_USER_GUIDE.md`](docs/TRAIL_STUDIO_USER_GUIDE.md) — Complete guide to Trail Studio tabs, gradient/layer editing, and randomizer recipes
- [`docs/TRAIL_STUDIO_PRESETS.md`](docs/TRAIL_STUDIO_PRESETS.md) — Full inventory of all 25 bundled presets and their distinctive geometry
- [`docs/TRAIL_STUDIO_PERFORMANCE.md`](docs/TRAIL_STUDIO_PERFORMANCE.md) — Empirical benchmark matrix across 13 scenarios and quality modes
- [`docs/LEGACY_AUDIT.md`](docs/LEGACY_AUDIT.md) — Original Kovy/Kovrycha source archaeology
- [`CHANGELOG.md`](CHANGELOG.md) — Release history

---

## Tests & Benchmarks

```bash
python -m unittest discover -s tests -v     # 36 automated tests (sim, brain, trails, studio)
python tools/bench.py 80                    # 13-scenario performance benchmark matrix
python tools/rastershot.py                  # headless frame dumps to docs/shots/
```
