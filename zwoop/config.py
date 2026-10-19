"""Zwoop configuration: defaults, persistence, personality presets, and migration.

Config lives at %APPDATA%\\Zwoop\\config.json (fallback: ~/.zwoop/config.json).
Deep-merged over DEFAULTS — never mutates the defaults (legacy bug §4.11).
Saves atomically via temp-file replacement to prevent corruption on crash.
"""

import copy
import json
import logging
import os
import tempfile

from .trails.schema import default_trails_config, migrate_legacy_config

log = logging.getLogger("zwoop.config")

DEFAULTS = {
    "version": "1.1.0",
    "personality": "playful",          # chill | playful | hyper | shy | custom
    "creature": {
        "size": 1.0,                   # scale factor on body radius
        "particle_count": 13,          # 1 core + ring
        "base_radius": 31.0,           # px, creature body radius at size=1
    },
    "behavior": {
        "activity": 0.6,               # autonomous activity level 0..1
        "curiosity": 0.6,              # interest in the cursor 0..1
        "shyness": 0.3,                # avoidance strength 0..1
        "expressiveness": 0.7,         # maneuver frequency/drama 0..1
        "preferred_distance": 160.0,   # px stand-off when curious
        "interest_radius": 460.0,      # px; beyond this the cursor is boring
        "scare_radius": 170.0,         # px; inside this with fast cursor -> shy
        "rest_after_idle": 240.0,      # s of user idleness -> rest
        "maneuver_cooldown": 6.0,      # s minimum between big maneuvers
    },
    "render": {
        "fps": 60,                     # 30 | 60 | 120
        "effects_level": 2,            # 0 flat, 1 +gradient/rim, 2 +inner glow/trail
        "theme": "cosmos",             # cosmos | orchid | lagoon | ember
        "opacity": 0.92,
        "trail": True,
        "window_size": 320,            # overlay box; must comfortably hold the body
        "trails": default_trails_config(),
    },
    "sim": {
        "hz": 120,                     # fixed simulation step
    },
    "platform": {
        "monitor": "auto",             # "auto" (roam) or index like 0, 1, ...
        "roam_monitors": True,         # may cross to other displays
        "hide_on_fullscreen": True,
        "start_minimized_log": False,
    },
    "autostart": False,                # launch on login — strictly opt-in
    "debug": False,
}

PERSONALITIES = {
    "chill":    {"activity": 0.35, "curiosity": 0.35, "shyness": 0.35,
                 "expressiveness": 0.35, "maneuver_cooldown": 14.0},
    "playful":  {"activity": 0.6, "curiosity": 0.65, "shyness": 0.3,
                 "expressiveness": 0.7, "maneuver_cooldown": 7.0},
    "hyper":    {"activity": 0.9, "curiosity": 0.7, "shyness": 0.15,
                 "expressiveness": 0.95, "maneuver_cooldown": 3.5},
    "shy":      {"activity": 0.45, "curiosity": 0.4, "shyness": 0.8,
                 "expressiveness": 0.4, "maneuver_cooldown": 12.0,
                 "preferred_distance": 230.0, "scare_radius": 230.0},
}

DEFAULT_PATH = None


def default_config_path() -> str:
    global DEFAULT_PATH
    if DEFAULT_PATH is None:
        appdata = os.environ.get("APPDATA")
        root = os.path.join(appdata, "Zwoop") if appdata else \
            os.path.join(os.path.expanduser("~"), ".zwoop")
        DEFAULT_PATH = os.path.join(root, "config.json")
    return DEFAULT_PATH


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = {}
    for k, v in base.items():
        if k in overlay and isinstance(v, dict) and isinstance(overlay[k], dict):
            out[k] = _deep_merge(v, overlay[k])
        elif k in overlay:
            out[k] = copy.deepcopy(overlay[k])
        else:
            out[k] = copy.deepcopy(v)
    for k, v in overlay.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    return out


class Config:
    """Dict-backed settings with dotted access, migration, and atomic JSON persistence."""

    def __init__(self, path: str | None = None, overrides: dict | None = None):
        self.path = path or default_config_path()
        raw_loaded: dict = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    raw_loaded = loaded
                log.info("config loaded: %s", self.path)
            except Exception as e:
                log.warning("config load failed (%s); using defaults", e)

        if overrides and isinstance(overrides, dict):
            raw_loaded = _deep_merge(raw_loaded, overrides)

        migrated_input = migrate_legacy_config(raw_loaded) if raw_loaded else {}
        self.data = _deep_merge(DEFAULTS, migrated_input)
        self.data = migrate_legacy_config(self.data)

        preset = PERSONALITIES.get(self.get("personality", "playful"), {})
        self.data["behavior"] = _deep_merge(self.data["behavior"], preset)

    def get(self, dotted: str, default=None):
        node = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value):
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        if dotted == "render.trail":
            self.data.setdefault("render", {}).setdefault("trails", {})["enabled"] = bool(value)
        elif dotted == "render.trails.enabled":
            self.data.setdefault("render", {})["trail"] = bool(value)

    def apply_personality(self, name: str):
        if name in PERSONALITIES:
            self.set("personality", name)
            self.data["behavior"] = _deep_merge(
                copy.deepcopy(DEFAULTS["behavior"]), PERSONALITIES[name])

    def save(self):
        try:
            folder = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(folder, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix=".zwoop_cfg_", suffix=".tmp", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
            log.info("config saved: %s", self.path)
        except Exception as e:
            log.warning("config save failed: %s", e)
