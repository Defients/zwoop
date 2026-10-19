"""Zwoop Trail Studio V1.0 — The Living Motion Effects Engine."""

from .schema import (
    SCHEMA_VERSION,
    GEOMETRY_FAMILIES,
    BLEND_MODES,
    QUALITY_LEVELS,
    PARAM_SCHEMA,
    validate_preset_dict,
    validate_trails_config,
    migrate_legacy_config,
    hex_to_rgb,
    rgb_to_hex,
)
from .history import TrailSample, TrailHistory
from .particles import ParticleSystem
from .reactive import ReactiveController
from .presets import BUNDLED_PRESETS, PresetStore
from .randomizer import TrailRandomizer
from .engine import TrailEngine

__all__ = [
    "SCHEMA_VERSION",
    "GEOMETRY_FAMILIES",
    "BLEND_MODES",
    "QUALITY_LEVELS",
    "PARAM_SCHEMA",
    "validate_preset_dict",
    "validate_trails_config",
    "migrate_legacy_config",
    "hex_to_rgb",
    "rgb_to_hex",
    "TrailSample",
    "TrailHistory",
    "ParticleSystem",
    "ReactiveController",
    "BUNDLED_PRESETS",
    "PresetStore",
    "TrailRandomizer",
    "TrailEngine",
]
