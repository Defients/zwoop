"""Preset Library (25 distinct presets across 7 collections) & PresetStore."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from typing import Any

from .schema import (
    MAX_PAYLOAD_BYTES,
    SCHEMA_VERSION,
    ValidationError,
    default_behavior_modifiers,
    default_layer,
    validate_preset_dict,
)

log = logging.getLogger("zwoop.trails.presets")


def _mk_layer(
    lid: str,
    name: str,
    family: str,
    stops: list[tuple[float, str, float]],
    **overrides: Any,
) -> dict[str, Any]:
    lyr = default_layer(lid, name, family)
    lyr["gradient_stops"] = [
        {"position": float(p), "color": c, "opacity": float(a)} for p, c, a in stops
    ]
    if stops:
        lyr["base_color"] = stops[0][1]
        lyr["secondary_color"] = stops[min(1, len(stops) - 1)][1]
    for k, v in overrides.items():
        if k in ("glow", "particles", "motion") and isinstance(v, dict):
            lyr[k].update(v)
        else:
            lyr[k] = v
    return lyr


def _mk_preset(
    pid: str,
    name: str,
    category: str,
    description: str,
    layers: list[dict[str, Any]],
    default_intensity: float = 0.85,
    performance_class: str = "light",
    behavior_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    beh = default_behavior_modifiers()
    if behavior_overrides:
        beh.update(behavior_overrides)
    raw = {
        "schema_version": SCHEMA_VERSION,
        "id": pid,
        "name": name,
        "category": category,
        "description": description,
        "author": "Zwoop Studio",
        "builtin": True,
        "default_intensity": default_intensity,
        "performance_class": performance_class,
        "layers": layers,
        "behavior": beh,
    }
    return validate_preset_dict(raw, strict=True)


# ============================================================================
# 25 BUNDLED PRESETS (24 Creative Presets + 1 Legacy Compatibility Preset)
# ============================================================================
_RAW_BUNDLED: list[dict[str, Any]] = [
    # ------------------------ 1. COSMIC COLLECTION (4) ----------------------
    _mk_preset(
        "nebula_silk",
        "Nebula Silk",
        "cosmic",
        "Broad, smooth violet silk ribbon with cyan highlights and graceful fading.",
        layers=[
            _mk_layer(
                "silk_ribbon", "Violet Silk Ribbon", "ribbon",
                [(0.0, "#D896FF", 1.0), (0.55, "#7B2CBF", 0.85), (1.0, "#48CAE4", 0.0)],
                head_width_px=24.0, tail_width_px=3.0, width_px=22.0,
                taper=0.75, smoothing=0.75, lifetime_s=2.4, opacity=0.80,
                soft_edge=0.70, blend_mode="add",
                glow={"enabled": True, "intensity": 0.75, "radius_px": 20.0, "halo_color": "#5A189A"},
                motion={"wave_amplitude": 6.0, "wave_frequency": 1.8, "curl_noise": 6.0},
            ),
            _mk_layer(
                "cyan_shimmer", "Cyan Shimmer Dust", "particles",
                [(0.0, "#90F1EF", 0.95), (0.6, "#7209B7", 0.55), (1.0, "#3A0CA3", 0.0)],
                lifetime_s=1.5, opacity=0.60, blend_mode="add",
                particles={
                    "spawn_rate": 24.0, "max_particles": 80, "shape": "star",
                    "size_px": 7.0, "sparkle": 0.45, "turbulence": 35.0, "gravity": -10.0,
                },
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),
    _mk_preset(
        "astral_wake",
        "Astral Wake",
        "cosmic",
        "Deep-space glow with a delicate luminous core and long fading silhouette.",
        layers=[
            _mk_layer(
                "deep_wake", "Deep Space Wake", "ribbon",
                [(0.0, "#5E60CE", 0.85), (0.5, "#3A0CA3", 0.65), (1.0, "#10002B", 0.0)],
                head_width_px=32.0, tail_width_px=8.0, width_px=28.0,
                taper=0.55, lifetime_s=3.2, opacity=0.72, blend_mode="alpha",
                glow={"enabled": True, "intensity": 0.85, "radius_px": 26.0, "halo_color": "#4EA8DE"},
                motion={"curl_noise": 8.0, "drift_y": -4.0},
            ),
            _mk_layer(
                "astral_core", "Delicate Core Thread", "beam",
                [(0.0, "#FFFFFF", 1.0), (0.4, "#80FFDB", 0.85), (1.0, "#5390D9", 0.0)],
                head_width_px=7.0, tail_width_px=1.0, width_px=6.0,
                sharpness=0.88, lifetime_s=2.1, opacity=0.90, blend_mode="add",
                glow={"enabled": True, "intensity": 0.60, "radius_px": 10.0, "core_intensity": 1.3},
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),
    _mk_preset(
        "stardust",
        "Stardust",
        "cosmic",
        "Scattered shimmering starlight particles with variable size and soft luminescence.",
        layers=[
            _mk_layer(
                "star_stream", "Shimmering Stars", "particles",
                [(0.0, "#FFF3B0", 1.0), (0.45, "#E0AAFF", 0.85), (1.0, "#4CC9F0", 0.0)],
                lifetime_s=2.2, opacity=0.88, hue_variance=0.18, blend_mode="add",
                glow={"enabled": True, "intensity": 0.70, "radius_px": 14.0, "halo_color": "#9D4EDD"},
                particles={
                    "spawn_rate": 58.0, "spawn_burst_size": 22, "max_particles": 160,
                    "shape": "star", "size_px": 10.5, "size_variation": 0.60,
                    "initial_velocity": 42.0, "directional_spread": 160.0,
                    "turbulence": 55.0, "gravity": -8.0, "sparkle": 0.75, "growth_rate": -0.25,
                },
            ),
        ],
        default_intensity=0.90,
        performance_class="light",
    ),
    _mk_preset(
        "event_horizon",
        "Event Horizon",
        "cosmic",
        "Dark-centered gravitational wake with vivid relativistic outer glow and optical contrast.",
        layers=[
            _mk_layer(
                "accretion_halo", "Relativistic Rim", "ribbon",
                [(0.0, "#FF9E00", 1.0), (0.5, "#9D4EDD", 0.90), (1.0, "#3C096C", 0.0)],
                head_width_px=34.0, tail_width_px=6.0, width_px=30.0,
                taper=0.70, sharpness=0.35, lifetime_s=2.2, opacity=0.90, blend_mode="add",
                glow={"enabled": True, "intensity": 1.15, "radius_px": 24.0, "halo_color": "#FF6D00"},
            ),
            _mk_layer(
                "void_core", "Singularity Core", "ribbon",
                [(0.0, "#0B0716", 0.98), (0.65, "#140A28", 0.85), (1.0, "#240046", 0.0)],
                head_width_px=16.0, tail_width_px=2.0, width_px=15.0,
                taper=0.80, sharpness=0.85, lifetime_s=1.8, opacity=0.95,
                blend_mode="contrast", priority=1,
                glow={"enabled": False, "intensity": 0.0, "radius_px": 4.0},
            ),
        ],
        default_intensity=0.90,
        performance_class="light",
    ),

    # ----------------------- 2. ELEMENTAL COLLECTION (4) --------------------
    _mk_preset(
        "solar_flare",
        "Solar Flare",
        "elemental",
        "Warm coronal ribbons with fiery streaks and high-acceleration spark bursts.",
        layers=[
            _mk_layer(
                "corona_ribbon", "Solar Corona", "ribbon",
                [(0.0, "#FFF3B0", 1.0), (0.4, "#FF7B00", 0.90), (0.8, "#D00000", 0.50), (1.0, "#370617", 0.0)],
                head_width_px=24.0, tail_width_px=2.0, width_px=20.0,
                width_noise=0.35, lifetime_s=1.7, opacity=0.85, blend_mode="add",
                glow={"enabled": True, "intensity": 0.95, "radius_px": 20.0, "halo_color": "#F48C06"},
                motion={"wave_amplitude": 8.0, "wave_frequency": 3.2, "curl_noise": 10.0},
            ),
            _mk_layer(
                "flare_sparks", "Prominence Sparks", "sparks",
                [(0.0, "#FFFFFF", 1.0), (0.35, "#FFB703", 0.95), (1.0, "#9D0208", 0.0)],
                lifetime_s=0.95, opacity=0.92, blend_mode="add",
                particles={
                    "spawn_rate": 64.0, "spawn_burst_size": 28, "max_particles": 150,
                    "shape": "streak", "size_px": 11.0, "initial_velocity": 135.0,
                    "velocity_inheritance": 0.45, "directional_spread": 85.0,
                    "drag": 2.4, "gravity": -35.0, "turbulence": 80.0,
                },
            ),
        ],
        default_intensity=0.90,
        performance_class="moderate",
        behavior_overrides={"dive_intensity": 1.9, "accel_to_burst": 1.3},
    ),
    _mk_preset(
        "frostwake",
        "Frostwake",
        "elemental",
        "Icy blue interwoven strands and slowly dissipating crystalline shards.",
        layers=[
            _mk_layer(
                "ice_strands", "Glacial Strands", "spiral",
                [(0.0, "#E0FBFC", 1.0), (0.5, "#48CAE4", 0.85), (1.0, "#023E8A", 0.0)],
                strand_count=2, head_width_px=11.0, tail_width_px=1.5, width_px=10.0,
                sharpness=0.75, lifetime_s=2.3, opacity=0.82, blend_mode="add",
                glow={"enabled": True, "intensity": 0.65, "radius_px": 14.0, "halo_color": "#0096C7"},
                motion={"spiral_radius": 14.0, "spiral_speed": 3.0, "wave_frequency": 2.2},
            ),
            _mk_layer(
                "ice_crystals", "Crystalline Shards", "particles",
                [(0.0, "#FFFFFF", 1.0), (0.5, "#90E0EF", 0.80), (1.0, "#0077B6", 0.0)],
                lifetime_s=2.4, opacity=0.80, blend_mode="add",
                particles={
                    "spawn_rate": 32.0, "max_particles": 110, "shape": "diamond",
                    "size_px": 8.5, "angular_velocity": 90.0, "initial_velocity": 28.0,
                    "drag": 2.8, "gravity": 14.0, "turbulence": 20.0, "sparkle": 0.60,
                },
            ),
        ],
        default_intensity=0.85,
        performance_class="moderate",
    ),
    _mk_preset(
        "storm_arc",
        "Storm Arc",
        "elemental",
        "Electric branching plasma conduits with high-voltage forks and rapid discharge.",
        layers=[
            _mk_layer(
                "lightning_spine", "High-Voltage Conduit", "branching",
                [(0.0, "#FFFFFF", 1.0), (0.4, "#4CC9F0", 0.95), (1.0, "#3F37C9", 0.0)],
                head_width_px=10.0, tail_width_px=2.0, width_px=9.0,
                sharpness=0.88, smoothing=0.10, lifetime_s=0.75, opacity=0.95,
                blend_mode="add",
                glow={
                    "enabled": True, "intensity": 1.10, "radius_px": 18.0,
                    "halo_color": "#4361EE", "pulse_speed": 6.5, "pulse_depth": 0.35,
                },
                motion={"position_jitter": 9.5, "wave_amplitude": 5.0, "wave_frequency": 6.0},
            ),
            _mk_layer(
                "arc_sparks", "Discharge Sparks", "sparks",
                [(0.0, "#FFFFFF", 1.0), (0.5, "#72EFDD", 0.85), (1.0, "#5E60CE", 0.0)],
                lifetime_s=0.55, opacity=0.85, blend_mode="add",
                particles={
                    "spawn_rate": 45.0, "spawn_burst_size": 25, "max_particles": 90,
                    "shape": "streak", "size_px": 8.0, "initial_velocity": 170.0,
                    "directional_spread": 240.0, "drag": 3.5, "sparkle": 0.8,
                },
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),
    _mk_preset(
        "ember_drift",
        "Ember Drift",
        "elemental",
        "Warm glowing cinders that separate, swirl, and float upward over soft ash mist.",
        layers=[
            _mk_layer(
                "warm_mist", "Smoldering Plume", "smoke",
                [(0.0, "#9D0208", 0.55), (0.5, "#590D22", 0.35), (1.0, "#2B2D42", 0.0)],
                lifetime_s=2.6, opacity=0.50, blend_mode="alpha",
                glow={"enabled": True, "intensity": 0.35, "radius_px": 18.0, "halo_color": "#6A040F"},
                particles={
                    "spawn_rate": 22.0, "max_particles": 70, "shape": "puff",
                    "size_px": 20.0, "growth_rate": 0.85, "gravity": -38.0,
                    "turbulence": 50.0, "drag": 2.4,
                },
            ),
            _mk_layer(
                "cinders", "Floating Embers", "particles",
                [(0.0, "#FFBA08", 1.0), (0.5, "#F48C06", 0.90), (0.85, "#DC2F02", 0.55), (1.0, "#370617", 0.0)],
                lifetime_s=2.8, opacity=0.92, blend_mode="add",
                glow={"enabled": True, "intensity": 0.80, "radius_px": 12.0, "halo_color": "#E85D04"},
                particles={
                    "spawn_rate": 48.0, "spawn_burst_size": 20, "max_particles": 140,
                    "shape": "circle", "size_px": 6.5, "size_variation": 0.55,
                    "initial_velocity": 45.0, "gravity": -65.0, "turbulence": 95.0,
                    "drag": 1.4, "sparkle": 0.55, "growth_rate": -0.35,
                },
            ),
        ],
        default_intensity=0.85,
        performance_class="moderate",
    ),

    # ----------------------- 3. ETHEREAL COLLECTION (4) ---------------------
    _mk_preset(
        "ghost_veil",
        "Ghost Veil",
        "ethereal",
        "Soft translucent deformation-preserving afterimages with graceful slow fading.",
        layers=[
            _mk_layer(
                "phantom_echoes", "Phantom Silhouettes", "echo",
                [(0.0, "#C77DFF", 0.85), (0.5, "#72EFDD", 0.55), (1.0, "#3A0CA3", 0.0)],
                echo_count=8, segment_spacing_px=28.0, size_scale=0.95,
                taper=0.45, lifetime_s=2.2, opacity=0.75, blend_mode="add",
                glow={"enabled": True, "intensity": 0.70, "radius_px": 16.0, "halo_color": "#5E60CE"},
                motion={"drift_y": -10.0, "curl_noise": 5.0},
            ),
            _mk_layer(
                "ectoplasm_ribbon", "Veil Gauze", "ribbon",
                [(0.0, "#E0AAFF", 0.55), (0.6, "#48BFE3", 0.30), (1.0, "#240046", 0.0)],
                head_width_px=28.0, tail_width_px=10.0, width_px=24.0,
                sharpness=0.20, soft_edge=0.90, lifetime_s=2.0, opacity=0.45,
                blend_mode="screen",
            ),
        ],
        default_intensity=0.80,
        performance_class="light",
    ),
    _mk_preset(
        "aurora_threads",
        "Aurora Threads",
        "ethereal",
        "Three flowing Borealis strands with independent color shifts and gentle wave motion.",
        layers=[
            _mk_layer(
                "borealis_curtain", "Borealis Tri-Strand", "ribbon",
                [(0.0, "#80FFDB", 1.0), (0.45, "#48BFE3", 0.85), (0.78, "#7209B7", 0.65), (1.0, "#10002B", 0.0)],
                strand_count=3, head_width_px=16.0, tail_width_px=3.0, width_px=14.0,
                sharpness=0.45, lifetime_s=2.8, opacity=0.82, color_cycle_rate=0.12,
                blend_mode="add",
                glow={"enabled": True, "intensity": 0.85, "radius_px": 20.0, "halo_color": "#64DFDF"},
                motion={
                    "spiral_radius": 16.0, "spiral_speed": 2.1,
                    "wave_amplitude": 12.0, "wave_frequency": 2.0, "curl_noise": 9.0,
                },
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),
    _mk_preset(
        "moon_mist",
        "Moon Mist",
        "ethereal",
        "Gentle expanding lunar wisps with restrained opacity and low-distraction serenity.",
        layers=[
            _mk_layer(
                "lunar_vapor", "Lunar Mist Puffs", "smoke",
                [(0.0, "#E2EAFC", 0.65), (0.5, "#A5A58D", 0.35), (1.0, "#3F37C9", 0.0)],
                lifetime_s=3.0, opacity=0.52, blend_mode="screen",
                glow={"enabled": True, "intensity": 0.45, "radius_px": 22.0, "halo_color": "#B8C0FF"},
                particles={
                    "spawn_rate": 24.0, "max_particles": 75, "shape": "puff",
                    "size_px": 22.0, "size_variation": 0.40, "initial_velocity": 18.0,
                    "drag": 2.6, "gravity": -10.0, "turbulence": 25.0, "growth_rate": 0.95,
                },
                motion={"drift_y": -5.0, "curl_noise": 8.0},
            ),
        ],
        default_intensity=0.70,
        performance_class="minimal",
        behavior_overrides={"idle_emission": 0.20, "startle_burst": 0.6},
    ),
    _mk_preset(
        "spirit_ribbon",
        "Spirit Ribbon",
        "ethereal",
        "Thin luminous spirit filament surrounded by a faint translucent aura haze.",
        layers=[
            _mk_layer(
                "aura_haze", "Spirit Aura Haze", "smoke",
                [(0.0, "#9BF6FF", 0.50), (0.5, "#BDB2FF", 0.30), (1.0, "#3A0CA3", 0.0)],
                lifetime_s=2.0, opacity=0.45, blend_mode="add",
                particles={
                    "spawn_rate": 26.0, "max_particles": 65, "shape": "puff",
                    "size_px": 18.0, "growth_rate": 0.6, "turbulence": 30.0, "gravity": -12.0,
                },
            ),
            _mk_layer(
                "spirit_filament", "Luminous Filament", "ribbon",
                [(0.0, "#FDFFFC", 1.0), (0.4, "#A0C4FF", 0.90), (1.0, "#7209B7", 0.0)],
                head_width_px=9.0, tail_width_px=1.0, width_px=8.0,
                sharpness=0.80, smoothing=0.85, lifetime_s=2.4, opacity=0.92,
                blend_mode="add", priority=1,
                glow={"enabled": True, "intensity": 0.85, "radius_px": 15.0, "halo_color": "#9BF6FF"},
                motion={"wave_amplitude": 7.0, "wave_frequency": 2.4},
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),

    # ----------------------- 4. ENERGETIC COLLECTION (4) --------------------
    _mk_preset(
        "plasma_jet",
        "Plasma Jet",
        "energetic",
        "Tight high-temperature plasma core with velocity-sensitive cyan-magenta radiance.",
        layers=[
            _mk_layer(
                "plasma_beam", "Plasma Core Beam", "beam",
                [(0.0, "#FFFFFF", 1.0), (0.3, "#F72585", 0.95), (0.7, "#7209B7", 0.80), (1.0, "#4CC9F0", 0.0)],
                head_width_px=16.0, tail_width_px=2.0, width_px=14.0,
                sharpness=0.86, taper=0.90, lifetime_s=1.4, opacity=0.95,
                velocity_color_mod=0.65, blend_mode="add",
                glow={
                    "enabled": True, "intensity": 1.15, "radius_px": 20.0,
                    "halo_color": "#F72585", "core_intensity": 1.4,
                },
            ),
            _mk_layer(
                "jet_ions", "Ionized Exhaust", "sparks",
                [(0.0, "#4CC9F0", 1.0), (0.5, "#F72585", 0.85), (1.0, "#3A0CA3", 0.0)],
                lifetime_s=0.70, opacity=0.85, blend_mode="add",
                particles={
                    "spawn_rate": 52.0, "spawn_burst_size": 24, "max_particles": 120,
                    "shape": "streak", "size_px": 9.0, "initial_velocity": 140.0,
                    "directional_spread": 45.0, "drag": 2.2, "gravity": 0.0,
                },
            ),
        ],
        default_intensity=0.92,
        performance_class="light",
    ),
    _mk_preset(
        "ion_pulse",
        "Ion Pulse",
        "energetic",
        "Pulsating narrow energy conduit with harmonic ring nodes along the flight path.",
        layers=[
            _mk_layer(
                "pulse_conduit", "Harmonic Beam", "beam",
                [(0.0, "#72EFDD", 1.0), (0.5, "#5390D9", 0.85), (1.0, "#7400B8", 0.0)],
                head_width_px=11.0, tail_width_px=2.0, width_px=10.0,
                sharpness=0.85, lifetime_s=1.6, opacity=0.88, blend_mode="add",
                glow={
                    "enabled": True, "intensity": 0.95, "radius_px": 16.0,
                    "halo_color": "#48BFE3", "pulse_speed": 4.5, "pulse_depth": 0.45,
                },
            ),
            _mk_layer(
                "pulse_nodes", "Ion Ring Nodes", "segmented",
                [(0.0, "#80FFDB", 1.0), (0.6, "#6930C3", 0.75), (1.0, "#5E60CE", 0.0)],
                segment_spacing_px=26.0, width_px=18.0, taper=0.65,
                lifetime_s=1.5, opacity=0.85, blend_mode="add",
                particles={"shape": "ring"},
            ),
        ],
        default_intensity=0.88,
        performance_class="light",
    ),
    _mk_preset(
        "laser_thread",
        "Laser Thread",
        "energetic",
        "Razor-sharp coherent optical filament with a restrained neon halo.",
        layers=[
            _mk_layer(
                "coherent_beam", "Coherent Laser", "beam",
                [(0.0, "#FFFFFF", 1.0), (0.25, "#FF007F", 0.98), (0.75, "#7928CA", 0.85), (1.0, "#FF0080", 0.0)],
                head_width_px=6.5, tail_width_px=1.5, width_px=6.0,
                taper=0.45, sharpness=0.95, soft_edge=0.20, smoothing=0.80,
                lifetime_s=2.0, opacity=0.96, blend_mode="add",
                glow={
                    "enabled": True, "intensity": 0.75, "radius_px": 10.0,
                    "halo_color": "#FF007F", "core_intensity": 1.6,
                },
            ),
        ],
        default_intensity=0.90,
        performance_class="minimal",
    ),
    _mk_preset(
        "hyperdrive",
        "Hyperdrive",
        "energetic",
        "Warp-speed elongated starlight streaks that dramatically stretch during maneuvers.",
        layers=[
            _mk_layer(
                "warp_core", "Slipstream Core", "beam",
                [(0.0, "#FFFFFF", 1.0), (0.35, "#90E0EF", 0.95), (1.0, "#03045E", 0.0)],
                head_width_px=14.0, tail_width_px=1.0, width_px=12.0,
                sharpness=0.90, lifetime_s=1.5, length_cap_px=1500.0,
                opacity=0.92, blend_mode="add",
                motion={"speed_response": 1.6, "acceleration_response": 1.4},
            ),
            _mk_layer(
                "warp_streaks", "Relativistic Streaks", "sparks",
                [(0.0, "#CAF0F8", 1.0), (0.5, "#00B4D8", 0.90), (1.0, "#7209B7", 0.0)],
                lifetime_s=1.1, opacity=0.92, blend_mode="add",
                particles={
                    "spawn_rate": 75.0, "spawn_burst_size": 32, "max_particles": 170,
                    "shape": "streak", "size_px": 13.0, "initial_velocity": 210.0,
                    "velocity_inheritance": 0.65, "directional_spread": 28.0,
                    "drag": 1.2, "gravity": 0.0, "turbulence": 10.0,
                },
            ),
        ],
        default_intensity=0.92,
        performance_class="moderate",
        behavior_overrides={"speed_to_length": 1.65, "dive_intensity": 2.0, "perform_intensity": 1.75},
    ),

    # ------------------------ 5. PLAYFUL COLLECTION (4) ---------------------
    _mk_preset(
        "pixie_dust",
        "Pixie Dust",
        "playful",
        "Sparkling fairy-gold and orchid stars with playful dispersion and lively twinkle.",
        layers=[
            _mk_layer(
                "fairy_glitter", "Fairy Glitter", "particles",
                [(0.0, "#FFEE93", 1.0), (0.45, "#FF70A6", 0.90), (0.8, "#C77DFF", 0.65), (1.0, "#70D6FF", 0.0)],
                lifetime_s=2.0, opacity=0.92, hue_variance=0.28, color_cycle_rate=0.25,
                blend_mode="add",
                glow={"enabled": True, "intensity": 0.80, "radius_px": 14.0, "halo_color": "#FF70A6"},
                particles={
                    "spawn_rate": 68.0, "spawn_burst_size": 26, "max_particles": 165,
                    "shape": "star", "size_px": 9.5, "size_variation": 0.55,
                    "angular_velocity": 140.0, "initial_velocity": 65.0,
                    "directional_spread": 180.0, "drag": 1.8, "gravity": 18.0,
                    "turbulence": 75.0, "sparkle": 0.85,
                },
            ),
        ],
        default_intensity=0.90,
        performance_class="light",
    ),
    _mk_preset(
        "bubble_pop",
        "Bubble Pop",
        "playful",
        "Iridescent hollow bubbles that expand, wobble upward, and gently pop.",
        layers=[
            _mk_layer(
                "soap_bubbles", "Iridescent Bubbles", "particles",
                [(0.0, "#A9DEF9", 0.95), (0.5, "#FF99C8", 0.85), (0.85, "#E4C1F9", 0.70), (1.0, "#D0F4DE", 0.0)],
                lifetime_s=2.6, fade_curve="expo", opacity=0.88, hue_variance=0.35,
                blend_mode="screen",
                glow={"enabled": True, "intensity": 0.45, "radius_px": 10.0, "halo_color": "#A9DEF9"},
                particles={
                    "spawn_rate": 30.0, "spawn_burst_size": 16, "max_particles": 95,
                    "shape": "ring", "size_px": 11.0, "size_variation": 0.55,
                    "initial_velocity": 48.0, "directional_spread": 150.0,
                    "drag": 2.0, "gravity": -55.0, "turbulence": 65.0,
                    "growth_rate": 1.15, "sparkle": 0.15,
                },
            ),
        ],
        default_intensity=0.88,
        performance_class="light",
    ),
    _mk_preset(
        "confetti_comet",
        "Confetti Comet",
        "playful",
        "Festive multi-colored geometric marks with alternating spin and a bright streamer tail.",
        layers=[
            _mk_layer(
                "streamer", "Comet Streamer", "ribbon",
                [(0.0, "#FFBE0B", 0.95), (0.5, "#FF006E", 0.80), (1.0, "#3A86FF", 0.0)],
                head_width_px=12.0, tail_width_px=2.0, width_px=10.0,
                lifetime_s=1.4, opacity=0.75, color_cycle_rate=0.45, blend_mode="add",
                motion={"wave_amplitude": 9.0, "wave_frequency": 3.5},
            ),
            _mk_layer(
                "confetti_shards", "Tumbling Confetti", "particles",
                [(0.0, "#FFBE0B", 1.0), (0.33, "#FB5607", 0.95), (0.66, "#8338EC", 0.90), (1.0, "#06D6A0", 0.0)],
                lifetime_s=1.9, opacity=0.92, hue_variance=0.65, blend_mode="alpha",
                glow={"enabled": False, "intensity": 0.2, "radius_px": 6.0},
                particles={
                    "spawn_rate": 54.0, "spawn_burst_size": 24, "max_particles": 140,
                    "shape": "shard", "size_px": 8.5, "size_variation": 0.35,
                    "angular_velocity": 240.0, "initial_velocity": 80.0,
                    "directional_spread": 140.0, "drag": 2.1, "gravity": 42.0,
                    "turbulence": 85.0,
                },
            ),
        ],
        default_intensity=0.88,
        performance_class="moderate",
    ),
    _mk_preset(
        "candy_swirl",
        "Candy Swirl",
        "playful",
        "Three pastel-neon ribbons braided in a lively helical twist behind Zwoop.",
        layers=[
            _mk_layer(
                "swirl_braid", "Pastel Helix Braid", "spiral",
                [(0.0, "#FF70A6", 1.0), (0.45, "#70D6FF", 0.90), (0.8, "#FFD670", 0.75), (1.0, "#E9FF70", 0.0)],
                strand_count=3, head_width_px=13.0, tail_width_px=2.5, width_px=12.0,
                sharpness=0.65, lifetime_s=2.1, opacity=0.88, hue_variance=0.30,
                blend_mode="add",
                glow={"enabled": True, "intensity": 0.65, "radius_px": 14.0, "halo_color": "#FF9770"},
                motion={"spiral_radius": 22.0, "spiral_speed": 5.2, "wave_frequency": 2.8},
            ),
        ],
        default_intensity=0.85,
        performance_class="light",
    ),

    # --------------------- 6. EXPERIMENTAL COLLECTION (4) -------------------
    _mk_preset(
        "double_helix",
        "Double Helix",
        "experimental",
        "Two synchronized counter-rotating bio-luminescent strands with base-pair rung markers.",
        layers=[
            _mk_layer(
                "dna_strands", "Counter-Rotating Strands", "spiral",
                [(0.0, "#00F5D4", 1.0), (0.5, "#9B5DE5", 0.90), (1.0, "#F15BB5", 0.0)],
                strand_count=2, head_width_px=11.0, tail_width_px=2.0, width_px=10.0,
                sharpness=0.78, lifetime_s=2.4, opacity=0.92, blend_mode="add",
                glow={"enabled": True, "intensity": 0.80, "radius_px": 15.0, "halo_color": "#00BBF9"},
                motion={"spiral_radius": 24.0, "spiral_speed": 4.6, "wave_frequency": 3.0},
            ),
            _mk_layer(
                "dna_rungs", "Base-Pair Nodes", "segmented",
                [(0.0, "#FEE440", 0.95), (0.5, "#00BBF9", 0.80), (1.0, "#9B5DE5", 0.0)],
                segment_spacing_px=22.0, width_px=12.0, lifetime_s=2.2,
                opacity=0.75, blend_mode="add",
                particles={"shape": "diamond"},
            ),
        ],
        default_intensity=0.88,
        performance_class="moderate",
    ),
    _mk_preset(
        "fractal_echo",
        "Fractal Echo",
        "experimental",
        "Recursive branching crystalline geometry paired with fading harmonic afterimages.",
        layers=[
            _mk_layer(
                "fractal_branches", "Recursive Branches", "branching",
                [(0.0, "#80FFDB", 1.0), (0.5, "#7400B8", 0.85), (1.0, "#5390D9", 0.0)],
                head_width_px=11.0, tail_width_px=1.5, width_px=10.0,
                sharpness=0.82, lifetime_s=1.8, opacity=0.85, blend_mode="add",
                glow={"enabled": True, "intensity": 0.75, "radius_px": 14.0, "halo_color": "#6930C3"},
                motion={"position_jitter": 4.5, "curl_noise": 7.0},
            ),
            _mk_layer(
                "harmonic_echo", "Harmonic Afterimage", "echo",
                [(0.0, "#64DFDF", 0.80), (0.6, "#7209B7", 0.50), (1.0, "#10002B", 0.0)],
                echo_count=6, segment_spacing_px=38.0, size_scale=0.85,
                lifetime_s=1.9, opacity=0.65, blend_mode="add",
            ),
        ],
        default_intensity=0.85,
        performance_class="moderate",
    ),
    _mk_preset(
        "quantum_scatter",
        "Quantum Scatter",
        "experimental",
        "Discrete phase-shifting lattice marks and quantum fragments that disperse on acceleration.",
        layers=[
            _mk_layer(
                "lattice_marks", "Phase Lattice", "segmented",
                [(0.0, "#00F5D4", 1.0), (0.5, "#F72585", 0.85), (1.0, "#4361EE", 0.0)],
                segment_spacing_px=20.0, width_px=14.0, lifetime_s=1.7,
                opacity=0.88, blend_mode="add",
                particles={"shape": "diamond"},
                motion={"wave_amplitude": 14.0, "wave_frequency": 4.0},
            ),
            _mk_layer(
                "quantum_shards", "Quantum Quanta", "particles",
                [(0.0, "#FFFFFF", 1.0), (0.4, "#4CC9F0", 0.90), (1.0, "#7209B7", 0.0)],
                lifetime_s=1.5, opacity=0.85, blend_mode="add",
                particles={
                    "spawn_rate": 42.0, "spawn_burst_size": 30, "max_particles": 130,
                    "shape": "shard", "size_px": 8.0, "initial_velocity": 95.0,
                    "directional_spread": 220.0, "drag": 2.5, "turbulence": 120.0,
                    "sparkle": 0.70,
                },
            ),
        ],
        default_intensity=0.88,
        performance_class="moderate",
    ),
    _mk_preset(
        "ink_in_water",
        "Ink in Water",
        "experimental",
        "Smooth dark-to-luminous indigo plumes with organic curl diffusion and fluid contrast.",
        layers=[
            _mk_layer(
                "indigo_plume", "Diffusing Ink Plume", "smoke",
                [(0.0, "#10002B", 0.92), (0.45, "#3C096C", 0.75), (0.8, "#48CAE4", 0.45), (1.0, "#90E0EF", 0.0)],
                lifetime_s=3.2, opacity=0.85, blend_mode="contrast",
                glow={"enabled": True, "intensity": 0.65, "radius_px": 22.0, "halo_color": "#48CAE4"},
                particles={
                    "spawn_rate": 34.0, "max_particles": 100, "shape": "puff",
                    "size_px": 18.0, "size_variation": 0.45, "initial_velocity": 22.0,
                    "drag": 2.8, "gravity": 6.0, "turbulence": 75.0, "growth_rate": 1.25,
                },
            ),
            _mk_layer(
                "ink_tendril", "Calligraphic Tendril", "ribbon",
                [(0.0, "#10002B", 0.95), (0.5, "#5A189A", 0.80), (1.0, "#48CAE4", 0.0)],
                head_width_px=16.0, tail_width_px=2.0, width_px=14.0,
                width_noise=0.45, lifetime_s=2.6, opacity=0.85, blend_mode="contrast",
                motion={"curl_noise": 18.0, "wave_amplitude": 8.0, "wave_frequency": 1.6},
            ),
        ],
        default_intensity=0.85,
        performance_class="moderate",
    ),

    # ------------------------ 7. LEGACY COLLECTION (1) ----------------------
    _mk_preset(
        "legacy_zwoop",
        "Legacy Zwoop",
        "legacy",
        "Reproduces the original speed-triggered, short metaball-integrated swoosh trail.",
        layers=[
            _mk_layer(
                "legacy_swoosh", "Original Metaball Swoosh", "legacy",
                [(0.0, "#EE8CFF", 0.95), (0.5, "#9E2EFF", 0.75), (1.0, "#4D149E", 0.0)],
                theme_sync=True, head_width_px=26.0, tail_width_px=6.0, width_px=22.0,
                taper=0.95, sharpness=0.35, lifetime_s=0.40, length_cap_px=240.0,
                opacity=0.80, blend_mode="add",
                glow={"enabled": True, "intensity": 0.60, "radius_px": 16.0, "halo_color": "#7B2CBF"},
                motion={"speed_response": 1.5, "curl_noise": 0.0},
            ),
        ],
        default_intensity=0.85,
        performance_class="minimal",
        behavior_overrides={"idle_emission": 0.0, "speed_to_length": 1.2},
    ),
]

BUNDLED_PRESETS: dict[str, dict[str, Any]] = {p["id"]: p for p in _RAW_BUNDLED}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower()).strip("_")
    return s[:48] or "custom_preset"


class PresetStore:
    """Manages immutable bundled presets and persistent user custom presets."""

    def __init__(self, user_dir: str | None = None):
        if user_dir is None:
            appdata = os.environ.get("APPDATA")
            root = (
                os.path.join(appdata, "Zwoop")
                if appdata
                else os.path.join(os.path.expanduser("~"), ".zwoop")
            )
            user_dir = os.path.join(root, "presets")
        self.user_dir = user_dir
        self._user_presets: dict[str, dict[str, Any]] = {}
        self.reload_user_presets()

    def reload_user_presets(self) -> None:
        self._user_presets.clear()
        if not os.path.isdir(self.user_dir):
            return
        try:
            for fname in sorted(os.listdir(self.user_dir)):
                if not fname.lower().endswith(".json"):
                    continue
                fpath = os.path.join(self.user_dir, fname)
                try:
                    if os.path.getsize(fpath) > MAX_PAYLOAD_BYTES:
                        continue
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    p = validate_preset_dict(raw, strict=False)
                    if p["id"] in BUNDLED_PRESETS:
                        p["id"] = f"{p['id']}_user"
                    p["builtin"] = False
                    self._user_presets[p["id"]] = p
                except Exception as e:
                    log.warning("Skipping invalid user preset %s: %s", fname, e)
        except OSError:
            pass

    def list_all(
        self,
        category: str | None = None,
        search: str | None = None,
        favorites_only: bool = False,
        favorites: list[str] | set[str] | None = None,
        sort_by: str = "category",
    ) -> list[dict[str, Any]]:
        """Return deep copies of presets matching filter/search criteria."""
        fav_set = set(favorites or ())
        items = [copy.deepcopy(p) for p in BUNDLED_PRESETS.values()] + [
            copy.deepcopy(p) for p in self._user_presets.values()
        ]
        if category and category.lower() not in ("all", ""):
            if category.lower() == "user":
                items = [p for p in items if not p.get("builtin", False)]
            else:
                items = [p for p in items if p.get("category") == category.lower()]
        if favorites_only:
            items = [p for p in items if p["id"] in fav_set]
        if search and search.strip():
            q = search.strip().lower()
            items = [
                p for p in items
                if q in p["name"].lower()
                or q in p.get("description", "").lower()
                or q in p.get("category", "").lower()
                or any(q in lyr.get("family", "") for lyr in p.get("layers", []))
            ]
        if sort_by == "name":
            items.sort(key=lambda p: p["name"].lower())
        elif sort_by == "performance":
            order = {"minimal": 0, "light": 1, "moderate": 2, "heavy": 3}
            items.sort(key=lambda p: (order.get(p.get("performance_class", "light"), 1), p["name"].lower()))
        return items

    def get(self, preset_id: str) -> dict[str, Any] | None:
        """Return a fresh deep copy of a preset by ID (editing never mutates store)."""
        if preset_id in self._user_presets:
            return copy.deepcopy(self._user_presets[preset_id])
        if preset_id in BUNDLED_PRESETS:
            return copy.deepcopy(BUNDLED_PRESETS[preset_id])
        return None

    def is_builtin(self, preset_id: str) -> bool:
        return preset_id in BUNDLED_PRESETS

    def unique_id(self, base_name: str) -> str:
        slug = _slugify(base_name)
        if slug not in BUNDLED_PRESETS and slug not in self._user_presets:
            return slug
        idx = 2
        while f"{slug}_{idx}" in BUNDLED_PRESETS or f"{slug}_{idx}" in self._user_presets:
            idx += 1
        return f"{slug}_{idx}"

    def save_custom(self, preset_data: dict[str, Any], allow_overwrite: bool = True) -> dict[str, Any]:
        """Validate and atomically persist a user preset. Never overwrites bundled presets."""
        p = validate_preset_dict(copy.deepcopy(preset_data), strict=False)
        if p["id"] in BUNDLED_PRESETS or not allow_overwrite:
            p["id"] = self.unique_id(p["name"])
        p["builtin"] = False
        if p["category"] == "legacy":
            p["category"] = "custom"

        os.makedirs(self.user_dir, exist_ok=True)
        target = os.path.join(self.user_dir, f"{p['id']}.json")
        self._atomic_write_json(target, p)
        self._user_presets[p["id"]] = copy.deepcopy(p)
        return copy.deepcopy(p)

    def duplicate(self, preset_id: str, new_name: str | None = None) -> dict[str, Any]:
        src = self.get(preset_id)
        if src is None:
            raise ValidationError(f"Preset '{preset_id}' not found")
        src["name"] = (new_name or f"{src['name']} Copy").strip()
        src["id"] = self.unique_id(src["name"])
        src["builtin"] = False
        src["category"] = "custom"
        return self.save_custom(src)

    def rename_custom(self, preset_id: str, new_name: str) -> dict[str, Any]:
        if preset_id in BUNDLED_PRESETS:
            raise ValidationError("Cannot rename a bundled preset; use Save As or Duplicate.")
        src = self.get(preset_id)
        if src is None:
            raise ValidationError(f"Custom preset '{preset_id}' not found")
        src["name"] = new_name.strip() or src["name"]
        return self.save_custom(src, allow_overwrite=True)

    def delete_custom(self, preset_id: str) -> bool:
        if preset_id in BUNDLED_PRESETS:
            raise ValidationError("Bundled presets are immutable and cannot be deleted.")
        if preset_id not in self._user_presets:
            return False
        del self._user_presets[preset_id]
        fpath = os.path.join(self.user_dir, f"{preset_id}.json")
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
        except OSError:
            pass
        return True

    def export_file(self, preset_data: dict[str, Any], file_path: str) -> None:
        p = validate_preset_dict(copy.deepcopy(preset_data), strict=False)
        p["builtin"] = False
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        self._atomic_write_json(file_path, p)

    def import_file(self, file_path: str, persist: bool = True) -> dict[str, Any]:
        if not os.path.isfile(file_path):
            raise ValidationError(f"File not found: {file_path}")
        if os.path.getsize(file_path) > MAX_PAYLOAD_BYTES:
            raise ValidationError("Preset file exceeds maximum allowed size (256 KB)")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            raise ValidationError(f"Malformed JSON file: {e}") from e

        p = validate_preset_dict(raw, strict=True)
        if p["id"] in BUNDLED_PRESETS or p["id"] in self._user_presets:
            p["id"] = self.unique_id(p["id"])
        p["builtin"] = False
        if persist:
            return self.save_custom(p, allow_overwrite=True)
        return p

    @staticmethod
    def _atomic_write_json(target_path: str, data: dict[str, Any]) -> None:
        folder = os.path.dirname(os.path.abspath(target_path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".zwoop_preset_", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
