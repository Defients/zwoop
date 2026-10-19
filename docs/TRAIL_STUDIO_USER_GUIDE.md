# Zwoop Trail Studio V1.0 — User Guide

Trail Studio transforms Zwoop's motion into an expressive, customizable visual language while keeping Zwoop's soft-body physics and click-through desktop behavior completely intact.

---

## 1. Launching Zwoop & Trail Studio

### Run Zwoop (Standard Desktop Mode)
```bash
python -m zwoop
# or windowless via the self-locating launcher:
pythonw run_zwoop.pyw
```

### Open Trail Studio Directly on Launch
```bash
python -m zwoop --studio
# or launch with a specific preset:
python -m zwoop --preset solar_flare --studio
```

### Open Trail Studio from the System Tray
- **Double-click** the Zwoop violet orb icon in the Windows system tray, OR
- **Right-click** the tray icon and choose **Open Trail Studio...** (or navigate into the **Trails** submenu for quick toggles, presets, intensity, quality, and trail clearing).

---

## 2. Navigating Trail Studio

Trail Studio uses a dark **CosmoTech** interface divided into a 5-tab workspace on the left and a **Persistent Live Preview Dock** on the right:

### Tab 1: Presets (25 Bundled + User Library)
- Browse all **25 bundled presets** across 7 collections (*Cosmic*, *Elemental*, *Ethereal*, *Energetic*, *Playful*, *Experimental*, and *Legacy*) plus any custom presets you save or import.
- Each card displays a real engine-rendered thumbnail, layer count, performance class badge (`minimal`, `light`, `moderate`, `heavy`), description, and a **★ Favorite** star toggle.
- Filter by collection, search by keyword or geometry family, or sort by Category, Name, or Performance.

### Tab 2: Basic Mode
Designed for rapid adjustments without layer management complexity:
- **Primary Trail Style:** Switch the main layer between `ribbon`, `beam`, `particles`, `smoke`, `sparks`, `segmented`, `spiral`, `echo`, `branching`, or `legacy`.
- **Primary Head Color & Secondary Tail Color:** Quick color pickers that automatically update the gradient endpoints.
- **Sliders:** Overall Intensity, Global Opacity, Trail Length (Lifespan), Trail Width, Glow Luminance, and Speed Reactivity.
- **Performance Quality:** Choose `eco`, `balanced`, `high`, `ultra`, or `auto`.
- **Accessibility Toggles:**
  - *React to Zwoop's Movement & Behavior States*
  - *Reduced Motion* (dampens waves, spins, jitter, and sudden bursts)
  - *Reduced Flashing / Sparkle* (suppresses high-frequency pulses and twinkle)

### Tab 3: Advanced & Layers
Full creative control over multi-layer effects and over 80 schema-validated parameters:
- **Layer Bar (1–4 Layers):**
  - Click a layer button (`L1..L4`) to select it; click the currently selected layer button again to toggle its enabled state (`✓` / `○`).
  - Use **+ Add**, **Dup**, **Del**, **↑ / ↓** (reorder), **Solo** (isolate one layer in preview and on desktop), **Rename**, **Copy**, **Paste**, and **Reset**.
- **Multi-Stop Gradient Editor:**
  - Click or drag stops directly on the interactive gradient bar (`0.0 .. 1.0`).
  - Add up to 12 stops, remove stops, adjust stop position, `#RRGGBB` hex color, or per-stop opacity, or apply one of the built-in **Preset Palettes**.
- **Grouped Parameter Tabs (Family-Aware):**
  - *Geometry*, *Time & Fade*, *Color*, *Blend*, *Glow & Halo*, *Particles*, *Motion & Waves*, *Behavior Matrix*, and *Quality & Budget*.
  - Controls that do not apply to the active layer's geometry family are automatically hidden so you only see relevant parameters.

### Tab 4: Preview & Reactivity
- Choose from **8 deterministic demonstration flight paths**:
  - `figure_eight`, `gentle_drift`, `fast_dash`, `swoop`, `dive`, `circular_orbit`, `erratic_startle`, and `rest_hover`.
- Change the preview background (`deep_space`, `desktop_dark`, `grid`, `light_slate`), adjust simulation speed (`0.2x .. 2.0x`), pause, or **scrub the timeline** (`0.0s .. 8.0s`).
- Inspect live telemetry: active behavioral state, maneuver, smoothed reactive multipliers (`Intensity`, `Length`, `Glow`), active sample/particle counts, and render frame time in milliseconds.

### Tab 5: Manage & Randomize
- **Preset Management:**
  - **Save As New Preset...** saves your current working configuration into `%APPDATA%\Zwoop\presets\` without ever mutating bundled presets.
  - **Duplicate**, **Rename Custom**, and **Delete Custom** manage your personal library.
  - **Import Preset (.json)...** and **Export Preset (.json)...** let you share validated JSON presets safely.
- **Controlled Randomizer:**
  - **5 Modes:** `variation` (subtle tweaks), `remix` (new compatible geometry/visuals), `wild` (experimental multi-layer builds within safety budgets), `palette_only` (new harmonious color schemes), and `motion_only` (waves, turbulence, and reactivity).
  - **8 Parameter Locks:** Check `Geometry`, `Colors`, `Length`, `Layers`, `Glow`, `Motion`, `Particles`, or `Quality` to keep those aspects untouched during randomization.
  - **Shareable Recipe Codes:** Every roll produces a deterministic recipe string (`ZTS1:<mode>:<seed>:<base_id>:<locks>`) that anyone can paste and apply to reproduce the exact same effect.

---

## 3. Bottom Action Bar & Safe Editing
- **Live Desktop Preview** (top right): When checked, adjustments immediately appear on Zwoop on your desktop.
- **Undo / Redo:** Step backward or forward through up to 40 editing actions in your session.
- **Revert:** Discard unsaved session changes and return to the last applied state.
- **Reset to Bundled:** Restore a modified built-in preset back to its factory definition.
- **Clear Trails:** Immediately wipe all active trail history and particles from both preview and desktop.
