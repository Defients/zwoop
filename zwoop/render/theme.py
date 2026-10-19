"""Color identity — the Cosmotech palette family.

Each theme: deep base, luminous core, rim glow, accent.
RGB 0..1 tuples.
"""

THEMES = {
    "cosmos": {   # default: violet -> magenta core, lavender rim, cyan spark
        "deep":    (0.30, 0.08, 0.62),
        "mid":     (0.62, 0.18, 0.95),
        "core":    (0.93, 0.55, 1.00),
        "rim":     (0.72, 0.80, 1.00),
        "spark":   (0.30, 0.95, 1.00),
    },
    "orchid": {   # warmer, magenta-forward
        "deep":    (0.42, 0.07, 0.55),
        "mid":     (0.85, 0.22, 0.85),
        "core":    (1.00, 0.66, 0.98),
        "rim":     (1.00, 0.75, 0.90),
        "spark":   (0.55, 0.85, 1.00),
    },
    "lagoon": {   # teal/cyan variant
        "deep":    (0.05, 0.32, 0.55),
        "mid":     (0.15, 0.65, 0.90),
        "core":    (0.60, 0.98, 1.00),
        "rim":     (0.65, 0.90, 1.00),
        "spark":   (0.75, 0.60, 1.00),
    },
    "ember": {    # magenta->warm accent
        "deep":    (0.48, 0.10, 0.40),
        "mid":     (0.92, 0.30, 0.62),
        "core":    (1.00, 0.70, 0.80),
        "rim":     (1.00, 0.82, 0.65),
        "spark":   (0.40, 0.90, 1.00),
    },
}
