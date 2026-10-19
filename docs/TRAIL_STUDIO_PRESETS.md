# Zwoop Trail Studio V1.0 — Bundled Preset Catalog (25 Presets)

All 25 bundled presets are data-driven, immutable definitions in `zwoop/trails/presets.py`, validated by `validate_preset_dict()` against `PARAM_SCHEMA`. Visual showcase rendered directly by `TrailEngine` + `Rasterizer` is saved at `docs/shots/trail_showcase_25.png`.

---

## 1. Cosmic Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 1 | `nebula_silk` | **Nebula Silk** | L1: `ribbon` (Violet Silk)<br>L2: `particles` (`star` Cyan Shimmer) | `add` + `add` | `light` | Broad, smooth purple-to-cyan silk ribbon with gentle wave modulation and twinkling cyan starlight dust. |
| 2 | `astral_wake` | **Astral Wake** | L1: `ribbon` (Deep Space Wake)<br>L2: `beam` (Delicate Core Thread) | `alpha` + `add` | `light` | Wide deep-indigo translucent wake (`3.2s` lifespan) bisected by a razor-thin luminous white-aquamarine core beam. |
| 3 | `stardust` | **Stardust** | L1: `particles` (`star` Shimmering Stars) | `add` | `light` | Scattered 4-pointed starlight particles with wide size variation (`0.60`), high scintillation (`sparkle=0.75`), and gentle upward buoyancy. |
| 4 | `event_horizon` | **Event Horizon** | L1: `ribbon` (Relativistic Rim)<br>L2: `ribbon` (Singularity Core) | `add` + `contrast` | `light` | Uses `contrast` blending on Layer 2 (`priority=1`) to carve a dark obsidian singularity core inside a blazing amber-violet accretion halo. |

---

## 2. Elemental Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 5 | `solar_flare` | **Solar Flare** | L1: `ribbon` (Solar Corona)<br>L2: `sparks` (`streak` Prominence Sparks) | `add` + `add` | `moderate` | Organic width-modulated coronal ribbon paired with high-velocity directional streaks and strong acceleration burst coupling (`accel_to_burst=1.3`). |
| 6 | `frostwake` | **Frostwake** | L1: `spiral` (2-Strand Glacial Helix)<br>L2: `particles` (`diamond` Ice Shards) | `add` + `add` | `moderate` | Interwoven icy cyan double helix shedding spinning diamond crystals that slowly settle downward (`gravity=+14`). |
| 7 | `storm_arc` | **Storm Arc** | L1: `branching` (High-Voltage Conduit)<br>L2: `sparks` (`streak` Discharge Sparks) | `add` + `add` | `light` | Electric jittered spline with procedural side-fork lightning branches (`branching`), rapid `6.5 Hz` halo pulsation, and omnidirectional spark bursts. |
| 8 | `ember_drift` | **Ember Drift** | L1: `smoke` (`puff` Smoldering Plume)<br>L2: `particles` (`circle` Floating Embers) | `alpha` + `add` | `moderate` | Expanding dark-crimson smoke puffs underneath buoyant golden-orange cinders (`gravity=-65`, `turbulence=95`) that swirl upward as they cool. |

---

## 3. Ethereal Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 9 | `ghost_veil` | **Ghost Veil** | L1: `echo` (8 Phantom Silhouettes)<br>L2: `ribbon` (Veil Gauze) | `add` + `screen` | `light` | Deformation-preserving hollow afterimage silhouettes of Zwoop's soft body (`echo_count=8`) draped in a soft screen-blended ectoplasmic gauze. |
| 10 | `aurora_threads` | **Aurora Threads** | L1: `ribbon` (`strand_count=3` Borealis) | `add` | `light` | Three parallel waving Borealis curtains with continuous hue cycling (`0.12 Hz`) and world-space curl drift. |
| 11 | `moon_mist` | **Moon Mist** | L1: `smoke` (`puff` Lunar Mist Puffs) | `screen` | `minimal` | Low-distraction, expanding silver-lavender vapor wisps (`growth_rate=0.95`) with restrained opacity (`0.52`) and calm startle response. |
| 12 | `spirit_ribbon` | **Spirit Ribbon** | L1: `smoke` (`puff` Spirit Aura Haze)<br>L2: `ribbon` (Luminous Filament) | `add` + `add` | `light` | Crisp white-cyan filament (`width_px=8`) floating above a soft billowing lavender-cyan mist bed. |

---

