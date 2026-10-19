"""Schema-driven parameter library, validation, and configuration migration.

Defines over 80 meaningful adjustable parameters across 9 parameter groups:
  1. geometry    (16 params)
  2. time        (9 params)
  3. color       (11 params + multi-stop gradient)
  4. blend       (6 params)
  5. glow        (9 params)
  6. particles   (18 params)
  7. motion      (12 params)
  8. behavior    (15 params)
  9. quality     (10 params)
"""

from __future__ import annotations

import colorsys
import copy
import math
import re
from typing import Any

import numpy as np

SCHEMA_VERSION = 1
MAX_LAYERS = 4
MAX_GRADIENT_STOPS = 12
MAX_PAYLOAD_BYTES = 262_144

GEOMETRY_FAMILIES = (
    "ribbon",
    "beam",
    "particles",
    "smoke",
    "sparks",
    "segmented",
    "spiral",
    "echo",
    "branching",
    "legacy",
)

BLEND_MODES = ("alpha", "add", "screen", "contrast")
FADE_CURVES = ("linear", "smooth", "expo", "cosine")
GRADIENT_INTERPS = ("linear", "smooth", "step")
GRADIENT_DIRS = ("along", "across", "radial", "velocity")
PARTICLE_SHAPES = ("circle", "star", "diamond", "streak", "ring", "puff", "shard")
EDGE_BEHAVIORS = ("none", "fade", "bounce")
END_CAPS = ("round", "taper", "flat")
QUALITY_LEVELS = ("eco", "balanced", "high", "ultra", "auto")
PRESET_CATEGORIES = (
    "cosmic",
    "elemental",
    "ethereal",
    "energetic",
    "playful",
    "experimental",
    "legacy",
    "custom",
)

QUALITY_BUDGETS = {
    "eco": {
        "res_scale": 4,
        "sample_spacing_px": 12.0,
        "segment_cap": 20,
        "particle_cap": 45,
        "max_lifetime_s": 2.2,
        "max_surface_w": 880,
        "max_surface_h": 640,
        "glow_passes": 1,
        "effect_budget": 0.45,
    },
    "balanced": {
        "res_scale": 4,
        "sample_spacing_px": 8.0,
        "segment_cap": 32,
        "particle_cap": 95,
        "max_lifetime_s": 4.0,
        "max_surface_w": 1120,
        "max_surface_h": 840,
        "glow_passes": 1,
        "effect_budget": 0.75,
    },
    "high": {
        "res_scale": 3,
        "sample_spacing_px": 6.0,
        "segment_cap": 48,
        "particle_cap": 160,
        "max_lifetime_s": 5.5,
        "max_surface_w": 1360,
        "max_surface_h": 1000,
        "glow_passes": 2,
        "effect_budget": 0.90,
    },
    "ultra": {
        "res_scale": 2,
        "sample_spacing_px": 4.5,
        "segment_cap": 68,
        "particle_cap": 240,
        "max_lifetime_s": 7.5,
        "max_surface_w": 1600,
        "max_surface_h": 1200,
        "glow_passes": 2,
        "effect_budget": 1.00,
    },
}

_ALL_FAMILIES = GEOMETRY_FAMILIES
_PATH_FAMILIES = ("ribbon", "beam", "segmented", "spiral", "branching", "legacy")
_PARTICLE_FAMILIES = ("particles", "smoke", "sparks")

