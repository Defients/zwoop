# ZWOOP — The Living Desktop Creature

One creature. Infinite motion.

Zwoop is a single autonomous soft-bodied organism that lives on your
Windows desktop. It is not a pet simulator, not an assistant, and not a
cursor toy — it is a creature with its own agenda. It wanders, gets
curious about your cursor, shies away from sudden movement, rests when
you idle, and occasionally throws itself into spontaneous aerial
maneuvers: darts, arcs, swoops, figure-eights, dives.

It is a resurrection of the legacy *Kovy/Kovrycha* project — same soul,
new body. The original source is preserved untouched in this repository;
see `docs/LEGACY_AUDIT.md` for what was kept, fixed, and replaced.

## Run it

Requires Windows 10/11 and Python 3.10+ with numpy:

```
pip install numpy
cd <this repo>
python -m zwoop
```

or double-click / run the launcher (works from anywhere):

```
pythonw run_zwoop.pyw
```

A tray icon appears. Right-click it for control:

- **Hide creature / Pause** — instant control
- **Personality** — chill / playful / hyper / shy
- **Theme** — cosmos / orchid / lagoon / ember
- **Frame rate** — 30 / 60 / 120 fps
- **Effects** — 0 flat, 1 gradient, 2 full glow + trail
- **Monitor** — roam all displays or pin to one
- **Debug overlay** — shows particles, waypoint, state
- **Launch on login** — opt-in autostart (HKCU Run key)
- **Exit Zwoop**

## Command line

```
python -m zwoop [--config PATH] [--debug] [--personality hyper]
                [--fps 60] [--monitor 0] [--no-tray] [--version]
```

## Configuration

Config lives at `%APPDATA%\Zwoop\config.json` (created on first save —
the tray "Open config folder" entry takes you there). Every key has a
sane default; you only need to write what you change. Highlights:

```json
{
  "personality": "playful",
  "behavior": {
    "activity": 0.6, "curiosity": 0.6, "shyness": 0.3,
    "expressiveness": 0.7, "preferred_distance": 160.0,
    "rest_after_idle": 240.0, "maneuver_cooldown": 6.0
  },
  "render": { "fps": 60, "effects_level": 2, "theme": "cosmos",
              "opacity": 0.92, "trail": true, "window_size": 420 },
  "platform": { "monitor": "auto", "roam_monitors": true,
                "hide_on_fullscreen": true },
  "autostart": false,
  "debug": false
}
```

`platform.monitor` accepts `"auto"` (free-roam across all displays) or a
display index `0, 1, 2, ...`. The log file sits next to the config at
`%APPDATA%\Zwoop\zwoop.log`.

## How it behaves

- **WANDER** — drifts between waypoints with smooth steering; never
  static, never pattern-locked.
- **CURIOUS** — notices your cursor inside ~460px and drifts closer,
  keeping a polite stand-off distance. It investigates; it does not beg.
- **PERFORM** — spontaneous maneuvers with real physics: stored
  velocity, actual trajectories. Anti-repetition — it won't do the same
  trick twice in a row.
- **RECOVER** — after a startle or a hard knock it settles itself.
- **REST** — when you go idle for minutes, it calms down instead of
  performing for an empty chair.

Fast cursor movement inside ~170px startles it. A left-click is a jab
it feels. Fullscreen apps make it hide itself and it comes back when
they're done. It never takes input focus — the overlay is click-through.

## Architecture

```
zwoop/
  sim/          platform-agnostic simulation (numpy only, testable)
    body.py       spring soft-body: 1 core + 12-particle ring
    brain.py      state machine: WANDER/CURIOUS/PERFORM/RECOVER/REST
    steering.py   seek/flee/orbit + maneuver generators
    region.py     monitor-union geometry (any layout, negative coords)
    perception.py cursor tracker: position, speed, jerk detection
    world.py      fixed-step orchestration, deterministic seeds
  render/
    rasterizer.py metaball field -> glow shading -> premul BGRA
    theme.py      color identities
  platform_win/  ctypes-only Win32 (no pywin32 dependency)
    overlay.py    layered click-through window via UpdateLayeredWindow
    monitors.py   multi-monitor enum + fullscreen awareness
    input.py      cursor pos / idle time / button state
    tray.py       system-tray icon + menu
    autostart.py  HKCU Run key (opt-in)
    defs.py       Win32 signatures/constants
  app.py         single-thread owner: pump, sim, render, composite
  config.py      JSON config, deep-merge, personalities
tests/test_zwoop.py   21 automated tests
tools/bench.py        pipeline benchmark
tools/rastershot.py   headless frame dumps (docs/shots)
tools/screenshot.py   live desktop capture
```

Design rule: `zwoop/sim` and `zwoop/render` never import Win32 — the
creature can be fully simulated, tested, and screenshotted headlessly.

## Tests & tools

```
python -m unittest discover -s tests -v     # 21 tests
python tools/bench.py                        # perf numbers
python tools/rastershot.py                   # dump frames to docs/shots
```

## Legacy

Original files (`main.py`, `kovrycha.py`, `motion.py`, `renderer.py`,
`interaction.py`, `utils.py`, `minimal_kovrycha.py`,
`overlay_kovrycha.py`, `bas0c_renderer.py`, `basic_screen.py`,
`kovrycha.log`) are preserved exactly as found — archaeology, not
baggage. `docs/LEGACY_AUDIT.md` documents what each did, what was
broken, and what Zwoop inherited.
