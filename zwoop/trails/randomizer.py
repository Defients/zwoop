"""Controlled, seeded randomization engine for Zwoop Trail Studio.

Modes:
  - variation     Modest organic adjustments to the current preset
  - remix         Changes compatible geometry and visual properties
  - wild          Experimental multi-layer combinations within safety budgets
  - palette_only  Preserves geometry/motion and generates harmonious color palettes
  - motion_only   Preserves colors/geometry and varies waves, turbulence, and reactivity

Locks:
  geometry, colors, length, layers, glow, motion, particles, quality
"""

from __future__ import annotations

import colorsys
import copy
import hashlib
from typing import Any

import numpy as np

from .schema import (
    BLEND_MODES,
    FADE_CURVES,
    GEOMETRY_FAMILIES,
    PARTICLE_SHAPES,
    default_layer,
    rgb_to_hex,
    validate_preset_dict,
)

RANDOMIZER_MODES = ("variation", "remix", "wild", "palette_only", "motion_only")
LOCK_KEYS = (
    "geometry",
    "colors",
    "length",
    "layers",
    "glow",
    "motion",
    "particles",
    "quality",
)

_CREATIVE_FAMILIES = (
    "ribbon",
    "beam",
    "particles",
    "smoke",
    "sparks",
    "segmented",
    "spiral",
    "echo",
    "branching",
)


def _seed_to_int(seed: int | str | None) -> int:
    if seed is None:
        return int(np.random.SeedSequence().entropy) & 0x7FFFFFFF
    if isinstance(seed, int):
        return abs(seed) & 0x7FFFFFFF
    s = str(seed).strip()
    if s.isdigit():
        return int(s) & 0x7FFFFFFF
    digest = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _harmonious_palette(rng: np.random.Generator, n_stops: int = 3) -> tuple[list[dict[str, Any]], str]:
    """Generate a cohesive Cosmotech / analogous / triadic gradient + halo color."""
    base_h = float(rng.uniform(0.0, 1.0))
    scheme = rng.choice(["analogous", "split", "triadic", "cosmic_duo"])
    stops = []
    for i in range(n_stops):
        u = i / max(1, n_stops - 1)
        if scheme == "analogous":
            h = (base_h + (u - 0.3) * 0.18) % 1.0
        elif scheme == "split":
            h = (base_h + u * 0.42) % 1.0
        elif scheme == "triadic":
            h = (base_h + i * 0.33) % 1.0
        else:  # cosmic_duo biased toward violet/cyan/magenta
            h = (0.72 + (u - 0.2) * 0.28 + float(rng.uniform(-0.08, 0.08))) % 1.0

        s = float(rng.uniform(0.62, 0.96)) * (0.65 if i == 0 else 1.0)
        v = float(rng.uniform(0.82, 1.0)) if i == 0 else float(rng.uniform(0.55, 0.92))
        rgb = colorsys.hsv_to_rgb(h, s, v)
        alpha = 1.0 if i == 0 else (0.0 if i == n_stops - 1 else float(rng.uniform(0.65, 0.92)))
        stops.append({
            "position": round(u, 2),
            "color": rgb_to_hex(rgb),
            "opacity": round(alpha, 2),
        })

    halo_rgb = colorsys.hsv_to_rgb((base_h + 0.05) % 1.0, 0.85, 0.85)
    return stops, rgb_to_hex(halo_rgb)