# Schema definition: key -> metadata dict
# Used by validation, Studio UI generation, family-aware hiding, and Randomizer.
PARAM_SCHEMA: dict[str, dict[str, Any]] = {
    # ---- 6.1 Geometry (16) --------------------------------------------------
    "family": {
        "group": "geometry", "type": "enum", "choices": GEOMETRY_FAMILIES,
        "default": "ribbon", "label": "Geometry Type", "families": _ALL_FAMILIES,
        "desc": "Primary visual geometry family for this layer.",
    },
    "size_scale": {
        "group": "geometry", "type": "float", "min": 0.2, "max": 3.0, "step": 0.05,
        "default": 1.0, "unit": "x", "label": "Overall Size", "families": _ALL_FAMILIES,
        "desc": "Uniform scale multiplier on layer width and particles.",
    },
    "width_px": {
        "group": "geometry", "type": "float", "min": 1.0, "max": 90.0, "step": 1.0,
        "default": 18.0, "unit": "px", "label": "Width",
        "families": ("ribbon", "beam", "segmented", "spiral", "branching", "legacy"),
        "desc": "Base stroke/ribbon radius in pixels.",
    },
    "head_width_px": {
        "group": "geometry", "type": "float", "min": 1.0, "max": 100.0, "step": 1.0,
        "default": 22.0, "unit": "px", "label": "Head Width",
        "families": ("ribbon", "beam", "spiral", "branching"),
        "desc": "Width of the trail near Zwoop's body.",
    },
    "tail_width_px": {
        "group": "geometry", "type": "float", "min": 0.0, "max": 80.0, "step": 1.0,
        "default": 2.0, "unit": "px", "label": "Tail Width",
        "families": ("ribbon", "beam", "spiral", "branching"),
        "desc": "Width at the oldest tip of the trail.",
    },
    "taper": {
        "group": "geometry", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.85, "unit": "", "label": "Taper Exponent",
        "families": _PATH_FAMILIES,
        "desc": "Controls how quickly width narrows from head to tail.",
    },
    "smoothing": {
        "group": "geometry", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.55, "unit": "", "label": "Curve Smoothing",
        "families": _PATH_FAMILIES,
        "desc": "Spline smoothing applied to the sampled trajectory.",
    },
    "segment_density": {
        "group": "geometry", "type": "float", "min": 0.25, "max": 2.5, "step": 0.05,
        "default": 1.0, "unit": "x", "label": "Segment Density",
        "families": _PATH_FAMILIES,
        "desc": "Subdivision density along the trajectory.",
    },
    "segment_spacing_px": {
        "group": "geometry", "type": "float", "min": 6.0, "max": 90.0, "step": 1.0,
        "default": 24.0, "unit": "px", "label": "Mark Spacing",
        "families": ("segmented", "echo", "branching"),
        "desc": "World-space distance between discrete marks or echoes.",
    },
    "curve_tension": {
        "group": "geometry", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.5, "unit": "", "label": "Curve Tension",
        "families": _PATH_FAMILIES,
        "desc": "Catmull-Rom spline tension along sharp turns.",
    },
    "sharpness": {
        "group": "geometry", "type": "float", "min": 0.05, "max": 1.0, "step": 0.05,
        "default": 0.5, "unit": "", "label": "Core Sharpness",
        "families": ("ribbon", "beam", "segmented", "spiral", "branching"),
        "desc": "Cross-sectional hardness from crisp laser to soft silk.",
    },
    "offset_px": {
        "group": "geometry", "type": "float", "min": -80.0, "max": 80.0, "step": 1.0,
        "default": 0.0, "unit": "px", "label": "Perpendicular Offset",
        "families": _ALL_FAMILIES,
        "desc": "Lateral offset perpendicular to travel direction.",
    },
    "strand_count": {
        "group": "geometry", "type": "int", "min": 1, "max": 5, "step": 1,
        "default": 2, "unit": "", "label": "Strand Count",
        "families": ("spiral", "ribbon", "beam"),
        "desc": "Number of interwoven or parallel strands.",
    },
    "end_cap": {
        "group": "geometry", "type": "enum", "choices": END_CAPS,
        "default": "round", "label": "End Caps",
        "families": ("ribbon", "beam", "spiral"),
        "desc": "Shape of the leading and trailing ends.",
    },
    "width_noise": {
        "group": "geometry", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.08, "unit": "", "label": "Width Noise",
        "families": ("ribbon", "smoke", "spiral", "branching"),
        "desc": "Organic thickness modulation along the path.",
    },
    "echo_count": {
        "group": "geometry", "type": "int", "min": 2, "max": 16, "step": 1,
        "default": 6, "unit": "", "label": "Echo Count",
        "families": ("echo",),
        "desc": "Number of discrete afterimage silhouettes retained.",
    },

    # ---- 6.2 Time (9) -------------------------------------------------------
    "lifetime_s": {
        "group": "time", "type": "float", "min": 0.15, "max": 8.0, "step": 0.05,
        "default": 1.8, "unit": "s", "label": "Lifespan",
        "families": _ALL_FAMILIES,
        "desc": "Duration in seconds that trail samples or particles remain visible.",
    },
    "fade_in_s": {
        "group": "time", "type": "float", "min": 0.0, "max": 1.5, "step": 0.02,
        "default": 0.04, "unit": "s", "label": "Fade-In Time",
        "families": _ALL_FAMILIES,
        "desc": "Soft ramp-up time right after emission near the head.",
    },
    "fade_out_s": {
        "group": "time", "type": "float", "min": 0.05, "max": 6.0, "step": 0.05,
        "default": 1.2, "unit": "s", "label": "Fade-Out Time",
        "families": _ALL_FAMILIES,
        "desc": "Duration of the trailing opacity decay.",
    },
    "fade_curve": {
        "group": "time", "type": "enum", "choices": FADE_CURVES,
        "default": "smooth", "label": "Fade Curve",
        "families": _ALL_FAMILIES,
        "desc": "Easing function for age-based opacity decay.",
    },
    "persistence": {
        "group": "time", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.6, "unit": "", "label": "Persistence",
        "families": _ALL_FAMILIES,
        "desc": "How strongly old trail segments resist rapid dissipation.",
    },
    "spawn_delay_s": {
        "group": "time", "type": "float", "min": 0.0, "max": 0.5, "step": 0.01,
        "default": 0.0, "unit": "s", "label": "Spawn Delay",
        "families": _ALL_FAMILIES,
        "desc": "Time offset behind Zwoop's head before the layer begins.",
    },
    "dissipation_rate": {
        "group": "time", "type": "float", "min": 0.1, "max": 4.0, "step": 0.05,
        "default": 1.0, "unit": "1/s", "label": "Dissipation Rate",
        "families": _ALL_FAMILIES,
        "desc": "Rate at which the trail thins or expands as it ages.",
    },
    "length_cap_px": {
        "group": "time", "type": "float", "min": 60.0, "max": 2400.0, "step": 20.0,
        "default": 900.0, "unit": "px", "label": "Trail Length Cap",
        "families": _PATH_FAMILIES,
        "desc": "Maximum arc length in world pixels before older tail trims.",
    },
    "lifetime_variance": {
        "group": "time", "type": "float", "min": 0.0, "max": 0.8, "step": 0.05,
        "default": 0.2, "unit": "", "label": "Lifetime Variance",
        "families": _PARTICLE_FAMILIES,
        "desc": "Random variation in individual particle lifespans.",
    },

    # ---- 6.3 Color (11) -----------------------------------------------------
    "base_color": {
        "group": "color", "type": "color", "default": "#8A3FFC",
        "label": "Base Color", "families": _ALL_FAMILIES,
        "desc": "Primary head color of the layer.",
    },
    "secondary_color": {
        "group": "color", "type": "color", "default": "#33E1FF",
        "label": "Secondary Color", "families": _ALL_FAMILIES,
        "desc": "Tail or accent color when gradient is simplified.",
    },
    "gradient_enabled": {
        "group": "color", "type": "bool", "default": True,
        "label": "Enable Multi-Stop Gradient", "families": _ALL_FAMILIES,
        "desc": "Use multi-stop color gradient along the trail.",
    },
    "gradient_interp": {
        "group": "color", "type": "enum", "choices": GRADIENT_INTERPS,
        "default": "smooth", "label": "Gradient Interpolation",
        "families": _ALL_FAMILIES,
        "desc": "How colors blend between gradient stops.",
    },
    "gradient_direction": {
        "group": "color", "type": "enum", "choices": GRADIENT_DIRS,
        "default": "along", "label": "Gradient Direction",
        "families": _ALL_FAMILIES,
        "desc": "Map gradient along trail age, across width, radially, or by speed.",
    },
    "color_cycle_rate": {
        "group": "color", "type": "float", "min": 0.0, "max": 3.0, "step": 0.05,
        "default": 0.0, "unit": "Hz", "label": "Color Cycle Rate",
        "families": _ALL_FAMILIES,
        "desc": "Continuous hue rotation speed over time.",
    },
    "hue_offset": {
        "group": "color", "type": "float", "min": -180.0, "max": 180.0, "step": 2.0,
        "default": 0.0, "unit": "deg", "label": "Hue Offset",
        "families": _ALL_FAMILIES,
        "desc": "Static hue shift applied to all colors in this layer.",
    },
    "hue_variance": {
        "group": "color", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.05, "unit": "", "label": "Hue Variance",
        "families": _ALL_FAMILIES,
        "desc": "Per-particle or per-segment hue spread.",
    },
    "saturation": {
        "group": "color", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 1.0, "unit": "x", "label": "Saturation",
        "families": _ALL_FAMILIES,
        "desc": "Color saturation multiplier.",
    },
    "brightness": {
        "group": "color", "type": "float", "min": 0.2, "max": 2.0, "step": 0.05,
        "default": 1.0, "unit": "x", "label": "Brightness",
        "families": _ALL_FAMILIES,
        "desc": "Color value/luminance multiplier.",
    },
    "theme_sync": {
        "group": "color", "type": "bool", "default": False,
        "label": "Sync with Creature Theme", "families": _ALL_FAMILIES,
        "desc": "Tint colors to match Zwoop's active body theme (cosmos/orchid/lagoon/ember).",
    },
    "velocity_color_mod": {
        "group": "color", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.25, "unit": "", "label": "Velocity Color Shift",
        "families": _ALL_FAMILIES,
        "desc": "Shifts color toward hot spark highlights at high velocity.",
    },

    # ---- 6.4 Transparency & Blending (6) ------------------------------------
    "opacity": {
        "group": "blend", "type": "float", "min": 0.0, "max": 1.0, "step": 0.02,
        "default": 0.78, "unit": "", "label": "Layer Opacity",
        "families": _ALL_FAMILIES,
        "desc": "Master alpha multiplier for this layer.",
    },
    "blend_mode": {
        "group": "blend", "type": "enum", "choices": BLEND_MODES,
        "default": "add", "label": "Blend Mode",
        "families": _ALL_FAMILIES,
        "desc": "Premultiplied-alpha compositing mode (alpha, add, screen, contrast).",
    },
    "soft_edge": {
        "group": "blend", "type": "float", "min": 0.05, "max": 1.0, "step": 0.05,
        "default": 0.55, "unit": "", "label": "Soft Edge",
        "families": _ALL_FAMILIES,
        "desc": "Feathering width at the outer boundary of geometry.",
    },
    "edge_falloff": {
        "group": "blend", "type": "float", "min": 0.3, "max": 4.0, "step": 0.1,
        "default": 1.4, "unit": "", "label": "Edge Falloff Power",
        "families": _ALL_FAMILIES,
        "desc": "Cross-sectional falloff exponent.",
    },
    "overlap_intensity": {
        "group": "blend", "type": "float", "min": 0.1, "max": 2.0, "step": 0.05,
        "default": 0.85, "unit": "", "label": "Overlap Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Controls self-brightening when segments or particles overlap.",
    },
    "priority": {
        "group": "blend", "type": "int", "min": -2, "max": 2, "step": 1,
        "default": 0, "unit": "", "label": "Compositing Priority",
        "families": _ALL_FAMILIES,
        "desc": "Fine Z-order adjustment relative to sibling layers.",
    },

    # ---- 6.5 Glow (9) -------------------------------------------------------
    "glow.enabled": {
        "group": "glow", "type": "bool", "default": True,
        "label": "Enable Glow", "families": _ALL_FAMILIES,
        "desc": "Render a soft luminous halo around this layer.",
    },
    "glow.intensity": {
        "group": "glow", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.65, "unit": "", "label": "Glow Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Brightness of the outer halo.",
    },
    "glow.radius_px": {
        "group": "glow", "type": "float", "min": 2.0, "max": 64.0, "step": 1.0,
        "default": 16.0, "unit": "px", "label": "Glow Radius",
        "families": _ALL_FAMILIES,
        "desc": "Spread radius of the luminous halo in pixels.",
    },
    "glow.falloff": {
        "group": "glow", "type": "float", "min": 0.4, "max": 3.5, "step": 0.1,
        "default": 1.5, "unit": "", "label": "Glow Falloff",
        "families": _ALL_FAMILIES,
        "desc": "Steepness of the halo attenuation.",
    },
    "glow.halo_color": {
        "group": "glow", "type": "color", "default": "#7B2CBF",
        "label": "Halo Color", "families": _ALL_FAMILIES,
        "desc": "Tint color of the outer glow halo.",
    },
    "glow.core_intensity": {
        "group": "glow", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.85, "unit": "", "label": "Core Luminance",
        "families": _ALL_FAMILIES,
        "desc": "Hot inner core highlight boost.",
    },
    "glow.pulse_speed": {
        "group": "glow", "type": "float", "min": 0.0, "max": 8.0, "step": 0.1,
        "default": 0.0, "unit": "Hz", "label": "Pulse Speed",
        "families": _ALL_FAMILIES,
        "desc": "Frequency of rhythmic glow pulsation.",
    },
    "glow.pulse_depth": {
        "group": "glow", "type": "float", "min": 0.0, "max": 0.9, "step": 0.05,
        "default": 0.0, "unit": "", "label": "Pulse Depth",
        "families": _ALL_FAMILIES,
        "desc": "Amplitude of glow pulsation.",
    },
    "glow.bloom_quality": {
        "group": "glow", "type": "int", "min": 1, "max": 3, "step": 1,
        "default": 2, "unit": "", "label": "Bloom Quality",
        "families": _ALL_FAMILIES,
        "desc": "Number of filter passes used for halo smoothing.",
    },

    # ---- 6.6 Particles (18) -------------------------------------------------
    "particles.spawn_rate": {
        "group": "particles", "type": "float", "min": 0.0, "max": 180.0, "step": 2.0,
        "default": 36.0, "unit": "/s", "label": "Spawn Rate",
        "families": _PARTICLE_FAMILIES,
        "desc": "Continuous particle emission rate per second.",
    },
    "particles.spawn_burst_size": {
        "group": "particles", "type": "int", "min": 0, "max": 60, "step": 1,
        "default": 12, "unit": "", "label": "Burst Count",
        "families": _PARTICLE_FAMILIES,
        "desc": "Particles emitted on startle, dive, or high acceleration.",
    },
    "particles.spawn_variance": {
        "group": "particles", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.25, "unit": "", "label": "Spawn Variance",
        "families": _PARTICLE_FAMILIES,
        "desc": "Randomness in emission intervals.",
    },
    "particles.max_particles": {
        "group": "particles", "type": "int", "min": 5, "max": 350, "step": 5,
        "default": 120, "unit": "", "label": "Max Particles",
        "families": _PARTICLE_FAMILIES,
        "desc": "Hard cap on active particles in this layer.",
    },
    "particles.shape": {
        "group": "particles", "type": "enum", "choices": PARTICLE_SHAPES,
        "default": "circle", "label": "Particle Shape",
        "families": _PARTICLE_FAMILIES,
        "desc": "Visual kernel used to render each particle.",
    },
    "particles.size_px": {
        "group": "particles", "type": "float", "min": 1.5, "max": 64.0, "step": 0.5,
        "default": 9.0, "unit": "px", "label": "Particle Size",
        "families": _PARTICLE_FAMILIES,
        "desc": "Base radius of emitted particles in pixels.",
    },
    "particles.size_variation": {
        "group": "particles", "type": "float", "min": 0.0, "max": 0.9, "step": 0.05,
        "default": 0.35, "unit": "", "label": "Size Variation",
        "families": _PARTICLE_FAMILIES,
        "desc": "Random spread in initial particle size.",
    },
    "particles.rotation_deg": {
        "group": "particles", "type": "float", "min": 0.0, "max": 360.0, "step": 5.0,
        "default": 0.0, "unit": "deg", "label": "Initial Rotation",
        "families": _PARTICLE_FAMILIES,
        "desc": "Initial orientation of non-circular particles.",
    },
    "particles.angular_velocity": {
        "group": "particles", "type": "float", "min": -360.0, "max": 360.0, "step": 10.0,
        "default": 45.0, "unit": "deg/s", "label": "Spin Speed",
        "families": _PARTICLE_FAMILIES,
        "desc": "Angular rotation velocity of particles.",
    },
    "particles.initial_velocity": {
        "group": "particles", "type": "float", "min": 0.0, "max": 500.0, "step": 5.0,
        "default": 55.0, "unit": "px/s", "label": "Ejection Speed",
        "families": _PARTICLE_FAMILIES,
        "desc": "Outward speed given to particles at birth.",
    },
    "particles.velocity_inheritance": {
        "group": "particles", "type": "float", "min": -0.5, "max": 1.2, "step": 0.05,
        "default": 0.25, "unit": "", "label": "Velocity Inheritance",
        "families": _PARTICLE_FAMILIES,
        "desc": "Fraction of Zwoop's velocity inherited by newly spawned particles.",
    },
    "particles.directional_spread": {
        "group": "particles", "type": "float", "min": 5.0, "max": 360.0, "step": 5.0,
        "default": 120.0, "unit": "deg", "label": "Directional Spread",
        "families": _PARTICLE_FAMILIES,
        "desc": "Cone angle of particle emission behind Zwoop.",
    },
    "particles.drag": {
        "group": "particles", "type": "float", "min": 0.0, "max": 8.0, "step": 0.1,
        "default": 1.6, "unit": "1/s", "label": "Air Drag",
        "families": _PARTICLE_FAMILIES,
        "desc": "Exponential velocity damping on particles.",
    },
    "particles.gravity": {
        "group": "particles", "type": "float", "min": -300.0, "max": 300.0, "step": 5.0,
        "default": -18.0, "unit": "px/s²", "label": "Gravity / Buoyancy",
        "families": _PARTICLE_FAMILIES,
        "desc": "Vertical acceleration (negative rises like bubbles/embers, positive falls).",
    },
    "particles.turbulence": {
        "group": "particles", "type": "float", "min": 0.0, "max": 350.0, "step": 5.0,
        "default": 45.0, "unit": "px/s²", "label": "Turbulence / Curl",
        "families": _PARTICLE_FAMILIES,
        "desc": "Swirling curl-like acceleration field acting on particles.",
    },
    "particles.edge_behavior": {
        "group": "particles", "type": "enum", "choices": EDGE_BEHAVIORS,
        "default": "fade", "label": "Boundary Behavior",
        "families": _PARTICLE_FAMILIES,
        "desc": "How particles behave near monitor boundaries.",
    },
    "particles.sparkle": {
        "group": "particles", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.25, "unit": "", "label": "Sparkle / Flicker",
        "families": _PARTICLE_FAMILIES,
        "desc": "Scintillation / twinkle modulation amplitude.",
    },
    "particles.growth_rate": {
        "group": "particles", "type": "float", "min": -2.0, "max": 4.0, "step": 0.1,
        "default": 0.3, "unit": "x/s", "label": "Growth / Expansion",
        "families": _PARTICLE_FAMILIES,
        "desc": "Rate at which particles expand (smoke/bubbles) or shrink (sparks) over life.",
    },

    # ---- 6.7 Motion Modulation (12) -----------------------------------------
    "motion.wave_amplitude": {
        "group": "motion", "type": "float", "min": 0.0, "max": 60.0, "step": 1.0,
        "default": 0.0, "unit": "px", "label": "Wave Amplitude",
        "families": _PATH_FAMILIES,
        "desc": "Sinusoidal lateral displacement along the path.",
    },
    "motion.wave_frequency": {
        "group": "motion", "type": "float", "min": 0.2, "max": 12.0, "step": 0.2,
        "default": 2.5, "unit": "Hz", "label": "Wave Frequency",
        "families": _PATH_FAMILIES,
        "desc": "Oscillation frequency of path waves.",
    },
    "motion.wave_phase": {
        "group": "motion", "type": "float", "min": 0.0, "max": 6.28, "step": 0.1,
        "default": 0.0, "unit": "rad", "label": "Wave Phase",
        "families": _PATH_FAMILIES,
        "desc": "Phase offset for multi-layer wave choreography.",
    },
    "motion.spiral_radius": {
        "group": "motion", "type": "float", "min": 0.0, "max": 75.0, "step": 1.0,
        "default": 18.0, "unit": "px", "label": "Helix Radius",
        "families": ("spiral", "ribbon", "beam"),
        "desc": "Orbital radius of helical strands around the trajectory.",
    },
    "motion.spiral_speed": {
        "group": "motion", "type": "float", "min": -12.0, "max": 12.0, "step": 0.25,
        "default": 4.0, "unit": "rad/s", "label": "Helix Rotation Speed",
        "families": ("spiral", "ribbon", "beam"),
        "desc": "Angular rotation rate of helical strands.",
    },
    "motion.curl_noise": {
        "group": "motion", "type": "float", "min": 0.0, "max": 60.0, "step": 1.0,
        "default": 4.0, "unit": "px", "label": "Organic Curl Drift",
        "families": _ALL_FAMILIES,
        "desc": "World-space coherent drift distorting older trail segments.",
    },
    "motion.drift_x": {
        "group": "motion", "type": "float", "min": -120.0, "max": 120.0, "step": 2.0,
        "default": 0.0, "unit": "px/s", "label": "Horizontal Drift",
        "families": _ALL_FAMILIES,
        "desc": "Steady horizontal wind drift applied to trail history.",
    },
    "motion.drift_y": {
        "group": "motion", "type": "float", "min": -120.0, "max": 120.0, "step": 2.0,
        "default": -8.0, "unit": "px/s", "label": "Vertical Drift",
        "families": _ALL_FAMILIES,
        "desc": "Steady vertical drift applied to trail history.",
    },
    "motion.position_jitter": {
        "group": "motion", "type": "float", "min": 0.0, "max": 30.0, "step": 0.5,
        "default": 0.0, "unit": "px", "label": "Electric Jitter",
        "families": _PATH_FAMILIES,
        "desc": "High-frequency vertex displacement for storm/arc effects.",
    },
    "motion.directional_smoothing": {
        "group": "motion", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.5, "unit": "", "label": "Tangent Smoothing",
        "families": _PATH_FAMILIES,
        "desc": "Stabilizes ribbon normals during tight reversals.",
    },
    "motion.acceleration_response": {
        "group": "motion", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.5, "unit": "", "label": "Acceleration Response",
        "families": _ALL_FAMILIES,
        "desc": "Boosts emission and flare during strong acceleration.",
    },
    "motion.curvature_response": {
        "group": "motion", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.4, "unit": "", "label": "Curvature Response",
        "families": _ALL_FAMILIES,
        "desc": "Widens or flares the trail during sharp turns and loops.",
    },
    "motion.speed_response": {
        "group": "motion", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.65, "unit": "", "label": "Speed Response",
        "families": _ALL_FAMILIES,
        "desc": "Scales trail length and opacity with Zwoop's speed.",
    },

    # ---- 6.8 Behavioral Response (15) ---------------------------------------
    "behavior.idle_emission": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 1.5, "step": 0.05,
        "default": 0.35, "unit": "", "label": "Idle Emission",
        "families": _ALL_FAMILIES,
        "desc": "Baseline trail visibility when Zwoop is hovering slowly.",
    },
    "behavior.wander_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.75, "unit": "x", "label": "Wander Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Trail intensity multiplier during autonomous WANDER state.",
    },
    "behavior.curious_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 1.05, "unit": "x", "label": "Curious Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Trail intensity multiplier when investigating the cursor.",
    },
    "behavior.perform_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.5, "step": 0.05,
        "default": 1.40, "unit": "x", "label": "Perform Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Boost applied during spontaneous aerial maneuvers.",
    },
    "behavior.swoop_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.5, "step": 0.05,
        "default": 1.35, "unit": "x", "label": "Swoop / Arc Boost",
        "families": _ALL_FAMILIES,
        "desc": "Multiplier during swoop, arc, figure-8, and corkscrew maneuvers.",
    },
    "behavior.dive_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.5, "step": 0.05,
        "default": 1.60, "unit": "x", "label": "Dive / Dart Boost",
        "families": _ALL_FAMILIES,
        "desc": "Elongation and brightness boost during high-speed dives and darts.",
    },
    "behavior.recover_intensity": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.70, "unit": "x", "label": "Recovery Intensity",
        "families": _ALL_FAMILIES,
        "desc": "Settling trail multiplier during RECOVER state.",
    },
    "behavior.startle_burst": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.5, "step": 0.05,
        "default": 1.50, "unit": "x", "label": "Startle / Evade Burst",
        "families": _ALL_FAMILIES,
        "desc": "Sudden spark/particle burst strength when startled.",
    },
    "behavior.resting_fade": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 1.0, "step": 0.05,
        "default": 0.10, "unit": "x", "label": "Resting Emission",
        "families": _ALL_FAMILIES,
        "desc": "Low-distraction emission level during REST state.",
    },
    "behavior.attack_time_s": {
        "group": "behavior", "type": "float", "min": 0.02, "max": 2.0, "step": 0.02,
        "default": 0.18, "unit": "s", "label": "Reaction Attack Time",
        "families": _ALL_FAMILIES,
        "desc": "How quickly behavioral intensity ramps up on state entry.",
    },
    "behavior.release_time_s": {
        "group": "behavior", "type": "float", "min": 0.05, "max": 4.0, "step": 0.05,
        "default": 0.65, "unit": "s", "label": "Reaction Release Time",
        "families": _ALL_FAMILIES,
        "desc": "How smoothly behavioral intensity decays after a maneuver.",
    },
    "behavior.speed_to_length": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.85, "unit": "", "label": "Speed -> Length",
        "families": _ALL_FAMILIES,
        "desc": "How strongly movement speed extends trail lifespan/length.",
    },
    "behavior.accel_to_burst": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.70, "unit": "", "label": "Accel -> Particle Burst",
        "families": _ALL_FAMILIES,
        "desc": "How strongly acceleration spikes trigger extra particle emission.",
    },
    "behavior.curvature_to_spiral": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.60, "unit": "", "label": "Curvature -> Wave/Spiral",
        "families": _ALL_FAMILIES,
        "desc": "Amplifies wave and helix radius during turns.",
    },
    "behavior.state_to_glow": {
        "group": "behavior", "type": "float", "min": 0.0, "max": 2.0, "step": 0.05,
        "default": 0.75, "unit": "", "label": "State -> Glow Boost",
        "families": _ALL_FAMILIES,
        "desc": "Modulates halo luminance with active behavioral state.",
    },

    # ---- 6.9 Quality / Performance & Accessibility (10) ---------------------
    "quality.preset": {
        "group": "quality", "type": "enum", "choices": QUALITY_LEVELS,
        "default": "balanced", "label": "Quality Mode",
        "families": _ALL_FAMILIES,
        "desc": "Overall rendering budget tier (eco, balanced, high, ultra, auto).",
    },
    "quality.res_scale": {
        "group": "quality", "type": "int", "min": 1, "max": 4, "step": 1,
        "default": 3, "unit": "div", "label": "Internal Resolution Divisor",
        "families": _ALL_FAMILIES,
        "desc": "Shading grid downscale factor (lower is sharper, higher is faster).",
    },
    "quality.sample_spacing_px": {
        "group": "quality", "type": "float", "min": 2.0, "max": 24.0, "step": 0.5,
        "default": 6.0, "unit": "px", "label": "Sample Spacing",
        "families": _ALL_FAMILIES,
        "desc": "Minimum distance in pixels between recorded trajectory samples.",
    },
    "quality.segment_cap": {
        "group": "quality", "type": "int", "min": 16, "max": 300, "step": 8,
        "default": 120, "unit": "", "label": "Geometry Segment Cap",
        "families": _ALL_FAMILIES,
        "desc": "Maximum resampled curve segments evaluated per frame.",
    },
    "quality.particle_cap": {
        "group": "quality", "type": "int", "min": 10, "max": 500, "step": 10,
        "default": 150, "unit": "", "label": "Global Particle Cap",
        "families": _ALL_FAMILIES,
        "desc": "Maximum simultaneous particles across all layers.",
    },
    "quality.max_lifetime_s": {
        "group": "quality", "type": "float", "min": 0.5, "max": 8.0, "step": 0.25,
        "default": 4.5, "unit": "s", "label": "Max Allowed Lifespan",
        "families": _ALL_FAMILIES,
        "desc": "Safety ceiling on trail lifespan.",
    },
    "quality.effect_budget": {
        "group": "quality", "type": "float", "min": 0.2, "max": 1.0, "step": 0.05,
        "default": 0.75, "unit": "", "label": "Effect Budget Ceiling",
        "families": _ALL_FAMILIES,
        "desc": "Normalized computational budget ceiling.",
    },
    "quality.auto_quality": {
        "group": "quality", "type": "bool", "default": True,
        "label": "Adaptive Auto-Quality", "families": _ALL_FAMILIES,
        "desc": "Automatically step down trail resolution if frame time exceeds budget.",
    },
    "quality.reduced_motion": {
        "group": "quality", "type": "bool", "default": False,
        "label": "Reduced Motion Mode", "families": _ALL_FAMILIES,
        "desc": "Dampens high-frequency waves, spins, jitter, and sudden bursts.",
    },
    "quality.reduced_flashing": {
        "group": "quality", "type": "bool", "default": False,
        "label": "Reduced Flashing / Sparkle", "families": _ALL_FAMILIES,
        "desc": "Suppresses rapid pulsing, electric flashes, and high-frequency flicker.",
    },
}