## 4. Energetic Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 13 | `plasma_jet` | **Plasma Jet** | L1: `beam` (Plasma Core Beam)<br>L2: `sparks` (`streak` Ionized Exhaust) | `add` + `add` | `light` | High-temperature magenta-cyan jet core (`core_intensity=1.4`, `velocity_color_mod=0.65`) with tight directional exhaust streaks (`spread=45°`). |
| 14 | `ion_pulse` | **Ion Pulse** | L1: `beam` (Harmonic Beam)<br>L2: `segmented` (`ring` Ion Ring Nodes) | `add` + `add` | `light` | Pulsating cyan-violet energy beam (`pulse_speed=4.5 Hz`) punctuated by evenly spaced hollow ring nodes (`segment_spacing_px=26`). |
| 15 | `laser_thread` | **Laser Thread** | L1: `beam` (Coherent Laser) | `add` | `minimal` | Ultra-crisp (`sharpness=0.95`, `width_px=6`) coherent neon-magenta optical filament with intense white inner core (`core_intensity=1.6`). |
| 16 | `hyperdrive` | **Hyperdrive** | L1: `beam` (Slipstream Core)<br>L2: `sparks` (`streak` Relativistic Streaks) | `add` + `add` | `moderate` | Extreme speed-reactive elongation (`speed_to_length=1.65`, `length_cap_px=1500`) that stays compact at cruise and stretches dramatically during dives/darts. |

---

## 5. Playful Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 17 | `pixie_dust` | **Pixie Dust** | L1: `particles` (`star` Fairy Glitter) | `add` | `light` | High-spin (`140 deg/s`), color-cycling fairy stars with wide hue variance (`0.28`) and lively scintillation (`sparkle=0.85`). |
| 18 | `bubble_pop` | **Bubble Pop** | L1: `particles` (`ring` Iridescent Bubbles) | `screen` | `light` | Specular-highlighted hollow soap bubbles (`shape=ring`) that expand (`growth_rate=1.15`), float upward (`gravity=-55`), and pop with `expo` fade. |
| 19 | `confetti_comet` | **Confetti Comet** | L1: `ribbon` (Comet Streamer)<br>L2: `particles` (`shard` Tumbling Confetti) | `add` + `alpha` | `moderate` | Waving rainbow streamer accompanied by tumbling, gravity-falling polygonal confetti shards (`hue_variance=0.65`, `angular_velocity=240 deg/s`). |
| 20 | `candy_swirl` | **Candy Swirl** | L1: `spiral` (`strand_count=3` Pastel Braid) | `add` | `light` | Three pastel-neon strands braided in a tight 3D-shaded helix (`spiral_radius=22`, `spiral_speed=5.2 rad/s`). |

---

## 6. Experimental Collection (4)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 21 | `double_helix` | **Double Helix** | L1: `spiral` (2 Counter-Rotating Strands)<br>L2: `segmented` (`diamond` Base-Pair Rungs) | `add` + `add` | `moderate` | Bio-luminescent cyan-magenta DNA double helix with discrete yellow-cyan diamond rung markers along the central axis. |
| 22 | `fractal_echo` | **Fractal Echo** | L1: `branching` (Recursive Branches)<br>L2: `echo` (6 Harmonic Afterimages) | `add` + `add` | `moderate` | Combines procedural branching energy forks with spaced soft-body afterimage silhouettes. |
| 23 | `quantum_scatter` | **Quantum Scatter** | L1: `segmented` (`diamond` Phase Lattice)<br>L2: `particles` (`shard` Quantum Quanta) | `add` + `add` | `moderate` | Wave-displaced discrete lattice nodes paired with high-turbulence (`120 px/s²`) shards that burst outward on acceleration. |
| 24 | `ink_in_water` | **Ink in Water** | L1: `smoke` (`puff` Diffusing Ink Plume)<br>L2: `ribbon` (Calligraphic Tendril) | `contrast` + `contrast` | `moderate` | Uses `contrast` blending and strong organic curl (`curl_noise=18`) to render dark-indigo calligraphic ink that diffuses into luminous cyan edges. |

---

## 7. Legacy Collection (1)

| # | ID | Name | Layers & Geometry Families | Blend Modes | Perf Class | Distinctive Visual & Motion Character |
|---|---|---|---|---|---|---|
| 25 | `legacy_zwoop` | **Legacy Zwoop** | L1: `legacy` (Original Metaball Swoosh) | `add` | `minimal` | Reproduces the original speed-gated (`speed > 200`), short (`0.40s`), theme-synchronized swoosh AND enables the classic metaball-field tail inside `Rasterizer`. |