class TrailRandomizer:
    """Deterministic, lock-aware preset randomizer with undo history."""

    def __init__(self):
        self.undo_stack: list[dict[str, Any]] = []

    def push_undo(self, preset: dict[str, Any]) -> None:
        self.undo_stack.append(copy.deepcopy(preset))
        if len(self.undo_stack) > 25:
            self.undo_stack.pop(0)

    def pop_undo(self) -> dict[str, Any] | None:
        if not self.undo_stack:
            return None
        return self.undo_stack.pop()

    @staticmethod
    def encode_recipe(
        mode: str,
        seed: int | str,
        base_id: str,
        locks: dict[str, bool] | None = None,
    ) -> str:
        s_int = _seed_to_int(seed)
        l_map = locks or {}
        bits = "".join("1" if l_map.get(k, False) else "0" for k in LOCK_KEYS)
        return f"ZTS1:{mode}:{s_int}:{base_id}:{bits}"

    @staticmethod
    def decode_recipe(recipe: str) -> dict[str, Any]:
        parts = recipe.strip().split(":")
        if len(parts) != 5 or parts[0] != "ZTS1":
            raise ValueError("Invalid recipe format (expected ZTS1:mode:seed:base_id:locks)")
        _, mode, seed_s, base_id, bits = parts
        if mode not in RANDOMIZER_MODES:
            raise ValueError(f"Unknown randomizer mode: {mode}")
        locks = {k: (i < len(bits) and bits[i] == "1") for i, k in enumerate(LOCK_KEYS)}
        return {
            "mode": mode,
            "seed": int(seed_s),
            "base_id": base_id,
            "locks": locks,
        }

    def randomize(
        self,
        base_preset: dict[str, Any],
        mode: str = "variation",
        seed: int | str | None = None,
        locks: dict[str, bool] | None = None,
        record_undo: bool = True,
    ) -> tuple[dict[str, Any], int]:
        """Generate a valid randomized preset and return (new_preset, numeric_seed)."""
        if mode not in RANDOMIZER_MODES:
            mode = "variation"
        if record_undo:
            self.push_undo(base_preset)

        num_seed = _seed_to_int(seed)
        rng = np.random.default_rng(num_seed)
        lck = {k: bool((locks or {}).get(k, False)) for k in LOCK_KEYS}

        out = copy.deepcopy(base_preset)
        out["builtin"] = False
        out["category"] = "custom"

        if mode == "palette_only":
            lck["geometry"] = True
            lck["length"] = True
            lck["layers"] = True
            lck["motion"] = True
            lck["particles"] = True
        elif mode == "motion_only":
            lck["geometry"] = True
            lck["colors"] = True
            lck["layers"] = True
            lck["glow"] = True

        # 1. Layer count & composition changes (only in remix/wild when 'layers' unlocked)
        if not lck["layers"] and mode in ("remix", "wild"):
            target_n = int(rng.integers(1, 4 if mode == "remix" else 5))
            cur_layers = out.get("layers", [])
            while len(cur_layers) < target_n:
                idx = len(cur_layers) + 1
                fam = str(rng.choice(_CREATIVE_FAMILIES))
                cur_layers.append(default_layer(f"layer_{idx}", f"Layer {idx}", fam))
            if len(cur_layers) > target_n:
                cur_layers = cur_layers[:target_n]
            out["layers"] = cur_layers

        scale_mag = 0.18 if mode == "variation" else (0.45 if mode == "remix" else 0.75)

        # Shared particle budget guardrail across layers
        n_layers = max(1, len(out["layers"]))
        per_layer_p_cap = max(35, 180 // n_layers)

        for idx, lyr in enumerate(out["layers"]):
            lyr["id"] = f"layer_{idx + 1}"

            # ---- Geometry ---------------------------------------------------
            if not lck["geometry"]:
                if mode in ("remix", "wild"):
                    lyr["family"] = str(rng.choice(_CREATIVE_FAMILIES))
                lyr["width_px"] = float(np.clip(
                    lyr.get("width_px", 18.0) * rng.uniform(1.0 - scale_mag, 1.0 + scale_mag),
                    4.0, 44.0,
                ))
                lyr["head_width_px"] = float(np.clip(
                    lyr["width_px"] * rng.uniform(0.9, 1.35), 4.0, 52.0
                ))
                lyr["tail_width_px"] = float(np.clip(
                    lyr["width_px"] * rng.uniform(0.05, 0.35), 1.0, 18.0
                ))
                lyr["taper"] = float(np.clip(
                    lyr.get("taper", 0.8) + rng.uniform(-0.25, 0.25) * scale_mag, 0.2, 1.6
                ))
                lyr["sharpness"] = float(np.clip(
                    lyr.get("sharpness", 0.5) + rng.uniform(-0.3, 0.3) * scale_mag, 0.15, 0.92
                ))
                if lyr["family"] == "spiral":
                    lyr["strand_count"] = int(rng.integers(2, 4))
                elif lyr["family"] == "echo":
                    lyr["echo_count"] = int(rng.integers(4, 10))
                    lyr["segment_spacing_px"] = float(rng.uniform(22.0, 46.0))

            # ---- Length / Time ----------------------------------------------
            if not lck["length"]:
                lyr["lifetime_s"] = float(np.clip(
                    lyr.get("lifetime_s", 1.8) * rng.uniform(1.0 - scale_mag, 1.0 + scale_mag),
                    0.55, 3.6,
                ))
                lyr["fade_curve"] = str(rng.choice(FADE_CURVES))
                lyr["length_cap_px"] = float(np.clip(
                    lyr.get("length_cap_px", 900.0) * rng.uniform(0.75, 1.25),
                    300.0, 1500.0,
                ))

            # ---- Colors & Gradient ------------------------------------------
            if not lck["colors"]:
                if mode == "variation" and lyr.get("gradient_stops"):
                    shift = float(rng.uniform(-32.0, 32.0))
                    lyr["hue_offset"] = float(np.clip(lyr.get("hue_offset", 0.0) + shift, -180.0, 180.0))
                else:
                    n_stops = int(rng.integers(2, 5))
                    stops, halo_hex = _harmonious_palette(rng, n_stops=n_stops)
                    lyr["gradient_stops"] = stops
                    lyr["base_color"] = stops[0]["color"]
                    lyr["secondary_color"] = stops[-1]["color"]
                    lyr["hue_offset"] = 0.0
                    if not lck["glow"]:
                        lyr.setdefault("glow", {})["halo_color"] = halo_hex
                if mode in ("remix", "wild"):
                    lyr["blend_mode"] = str(rng.choice(["add", "add", "screen", "alpha"]))

            # ---- Glow (guarded against aggressive flashing) -----------------
            if not lck["glow"]:
                g = lyr.setdefault("glow", {})
                g["enabled"] = bool(rng.random() > 0.12)
                g["intensity"] = float(np.clip(
                    g.get("intensity", 0.65) * rng.uniform(0.75, 1.3), 0.25, 1.35
                ))
                g["radius_px"] = float(np.clip(
                    g.get("radius_px", 16.0) * rng.uniform(0.75, 1.3), 6.0, 32.0
                ))
                # Safe non-flashing pulse bounds
                if rng.random() < 0.35:
                    g["pulse_speed"] = float(rng.uniform(0.8, 3.2))
                    g["pulse_depth"] = float(rng.uniform(0.10, 0.35))
                else:
                    g["pulse_speed"] = 0.0
                    g["pulse_depth"] = 0.0

            # ---- Particles --------------------------------------------------
            if not lck["particles"]:
                p = lyr.setdefault("particles", {})
                if mode in ("remix", "wild"):
                    p["shape"] = str(rng.choice(PARTICLE_SHAPES))
                p["spawn_rate"] = float(np.clip(
                    p.get("spawn_rate", 36.0) * rng.uniform(0.7, 1.35), 14.0, 78.0
                ))
                p["max_particles"] = int(min(per_layer_p_cap, max(30, p.get("max_particles", 110))))
                p["size_px"] = float(np.clip(
                    p.get("size_px", 9.0) * rng.uniform(0.75, 1.3), 4.5, 22.0
                ))
                p["turbulence"] = float(np.clip(
                    p.get("turbulence", 45.0) + rng.uniform(-30.0, 40.0) * scale_mag, 5.0, 140.0
                ))
                p["gravity"] = float(np.clip(
                    p.get("gravity", -18.0) + rng.uniform(-35.0, 35.0) * scale_mag, -85.0, 65.0
                ))
                p["sparkle"] = float(np.clip(rng.uniform(0.1, 0.7), 0.0, 0.75))

            # ---- Motion -----------------------------------------------------
            if not lck["motion"]:
                m = lyr.setdefault("motion", {})
                m["wave_amplitude"] = float(np.clip(
                    m.get("wave_amplitude", 4.0) + rng.uniform(-6.0, 10.0) * scale_mag, 0.0, 24.0
                ))
                m["wave_frequency"] = float(np.clip(
                    m.get("wave_frequency", 2.5) * rng.uniform(0.8, 1.25), 0.8, 5.5
                ))
                m["spiral_radius"] = float(np.clip(
                    m.get("spiral_radius", 18.0) * rng.uniform(0.75, 1.3), 6.0, 34.0
                ))
                m["spiral_speed"] = float(np.clip(
                    m.get("spiral_speed", 4.0) * rng.uniform(0.75, 1.3), -6.5, 6.5
                ))
                m["curl_noise"] = float(np.clip(
                    m.get("curl_noise", 4.0) + rng.uniform(-4.0, 8.0) * scale_mag, 0.0, 22.0
                ))

        if not lck["motion"]:
            beh = out.setdefault("behavior", {})
            beh["speed_to_length"] = float(np.clip(rng.uniform(0.45, 1.35), 0.2, 1.6))
            beh["accel_to_burst"] = float(np.clip(rng.uniform(0.40, 1.25), 0.1, 1.5))
            beh["curvature_to_spiral"] = float(np.clip(rng.uniform(0.30, 1.15), 0.1, 1.5))

        return validate_preset_dict(out, strict=False), num_seed