class ValidationError(ValueError):
    """Raised when a preset or trail configuration fails validation."""


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' -> (r, g, b) floats in 0..1."""
    if not isinstance(hex_str, str) or not _HEX_RE.match(hex_str.strip()):
        return (0.54, 0.25, 0.99)
    s = hex_str.strip().lstrip("#")
    return (
        int(s[0:2], 16) / 255.0,
        int(s[2:4], 16) / 255.0,
        int(s[4:6], 16) / 255.0,
    )


def rgb_to_hex(rgb: tuple[float, float, float] | list[float]) -> str:
    """Convert (r, g, b) in 0..1 -> '#RRGGBB'."""
    r = int(np.clip(round(float(rgb[0]) * 255), 0, 255))
    g = int(np.clip(round(float(rgb[1]) * 255), 0, 255))
    b = int(np.clip(round(float(rgb[2]) * 255), 0, 255))
    return f"#{r:02X}{g:02X}{b:02X}"


def transform_rgb(
    rgb: tuple[float, float, float],
    hue_deg: float = 0.0,
    sat_mult: float = 1.0,
    val_mult: float = 1.0,
) -> tuple[float, float, float]:
    """Apply HSV shift/scale to an RGB 0..1 tuple."""
    if hue_deg == 0.0 and sat_mult == 1.0 and val_mult == 1.0:
        return rgb
    h, s, v = colorsys.rgb_to_hsv(
        float(np.clip(rgb[0], 0.0, 1.0)),
        float(np.clip(rgb[1], 0.0, 1.0)),
        float(np.clip(rgb[2], 0.0, 1.0)),
    )
    h = (h + (hue_deg / 360.0)) % 1.0
    s = float(np.clip(s * sat_mult, 0.0, 1.0))
    v = float(np.clip(v * val_mult, 0.0, 1.0))
    return colorsys.hsv_to_rgb(h, s, v)


