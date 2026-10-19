"""Trail Studio V1.0 — Full CosmoTech Configuration & Live Preview Editor.

Provides:
  - Preset Gallery with cached real-engine thumbnails, search, category filter,
    performance badges, and favorites
  - Basic Mode (quick style, colors, intensity, length, width, glow, quality)
  - Advanced Mode (4-layer manager, multi-stop Gradient Editor, 8 grouped
    family-aware parameter tabs covering 80+ validated parameters)
  - Persistent Live Preview Dock + Preview tab using the real TrailEngine and
    creature Rasterizer across 8 deterministic demonstration flight paths
  - Management & Controlled Randomizer tab (Save As, Duplicate, Rename, Delete,
    Import/Export JSON, 5 randomizer modes, 8 lock categories, recipe codes)
  - Full session Undo / Redo, Apply, Revert, and Unsaved-change tracking
"""

from __future__ import annotations

import copy
import logging
import math
import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

import numpy as np

from ..render.rasterizer import Rasterizer
from ..trails.engine import TrailEngine
from ..trails.presets import BUNDLED_PRESETS, PresetStore
from ..trails.randomizer import LOCK_KEYS, RANDOMIZER_MODES, TrailRandomizer
from ..trails.schema import (
    BLEND_MODES,
    FADE_CURVES,
    GEOMETRY_FAMILIES,
    GRADIENT_DIRS,
    GRADIENT_INTERPS,
    MAX_LAYERS,
    PARAM_SCHEMA,
    QUALITY_LEVELS,
    ValidationError,
    default_layer,
    sample_gradient,
    validate_preset_dict,
)

log = logging.getLogger("zwoop.ui.studio")

# CosmoTech UI Palette
C_BG = "#0D0A14"
C_PANEL = "#151022"
C_CARD = "#1D1630"
C_CARD_SEL = "#2B1F4A"
C_BORDER = "#352856"
C_ACCENT = "#8A3FFC"
C_ACCENT_HI = "#C77DFF"
C_CYAN = "#48CAE4"
C_TEXT = "#F3EEFF"
C_MUTED = "#9E92B8"
C_WARN = "#FFB703"
C_OK = "#06D6A0"

DEMO_PATHS = (
    "figure_eight",
    "gentle_drift",
    "fast_dash",
    "swoop",
    "dive",
    "circular_orbit",
    "erratic_startle",
    "rest_hover",
)

DEMO_PATH_LABELS = {
    "figure_eight": "Figure-Eight",
    "gentle_drift": "Gentle Drift",
    "fast_dash": "Fast Straight Dash",
    "swoop": "Swoop Arc",
    "dive": "High-Speed Dive",
    "circular_orbit": "Circular Orbit",
    "erratic_startle": "Erratic / Startle",
    "rest_hover": "Rest / Slow Hover",
}

PRESET_PALETTES = {
    "CosmoTech Violet": [
        {"position": 0.0, "color": "#D896FF", "opacity": 1.0},
        {"position": 0.55, "color": "#7B2CBF", "opacity": 0.85},
        {"position": 1.0, "color": "#48CAE4", "opacity": 0.0},
    ],
    "Solar Prominence": [
        {"position": 0.0, "color": "#FFF3B0", "opacity": 1.0},
        {"position": 0.45, "color": "#FF7B00", "opacity": 0.90},
        {"position": 1.0, "color": "#9D0208", "opacity": 0.0},
    ],
    "Aurora Borealis": [
        {"position": 0.0, "color": "#80FFDB", "opacity": 1.0},
        {"position": 0.5, "color": "#48BFE3", "opacity": 0.85},
        {"position": 1.0, "color": "#7209B7", "opacity": 0.0},
    ],
    "Cyber Magenta": [
        {"position": 0.0, "color": "#FFFFFF", "opacity": 1.0},
        {"position": 0.35, "color": "#F72585", "opacity": 0.95},
        {"position": 1.0, "color": "#3A0CA3", "opacity": 0.0},
    ],
    "Glacial Cyan": [
        {"position": 0.0, "color": "#E0FBFC", "opacity": 1.0},
        {"position": 0.5, "color": "#00B4D8", "opacity": 0.85},
        {"position": 1.0, "color": "#03045E", "opacity": 0.0},
    ],
}


def generate_demo_snapshot(
    path_name: str,
    t: float,
    w: int = 360,
    h: int = 260,
    body_radius: float = 18.0,
) -> dict[str, Any]:
    """Generate a deterministic synthetic simulation snapshot for previewing."""
    cx0, cy0 = w * 0.5, h * 0.5
    rx, ry = w * 0.34, h * 0.32
    dt = 1.0 / 60.0

    def _eval_pos(tau: float) -> tuple[float, float, str, str]:
        if path_name == "gentle_drift":
            x = cx0 + rx * 0.75 * math.sin(tau * 1.1)
            y = cy0 + ry * 0.55 * math.cos(tau * 0.85)
            return x, y, "WANDER", ""
        if path_name == "fast_dash":
            cycle = (tau * 0.85) % 1.0
            u = cycle * cycle * (3.0 - 2.0 * cycle)
            x = w * 0.14 + (w * 0.72) * u
            y = cy0 + math.sin(u * math.pi) * (-18.0)
            return x, y, "PERFORM", "dart"
        if path_name == "swoop":
            a = tau * 1.8
            x = cx0 + rx * math.cos(a)
            y = cy0 - ry * 0.5 + ry * 0.9 * abs(math.sin(a))
            return x, y, "PERFORM", "swoop"
        if path_name == "dive":
            cycle = (tau * 0.75) % 1.0
            x = cx0 + rx * 0.65 * math.sin(cycle * 2.0 * math.pi)
            y = h * 0.18 + (h * 0.64) * (math.sin(cycle * math.pi) ** 1.6)
            return x, y, "PERFORM", "dive"
        if path_name == "circular_orbit":
            a = tau * 2.3
            x = cx0 + rx * 0.75 * math.cos(a)
            y = cy0 + ry * 0.75 * math.sin(a)
            return x, y, "CURIOUS", "orbit"
        if path_name == "erratic_startle":
            a = tau * 2.6
            x = cx0 + rx * 0.75 * math.sin(a) + 18.0 * math.sin(a * 4.3)
            y = cy0 + ry * 0.70 * math.cos(a * 1.3) + 16.0 * math.cos(a * 3.7)
            st = "STARTLE" if int(tau * 2.0) % 4 == 0 else "EVADE"
            return x, y, st, ""
        if path_name == "rest_hover":
            x = cx0 + 14.0 * math.sin(tau * 0.9)
            y = cy0 + 10.0 * math.cos(tau * 1.1)
            return x, y, "REST", ""
        # Default: figure_eight
        a = tau * 1.9
        x = cx0 + rx * math.sin(a)
        y = cy0 + ry * 0.85 * math.sin(2.0 * a)
        return x, y, "PERFORM", "figure8"

    x0, y0, _, _ = _eval_pos(t - dt)
    x1, y1, state, maneuver = _eval_pos(t)
    vx = (x1 - x0) / dt
    vy = (y1 - y0) / dt
    # Scale apparent speed to match desktop world-space speeds (0..850 px/s)
    speed = math.hypot(vx, vy) * 2.1

    n_outer = 12
    pos = np.zeros((n_outer + 1, 2), dtype=np.float32)
    vel = np.zeros((n_outer + 1, 2), dtype=np.float32)
    rad = np.full(n_outer + 1, body_radius * 0.48, dtype=np.float32)
    rad[0] = body_radius * 0.65

    pos[0] = (x1, y1)
    vel[:] = (vx * 2.1, vy * 2.1)
    ring_r = body_radius * 1.13
    hdg = math.atan2(vy, vx) if speed > 5.0 else 0.0
    stretch = min(0.35, speed / 1800.0)

    for i in range(1, n_outer + 1):
        ang = (i - 1) * 2.0 * math.pi / n_outer
        da = ang - hdg
        r_i = ring_r * (1.0 + stretch * math.cos(2.0 * da))
        pos[i, 0] = x1 + r_i * math.cos(ang)
        pos[i, 1] = y1 + r_i * math.sin(ang)

    return {
        "pos": pos,
        "radius": rad,
        "vel": vel,
        "center": np.array([x1, y1], dtype=np.float32),
        "speed": float(speed),
        "deform": float(stretch * 0.6),
        "energy": float(0.5 * speed * speed),
        "state": state,
        "maneuver": maneuver,
        "waypoint": None,
        "edge_hit": None,
        "t": float(t),
    }


def render_preview_rgba(
    engine: TrailEngine,
    creature_rast: Rasterizer,
    snap: dict[str, Any],
    w: int = 360,
    h: int = 260,
    bg_mode: str = "deep_space",
    theme_name: str = "cosmos",
) -> np.ndarray:
    """Composite background + TrailEngine + Creature into an (H, W, 3) uint8 RGB image."""
    # 1. Background
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    if bg_mode == "light_slate":
        rgb[:] = (0.86, 0.88, 0.92)
    elif bg_mode == "desktop_dark":
        rgb[:] = (0.11, 0.12, 0.15)
    else:  # deep_space or grid
        y_grad = np.linspace(0.04, 0.09, h, dtype=np.float32)[:, None]
        rgb[..., 0] = y_grad * 1.1
        rgb[..., 1] = y_grad * 0.8
        rgb[..., 2] = y_grad * 1.8
        if bg_mode == "grid":
            rgb[::24, :, :] += 0.05
            rgb[:, ::24, :] += 0.05

    # 2. Trail frame (premultiplied BGRA)
    t_frame = np.zeros((h, w, 4), dtype=np.uint8)
    engine.render_into(t_frame, (0.0, 0.0), snap, theme_name=theme_name, res_scale_override=2)
    ta = t_frame[..., 3:4].astype(np.float32) / 255.0
    t_rgb_pre = t_frame[..., [2, 1, 0]].astype(np.float32) / 255.0
    rgb = t_rgb_pre + rgb * (1.0 - ta)

    # 3. Creature silhouette on top
    csz = creature_rast.size
    c_frame = np.zeros((csz, csz, 4), dtype=np.uint8)
    cx, cy = float(snap["center"][0]), float(snap["center"][1])
    ox, oy = int(round(cx - csz * 0.5)), int(round(cy - csz * 0.5))
    creature_rast.render(c_frame, snap, (ox, oy), dt=1 / 60, debug=False)

    # Clip creature box to preview (w, h)
    x0 = max(0, ox)
    y0 = max(0, oy)
    x1 = min(w, ox + csz)
    y1 = min(h, oy + csz)
    if x1 > x0 and y1 > y0:
        sub_c = c_frame[y0 - oy : y1 - oy, x0 - ox : x1 - ox]
        ca = sub_c[..., 3:4].astype(np.float32) / 255.0
        c_rgb_pre = sub_c[..., [2, 1, 0]].astype(np.float32) / 255.0
        rgb[y0:y1, x0:x1] = c_rgb_pre + rgb[y0:y1, x0:x1] * (1.0 - ca)

    return (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)