def sample_gradient(
    stops: list[dict[str, Any]],
    t: np.ndarray | float,
    interp: str = "smooth",
    hue_deg: float = 0.0,
    sat_mult: float = 1.0,
    val_mult: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate a multi-stop gradient at parameter `t` in [0, 1].

    Returns (rgb, stop_alpha) with shapes (*t.shape, 3) and (*t.shape,).
    """
    t_arr = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    if not stops:
        rgb = np.broadcast_to(
            np.array([0.55, 0.25, 0.98], dtype=np.float32), (*t_arr.shape, 3)
        ).copy()
        return rgb, np.ones_like(t_arr, dtype=np.float32)

    ordered = sorted(stops, key=lambda s: float(s.get("position", 0.0)))
    pos = np.array([float(s.get("position", 0.0)) for s in ordered], dtype=np.float32)
    cols = np.array(
        [
            transform_rgb(
                hex_to_rgb(s.get("color", "#8A3FFC")), hue_deg, sat_mult, val_mult
            )
            for s in ordered
        ],
        dtype=np.float32,
    )
    alphas = np.array([float(s.get("opacity", 1.0)) for s in ordered], dtype=np.float32)

    if len(ordered) == 1:
        rgb = np.broadcast_to(cols[0], (*t_arr.shape, 3)).copy()
        a = np.full(t_arr.shape, alphas[0], dtype=np.float32)
        return rgb, a

    if interp == "step":
        idx = np.clip(np.searchsorted(pos, t_arr, side="right") - 1, 0, len(pos) - 1)
        return cols[idx], alphas[idx]

    # Piecewise interpolation
    idx_hi = np.clip(np.searchsorted(pos, t_arr, side="right"), 1, len(pos) - 1)
    idx_lo = idx_hi - 1
    p0 = pos[idx_lo]
    p1 = pos[idx_hi]
    span = np.maximum(p1 - p0, 1e-6)
    u = np.clip((t_arr - p0) / span, 0.0, 1.0)
    if interp == "smooth":
        u = u * u * (3.0 - 2.0 * u)

    c0 = cols[idx_lo]
    c1 = cols[idx_hi]
    rgb = c0 + (c1 - c0) * u[..., None]
    a = alphas[idx_lo] + (alphas[idx_hi] - alphas[idx_lo]) * u
    return rgb, a


def default_layer(
    layer_id: str = "layer_1",
    name: str = "Primary Layer",
    family: str = "ribbon",
) -> dict[str, Any]:
    """Construct a complete validated default layer dictionary."""
    return {
        "id": layer_id,
        "name": name,
        "enabled": True,
        "solo": False,
        "family": family if family in GEOMETRY_FAMILIES else "ribbon",
        "size_scale": 1.0,
        "width_px": 18.0,
        "head_width_px": 22.0,
        "tail_width_px": 2.0,
        "taper": 0.85,
        "smoothing": 0.55,
        "segment_density": 1.0,
        "segment_spacing_px": 22.0,
        "curve_tension": 0.5,
        "sharpness": 0.45,
        "offset_px": 0.0,
        "strand_count": 2 if family == "spiral" else 1,
        "end_cap": "round",
        "width_noise": 0.08,
        "echo_count": 6,
        "lifetime_s": 1.8,
        "fade_in_s": 0.04,
        "fade_out_s": 1.2,
        "fade_curve": "smooth",
        "persistence": 0.6,
        "spawn_delay_s": 0.0,
        "dissipation_rate": 1.0,
        "length_cap_px": 900.0,
        "lifetime_variance": 0.2,
        "base_color": "#8A3FFC",
        "secondary_color": "#33E1FF",
        "gradient_enabled": True,
        "gradient_stops": [
            {"position": 0.0, "color": "#C77DFF", "opacity": 1.0},
            {"position": 0.55, "color": "#7B2CBF", "opacity": 0.85},
            {"position": 1.0, "color": "#48CAE4", "opacity": 0.0},
        ],
        "gradient_interp": "smooth",
        "gradient_direction": "along",
        "color_cycle_rate": 0.0,
        "hue_offset": 0.0,
        "hue_variance": 0.05,
        "saturation": 1.0,
        "brightness": 1.0,
        "theme_sync": False,
        "velocity_color_mod": 0.25,
        "opacity": 0.78,
        "blend_mode": "add",
        "soft_edge": 0.55,
        "edge_falloff": 1.4,
        "overlap_intensity": 0.85,
        "priority": 0,
        "glow": {
            "enabled": True,
            "intensity": 0.65,
            "radius_px": 16.0,
            "falloff": 1.5,
            "halo_color": "#7B2CBF",
            "core_intensity": 0.85,
            "pulse_speed": 0.0,
            "pulse_depth": 0.0,
            "bloom_quality": 2,
        },
        "particles": {
            "spawn_rate": 36.0,
            "spawn_burst_size": 12,
            "spawn_variance": 0.25,
            "max_particles": 120,
            "shape": "circle",
            "size_px": 9.0,
            "size_variation": 0.35,
            "rotation_deg": 0.0,
            "angular_velocity": 45.0,
            "initial_velocity": 55.0,
            "velocity_inheritance": 0.25,
            "directional_spread": 120.0,
            "drag": 1.6,
            "gravity": -18.0,
            "turbulence": 45.0,
            "edge_behavior": "fade",
            "sparkle": 0.25,
            "growth_rate": 0.3,
        },
        "motion": {
            "wave_amplitude": 0.0,
            "wave_frequency": 2.5,
            "wave_phase": 0.0,
            "spiral_radius": 18.0,
            "spiral_speed": 4.0,
            "curl_noise": 4.0,
            "drift_x": 0.0,
            "drift_y": -8.0,
            "position_jitter": 0.0,
            "directional_smoothing": 0.5,
            "acceleration_response": 0.5,
            "curvature_response": 0.4,
            "speed_response": 0.65,
        },
    }


def default_behavior_modifiers() -> dict[str, Any]:
    return {
        "enabled": True,
        "idle_emission": 0.35,
        "wander_intensity": 0.75,
        "curious_intensity": 1.05,
        "perform_intensity": 1.40,
        "swoop_intensity": 1.35,
        "dive_intensity": 1.60,
        "recover_intensity": 0.70,
        "startle_burst": 1.50,
        "resting_fade": 0.10,
        "attack_time_s": 0.18,
        "release_time_s": 0.65,
        "speed_to_length": 0.85,
        "accel_to_burst": 0.70,
        "curvature_to_spiral": 0.60,
        "state_to_glow": 0.75,
    }


def default_quality_config() -> dict[str, Any]:
    return {
        "preset": "balanced",
        "res_scale": 3,
        "sample_spacing_px": 6.0,
        "segment_cap": 120,
        "particle_cap": 150,
        "max_lifetime_s": 4.5,
        "effect_budget": 0.75,
        "auto_quality": True,
        "reduced_motion": False,
        "reduced_flashing": False,
        "disable_bursts": False,
    }


def _check_finite_number(val: Any, name: str) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValidationError(f"Parameter '{name}' must be a number, got {type(val).__name__}")
    f = float(val)
    if not math.isfinite(f):
        raise ValidationError(f"Parameter '{name}' must be finite, got {val!r}")
    return f


def _validate_param_value(key: str, val: Any, strict: bool = False) -> Any:
    meta = PARAM_SCHEMA.get(key)
    if meta is None:
        if strict:
            raise ValidationError(f"Unknown parameter '{key}'")
        return val
    ptype = meta["type"]
    if ptype == "bool":
        if not isinstance(val, bool):
            if strict:
                raise ValidationError(f"Parameter '{key}' must be bool")
            return bool(val)
        return val
    if ptype == "enum":
        if val not in meta["choices"]:
            raise ValidationError(
                f"Parameter '{key}' value {val!r} not in {meta['choices']}"
            )
        return val
    if ptype == "color":
        if not isinstance(val, str) or not _HEX_RE.match(val.strip()):
            raise ValidationError(f"Parameter '{key}' must be '#RRGGBB' hex color, got {val!r}")
        s = val.strip().upper()
        return s if s.startswith("#") else f"#{s}"
    if ptype in ("float", "int"):
        f = _check_finite_number(val, key)
        lo, hi = float(meta["min"]), float(meta["max"])
        if strict and (f < lo - 1e-6 or f > hi + 1e-6):
            raise ValidationError(f"Parameter '{key}'={f} out of range [{lo}, {hi}]")
        f = float(np.clip(f, lo, hi))
        return int(round(f)) if ptype == "int" else f
    return val


def validate_gradient_stops(stops: Any, strict: bool = False) -> list[dict[str, Any]]:
    if not isinstance(stops, list) or len(stops) == 0:
        raise ValidationError("gradient_stops must be a non-empty list")
    if len(stops) > MAX_GRADIENT_STOPS:
        if strict:
            raise ValidationError(f"Too many gradient stops ({len(stops)} > {MAX_GRADIENT_STOPS})")
        stops = stops[:MAX_GRADIENT_STOPS]
    out = []
    for i, st in enumerate(stops):
        if not isinstance(st, dict):
            raise ValidationError(f"gradient_stops[{i}] must be a dict")
        pos = _check_finite_number(st.get("position", i / max(1, len(stops) - 1)), f"gradient_stops[{i}].position")
        if strict and (pos < -1e-6 or pos > 1.0 + 1e-6):
            raise ValidationError(f"gradient_stops[{i}].position out of [0, 1]")
        col = _validate_param_value("base_color", st.get("color", "#8A3FFC"), strict=strict)
        op = _check_finite_number(st.get("opacity", 1.0), f"gradient_stops[{i}].opacity")
        if strict and (op < -1e-6 or op > 1.0 + 1e-6):
            raise ValidationError(f"gradient_stops[{i}].opacity out of [0, 1]")
        out.append({
            "position": float(np.clip(pos, 0.0, 1.0)),
            "color": col,
            "opacity": float(np.clip(op, 0.0, 1.0)),
        })
    out.sort(key=lambda s: s["position"])
    return out


def validate_layer_dict(layer: Any, index: int = 0, strict: bool = False) -> dict[str, Any]:
    if not isinstance(layer, dict):
        raise ValidationError(f"Layer {index} must be a dict")
    base = default_layer(
        layer_id=str(layer.get("id") or f"layer_{index + 1}"),
        name=str(layer.get("name") or f"Layer {index + 1}"),
        family=str(layer.get("family", layer.get("type", "ribbon"))),
    )
    if not base["id"].strip():
        raise ValidationError(f"Layer {index} has empty id")

    fam = layer.get("family", layer.get("type", base["family"]))
    base["family"] = _validate_param_value("family", fam, strict=strict)
    base["enabled"] = bool(layer.get("enabled", True))
    base["solo"] = bool(layer.get("solo", False))

    # Top-level scalar keys
    for k in (
        "size_scale", "width_px", "head_width_px", "tail_width_px", "taper",
        "smoothing", "segment_density", "segment_spacing_px", "curve_tension",
        "sharpness", "offset_px", "strand_count", "end_cap", "width_noise",
        "echo_count", "lifetime_s", "fade_in_s", "fade_out_s", "fade_curve",
        "persistence", "spawn_delay_s", "dissipation_rate", "length_cap_px",
        "lifetime_variance", "base_color", "secondary_color", "gradient_enabled",
        "gradient_interp", "gradient_direction", "color_cycle_rate", "hue_offset",
        "hue_variance", "saturation", "brightness", "theme_sync",
        "velocity_color_mod", "opacity", "blend_mode", "soft_edge",
        "edge_falloff", "overlap_intensity", "priority",
    ):
        if k in layer:
            base[k] = _validate_param_value(k, layer[k], strict=strict)

    if "gradient_stops" in layer or "gradient" in layer:
        raw_stops = layer.get("gradient_stops", layer.get("gradient"))
        base["gradient_stops"] = validate_gradient_stops(raw_stops, strict=strict)

    # Nested sub-dicts: glow, particles, motion
    for sub_name in ("glow", "particles", "motion"):
        if sub_name in layer:
            sub = layer[sub_name]
            if not isinstance(sub, dict):
                raise ValidationError(f"Layer '{base['id']}.{sub_name}' must be a dict")
            for sk, sv in sub.items():
                dotted = f"{sub_name}.{sk}"
                if dotted in PARAM_SCHEMA:
                    base[sub_name][sk] = _validate_param_value(dotted, sv, strict=strict)
                elif strict:
                    raise ValidationError(f"Unknown parameter '{dotted}'")

    return base


def validate_preset_dict(data: Any, strict: bool = False) -> dict[str, Any]:
    """Validate and normalize a preset dictionary.

    Raises ValidationError on malformed input. Clamps numeric bounds unless
    strict=True is requested (used for import validation).
    """
    if not isinstance(data, dict):
        raise ValidationError("Preset must be a JSON object / dict")
    ver = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(ver, int) or ver < 1 or ver > SCHEMA_VERSION:
        raise ValidationError(f"Unsupported schema_version: {ver!r}")

    pid = str(data.get("id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not pid or not name:
        raise ValidationError("Preset requires non-empty 'id' and 'name'")
    if len(pid) > 80 or len(name) > 100:
        raise ValidationError("Preset 'id' or 'name' exceeds maximum length")

    cat = str(data.get("category", "custom")).lower()
    if cat not in PRESET_CATEGORIES:
        if strict:
            raise ValidationError(f"Unknown preset category: {cat!r}")
        cat = "custom"

    raw_layers = data.get("layers")
    if not isinstance(raw_layers, list) or len(raw_layers) == 0:
        raise ValidationError("Preset requires a non-empty 'layers' list")
    if len(raw_layers) > MAX_LAYERS:
        if strict:
            raise ValidationError(f"Preset has {len(raw_layers)} layers (max {MAX_LAYERS})")
        raw_layers = raw_layers[:MAX_LAYERS]

    layers = []
    seen_ids = set()
    for i, lyr in enumerate(raw_layers):
        v = validate_layer_dict(lyr, index=i, strict=strict)
        if v["id"] in seen_ids:
            if strict:
                raise ValidationError(f"Duplicate layer id '{v['id']}' in preset '{pid}'")
            v["id"] = f"{v['id']}_{i + 1}"
        seen_ids.add(v["id"])
        layers.append(v)

    beh = default_behavior_modifiers()
    raw_beh = data.get("behavior", data.get("reactivity", {}))
    if raw_beh is not None:
        if not isinstance(raw_beh, dict):
            raise ValidationError("'behavior' must be a dict")
        for bk, bv in raw_beh.items():
            if bk == "enabled":
                beh["enabled"] = bool(bv)
                continue
            dotted = f"behavior.{bk}"
            if dotted in PARAM_SCHEMA:
                beh[bk] = _validate_param_value(dotted, bv, strict=strict)
            elif strict:
                raise ValidationError(f"Unknown behavior modifier '{bk}'")

    gi = _check_finite_number(data.get("default_intensity", data.get("global_intensity", 0.85)), "default_intensity")
    if strict and (gi < 0.0 or gi > 2.0):
        raise ValidationError("default_intensity out of range [0.0, 2.0]")

    perf_class = str(data.get("performance_class", "light")).lower()
    if perf_class not in ("minimal", "light", "moderate", "heavy"):
        perf_class = "moderate"

    return {
        "schema_version": SCHEMA_VERSION,
        "id": pid,
        "name": name,
        "category": cat,
        "description": str(data.get("description", ""))[:400],
        "author": str(data.get("author", "Zwoop Studio"))[:80],
        "builtin": bool(data.get("builtin", False)),
        "default_intensity": float(np.clip(gi, 0.0, 2.0)),
        "performance_class": perf_class,
        "layers": layers,
        "behavior": beh,
    }


def default_trails_config() -> dict[str, Any]:
    """Default `render.trails` configuration block."""
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "active_preset": "nebula_silk",
        "favorites": ["nebula_silk", "stardust", "plasma_jet", "aurora_threads"],
        "recent_presets": ["nebula_silk"],
        "global_intensity": 0.85,
        "global_opacity": 0.90,
        "speed_reactivity": 0.80,
        "quality": default_quality_config(),
        "behavior_modifiers": default_behavior_modifiers(),
        "custom_working": None,
    }


def validate_trails_config(raw: Any) -> dict[str, Any]:
    """Validate and sanitize a `render.trails` configuration dictionary."""
    base = default_trails_config()
    if not isinstance(raw, dict):
        return base
    base["enabled"] = bool(raw.get("enabled", True))
    ap = raw.get("active_preset", base["active_preset"])
    if isinstance(ap, str) and ap.strip():
        base["active_preset"] = ap.strip()

    if isinstance(raw.get("favorites"), list):
        base["favorites"] = [str(x) for x in raw["favorites"] if isinstance(x, str)][:50]
    if isinstance(raw.get("recent_presets"), list):
        base["recent_presets"] = [str(x) for x in raw["recent_presets"] if isinstance(x, str)][:12]

    for k, lo, hi in (
        ("global_intensity", 0.0, 2.0),
        ("global_opacity", 0.0, 1.0),
        ("speed_reactivity", 0.0, 2.0),
    ):
        if k in raw:
            try:
                f = _check_finite_number(raw[k], k)
                base[k] = float(np.clip(f, lo, hi))
            except ValidationError:
                pass

    if isinstance(raw.get("quality"), dict):
        q = raw["quality"]
        for qk, qv in q.items():
            if qk == "disable_bursts":
                base["quality"]["disable_bursts"] = bool(qv)
                continue
            dotted = f"quality.{qk}"
            if dotted in PARAM_SCHEMA:
                try:
                    base["quality"][qk] = _validate_param_value(dotted, qv, strict=False)
                except ValidationError:
                    pass
    elif isinstance(raw.get("quality"), str) and raw["quality"] in QUALITY_LEVELS:
        base["quality"]["preset"] = raw["quality"]

    if isinstance(raw.get("behavior_modifiers"), dict):
        bm = raw["behavior_modifiers"]
        for bk, bv in bm.items():
            if bk == "enabled":
                base["behavior_modifiers"]["enabled"] = bool(bv)
                continue
            dotted = f"behavior.{bk}"
            if dotted in PARAM_SCHEMA:
                try:
                    base["behavior_modifiers"][bk] = _validate_param_value(dotted, bv, strict=False)
                except ValidationError:
                    pass

    if isinstance(raw.get("custom_working"), dict):
        try:
            base["custom_working"] = validate_preset_dict(raw["custom_working"], strict=False)
        except ValidationError:
            base["custom_working"] = None

    return base


def migrate_legacy_config(cfg_data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a pre-Trail-Studio config dict cleanly and deterministically.

    Compatibility rules (Section 10.1):
    - If `render.trails` is missing or invalid, create it from defaults.
    - If legacy `render.trail` was explicitly `False`, set `render.trails.enabled = False`
      so users who disabled trails do not unexpectedly get expensive effects.
    - If `render.effects_level == 0`, default `render.trails.quality.preset = "eco"`
      and if `render.trail` was not explicitly set alongside `render.trails`,
      keep `render.trail` synchronized with `render.trails.enabled`.
    - Decouple `render.effects_level` from silently blocking trails when
      `render.trails.enabled` is explicitly `True`.
    """
    out = copy.deepcopy(cfg_data) if isinstance(cfg_data, dict) else {}
    render = out.setdefault("render", {})
    if not isinstance(render, dict):
        render = {}
        out["render"] = render

    had_trails_block = isinstance(render.get("trails"), dict)
    legacy_trail_flag = render.get("trail", True)
    effects_level = render.get("effects_level", 2)

    trails = validate_trails_config(render.get("trails"))

    if not had_trails_block:
        # First-time migration from legacy schema
        if legacy_trail_flag is False:
            trails["enabled"] = False
        elif effects_level == 0 and "trail" not in render:
            trails["enabled"] = False
            trails["quality"]["preset"] = "eco"
        elif effects_level == 1:
            trails["quality"]["preset"] = "eco"

    render["trails"] = trails
    render["trail"] = bool(trails["enabled"])
    return out