def _rgb_to_photoimage(rgb_arr: np.ndarray) -> tk.PhotoImage:
    """Convert an (H, W, 3) uint8 numpy array to a Tkinter PhotoImage via binary PPM."""
    h, w = rgb_arr.shape[:2]
    header = f"P6 {w} {h} 255\n".encode("ascii")
    ppm_bytes = header + np.ascontiguousarray(rgb_arr, dtype=np.uint8).tobytes()
    return tk.PhotoImage(width=w, height=h, data=ppm_bytes, format="PPM")


class TrailStudio:
    """Full Trail Studio configuration editor & live preview controller."""

    def __init__(
        self,
        trails_cfg: dict[str, Any],
        preset_store: PresetStore | None = None,
        on_apply: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        on_clear_trails: Callable[[], None] | None = None,
        theme_name: str = "cosmos",
    ):
        self.store = preset_store or PresetStore()
        self.on_apply = on_apply or (lambda cfg, preset: None)
        self.on_clear_trails = on_clear_trails or (lambda: None)
        self.theme_name = theme_name

        # Committed state (for Revert) vs Working state
        self.committed_cfg = copy.deepcopy(trails_cfg)
        self.working_cfg = copy.deepcopy(trails_cfg)

        init_preset = self._load_initial_preset()
        self.committed_preset = copy.deepcopy(init_preset)
        self.working_preset = copy.deepcopy(init_preset)

        self.selected_layer_idx: int = 0
        self.selected_stop_idx: int = 0
        self.clipboard_layer: dict[str, Any] | None = None
        self.unsaved_changes: bool = False

        # Session Undo / Redo stacks
        self.undo_stack: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.redo_stack: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.randomizer = TrailRandomizer()

        # Dedicated preview engine & creature rasterizer
        self.preview_engine = TrailEngine(copy.deepcopy(self.working_cfg), self.store, seed=77)
        self.preview_engine.load_preset(copy.deepcopy(self.working_preset), clear_existing=True)
        self.preview_creature = Rasterizer(160, theme=self.theme_name, effects=2, trail=False, res_scale=2)

        self.preview_path: str = "figure_eight"
        self.preview_speed: float = 1.0
        self.preview_paused: bool = False
        self.preview_bg: str = "deep_space"
        self.preview_t: float = 0.0
        self.live_desktop_apply: bool = True

        # Cached thumbnail PhotoImages by preset_id
        self._thumb_cache: dict[str, tk.PhotoImage] = {}
        self._preview_photo: tk.PhotoImage | None = None
        self._grad_photo: tk.PhotoImage | None = None

        # Tk widgets (created lazily on open_window)
        self.root: tk.Misc | None = None
        self.win: tk.Toplevel | tk.Tk | None = None
        self._is_open: bool = False
        self._suppress_callbacks: bool = False
        self._last_preview_tick: float = 0.0

    def _load_initial_preset(self) -> dict[str, Any]:
        cw = self.working_cfg.get("custom_working")
        if isinstance(cw, dict):
            try:
                return validate_preset_dict(cw, strict=False)
            except Exception:
                pass
        pid = self.working_cfg.get("active_preset", "nebula_silk")
        return self.store.get(pid) or copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])

    # ========================================================================
    # Programmatic State Manipulation (used by both UI callbacks and tests)
    # ========================================================================
    @property
    def active_layer(self) -> dict[str, Any]:
        layers = self.working_preset.get("layers", [])
        if not layers:
            layers.append(default_layer("layer_1", "Layer 1", "ribbon"))
        self.selected_layer_idx = max(0, min(len(layers) - 1, self.selected_layer_idx))
        return layers[self.selected_layer_idx]

    def _record_undo(self) -> None:
        self.undo_stack.append((copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset)))
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _mark_modified(self, sync_desktop: bool = True) -> None:
        self.unsaved_changes = True
        self.working_cfg["custom_working"] = copy.deepcopy(self.working_preset)
        self.preview_engine.cfg = copy.deepcopy(self.working_cfg)
        self.preview_engine.load_preset(copy.deepcopy(self.working_preset), clear_existing=False)
        if sync_desktop and self.live_desktop_apply:
            self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._refresh_status_bar()

    def select_preset(self, preset_id: str) -> dict[str, Any]:
        p = self.store.get(preset_id)
        if p is None:
            raise ValidationError(f"Preset '{preset_id}' not found")
        self._record_undo()
        self.working_preset = copy.deepcopy(p)
        self.working_cfg["active_preset"] = p["id"]
        self.working_cfg["custom_working"] = None
        self.selected_layer_idx = 0
        self.selected_stop_idx = 0
        self.unsaved_changes = False
        self.preview_engine.load_preset(copy.deepcopy(p), clear_existing=True)
        self._warm_preview_engine()
        if self.live_desktop_apply:
            self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._sync_all_widgets()
        return copy.deepcopy(self.working_preset)

    def _warm_preview_engine(self, steps: int = 32, w: int = 340, h: int = 230) -> None:
        """Pre-step preview engine so a rich trail is immediately visible."""
        dt = 1.0 / 30.0
        for _ in range(steps):
            self.preview_t += dt * self.preview_speed
            snap = generate_demo_snapshot(self.preview_path, self.preview_t, w=w, h=h, body_radius=17.0)
            self.preview_engine.step(dt * self.preview_speed, snap)

    def undo(self) -> bool:
        if not self.undo_stack:
            return False
        self.redo_stack.append((copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset)))
        self.working_cfg, self.working_preset = self.undo_stack.pop()
        self.preview_engine.cfg = copy.deepcopy(self.working_cfg)
        self.preview_engine.load_preset(copy.deepcopy(self.working_preset), clear_existing=False)
        if self.live_desktop_apply:
            self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._sync_all_widgets()
        return True

    def redo(self) -> bool:
        if not self.redo_stack:
            return False
        self.undo_stack.append((copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset)))
        self.working_cfg, self.working_preset = self.redo_stack.pop()
        self.preview_engine.cfg = copy.deepcopy(self.working_cfg)
        self.preview_engine.load_preset(copy.deepcopy(self.working_preset), clear_existing=False)
        if self.live_desktop_apply:
            self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._sync_all_widgets()
        return True

    def apply_changes(self) -> None:
        self.committed_cfg = copy.deepcopy(self.working_cfg)
        self.committed_preset = copy.deepcopy(self.working_preset)
        self.unsaved_changes = False
        self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._refresh_status_bar()

    def revert_changes(self) -> None:
        self._record_undo()
        self.working_cfg = copy.deepcopy(self.committed_cfg)
        self.working_preset = copy.deepcopy(self.committed_preset)
        self.unsaved_changes = False
        self.preview_engine.cfg = copy.deepcopy(self.working_cfg)
        self.preview_engine.load_preset(copy.deepcopy(self.working_preset), clear_existing=True)
        self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._sync_all_widgets()

    def reset_to_bundled(self) -> None:
        pid = self.working_preset.get("id", "nebula_silk")
        if pid in BUNDLED_PRESETS:
            self.select_preset(pid)
        else:
            self.select_preset("nebula_silk")

    def toggle_favorite(self, preset_id: str | None = None) -> bool:
        pid = preset_id or self.working_preset["id"]
        favs = list(self.working_cfg.get("favorites", []))
        if pid in favs:
            favs.remove(pid)
            is_fav = False
        else:
            favs.append(pid)
            is_fav = True
        self.working_cfg["favorites"] = favs
        self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))
        self._rebuild_gallery_cards()
        return is_fav

    # ---- Layer operations (Section 5.1) ------------------------------------
    def add_layer(self, family: str = "particles") -> dict[str, Any]:
        layers = self.working_preset["layers"]
        if len(layers) >= MAX_LAYERS:
            raise ValidationError(f"Maximum of {MAX_LAYERS} layers reached")
        self._record_undo()
        idx = len(layers) + 1
        lid = f"layer_{idx}"
        existing_ids = {l["id"] for l in layers}
        while lid in existing_ids:
            idx += 1
            lid = f"layer_{idx}"
        new_lyr = default_layer(lid, f"Layer {len(layers) + 1} ({family})", family)
        layers.append(new_lyr)
        self.selected_layer_idx = len(layers) - 1
        self._mark_modified()
        self._sync_all_widgets()
        return new_lyr

    def delete_layer(self, index: int | None = None) -> bool:
        layers = self.working_preset["layers"]
        if len(layers) <= 1:
            return False
        idx = self.selected_layer_idx if index is None else int(index)
        if not (0 <= idx < len(layers)):
            return False
        self._record_undo()
        layers.pop(idx)
        self.selected_layer_idx = max(0, min(len(layers) - 1, idx))
        self._mark_modified()
        self._sync_all_widgets()
        return True

    def duplicate_layer(self, index: int | None = None) -> dict[str, Any]:
        layers = self.working_preset["layers"]
        if len(layers) >= MAX_LAYERS:
            raise ValidationError(f"Maximum of {MAX_LAYERS} layers reached")
        idx = self.selected_layer_idx if index is None else int(index)
        src = copy.deepcopy(layers[idx])
        self._record_undo()
        n = len(layers) + 1
        existing_ids = {l["id"] for l in layers}
        lid = f"{src['id']}_copy"
        while lid in existing_ids:
            lid = f"{src['id']}_{n}"
            n += 1
        src["id"] = lid
        src["name"] = f"{src['name']} Copy"
        layers.insert(idx + 1, src)
        self.selected_layer_idx = idx + 1
        self._mark_modified()
        self._sync_all_widgets()
        return src

    def reorder_layer(self, delta: int) -> bool:
        layers = self.working_preset["layers"]
        i = self.selected_layer_idx
        j = i + int(delta)
        if not (0 <= j < len(layers)):
            return False
        self._record_undo()
        layers[i], layers[j] = layers[j], layers[i]
        self.selected_layer_idx = j
        self._mark_modified()
        self._sync_all_widgets()
        return True

    def rename_layer(self, new_name: str, index: int | None = None) -> None:
        idx = self.selected_layer_idx if index is None else int(index)
        if new_name.strip():
            self._record_undo()
            self.working_preset["layers"][idx]["name"] = new_name.strip()[:48]
            self._mark_modified()
            self._sync_all_widgets()

    def reset_layer(self, index: int | None = None) -> None:
        idx = self.selected_layer_idx if index is None else int(index)
        old = self.working_preset["layers"][idx]
        self._record_undo()
        self.working_preset["layers"][idx] = default_layer(old["id"], old["name"], old["family"])
        self._mark_modified()
        self._sync_all_widgets()

    def toggle_solo_layer(self, index: int | None = None) -> bool:
        idx = self.selected_layer_idx if index is None else int(index)
        lyr = self.working_preset["layers"][idx]
        new_solo = not bool(lyr.get("solo", False))
        for i, l in enumerate(self.working_preset["layers"]):
            l["solo"] = new_solo if i == idx else False
        self._mark_modified()
        self._sync_all_widgets()
        return new_solo

    def copy_layer_settings(self) -> None:
        self.clipboard_layer = copy.deepcopy(self.active_layer)

    def paste_layer_settings(self) -> bool:
        if self.clipboard_layer is None:
            return False
        self._record_undo()
        cur = self.active_layer
        lid, lname = cur["id"], cur["name"]
        pasted = copy.deepcopy(self.clipboard_layer)
        pasted["id"] = lid
        pasted["name"] = lname
        self.working_preset["layers"][self.selected_layer_idx] = pasted
        self._mark_modified()
        self._sync_all_widgets()
        return True

    # ---- Gradient stop operations (Section 9.6) ----------------------------
    def add_gradient_stop(self, position: float = 0.5, color: str = "#48CAE4", opacity: float = 0.9) -> None:
        stops = self.active_layer.setdefault("gradient_stops", [])
        if len(stops) >= 12:
            return
        self._record_undo()
        stops.append({
            "position": float(np.clip(position, 0.0, 1.0)),
            "color": color.upper(),
            "opacity": float(np.clip(opacity, 0.0, 1.0)),
        })
        stops.sort(key=lambda s: s["position"])
        self.selected_stop_idx = min(len(stops) - 1, max(0, self.selected_stop_idx))
        self._mark_modified()
        self._sync_all_widgets()

    def remove_gradient_stop(self, index: int | None = None) -> bool:
        stops = self.active_layer.get("gradient_stops", [])
        if len(stops) <= 2:
            return False
        idx = self.selected_stop_idx if index is None else int(index)
        if not (0 <= idx < len(stops)):
            return False
        self._record_undo()
        stops.pop(idx)
        self.selected_stop_idx = max(0, min(len(stops) - 1, idx))
        self._mark_modified()
        self._sync_all_widgets()
        return True

    def update_gradient_stop(self, index: int, position: float | None = None, color: str | None = None, opacity: float | None = None) -> None:
        stops = self.active_layer.get("gradient_stops", [])
        if not (0 <= index < len(stops)):
            return
        self._record_undo()
        st = stops[index]
        if position is not None:
            st["position"] = float(np.clip(position, 0.0, 1.0))
        if color is not None:
            c = color.strip().upper()
            if not c.startswith("#"):
                c = "#" + c
            if len(c) == 7:
                st["color"] = c
        if opacity is not None:
            st["opacity"] = float(np.clip(opacity, 0.0, 1.0))
        stops.sort(key=lambda s: s["position"])
        self.active_layer["base_color"] = stops[0]["color"]
        self.active_layer["secondary_color"] = stops[-1]["color"]
        self._mark_modified()
        self._sync_all_widgets()

    def set_layer_param(self, key: str, value: Any) -> None:
        """Set a parameter on the active layer (or behavior/quality block)."""
        self._record_undo()
        if key.startswith("behavior."):
            subk = key.split(".", 1)[1]
            self.working_preset.setdefault("behavior", {})[subk] = value
        elif key.startswith("quality."):
            subk = key.split(".", 1)[1]
            self.working_cfg.setdefault("quality", {})[subk] = value
        elif "." in key:
            grp, subk = key.split(".", 1)
            self.active_layer.setdefault(grp, {})[subk] = value
        else:
            self.active_layer[key] = value
        self._mark_modified()

    # ========================================================================
    # Thumbnail & Preview Rendering
    # ========================================================================
    def render_preset_thumbnail_array(self, preset_id: str, w: int = 136, h: int = 68) -> np.ndarray:
        """Render a deterministic preview thumbnail array (H, W, 3) for `preset_id`."""
        eng = TrailEngine(copy.deepcopy(self.working_cfg), self.store, seed=19)
        p = self.store.get(preset_id) or copy.deepcopy(BUNDLED_PRESETS["nebula_silk"])
        eng.load_preset(p, clear_existing=True)
        eng.cfg["quality"]["res_scale"] = 2
        rast = Rasterizer(88, theme=self.theme_name, effects=2, trail=False, res_scale=2)

        for step_i in range(28):
            t = step_i * (1.0 / 30.0)
            snap = generate_demo_snapshot("swoop", t, w=w, h=h, body_radius=10.0)
            snap["speed"] = 440.0
            eng.step(1.0 / 30.0, snap)
        return render_preview_rgba(eng, rast, snap, w=w, h=h, bg_mode="deep_space", theme_name=self.theme_name)

    def step_preview_frame(self, dt: float = 1 / 30, w: int = 340, h: int = 230) -> np.ndarray:
        """Advance the studio's live preview simulation and return (H, W, 3) RGB uint8."""
        if not self.preview_paused:
            self.preview_t += dt * self.preview_speed
        snap = generate_demo_snapshot(self.preview_path, self.preview_t, w=w, h=h, body_radius=17.0)
        if not self.preview_paused:
            self.preview_engine.step(dt * self.preview_speed, snap)
        return render_preview_rgba(
            self.preview_engine,
            self.preview_creature,
            snap,
            w=w,
            h=h,
            bg_mode=self.preview_bg,
            theme_name=self.theme_name,
        )

    # ========================================================================
    # Tkinter Window Lifecycle & Non-Blocking Main-Thread Pump
    # ========================================================================
    @property
    def is_open(self) -> bool:
        return bool(self._is_open and self.win is not None)

    def open_window(self) -> None:
        """Open or bring Trail Studio to front without blocking Zwoop's loop."""
        if self.is_open:
            try:
                self.win.deiconify()
                self.win.lift()
                return
            except tk.TclError:
                self._is_open = False

        if self.root is None:
            self.root = tk.Tk()
            self.root.withdraw()

        self.win = tk.Toplevel(self.root)
        self.win.title("Zwoop Trail Studio V1.0 — The Living Motion Effects Engine")
        self.win.geometry("1120x740")
        self.win.minsize(980, 640)
        self.win.configure(bg=C_BG)
        self.win.protocol("WM_DELETE_WINDOW", self.close_window)

        self._configure_ttk_styles()
        self._build_ui()
        self._is_open = True
        self._warm_preview_engine()
        self.win.update_idletasks()
        self._sync_all_widgets()
        self._update_preview_canvas()
        log.info("Trail Studio window opened")

    def close_window(self) -> None:
        self._is_open = False
        if self.win is not None:
            try:
                self.win.destroy()
            except Exception:
                pass
            self.win = None
        log.info("Trail Studio window closed")

    def pump(self, now: float | None = None) -> None:
        """Non-blocking GUI + preview pump called from ZwoopApp's main loop."""
        if not self._is_open or self.win is None:
            return
        try:
            import time as _time
            t_now = _time.perf_counter() if now is None else now
            if t_now - self._last_preview_tick >= (1.0 / 28.0):
                self._last_preview_tick = t_now
                self._update_preview_canvas()
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            self._is_open = False
            self.win = None
        except Exception as e:
            log.warning("Trail Studio pump error: %s", e)

    # ========================================================================
    # UI Construction
    # ========================================================================
    def _configure_ttk_styles(self) -> None:
        style = ttk.Style(self.win)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=C_BG, foreground=C_TEXT, font=("Segoe UI", 9))
        style.configure("TFrame", background=C_BG)
        style.configure("Panel.TFrame", background=C_PANEL)
        style.configure("Card.TFrame", background=C_CARD)
        style.configure("TLabel", background=C_BG, foreground=C_TEXT, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=C_PANEL, foreground=C_TEXT, font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=C_PANEL, foreground=C_MUTED, font=("Segoe UI", 8))
        style.configure("Header.TLabel", background=C_BG, foreground=C_TEXT, font=("Segoe UI Semibold", 13))
        style.configure("SubHeader.TLabel", background=C_PANEL, foreground=C_ACCENT_HI, font=("Segoe UI Semibold", 10))

        style.configure(
            "TNotebook", background=C_BG, borderwidth=0, tabmargins=[2, 4, 2, 0]
        )
        style.configure(
            "TNotebook.Tab",
            background=C_PANEL,
            foreground=C_MUTED,
            padding=[14, 6],
            font=("Segoe UI Semibold", 9),
            borderwidth=1,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", C_ACCENT), ("active", C_CARD)],
            foreground=[("selected", "#FFFFFF"), ("active", C_TEXT)],
        )

        style.configure(
            "TButton",
            background=C_CARD,
            foreground=C_TEXT,
            bordercolor=C_BORDER,
            padding=[10, 4],
            font=("Segoe UI", 9),
        )
        style.map(
            "TButton",
            background=[("active", C_ACCENT), ("pressed", C_ACCENT_HI)],
            foreground=[("active", "#FFFFFF")],
        )
        style.configure(
            "Accent.TButton",
            background=C_ACCENT,
            foreground="#FFFFFF",
            font=("Segoe UI Semibold", 9),
            padding=[12, 5],
        )
        style.map("Accent.TButton", background=[("active", C_ACCENT_HI)])

        style.configure("TCheckbutton", background=C_PANEL, foreground=C_TEXT)
        style.map("TCheckbutton", background=[("active", C_PANEL)])
        style.configure(
            "TCombobox",
            fieldbackground=C_CARD,
            background=C_CARD,
            foreground=C_TEXT,
            arrowcolor=C_ACCENT_HI,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C_CARD), ("disabled", C_PANEL)],
            selectbackground=[("readonly", C_CARD)],
            selectforeground=[("readonly", C_TEXT)],
            foreground=[("readonly", C_TEXT)],
            background=[("readonly", C_CARD)],
        )
        style.configure("Horizontal.TScale", background=C_PANEL, troughcolor=C_CARD)

    def _build_ui(self) -> None:
        # ---- Top Header Bar ------------------------------------------------
        hdr = tk.Frame(self.win, bg=C_BG, padx=14, pady=8)
        hdr.pack(fill="x")
        tk.Label(
            hdr,
            text="ZWOOP TRAIL STUDIO",
            bg=C_BG,
            fg=C_TEXT,
            font=("Segoe UI Semibold", 14),
        ).pack(side="left")
        tk.Label(
            hdr,
            text="  V1.0 · The Living Motion Effects Engine",
            bg=C_BG,
            fg=C_ACCENT_HI,
            font=("Segoe UI", 10),
        ).pack(side="left")

        self.var_enabled = tk.BooleanVar(value=bool(self.working_cfg.get("enabled", True)))
        chk_en = ttk.Checkbutton(
            hdr,
            text="Enable Trails",
            variable=self.var_enabled,
            command=self._on_toggle_enabled,
        )
        chk_en.pack(side="right", padx=6)

        self.var_live_apply = tk.BooleanVar(value=self.live_desktop_apply)
        ttk.Checkbutton(
            hdr,
            text="Live Desktop Preview",
            variable=self.var_live_apply,
            command=self._on_toggle_live_apply,
        ).pack(side="right", padx=12)

        # ---- Main Split Body: Left Notebook + Right Persistent Preview -----
        body = tk.Frame(self.win, bg=C_BG, padx=12, pady=2)
        body.pack(fill="both", expand=True)

        # Pack right_col FIRST so it always receives its full 368px width
        right_col = tk.Frame(body, bg=C_PANEL, width=368, highlightthickness=1, highlightbackground=C_BORDER)
        right_col.pack(side="right", fill="y")
        right_col.pack_propagate(False)

        left_col = tk.Frame(body, bg=C_BG)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.notebook = ttk.Notebook(left_col)
        self.notebook.pack(fill="both", expand=True)

        self.tab_presets = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_basic = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_advanced = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_preview = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.tab_manage = ttk.Frame(self.notebook, style="Panel.TFrame")

        self.notebook.add(self.tab_presets, text="  Presets (25)  ")
        self.notebook.add(self.tab_basic, text="  Basic  ")
        self.notebook.add(self.tab_advanced, text="  Advanced & Layers  ")
        self.notebook.add(self.tab_preview, text="  Preview & Reactivity  ")
        self.notebook.add(self.tab_manage, text="  Manage & Randomize  ")

        self._build_presets_tab()
        self._build_basic_tab()
        self._build_advanced_tab()
        self._build_preview_tab()
        self._build_manage_tab()
        self._build_right_preview_dock(right_col)

        # ---- Bottom Action & Status Bar ------------------------------------
        bar = tk.Frame(self.win, bg=C_PANEL, padx=14, pady=8, highlightthickness=1, highlightbackground=C_BORDER)
        bar.pack(fill="x", side="bottom")

        self.lbl_status = tk.Label(
            bar,
            text="Ready",
            bg=C_PANEL,
            fg=C_OK,
            font=("Segoe UI Semibold", 9),
        )
        self.lbl_status.pack(side="left")

        ttk.Button(bar, text="Undo", command=self.undo).pack(side="left", padx=(18, 4))
        ttk.Button(bar, text="Redo", command=self.redo).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear Trails", command=self._on_clear_clicked).pack(side="left", padx=8)

        ttk.Button(bar, text="Apply", style="Accent.TButton", command=self.apply_changes).pack(side="right", padx=4)
        ttk.Button(bar, text="Save As Preset...", command=self._prompt_save_as).pack(side="right", padx=4)
        ttk.Button(bar, text="Revert", command=self.revert_changes).pack(side="right", padx=4)
        ttk.Button(bar, text="Reset to Bundled", command=self.reset_to_bundled).pack(side="right", padx=4)

    # -------------------------------------------------------- 1. Presets Tab
    def _build_presets_tab(self) -> None:
        top = tk.Frame(self.tab_presets, bg=C_PANEL, padx=10, pady=8)
        top.pack(fill="x")

        tk.Label(top, text="Search:", bg=C_PANEL, fg=C_TEXT).pack(side="left")
        self.var_search = tk.StringVar()
        self.var_search.trace_add("write", lambda *_: self._rebuild_gallery_cards())
        ent = tk.Entry(top, textvariable=self.var_search, bg=C_CARD, fg=C_TEXT, insertbackground=C_TEXT, relief="flat", width=18)
        ent.pack(side="left", padx=(4, 12), ipady=3)

        tk.Label(top, text="Collection:", bg=C_PANEL, fg=C_TEXT).pack(side="left")
        self.var_cat_filter = tk.StringVar(value="All")
        cb_cat = ttk.Combobox(
            top,
            textvariable=self.var_cat_filter,
            values=["All", "Cosmic", "Elemental", "Ethereal", "Energetic", "Playful", "Experimental", "Legacy", "User"],
            state="readonly",
            width=13,
        )
        cb_cat.pack(side="left", padx=(4, 12))
        cb_cat.bind("<<ComboboxSelected>>", lambda _e: self._rebuild_gallery_cards())

        tk.Label(top, text="Sort:", bg=C_PANEL, fg=C_TEXT).pack(side="left")
        self.var_sort = tk.StringVar(value="category")
        cb_sort = ttk.Combobox(
            top,
            textvariable=self.var_sort,
            values=["category", "name", "performance"],
            state="readonly",
            width=11,
        )
        cb_sort.pack(side="left", padx=(4, 12))
        cb_sort.bind("<<ComboboxSelected>>", lambda _e: self._rebuild_gallery_cards())

        self.var_fav_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top,
            text="★ Favorites Only",
            variable=self.var_fav_only,
            command=self._rebuild_gallery_cards,
        ).pack(side="left")

        # Scrollable canvas for preset cards
        wrap = tk.Frame(self.tab_presets, bg=C_PANEL)
        wrap.pack(fill="both", expand=True, padx=8, pady=4)

        self.gal_canvas = tk.Canvas(wrap, bg=C_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.gal_canvas.yview)
        self.gal_inner = tk.Frame(self.gal_canvas, bg=C_PANEL)

        self.gal_inner.bind(
            "<Configure>",
            lambda _e: self.gal_canvas.configure(scrollregion=self.gal_canvas.bbox("all")),
        )
        self.gal_canvas.create_window((0, 0), window=self.gal_inner, anchor="nw")
        self.gal_canvas.configure(yscrollcommand=sb.set)

        self.gal_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._rebuild_gallery_cards()

    def _rebuild_gallery_cards(self) -> None:
        if not hasattr(self, "gal_inner") or self.gal_inner is None:
            return
        for child in self.gal_inner.winfo_children():
            child.destroy()

        presets = self.store.list_all(
            category=self.var_cat_filter.get(),
            search=self.var_search.get(),
            favorites_only=self.var_fav_only.get(),
            favorites=self.working_cfg.get("favorites", []),
            sort_by=self.var_sort.get(),
        )
        fav_set = set(self.working_cfg.get("favorites", []))
        active_id = self.working_preset.get("id")

        cols = 2
        for idx, p in enumerate(presets):
            r, c = divmod(idx, cols)
            pid = p["id"]
            is_sel = pid == active_id
            bg = C_CARD_SEL if is_sel else C_CARD
            border = C_ACCENT_HI if is_sel else C_BORDER

            card = tk.Frame(
                self.gal_inner,
                bg=bg,
                padx=8,
                pady=7,
                width=330,
                highlightthickness=1,
                highlightbackground=border,
            )
            card.grid(row=r, column=c, padx=6, pady=5, sticky="nsew")

            # Lazy cached thumbnail
            if pid not in self._thumb_cache:
                try:
                    arr = self.render_preset_thumbnail_array(pid, w=108, h=56)
                    self._thumb_cache[pid] = _rgb_to_photoimage(arr)
                except Exception:
                    pass
            thumb = self._thumb_cache.get(pid)
            if thumb is not None:
                lbl_img = tk.Label(card, image=thumb, bg=bg, bd=0)
                lbl_img.pack(side="left", padx=(0, 8))
                lbl_img.bind("<Button-1>", lambda _e, x=pid: self.select_preset(x))

            info = tk.Frame(card, bg=bg)
            info.pack(side="left", fill="both", expand=True)

            row1 = tk.Frame(info, bg=bg)
            row1.pack(fill="x")
            lbl_name = tk.Label(
                row1,
                text=p["name"],
                bg=bg,
                fg=C_TEXT,
                font=("Segoe UI Semibold", 10),
                anchor="w",
            )
            lbl_name.pack(side="left")
            lbl_name.bind("<Button-1>", lambda _e, x=pid: self.select_preset(x))

            star_txt = "★" if pid in fav_set else "☆"
            btn_fav = tk.Button(
                row1,
                text=star_txt,
                bg=bg,
                fg=C_WARN if pid in fav_set else C_MUTED,
                bd=0,
                font=("Segoe UI", 11),
                activebackground=bg,
                command=lambda x=pid: self.toggle_favorite(x),
            )
            btn_fav.pack(side="right")

            meta_txt = f"{p.get('category', 'custom').upper()} · {len(p.get('layers', []))}L · {p.get('performance_class', 'light')}"
            lbl_meta = tk.Label(info, text=meta_txt, bg=bg, fg=C_CYAN, font=("Segoe UI", 8), anchor="w")
            lbl_meta.pack(fill="x")
            lbl_meta.bind("<Button-1>", lambda _e, x=pid: self.select_preset(x))

            desc_txt = p.get("description", "")
            if len(desc_txt) > 68:
                desc_txt = desc_txt[:65] + "..."
            lbl_desc = tk.Label(info, text=desc_txt, bg=bg, fg=C_MUTED, font=("Segoe UI", 8), anchor="w", justify="left", wraplength=195)
            lbl_desc.pack(fill="x")
            lbl_desc.bind("<Button-1>", lambda _e, x=pid: self.select_preset(x))

            card.bind("<Button-1>", lambda _e, x=pid: self.select_preset(x))

    # ---------------------------------------------------------- 2. Basic Tab
    def _build_basic_tab(self) -> None:
        f = tk.Frame(self.tab_basic, bg=C_PANEL, padx=18, pady=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Quick Trail Controls", style="SubHeader.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        # Primary style selector
        ttk.Label(f, text="Primary Trail Style:", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        self.var_basic_family = tk.StringVar(value="ribbon")
        cb_fam = ttk.Combobox(f, textvariable=self.var_basic_family, values=list(GEOMETRY_FAMILIES), state="readonly", width=18)
        cb_fam.grid(row=1, column=1, sticky="w", pady=5)
        cb_fam.bind("<<ComboboxSelected>>", self._on_basic_family_changed)

        # Primary & Secondary Color pickers
        ttk.Label(f, text="Primary Head Color:", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        self.btn_basic_col1 = tk.Button(f, text="#8A3FFC", bg="#8A3FFC", fg="#FFFFFF", width=12, relief="flat", command=lambda: self._pick_basic_color(0))
        self.btn_basic_col1.grid(row=2, column=1, sticky="w", pady=5)

        ttk.Label(f, text="Secondary Tail Color:", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=5)
        self.btn_basic_col2 = tk.Button(f, text="#48CAE4", bg="#48CAE4", fg="#000000", width=12, relief="flat", command=lambda: self._pick_basic_color(1))
        self.btn_basic_col2.grid(row=3, column=1, sticky="w", pady=5)

        # Sliders: Intensity, Opacity, Length, Width, Glow, Speed Reactivity
        self._basic_vars: dict[str, tk.DoubleVar] = {}
        basic_sliders = [
            ("global_intensity", "Overall Intensity", 0.0, 2.0),
            ("global_opacity", "Global Opacity", 0.0, 1.0),
            ("lifetime_s", "Trail Length (Lifespan s)", 0.2, 6.0),
            ("width_px", "Trail Width (px)", 2.0, 64.0),
            ("glow_intensity", "Glow Luminance", 0.0, 2.0),
            ("speed_reactivity", "Speed Reactivity", 0.0, 2.0),
        ]
        for idx, (k, label, lo, hi) in enumerate(basic_sliders, start=4):
            ttk.Label(f, text=label + ":", style="Panel.TLabel").grid(row=idx, column=0, sticky="w", pady=5)
            v = tk.DoubleVar(value=1.0)
            self._basic_vars[k] = v
            lbl_val = ttk.Label(f, text="1.00", style="Muted.TLabel", width=8)
            lbl_val.grid(row=idx, column=2, sticky="w", padx=6)
            sc = ttk.Scale(
                f,
                from_=lo,
                to=hi,
                variable=v,
                orient="horizontal",
                length=240,
                command=lambda _val, key=k, lv=lbl_val: self._on_basic_slider(key, lv),
            )
            sc.grid(row=idx, column=1, sticky="ew", pady=5)

        # Quality preset & Accessibility toggles
        row_q = 10
        ttk.Label(f, text="Performance Quality:", style="Panel.TLabel").grid(row=row_q, column=0, sticky="w", pady=8)
        self.var_basic_quality = tk.StringVar(value="balanced")
        cb_q = ttk.Combobox(f, textvariable=self.var_basic_quality, values=list(QUALITY_LEVELS), state="readonly", width=18)
        cb_q.grid(row=row_q, column=1, sticky="w", pady=8)
        cb_q.bind("<<ComboboxSelected>>", self._on_basic_quality_changed)

        self.var_react_toggle = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            f,
            text="React to Zwoop's Movement & Behavior States",
            variable=self.var_react_toggle,
            command=self._on_basic_toggles_changed,
        ).grid(row=row_q + 1, column=0, columnspan=2, sticky="w", pady=4)

        self.var_red_motion = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f,
            text="Accessibility: Reduced Motion (dampen waves, spins, and bursts)",
            variable=self.var_red_motion,
            command=self._on_basic_toggles_changed,
        ).grid(row=row_q + 2, column=0, columnspan=3, sticky="w", pady=4)

        self.var_red_flash = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f,
            text="Accessibility: Reduced Flashing / Sparkle",
            variable=self.var_red_flash,
            command=self._on_basic_toggles_changed,
        ).grid(row=row_q + 3, column=0, columnspan=3, sticky="w", pady=4)

    # ------------------------------------------------------- 3. Advanced Tab
    def _build_advanced_tab(self) -> None:
        # ---- Top Layer Editor Bar (up to 4 layers) -------------------------
        lbar = tk.Frame(self.tab_advanced, bg=C_CARD, padx=10, pady=6, highlightthickness=1, highlightbackground=C_BORDER)
        lbar.pack(fill="x", padx=8, pady=(8, 4))

        tk.Label(lbar, text="LAYERS (1–4):", bg=C_CARD, fg=C_ACCENT_HI, font=("Segoe UI Semibold", 9)).pack(side="left", padx=(0, 8))
        self.layer_btn_frame = tk.Frame(lbar, bg=C_CARD)
        self.layer_btn_frame.pack(side="left")

        ops = tk.Frame(lbar, bg=C_CARD)
        ops.pack(side="right")
        ttk.Button(ops, text="+ Add", width=6, command=self._ui_add_layer).pack(side="left", padx=2)
        ttk.Button(ops, text="Dup", width=5, command=self._ui_dup_layer).pack(side="left", padx=2)
        ttk.Button(ops, text="Del", width=5, command=lambda: self.delete_layer()).pack(side="left", padx=2)
        ttk.Button(ops, text="↑", width=3, command=lambda: self.reorder_layer(-1)).pack(side="left", padx=1)
        ttk.Button(ops, text="↓", width=3, command=lambda: self.reorder_layer(1)).pack(side="left", padx=1)
        ttk.Button(ops, text="Solo", width=5, command=lambda: self.toggle_solo_layer()).pack(side="left", padx=2)
        ttk.Button(ops, text="Rename", width=7, command=self._ui_rename_layer).pack(side="left", padx=2)
        ttk.Button(ops, text="Copy", width=5, command=self.copy_layer_settings).pack(side="left", padx=2)
        ttk.Button(ops, text="Paste", width=5, command=self.paste_layer_settings).pack(side="left", padx=2)
        ttk.Button(ops, text="Reset", width=6, command=lambda: self.reset_layer()).pack(side="left", padx=2)

        # ---- Multi-Stop Gradient Editor Panel ------------------------------
        gbox = tk.Frame(self.tab_advanced, bg=C_CARD, padx=10, pady=6, highlightthickness=1, highlightbackground=C_BORDER)
        gbox.pack(fill="x", padx=8, pady=4)

        gtop = tk.Frame(gbox, bg=C_CARD)
        gtop.pack(fill="x")
        tk.Label(gtop, text="MULTI-STOP GRADIENT:", bg=C_CARD, fg=C_CYAN, font=("Segoe UI Semibold", 9)).pack(side="left")

        self.var_palette_pick = tk.StringVar(value="CosmoTech Violet")
        cb_pal = ttk.Combobox(gtop, textvariable=self.var_palette_pick, values=list(PRESET_PALETTES.keys()), state="readonly", width=16)
        cb_pal.pack(side="right", padx=4)
        cb_pal.bind("<<ComboboxSelected>>", self._on_apply_preset_palette)
        tk.Label(gtop, text="Palette:", bg=C_CARD, fg=C_MUTED).pack(side="right")

        self.grad_canvas = tk.Canvas(gbox, height=28, bg=C_BG, highlightthickness=1, highlightbackground=C_BORDER)
        self.grad_canvas.pack(fill="x", pady=4)
        self.grad_canvas.bind("<Button-1>", self._on_grad_canvas_click)
        self.grad_canvas.bind("<B1-Motion>", self._on_grad_canvas_drag)
        self.grad_canvas.bind("<Configure>", lambda _e: self._draw_gradient_bar())

        gctrl = tk.Frame(gbox, bg=C_CARD)
        gctrl.pack(fill="x")
        tk.Label(gctrl, text="Stop:", bg=C_CARD, fg=C_TEXT).pack(side="left")
        self.cb_stop_sel = ttk.Combobox(gctrl, state="readonly", width=10)
        self.cb_stop_sel.pack(side="left", padx=4)
        self.cb_stop_sel.bind("<<ComboboxSelected>>", self._on_stop_selected)

        tk.Label(gctrl, text="Pos:", bg=C_CARD, fg=C_TEXT).pack(side="left", padx=(6, 2))
        self.var_stop_pos = tk.DoubleVar(value=0.0)
        sp_pos = ttk.Scale(gctrl, from_=0.0, to=1.0, variable=self.var_stop_pos, orient="horizontal", length=90, command=self._on_stop_slider_changed)
        sp_pos.pack(side="left", padx=2)

        tk.Label(gctrl, text="Hex:", bg=C_CARD, fg=C_TEXT).pack(side="left", padx=(6, 2))
        self.var_stop_hex = tk.StringVar(value="#8A3FFC")
        ent_hex = tk.Entry(gctrl, textvariable=self.var_stop_hex, bg=C_PANEL, fg=C_TEXT, width=8, relief="flat")
        ent_hex.pack(side="left", padx=2)
        ent_hex.bind("<Return>", self._on_stop_hex_entered)
        self.btn_stop_pick = tk.Button(gctrl, text="Pick", bg="#8A3FFC", fg="#FFF", width=5, relief="flat", command=self._on_pick_stop_color)
        self.btn_stop_pick.pack(side="left", padx=3)

        tk.Label(gctrl, text="Alpha:", bg=C_CARD, fg=C_TEXT).pack(side="left", padx=(6, 2))
        self.var_stop_op = tk.DoubleVar(value=1.0)
        sp_op = ttk.Scale(gctrl, from_=0.0, to=1.0, variable=self.var_stop_op, orient="horizontal", length=80, command=self._on_stop_slider_changed)
        sp_op.pack(side="left", padx=2)

        ttk.Button(gctrl, text="+ Stop", width=6, command=lambda: self.add_gradient_stop(0.5, "#48CAE4", 0.85)).pack(side="right", padx=2)
        ttk.Button(gctrl, text="- Stop", width=6, command=lambda: self.remove_gradient_stop()).pack(side="right", padx=2)

        # ---- Grouped Sub-Notebook for 80+ Schema Parameters ----------------
        self.adv_sub_nb = ttk.Notebook(self.tab_advanced)
        self.adv_sub_nb.pack(fill="both", expand=True, padx=8, pady=4)

        self._param_vars: dict[str, tk.Variable] = {}
        self._param_rows: dict[str, tuple[tk.Widget, ...]] = {}
        self._param_val_labels: dict[str, ttk.Label] = {}

        groups = [
            ("geometry", "Geometry"),
            ("time", "Time & Fade"),
            ("color", "Color"),
            ("blend", "Blend"),
            ("glow", "Glow & Halo"),
            ("particles", "Particles"),
            ("motion", "Motion & Waves"),
            ("behavior", "Behavior Matrix"),
            ("quality", "Quality & Budget"),
        ]
        for grp_key, grp_title in groups:
            page = ttk.Frame(self.adv_sub_nb, style="Panel.TFrame")
            self.adv_sub_nb.add(page, text=f" {grp_title} ")
            self._populate_param_group_tab(page, grp_key)

    def _populate_param_group_tab(self, parent: ttk.Frame, group_key: str) -> None:
        canvas = tk.Canvas(parent, bg=C_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=C_PANEL, padx=12, pady=8)

        inner.bind("<Configure>", lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        keys = [k for k, m in PARAM_SCHEMA.items() if m["group"] == group_key]
        for r_idx, key in enumerate(keys):
            meta = PARAM_SCHEMA[key]
            ptype = meta["type"]
            lbl = ttk.Label(inner, text=meta["label"] + ":", style="Panel.TLabel", width=24, anchor="w")
            lbl.grid(row=r_idx, column=0, sticky="w", pady=3, padx=(0, 8))

            val_lbl = ttk.Label(inner, text="", style="Muted.TLabel", width=10)
            val_lbl.grid(row=r_idx, column=2, sticky="w", padx=6)
            self._param_val_labels[key] = val_lbl

            if ptype == "bool":
                var = tk.BooleanVar(value=bool(meta["default"]))
                ctrl = ttk.Checkbutton(
                    inner,
                    text=meta.get("desc", ""),
                    variable=var,
                    command=lambda k=key: self._on_adv_param_changed(k),
                )
                ctrl.grid(row=r_idx, column=1, columnspan=2, sticky="w", pady=3)
            elif ptype == "enum":
                var = tk.StringVar(value=str(meta["default"]))
                ctrl = ttk.Combobox(inner, textvariable=var, values=list(meta["choices"]), state="readonly", width=18)
                ctrl.grid(row=r_idx, column=1, sticky="w", pady=3)
                ctrl.bind("<<ComboboxSelected>>", lambda _e, k=key: self._on_adv_param_changed(k))
            elif ptype == "color":
                var = tk.StringVar(value=str(meta["default"]))
                ctrl = tk.Button(
                    inner,
                    textvariable=var,
                    bg=str(meta["default"]),
                    fg="#FFFFFF",
                    width=12,
                    relief="flat",
                    command=lambda k=key: self._on_pick_schema_color(k),
                )
                ctrl.grid(row=r_idx, column=1, sticky="w", pady=3)
            else:
                var = tk.DoubleVar(value=float(meta["default"]))
                ctrl = ttk.Scale(
                    inner,
                    from_=float(meta["min"]),
                    to=float(meta["max"]),
                    variable=var,
                    orient="horizontal",
                    length=220,
                    command=lambda _v, k=key: self._on_adv_param_changed(k),
                )
                ctrl.grid(row=r_idx, column=1, sticky="ew", pady=3)

            self._param_vars[key] = var
            self._param_rows[key] = (lbl, ctrl, val_lbl)

    # ---------------------------------------------- 4. Preview & Reactivity Tab
    def _build_preview_tab(self) -> None:
        f = tk.Frame(self.tab_preview, bg=C_PANEL, padx=18, pady=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Simulation & Flight Path Controls", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 8))

        row1 = tk.Frame(f, bg=C_PANEL)
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="Demonstration Flight Path:", bg=C_PANEL, fg=C_TEXT, width=24, anchor="w").pack(side="left")
        self.var_prev_path = tk.StringVar(value=self.preview_path)
        cb_p = ttk.Combobox(row1, textvariable=self.var_prev_path, values=list(DEMO_PATHS), state="readonly", width=20)
        cb_p.pack(side="left", padx=6)
        cb_p.bind("<<ComboboxSelected>>", self._on_preview_settings_changed)

        row2 = tk.Frame(f, bg=C_PANEL)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Preview Background:", bg=C_PANEL, fg=C_TEXT, width=24, anchor="w").pack(side="left")
        self.var_prev_bg = tk.StringVar(value=self.preview_bg)
        cb_bg = ttk.Combobox(row2, textvariable=self.var_prev_bg, values=["deep_space", "desktop_dark", "grid", "light_slate"], state="readonly", width=20)
        cb_bg.pack(side="left", padx=6)
        cb_bg.bind("<<ComboboxSelected>>", self._on_preview_settings_changed)

        row3 = tk.Frame(f, bg=C_PANEL)
        row3.pack(fill="x", pady=4)
        tk.Label(row3, text="Simulation Speed:", bg=C_PANEL, fg=C_TEXT, width=24, anchor="w").pack(side="left")
        self.var_prev_spd = tk.DoubleVar(value=1.0)
        ttk.Scale(row3, from_=0.2, to=2.0, variable=self.var_prev_spd, orient="horizontal", length=200, command=lambda _v: self._on_preview_settings_changed()).pack(side="left", padx=6)

        row4 = tk.Frame(f, bg=C_PANEL)
        row4.pack(fill="x", pady=6)
        tk.Label(row4, text="Timeline Scrub (s):", bg=C_PANEL, fg=C_TEXT, width=24, anchor="w").pack(side="left")
        self.var_prev_scrub = tk.DoubleVar(value=0.0)
        ttk.Scale(row4, from_=0.0, to=8.0, variable=self.var_prev_scrub, orient="horizontal", length=240, command=self._on_scrub_preview).pack(side="left", padx=6)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=14)
        ttk.Label(f, text="Live Telemetry & Engine Diagnostics", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 8))

        self.lbl_diag = tk.Label(
            f,
            text="",
            bg=C_CARD,
            fg=C_CYAN,
            font=("Consolas", 9),
            justify="left",
            anchor="nw",
            padx=12,
            pady=10,
        )
        self.lbl_diag.pack(fill="x", pady=4)

    # ------------------------------------------- 5. Management & Randomize Tab
    def _build_manage_tab(self) -> None:
        f = tk.Frame(self.tab_manage, bg=C_PANEL, padx=18, pady=14)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Preset Library Management", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 8))
        p_btns = tk.Frame(f, bg=C_PANEL)
        p_btns.pack(fill="x", pady=4)
        ttk.Button(p_btns, text="Save As New Preset...", style="Accent.TButton", command=self._prompt_save_as).pack(side="left", padx=4)
        ttk.Button(p_btns, text="Duplicate Preset", command=self._ui_duplicate_preset).pack(side="left", padx=4)
        ttk.Button(p_btns, text="Rename Custom...", command=self._ui_rename_preset).pack(side="left", padx=4)
        ttk.Button(p_btns, text="Delete Custom", command=self._ui_delete_preset).pack(side="left", padx=4)

        io_btns = tk.Frame(f, bg=C_PANEL)
        io_btns.pack(fill="x", pady=6)
        ttk.Button(io_btns, text="Import Preset (.json)...", command=self._ui_import_preset).pack(side="left", padx=4)
        ttk.Button(io_btns, text="Export Preset (.json)...", command=self._ui_export_preset).pack(side="left", padx=4)

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=14)
        ttk.Label(f, text="Controlled Randomizer & Recipe Engine", style="SubHeader.TLabel").pack(anchor="w", pady=(0, 8))

        r_row1 = tk.Frame(f, bg=C_PANEL)
        r_row1.pack(fill="x", pady=4)
        tk.Label(r_row1, text="Randomize Mode:", bg=C_PANEL, fg=C_TEXT).pack(side="left")
        self.var_rand_mode = tk.StringVar(value="variation")
        ttk.Combobox(r_row1, textvariable=self.var_rand_mode, values=list(RANDOMIZER_MODES), state="readonly", width=15).pack(side="left", padx=8)

        tk.Label(r_row1, text="Seed (optional):", bg=C_PANEL, fg=C_TEXT).pack(side="left", padx=(12, 4))
        self.var_rand_seed = tk.StringVar(value="")
        tk.Entry(r_row1, textvariable=self.var_rand_seed, bg=C_CARD, fg=C_TEXT, width=12, relief="flat").pack(side="left", padx=4)

        ttk.Button(r_row1, text="Roll Random!", style="Accent.TButton", command=lambda: self._ui_run_randomizer(use_typed_seed=False)).pack(side="left", padx=6)
        ttk.Button(r_row1, text="Run Seed", command=lambda: self._ui_run_randomizer(use_typed_seed=True)).pack(side="left", padx=4)
        ttk.Button(r_row1, text="Undo Roll", command=self._ui_undo_randomizer).pack(side="left", padx=4)

        # Lock checkboxes
        tk.Label(f, text="Parameter Locks (checked categories stay unchanged):", bg=C_PANEL, fg=C_MUTED).pack(anchor="w", pady=(10, 4))
        l_frame = tk.Frame(f, bg=C_PANEL)
        l_frame.pack(fill="x", pady=2)
        self.rand_lock_vars: dict[str, tk.BooleanVar] = {}
        for i, lk in enumerate(LOCK_KEYS):
            v = tk.BooleanVar(value=False)
            self.rand_lock_vars[lk] = v
            ttk.Checkbutton(l_frame, text=lk.capitalize(), variable=v).grid(row=i // 4, column=i % 4, sticky="w", padx=10, pady=2)

        # Shareable recipe string
        rec_row = tk.Frame(f, bg=C_PANEL)
        rec_row.pack(fill="x", pady=(12, 4))
        tk.Label(rec_row, text="Shareable Recipe:", bg=C_PANEL, fg=C_TEXT).pack(side="left")
        self.var_recipe_str = tk.StringVar(value="")
        tk.Entry(rec_row, textvariable=self.var_recipe_str, bg=C_CARD, fg=C_CYAN, width=42, relief="flat").pack(side="left", padx=8)
        ttk.Button(rec_row, text="Apply Recipe", command=self._ui_apply_recipe).pack(side="left", padx=4)

    # ------------------------------------------- Right Persistent Preview Dock
    def _build_right_preview_dock(self, parent: tk.Frame) -> None:
        pad = tk.Frame(parent, bg=C_PANEL, padx=10, pady=10)
        pad.pack(fill="both", expand=True)

        self.lbl_dock_title = tk.Label(
            pad,
            text="LIVE ENGINE PREVIEW",
            bg=C_PANEL,
            fg=C_ACCENT_HI,
            font=("Segoe UI Semibold", 10),
        )
        self.lbl_dock_title.pack(anchor="w")

        self.lbl_active_preset_name = tk.Label(
            pad,
            text="Nebula Silk",
            bg=C_PANEL,
            fg=C_TEXT,
            font=("Segoe UI Semibold", 12),
        )
        self.lbl_active_preset_name.pack(anchor="w", pady=(0, 6))

        self.prev_canvas = tk.Canvas(
            pad, width=340, height=230, bg=C_BG, highlightthickness=1, highlightbackground=C_BORDER
        )
        self.prev_canvas.pack()

        pbar = tk.Frame(pad, bg=C_PANEL, pady=6)
        pbar.pack(fill="x")
        self.btn_pause_prev = ttk.Button(pbar, text="Pause", width=8, command=self._on_toggle_pause_preview)
        self.btn_pause_prev.pack(side="left")

        self.cb_dock_path = ttk.Combobox(pbar, values=list(DEMO_PATHS), state="readonly", width=15)
        self.cb_dock_path.set(self.preview_path)
        self.cb_dock_path.pack(side="right")
        self.cb_dock_path.bind("<<ComboboxSelected>>", self._on_dock_path_changed)

        # Quick Layer Summary in dock
        tk.Label(pad, text="Active Layer Stack:", bg=C_PANEL, fg=C_MUTED, font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 4))
        self.dock_layer_info = tk.Label(
            pad,
            text="",
            bg=C_CARD,
            fg=C_TEXT,
            font=("Consolas", 8),
            justify="left",
            anchor="nw",
            padx=8,
            pady=8,
        )
        self.dock_layer_info.pack(fill="x")

        self.lbl_perf_badge = tk.Label(
            pad,
            text="",
            bg=C_PANEL,
            fg=C_CYAN,
            font=("Segoe UI", 8),
            justify="left",
            anchor="w",
        )
        self.lbl_perf_badge.pack(fill="x", pady=(8, 0))

    # ========================================================================
    # Widget Synchronization & Event Handlers
    # ========================================================================
    def _sync_all_widgets(self) -> None:
        if not self._is_open or self.win is None:
            return
        self._suppress_callbacks = True
        try:
            p = self.working_preset
            lyr = self.active_layer

            self.var_enabled.set(bool(self.working_cfg.get("enabled", True)))
            self.lbl_active_preset_name.configure(text=f"{p.get('name', 'Custom')} ({p.get('category', 'custom')})")

            # Basic tab sync
            self.var_basic_family.set(lyr.get("family", "ribbon"))
            c1 = lyr.get("base_color", "#8A3FFC")
            c2 = lyr.get("secondary_color", "#48CAE4")
            self.btn_basic_col1.configure(text=c1, bg=c1)
            self.btn_basic_col2.configure(text=c2, bg=c2)

            self._basic_vars["global_intensity"].set(float(self.working_cfg.get("global_intensity", 0.85)))
            self._basic_vars["global_opacity"].set(float(self.working_cfg.get("global_opacity", 0.90)))
            self._basic_vars["lifetime_s"].set(float(lyr.get("lifetime_s", 1.8)))
            self._basic_vars["width_px"].set(float(lyr.get("width_px", 18.0)))
            self._basic_vars["glow_intensity"].set(float(lyr.get("glow", {}).get("intensity", 0.65)))
            self._basic_vars["speed_reactivity"].set(float(self.working_cfg.get("speed_reactivity", 0.80)))
            self.var_basic_quality.set(str(self.working_cfg.get("quality", {}).get("preset", "balanced")))
            self.var_react_toggle.set(bool(p.get("behavior", {}).get("enabled", True)))
            self.var_red_motion.set(bool(self.working_cfg.get("quality", {}).get("reduced_motion", False)))
            self.var_red_flash.set(bool(self.working_cfg.get("quality", {}).get("reduced_flashing", False)))

            # Rebuild layer selector bar
            for ch in self.layer_btn_frame.winfo_children():
                ch.destroy()
            for i, l in enumerate(p.get("layers", [])):
                is_cur = i == self.selected_layer_idx
                solo_tag = " [SOLO]" if l.get("solo") else ""
                en_tag = "✓" if l.get("enabled", True) else "○"
                btn = tk.Button(
                    self.layer_btn_frame,
                    text=f"{en_tag} L{i + 1}: {l.get('family', 'ribbon')}{solo_tag}",
                    bg=C_ACCENT if is_cur else C_PANEL,
                    fg="#FFFFFF" if is_cur else C_TEXT,
                    relief="flat",
                    padx=8,
                    pady=2,
                    command=lambda idx=i: self._on_select_layer(idx),
                )
                btn.pack(side="left", padx=2)

            # Sync gradient editor
            self._sync_gradient_widgets()

            # Sync all 80+ schema controls & hide non-applicable family rows
            fam = lyr.get("family", "ribbon")
            for key, var in self._param_vars.items():
                meta = PARAM_SCHEMA[key]
                val = self._read_param_from_working(key)
                if val is not None:
                    var.set(val)
                if key in self._param_val_labels:
                    if meta["type"] == "float":
                        self._param_val_labels[key].configure(text=f"{float(val):.2f} {meta.get('unit', '')}")
                    elif meta["type"] == "int":
                        self._param_val_labels[key].configure(text=f"{int(val)} {meta.get('unit', '')}")
                    else:
                        self._param_val_labels[key].configure(text="")

                if meta["type"] == "color" and key in self._param_rows:
                    btn_c = self._param_rows[key][1]
                    try:
                        btn_c.configure(bg=str(val))
                    except tk.TclError:
                        pass

                # Family applicability visibility
                applicable = fam in meta.get("families", GEOMETRY_FAMILIES)
                row_widgets = self._param_rows.get(key, ())
                for w_item in row_widgets:
                    if applicable:
                        w_item.grid()
                    else:
                        w_item.grid_remove()

            self._rebuild_gallery_cards()
            self._refresh_status_bar()
        finally:
            self._suppress_callbacks = False

    def _read_param_from_working(self, key: str) -> Any:
        lyr = self.active_layer
        if key.startswith("behavior."):
            return self.working_preset.get("behavior", {}).get(key.split(".", 1)[1], PARAM_SCHEMA[key]["default"])
        if key.startswith("quality."):
            return self.working_cfg.get("quality", {}).get(key.split(".", 1)[1], PARAM_SCHEMA[key]["default"])
        if "." in key:
            grp, subk = key.split(".", 1)
            return lyr.get(grp, {}).get(subk, PARAM_SCHEMA[key]["default"])
        return lyr.get(key, PARAM_SCHEMA[key]["default"])

    def _sync_gradient_widgets(self) -> None:
        stops = self.active_layer.get("gradient_stops", [])
        if not stops:
            return
        self.selected_stop_idx = max(0, min(len(stops) - 1, self.selected_stop_idx))
        labels = [f"Stop {i + 1} ({s['position']:.2f})" for i, s in enumerate(stops)]
        self.cb_stop_sel.configure(values=labels)
        self.cb_stop_sel.current(self.selected_stop_idx)
        st = stops[self.selected_stop_idx]
        self.var_stop_pos.set(float(st["position"]))
        self.var_stop_hex.set(str(st["color"]))
        self.var_stop_op.set(float(st["opacity"]))
        try:
            self.btn_stop_pick.configure(bg=str(st["color"]))
        except tk.TclError:
            pass
        self._draw_gradient_bar()

    def _draw_gradient_bar(self) -> None:
        if not hasattr(self, "grad_canvas") or self.grad_canvas is None:
            return
        w = max(260, self.grad_canvas.winfo_width())
        h = 28
        stops = self.active_layer.get("gradient_stops", [])
        u = np.linspace(0.0, 1.0, w, dtype=np.float32)
        rgb, alpha = sample_gradient(stops, u, interp=self.active_layer.get("gradient_interp", "smooth"))
        # Composite over subtle checkerboard to show stop opacity
        chk = (((np.arange(h)[:, None] // 7) + (np.arange(w)[None, :] // 7)) % 2) * 0.12 + 0.14
        bg = np.repeat(chk[:, :, None], 3, axis=2)
        a2d = alpha[None, :, None]
        comp = (rgb[None, :, :] * a2d + bg * (1.0 - a2d)) * 255.0
        self._grad_photo = _rgb_to_photoimage(comp.astype(np.uint8))
        self.grad_canvas.delete("all")
        self.grad_canvas.create_image(0, 0, anchor="nw", image=self._grad_photo)

        # Draw stop handles
        for i, st in enumerate(stops):
            sx = int(float(st["position"]) * (w - 8)) + 4
            outline = "#FFFFFF" if i == self.selected_stop_idx else "#222222"
            width_b = 2 if i == self.selected_stop_idx else 1
            self.grad_canvas.create_oval(
                sx - 6, 6, sx + 6, 22, fill=st["color"], outline=outline, width=width_b
            )

    def _update_preview_canvas(self) -> None:
        if not self._is_open or not hasattr(self, "prev_canvas"):
            return
        arr = self.step_preview_frame(dt=1 / 28.0, w=340, h=230)
        self._preview_photo = _rgb_to_photoimage(arr)
        self.prev_canvas.delete("all")
        self.prev_canvas.create_image(0, 0, anchor="nw", image=self._preview_photo)

        # Update dock layer summary & diagnostics
        layers = self.working_preset.get("layers", [])
        lines = []
        for i, l in enumerate(layers):
            mark = "▶" if i == self.selected_layer_idx else " "
            en = "ON " if l.get("enabled", True) else "OFF"
            lines.append(f"{mark} L{i+1} [{en}] {l.get('family','ribbon'):9s} {l.get('blend_mode','add'):8s} {l.get('lifetime_s',1.8):.1f}s")
        self.dock_layer_info.configure(text="\n".join(lines))

        prof = self.preview_engine.profiler
        mod = self.preview_engine.last_modulation
        self.lbl_perf_badge.configure(
            text=f"Render: {prof.avg_render_ms:.2f} ms | Samples: {prof.active_samples} | Particles: {prof.active_particles} | Tier: {prof.effective_tier}"
        )
        if hasattr(self, "lbl_diag"):
            self.lbl_diag.configure(
                text=(
                    f"State: {mod.state:<10s}  Maneuver: {mod.maneuver or 'none':<10s}  Path: {self.preview_path}\n"
                    f"Intensity Mult: {mod.intensity_mult:.2f}x   Length Mult: {mod.length_mult:.2f}x   Glow Mult: {mod.glow_mult:.2f}x\n"
                    f"Active Samples: {prof.active_samples:<6d}  Active Particles: {prof.active_particles:<6d}  Avg Render: {prof.avg_render_ms:.2f} ms"
                )
            )

    def _refresh_status_bar(self) -> None:
        if not hasattr(self, "lbl_status") or self.lbl_status is None:
            return
        if self.unsaved_changes:
            self.lbl_status.configure(text="● Unsaved modifications (Live preview active)", fg=C_WARN)
        else:
            self.lbl_status.configure(
                text=f"✓ Active Preset: {self.working_preset.get('name', 'Custom')}", fg=C_OK
            )

    # ---- UI Callbacks ------------------------------------------------------
    def _on_toggle_enabled(self) -> None:
        if self._suppress_callbacks:
            return
        self.working_cfg["enabled"] = bool(self.var_enabled.get())
        self._mark_modified()

    def _on_toggle_live_apply(self) -> None:
        self.live_desktop_apply = bool(self.var_live_apply.get())
        if self.live_desktop_apply:
            self.on_apply(copy.deepcopy(self.working_cfg), copy.deepcopy(self.working_preset))

    def _on_clear_clicked(self) -> None:
        self.preview_engine.clear()
        self.on_clear_trails()

    def _on_basic_family_changed(self, _event=None) -> None:
        if self._suppress_callbacks:
            return
        self.set_layer_param("family", self.var_basic_family.get())
        self._sync_all_widgets()

    def _pick_basic_color(self, which: int) -> None:
        cur = self.active_layer.get("base_color" if which == 0 else "secondary_color", "#8A3FFC")
        _, hex_col = colorchooser.askcolor(color=cur, parent=self.win)
        if hex_col:
            self._record_undo()
            hex_col = hex_col.upper()
            stops = self.active_layer.get("gradient_stops", [])
            if which == 0:
                self.active_layer["base_color"] = hex_col
                if stops:
                    stops[0]["color"] = hex_col
            else:
                self.active_layer["secondary_color"] = hex_col
                if len(stops) >= 2:
                    stops[-1]["color"] = hex_col
            self._mark_modified()
            self._sync_all_widgets()

    def _on_basic_slider(self, key: str, lbl: ttk.Label) -> None:
        if self._suppress_callbacks:
            return
        val = float(self._basic_vars[key].get())
        lbl.configure(text=f"{val:.2f}")
        if key in ("global_intensity", "global_opacity", "speed_reactivity"):
            self.working_cfg[key] = val
        elif key == "glow_intensity":
            self.active_layer.setdefault("glow", {})["intensity"] = val
        elif key == "width_px":
            self.active_layer["width_px"] = val
            self.active_layer["head_width_px"] = val * 1.15
        else:
            self.active_layer[key] = val
        self._mark_modified()

    def _on_basic_quality_changed(self, _event=None) -> None:
        if self._suppress_callbacks:
            return
        self.working_cfg.setdefault("quality", {})["preset"] = self.var_basic_quality.get()
        self._mark_modified()

    def _on_basic_toggles_changed(self) -> None:
        if self._suppress_callbacks:
            return
        self.working_preset.setdefault("behavior", {})["enabled"] = bool(self.var_react_toggle.get())
        q = self.working_cfg.setdefault("quality", {})
        q["reduced_motion"] = bool(self.var_red_motion.get())
        q["reduced_flashing"] = bool(self.var_red_flash.get())
        self._mark_modified()

    def _on_select_layer(self, idx: int) -> None:
        layers = self.working_preset.get("layers", [])
        if 0 <= idx < len(layers):
            if self.selected_layer_idx == idx:
                # Clicking already-selected layer button toggles its enabled state
                layers[idx]["enabled"] = not bool(layers[idx].get("enabled", True))
                self._mark_modified()
            else:
                self.selected_layer_idx = idx
            self._sync_all_widgets()

    def _ui_add_layer(self) -> None:
        try:
            self.add_layer("particles")
        except ValidationError as e:
            messagebox.showwarning("Layer Limit", str(e), parent=self.win)

    def _ui_dup_layer(self) -> None:
        try:
            self.duplicate_layer()
        except ValidationError as e:
            messagebox.showwarning("Layer Limit", str(e), parent=self.win)

    def _ui_rename_layer(self) -> None:
        cur = self.active_layer.get("name", "Layer")
        name = simpledialog.askstring("Rename Layer", "Layer name:", initialvalue=cur, parent=self.win)
        if name:
            self.rename_layer(name)

    def _on_apply_preset_palette(self, _event=None) -> None:
        pal_name = self.var_palette_pick.get()
        if pal_name in PRESET_PALETTES:
            self._record_undo()
            self.active_layer["gradient_stops"] = copy.deepcopy(PRESET_PALETTES[pal_name])
            self.active_layer["base_color"] = self.active_layer["gradient_stops"][0]["color"]
            self.active_layer["secondary_color"] = self.active_layer["gradient_stops"][-1]["color"]
            self._mark_modified()
            self._sync_all_widgets()

    def _on_stop_selected(self, _event=None) -> None:
        self.selected_stop_idx = max(0, self.cb_stop_sel.current())
        self._sync_gradient_widgets()

    def _on_stop_slider_changed(self, _val=None) -> None:
        if self._suppress_callbacks:
            return
        stops = self.active_layer.get("gradient_stops", [])
        if 0 <= self.selected_stop_idx < len(stops):
            st = stops[self.selected_stop_idx]
            st["position"] = float(np.clip(self.var_stop_pos.get(), 0.0, 1.0))
            st["opacity"] = float(np.clip(self.var_stop_op.get(), 0.0, 1.0))
            self._draw_gradient_bar()
            self._mark_modified()

    def _on_stop_hex_entered(self, _event=None) -> None:
        self.update_gradient_stop(self.selected_stop_idx, color=self.var_stop_hex.get())

    def _on_pick_stop_color(self) -> None:
        stops = self.active_layer.get("gradient_stops", [])
        if not (0 <= self.selected_stop_idx < len(stops)):
            return
        cur = stops[self.selected_stop_idx]["color"]
        _, hex_col = colorchooser.askcolor(color=cur, parent=self.win)
        if hex_col:
            self.update_gradient_stop(self.selected_stop_idx, color=hex_col)

    def _on_grad_canvas_click(self, event) -> None:
        w = max(260, self.grad_canvas.winfo_width())
        stops = self.active_layer.get("gradient_stops", [])
        if not stops:
            return
        u = float(np.clip((event.x - 4) / max(1, w - 8), 0.0, 1.0))
        best_i = min(range(len(stops)), key=lambda i: abs(float(stops[i]["position"]) - u))
        self.selected_stop_idx = best_i
        self._sync_gradient_widgets()

    def _on_grad_canvas_drag(self, event) -> None:
        w = max(260, self.grad_canvas.winfo_width())
        stops = self.active_layer.get("gradient_stops", [])
        if not (0 <= self.selected_stop_idx < len(stops)):
            return
        u = float(np.clip((event.x - 4) / max(1, w - 8), 0.0, 1.0))
        stops[self.selected_stop_idx]["position"] = u
        self.var_stop_pos.set(u)
        self._draw_gradient_bar()
        self._mark_modified()

    def _on_adv_param_changed(self, key: str) -> None:
        if self._suppress_callbacks:
            return
        meta = PARAM_SCHEMA[key]
        raw_val = self._param_vars[key].get()
        if meta["type"] == "int":
            val = int(round(float(raw_val)))
        elif meta["type"] == "float":
            val = float(raw_val)
        elif meta["type"] == "bool":
            val = bool(raw_val)
        else:
            val = str(raw_val)

        if key in self._param_val_labels:
            if meta["type"] == "float":
                self._param_val_labels[key].configure(text=f"{val:.2f} {meta.get('unit', '')}")
            elif meta["type"] == "int":
                self._param_val_labels[key].configure(text=f"{val} {meta.get('unit', '')}")

        self.set_layer_param(key, val)
        if key == "family":
            self._sync_all_widgets()

    def _on_pick_schema_color(self, key: str) -> None:
        cur = str(self._param_vars[key].get())
        _, hex_col = colorchooser.askcolor(color=cur, parent=self.win)
        if hex_col:
            hex_col = hex_col.upper()
            self._param_vars[key].set(hex_col)
            self.set_layer_param(key, hex_col)
            self._sync_all_widgets()

    def _on_preview_settings_changed(self, _event=None) -> None:
        self.preview_path = self.var_prev_path.get()
        self.preview_bg = self.var_prev_bg.get()
        self.preview_speed = float(self.var_prev_spd.get())
        self.cb_dock_path.set(self.preview_path)
        self.preview_engine.notify_discontinuity()

    def _on_dock_path_changed(self, _event=None) -> None:
        self.preview_path = self.cb_dock_path.get()
        self.var_prev_path.set(self.preview_path)
        self.preview_engine.notify_discontinuity()

    def _on_toggle_pause_preview(self) -> None:
        self.preview_paused = not self.preview_paused
        self.btn_pause_prev.configure(text="Resume" if self.preview_paused else "Pause")

    def _on_scrub_preview(self, _val=None) -> None:
        target_t = float(self.var_prev_scrub.get())
        self.preview_paused = True
        self.btn_pause_prev.configure(text="Resume")
        self.preview_engine.clear()
        # Replay deterministically up to target_t
        steps = max(4, min(90, int(target_t * 30)))
        t0 = max(0.0, target_t - steps / 30.0)
        for i in range(steps + 1):
            t_i = t0 + i / 30.0
            snap = generate_demo_snapshot(self.preview_path, t_i, w=340, h=230, body_radius=17.0)
            self.preview_engine.step(1 / 30.0, snap)
        self.preview_t = target_t
        self._update_preview_canvas()

    # ---- Management & Randomizer UI Actions --------------------------------
    def _prompt_save_as(self) -> None:
        default_name = f"{self.working_preset.get('name', 'Custom')} Custom"
        name = simpledialog.askstring("Save Custom Preset", "Enter preset name:", initialvalue=default_name, parent=self.win)
        if not name or not name.strip():
            return
        data = copy.deepcopy(self.working_preset)
        data["name"] = name.strip()
        data["id"] = self.store.unique_id(name.strip())
        saved = self.store.save_custom(data, allow_overwrite=True)
        self.working_preset = saved
        self.working_cfg["active_preset"] = saved["id"]
        self.working_cfg["custom_working"] = None
        self.apply_changes()
        self._sync_all_widgets()

    def _ui_duplicate_preset(self) -> None:
        pid = self.working_preset.get("id", "nebula_silk")
        if pid not in BUNDLED_PRESETS and self.store.get(pid) is None:
            self.store.save_custom(self.working_preset)
        dup = self.store.duplicate(self.working_preset["id"])
        self.select_preset(dup["id"])

    def _ui_rename_preset(self) -> None:
        pid = self.working_preset.get("id", "")
        if self.store.is_builtin(pid):
            messagebox.showinfo("Bundled Preset", "Bundled presets cannot be renamed directly. Use 'Save As New Preset'.", parent=self.win)
            return
        name = simpledialog.askstring("Rename Preset", "New name:", initialvalue=self.working_preset.get("name", ""), parent=self.win)
        if name and name.strip():
            renamed = self.store.rename_custom(pid, name.strip())
            self.working_preset = renamed
            self._sync_all_widgets()

    def _ui_delete_preset(self) -> None:
        pid = self.working_preset.get("id", "")
        if self.store.is_builtin(pid):
            messagebox.showwarning("Protected Preset", "Bundled presets are immutable and cannot be deleted.", parent=self.win)
            return
        if messagebox.askyesno("Delete Custom Preset", f"Delete '{self.working_preset.get('name')}'?", parent=self.win):
            self.store.delete_custom(pid)
            self.select_preset("nebula_silk")

    def _ui_import_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Trail Preset",
            filetypes=[("Zwoop Trail Preset", "*.json"), ("All Files", "*.*")],
            parent=self.win,
        )
        if not path:
            return
        try:
            imp = self.store.import_file(path, persist=True)
            self.select_preset(imp["id"])
            messagebox.showinfo("Import Successful", f"Imported preset '{imp['name']}'.", parent=self.win)
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not import preset:\n{e}", parent=self.win)

    def _ui_export_preset(self) -> None:
        slug = self.working_preset.get("id", "custom_trail")
        path = filedialog.asksaveasfilename(
            title="Export Trail Preset",
            initialfile=f"{slug}.json",
            defaultextension=".json",
            filetypes=[("Zwoop Trail Preset", "*.json")],
            parent=self.win,
        )
        if not path:
            return
        try:
            self.store.export_file(self.working_preset, path)
            messagebox.showinfo("Export Successful", f"Saved preset to:\n{path}", parent=self.win)
        except Exception as e:
            messagebox.showerror("Export Error", f"Could not export preset:\n{e}", parent=self.win)

    def _ui_run_randomizer(self, use_typed_seed: bool = False) -> None:
        mode = self.var_rand_mode.get()
        seed_in = self.var_rand_seed.get().strip() if use_typed_seed else None
        locks = {k: bool(v.get()) for k, v in self.rand_lock_vars.items()}
        self._record_undo()
        base_id = self.working_preset.get("id", "nebula_silk")
        new_p, num_seed = self.randomizer.randomize(
            self.working_preset, mode=mode, seed=seed_in or None, locks=locks
        )
        self.working_preset = new_p
        self.var_rand_seed.set(str(num_seed))
        self.var_recipe_str.set(self.randomizer.encode_recipe(mode, num_seed, base_id, locks))
        self._mark_modified()
        self._sync_all_widgets()

    def _ui_undo_randomizer(self) -> None:
        prev = self.randomizer.pop_undo()
        if prev is not None:
            self.working_preset = prev
            self._mark_modified()
            self._sync_all_widgets()
        else:
            self.undo()

    def _ui_apply_recipe(self) -> None:
        rec = self.var_recipe_str.get().strip()
        if not rec:
            return
        try:
            info = self.randomizer.decode_recipe(rec)
            base = self.store.get(info["base_id"]) or copy.deepcopy(self.working_preset)
            self._record_undo()
            new_p, num_seed = self.randomizer.randomize(
                base, mode=info["mode"], seed=info["seed"], locks=info["locks"]
            )
            self.working_preset = new_p
            self.var_rand_mode.set(info["mode"])
            self.var_rand_seed.set(str(num_seed))
            for k, v in info["locks"].items():
                if k in self.rand_lock_vars:
                    self.rand_lock_vars[k].set(v)
            self._mark_modified()
            self._sync_all_widgets()
        except Exception as e:
            messagebox.showerror("Invalid Recipe", str(e), parent=self.win)
