"""Vectorized geometry generators and layer shaders for Zwoop Trail Studio.

Supports all 10 geometry families:
  - ribbon      Smooth tapered spline ribbon with wave/width modulation
  - beam        Crisp high-luminance laser core with wide halo & pulsation
  - particles   Multi-shape particle renderer (circle, star, diamond, streak, ring, puff, shard)
  - smoke       Expanding, curl-diffusing translucent volumetric wisps
  - sparks      High-speed directional velocity streaks with hot cores
  - segmented   Arc-length spaced discrete geometric marks with alternation
  - spiral      3D-shaded multi-strand helical ribbons wrapping the path
  - echo        Deformation-preserving afterimage silhouettes of Zwoop
  - branching   Procedural fractal / electric branching arcs
  - legacy      Original speed-gated metaball-tail swoosh compatibility mode
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from ..render.theme import THEMES
from .history import TrailHistory, TrailSample, resample_stroke
from .particles import ParticleSystem
from .reactive import ReactiveModulation
from .schema import hex_to_rgb, sample_gradient, transform_rgb


def apply_fade_curve(u_age: np.ndarray, fade_in_u: float, curve: str) -> np.ndarray:
    """Compute [0, 1] age opacity envelope where u_age=0 is birth and u_age=1 is death."""
    u = np.clip(u_age, 0.0, 1.0)
    # Fade-in near head (u close to 0)
    if fade_in_u > 1e-3:
        fin = np.clip(u / max(fade_in_u, 1e-4), 0.0, 1.0)
    else:
        fin = 1.0

    rem = np.clip(1.0 - u, 0.0, 1.0)
    if curve == "linear":
        fout = rem
    elif curve == "expo":
        fout = rem * rem * rem
    elif curve == "cosine":
        fout = 0.5 * (1.0 - np.cos(rem * math.pi))
    else:  # smooth
        fout = rem * rem * (3.0 - 2.0 * rem)
    return (fin * fout).astype(np.float32)


def _eval_layer_colors(
    layer: dict[str, Any],
    u_param: np.ndarray,
    speed_norm: np.ndarray | float,
    now_t: float,
    theme_name: str = "cosmos",
    hue_jitter: np.ndarray | float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate RGB (..., 3) and stop alpha (...,) for array `u_param` in [0, 1]."""
    cycle = float(layer.get("color_cycle_rate", 0.0))
    hue_deg = float(layer.get("hue_offset", 0.0)) + cycle * now_t * 360.0
    sat = float(layer.get("saturation", 1.0))
    bri = float(layer.get("brightness", 1.0))

    if layer.get("theme_sync", False):
        th = THEMES.get(theme_name, THEMES["cosmos"])
        stops = [
            {"position": 0.0, "color": _tuple_to_hex(th["core"]), "opacity": 1.0},
            {"position": 0.5, "color": _tuple_to_hex(th["mid"]), "opacity": 0.85},
            {"position": 1.0, "color": _tuple_to_hex(th["deep"]), "opacity": 0.0},
        ]
    elif layer.get("gradient_enabled", True) and layer.get("gradient_stops"):
        stops = layer["gradient_stops"]
    else:
        stops = [
            {"position": 0.0, "color": layer.get("base_color", "#8A3FFC"), "opacity": 1.0},
            {"position": 1.0, "color": layer.get("secondary_color", "#33E1FF"), "opacity": 0.1},
        ]

    interp = layer.get("gradient_interp", "smooth")
    rgb, stop_a = sample_gradient(stops, u_param, interp=interp, hue_deg=hue_deg, sat_mult=sat, val_mult=bri)

    # Apply per-element hue jitter if non-zero
    if isinstance(hue_jitter, np.ndarray) and np.any(np.abs(hue_jitter) > 0.5):
        # Fast approximate hue rotation in RGB space around luma axis
        ang = np.radians(hue_jitter).astype(np.float32)
        cos_a = np.cos(ang)[..., None]
        sin_a = np.sin(ang)[..., None]
        luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])[..., None]
        diff = rgb - luma
        perp = np.stack([
            diff[..., 1] - diff[..., 2],
            diff[..., 2] - diff[..., 0],
            diff[..., 0] - diff[..., 1],
        ], axis=-1) * 0.57735
        rgb = np.clip(luma + diff * cos_a + perp * sin_a, 0.0, 1.0)

    # Velocity color modulation toward bright spark tint
    v_mod = float(layer.get("velocity_color_mod", 0.25))
    if v_mod > 0.01:
        th = THEMES.get(theme_name, THEMES["cosmos"])
        spark = np.array(th["spark"], dtype=np.float32)
        amt = np.clip(np.asarray(speed_norm, dtype=np.float32) * v_mod * 0.65, 0.0, 0.75)
        rgb = rgb + (spark - rgb) * amt[..., None]

    return np.clip(rgb, 0.0, 1.0), stop_a


def _tuple_to_hex(rgb: tuple[float, float, float]) -> str:
    r = int(np.clip(round(rgb[0] * 255), 0, 255))
    g = int(np.clip(round(rgb[1] * 255), 0, 255))
    b = int(np.clip(round(rgb[2] * 255), 0, 255))
    return f"#{r:02X}{g:02X}{b:02X}"


def _box_blur_2d(arr: np.ndarray, passes: int = 1) -> np.ndarray:
    """Fast in-place separable 3x3 tent filter on 2D or 3D float32 array."""
    for _ in range(max(0, int(passes))):
        if arr.shape[0] >= 3 and arr.shape[1] >= 3:
            arr[1:-1, :] = 0.25 * arr[:-2, :] + 0.5 * arr[1:-1, :] + 0.25 * arr[2:, :]
            arr[:, 1:-1] = 0.25 * arr[:, :-2] + 0.5 * arr[:, 1:-1] + 0.25 * arr[:, 2:]
    return arr


def composite_layer(
    dst_rgb_pre: np.ndarray,
    dst_a: np.ndarray,
    src_rgb: np.ndarray,
    src_a: np.ndarray,
    blend_mode: str = "add",
    overlap_intensity: float = 0.85,
) -> None:
    """Composite straight `src_rgb` + `src_a` onto premultiplied `(dst_rgb_pre, dst_a)`.

    Guarantees valid premultiplied invariants: 0 <= dst_rgb_pre <= dst_a <= 1.
    """
    sa = np.clip(src_a, 0.0, 1.0)[..., None]
    s_pre = np.clip(src_rgb, 0.0, 1.0) * sa

    if blend_mode == "alpha":
        dst_rgb_pre[:] = s_pre + dst_rgb_pre * (1.0 - sa)
        dst_a[:] = src_a + dst_a * (1.0 - src_a)
    elif blend_mode == "screen":
        dst_rgb_pre[:] = dst_rgb_pre + s_pre - dst_rgb_pre * s_pre
        dst_a[:] = src_a + dst_a * (1.0 - src_a)
    elif blend_mode == "contrast":
        # Dark-core / optical contrast mode (Event Horizon, Ink in Water):
        # High alpha darkens underlying pixels where src_rgb is dark, while bright rims add.
        dst_rgb_pre[:] = s_pre * overlap_intensity + dst_rgb_pre * (1.0 - sa * 0.92)
        dst_a[:] = np.maximum(dst_a, src_a + dst_a * (1.0 - src_a))
    else:  # "add" (premultiplied-alpha-safe self-luminous glow)
        boost = float(np.clip(overlap_intensity, 0.2, 2.0))
        dst_rgb_pre[:] = np.minimum(1.0, dst_rgb_pre + s_pre * boost)
        dst_a[:] = src_a + dst_a * (1.0 - src_a)

    # Enforce strict premultiplied invariant so DWM never sees RGB > A
    max_c = np.max(dst_rgb_pre, axis=-1)
    dst_a[:] = np.clip(np.maximum(dst_a, max_c), 0.0, 1.0)
    np.minimum(dst_rgb_pre, dst_a[..., None], out=dst_rgb_pre)


class LayerRenderer:
    """Renders individual trail layers onto the shading grid."""

    def render_layer(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        dst_rgb_pre: np.ndarray,
        dst_a: np.ndarray,
        layer: dict[str, Any],
        history: TrailHistory,
        psys: ParticleSystem | None,
        mod: ReactiveModulation,
        snap: dict[str, Any],
        now_t: float,
        quality_cfg: dict[str, Any],
        global_intensity: float = 0.85,
        global_opacity: float = 0.90,
        theme_name: str = "cosmos",
    ) -> None:
        if not layer.get("enabled", True):
            return
        fam = layer.get("family", "ribbon")
        h, w = gx.shape
        rs = float(gx[0, 1] - gx[0, 0]) if w > 1 else 3.0
        ox = float(gx[0, 0] - rs * 0.5)
        oy = float(gy[0, 0] - rs * 0.5)

        layer_rgb = np.zeros((h, w, 3), dtype=np.float32)
        layer_a = np.zeros((h, w), dtype=np.float32)

        if fam in ("particles", "smoke", "sparks"):
            if psys is not None and psys.count > 0:
                self._render_particles_family(
                    gx, gy, ox, oy, rs, layer_rgb, layer_a,
                    layer, psys, mod, now_t, quality_cfg, theme_name,
                )
        elif fam == "echo":
            self._render_echo_family(
                gx, gy, ox, oy, rs, layer_rgb, layer_a,
                layer, history, mod, now_t, quality_cfg, theme_name,
            )
        elif fam == "segmented":
            self._render_segmented_family(
                gx, gy, ox, oy, rs, layer_rgb, layer_a,
                layer, history, mod, now_t, quality_cfg, theme_name,
            )
        else:
            # Path-based families: ribbon, beam, spiral, branching, legacy
            self._render_path_family(
                gx, gy, ox, oy, rs, layer_rgb, layer_a,
                layer, history, mod, snap, now_t, quality_cfg, theme_name,
            )

        if not np.any(layer_a > 1e-3):
            return

        # Apply layer glow halo if enabled
        gcfg = layer.get("glow", {})
        if gcfg.get("enabled", True) and float(gcfg.get("intensity", 0.65)) > 0.02:
            self._apply_glow(
                layer_rgb, layer_a, layer, mod, now_t, rs, quality_cfg
            )

        # Master opacity & intensity scaling
        master_op = (
            float(layer.get("opacity", 0.78))
            * float(global_opacity)
            * float(np.clip(global_intensity * mod.intensity_mult, 0.0, 2.2))
        )
        layer_a *= min(1.0, master_op)

        composite_layer(
            dst_rgb_pre,
            dst_a,
            layer_rgb,
            layer_a,
            blend_mode=layer.get("blend_mode", "add"),
            overlap_intensity=float(layer.get("overlap_intensity", 0.85)),
        )

    def _apply_glow(
        self,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        layer: dict[str, Any],
        mod: ReactiveModulation,
        now_t: float,
        rs: float,
        quality_cfg: dict[str, Any],
    ) -> None:
        gcfg = layer.get("glow", {})
        g_int = float(gcfg.get("intensity", 0.65)) * mod.glow_mult
        g_rad = float(gcfg.get("radius_px", 16.0))
        core_int = float(gcfg.get("core_intensity", 0.85))
        pulse_spd = float(gcfg.get("pulse_speed", 0.0))
        pulse_dep = float(gcfg.get("pulse_depth", 0.0))

        if quality_cfg.get("reduced_flashing", False):
            pulse_dep *= 0.15

        if pulse_spd > 0.05 and pulse_dep > 0.01:
            g_int *= 1.0 + pulse_dep * math.sin(now_t * pulse_spd * 2.0 * math.pi)

        halo_col = np.array(hex_to_rgb(gcfg.get("halo_color", "#7B2CBF")), dtype=np.float32)
        passes = min(
            int(gcfg.get("bloom_quality", 2)),
            max(1, int(round(g_rad / max(rs * 3.0, 4.0)))),
        )
        halo_a = layer_a.copy()
        _box_blur_2d(halo_a, passes=passes)
        falloff = float(gcfg.get("falloff", 1.5))
        halo_a = np.clip(halo_a * g_int * (1.25 / max(0.5, falloff)), 0.0, 0.85)

        # Core hot highlight where layer_a is strong
        if core_int > 0.05:
            core_mask = np.clip((layer_a - 0.45) / 0.55, 0.0, 1.0) ** 1.5
            white_tint = np.array([0.96, 0.94, 1.0], dtype=np.float32)
            layer_rgb[:] = layer_rgb + (white_tint - layer_rgb) * (
                core_mask[..., None] * min(0.85, core_int * 0.5)
            )

        # Blend halo underneath core
        comb_a = np.maximum(layer_a, halo_a)
        halo_only = np.clip(comb_a - layer_a, 0.0, 1.0)
        denom = np.maximum(comb_a, 1e-5)[..., None]
        layer_rgb[:] = (
            layer_rgb * layer_a[..., None] + halo_col[None, None, :] * halo_only[..., None]
        ) / denom
        layer_a[:] = comb_a

    # ----------------------------------------------------------------- paths
    def _render_path_family(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        layer: dict[str, Any],
        history: TrailHistory,
        mod: ReactiveModulation,
        snap: dict[str, Any],
        now_t: float,
        quality_cfg: dict[str, Any],
        theme_name: str,
    ) -> None:
        fam = layer.get("family", "ribbon")
        max_life = float(quality_cfg.get("max_lifetime_s", 4.5))
        life_s = min(max_life, float(layer.get("lifetime_s", 1.8)) * mod.length_mult)
        if fam == "legacy":
            # Legacy compatibility mode: short speed-gated swoosh
            if float(snap.get("speed", 0.0)) < 200.0 and len(history.samples) < 4:
                return
            life_s = min(life_s, 0.45)

        delay_s = float(layer.get("spawn_delay_s", 0.0))
        len_cap = float(layer.get("length_cap_px", 900.0)) * mod.length_mult
        strokes = history.get_strokes(now_t, life_s, spawn_delay_s=delay_s, length_cap_px=len_cap)
        if not strokes:
            return

        seg_cap = int(quality_cfg.get("segment_cap", 120))
        dens = float(layer.get("segment_density", 1.0))
        max_pts = int(np.clip(int(seg_cap * dens * 0.6), 12, seg_cap))
        mcfg = layer.get("motion", {})
        reduced_motion = bool(quality_cfg.get("reduced_motion", False))

        smoothing = float(layer.get("smoothing", 0.55))
        tension = float(layer.get("curve_tension", 0.5))
        drift_x = float(mcfg.get("drift_x", 0.0))
        drift_y = float(mcfg.get("drift_y", -8.0))
        curl = float(mcfg.get("curl_noise", 4.0)) * (0.25 if reduced_motion else 1.0)

        scale = float(layer.get("size_scale", 1.0)) * mod.width_mult
        head_w = float(layer.get("head_width_px", layer.get("width_px", 18.0))) * scale
        tail_w = float(layer.get("tail_width_px", 2.0)) * scale
        taper = float(layer.get("taper", 0.85))
        sharp = float(layer.get("sharpness", 0.45))
        if fam == "beam":
            sharp = max(sharp, 0.78)
        elif fam == "legacy":
            sharp = 0.35

        soft_edge = float(layer.get("soft_edge", 0.55))
        falloff = float(layer.get("edge_falloff", 1.4))
        offset_px = float(layer.get("offset_px", 0.0))
        w_noise = float(layer.get("width_noise", 0.08))

        wave_amp = float(mcfg.get("wave_amplitude", 0.0)) * mod.spiral_mult
        wave_freq = float(mcfg.get("wave_frequency", 2.5))
        wave_phase = float(mcfg.get("wave_phase", 0.0))
        spiral_rad = float(mcfg.get("spiral_radius", 18.0)) * mod.spiral_mult
        spiral_spd = float(mcfg.get("spiral_speed", 4.0))
        jitter = float(mcfg.get("position_jitter", 0.0))
        if reduced_motion:
            wave_amp *= 0.25
            spiral_spd *= 0.25
            jitter *= 0.15

        n_strands = int(layer.get("strand_count", 2)) if fam == "spiral" else int(layer.get("strand_count", 1))
        n_strands = max(1, min(5, n_strands))

        fade_in_u = float(layer.get("fade_in_s", 0.04)) / max(life_s, 0.1)
        fade_curve = layer.get("fade_curve", "smooth")
        grad_dir = layer.get("gradient_direction", "along")

        for stroke in strokes:
            rs_data = resample_stroke(
                stroke,
                now_t=now_t,
                lifetime_s=life_s,
                max_points=max_pts,
                smoothing=smoothing,
                tension=tension,
                drift_x=drift_x,
                drift_y=drift_y,
                curl_noise=curl,
            )
            if rs_data is None:
                continue

            base_pos = rs_data["pos"]
            norm = rs_data["norm"]
            u_age = rs_data["u_age"]
            u_arc = rs_data["u_arc"]
            spd = rs_data["speed"]
            curv = rs_data["curvature"]
            m_pts = len(base_pos)
            if m_pts < 2:
                continue

            # Width profile from head (u_arc=0) to tail (u_arc=1)
            taper_u = np.power(np.clip(1.0 - u_arc, 0.0, 1.0), max(0.1, taper))
            radii = tail_w + (head_w - tail_w) * taper_u
            # Curvature response widens slightly on dramatic turns
            curv_resp = float(mcfg.get("curvature_response", 0.4))
            radii *= 1.0 + curv_resp * np.clip(curv * 12.0, 0.0, 0.6)
            if w_noise > 0.01:
                radii *= 1.0 + w_noise * 0.35 * np.sin(u_arc * 18.0 + now_t * 3.0)
            radii = np.maximum(1.5, radii).astype(np.float32)

            age_env = apply_fade_curve(u_age, fade_in_u, fade_curve)

            for s_idx in range(n_strands):
                strand_phase = wave_phase + (2.0 * math.pi * s_idx / max(1, n_strands))
                pts = base_pos + norm * offset_px

                if fam == "spiral":
                    r_hel = spiral_rad * np.clip(u_arc * 2.5, 0.15, 1.0) * (1.0 - 0.35 * u_age)
                    theta = u_arc * wave_freq * 2.0 * math.pi - now_t * spiral_spd + strand_phase
                    disp = r_hel * np.sin(theta)
                    depth_shade = 0.78 + 0.22 * np.cos(theta)  # 3D front/back illusion
                    pts = pts + norm * disp[:, None]
                else:
                    depth_shade = np.ones(m_pts, dtype=np.float32)
                    if n_strands > 1:
                        # Parallel / gently waving multi-threads (e.g. Aurora Threads)
                        spread = (s_idx - (n_strands - 1) * 0.5) * max(6.0, spiral_rad * 0.65)
                        pts = pts + norm * (spread * np.clip(u_arc * 2.2, 0.2, 1.0))[:, None]
                    if wave_amp > 0.2:
                        theta = u_arc * wave_freq * 2.0 * math.pi - now_t * 3.2 + strand_phase
                        disp = wave_amp * np.sin(theta) * np.clip(u_arc * 2.0, 0.0, 1.0)
                        pts = pts + norm * disp[:, None]

                if jitter > 0.2 or fam == "branching":
                    jit_amp = max(jitter, 5.5 if fam == "branching" else 0.0)
                    # Deterministic pseudo-random jitter keyed by point index & time bucket
                    t_bucket = int(now_t * (8.0 if reduced_motion else 18.0))
                    idx_arr = np.arange(m_pts, dtype=np.float32)
                    j_val = np.sin(idx_arr * 12.9898 + t_bucket * 78.233 + s_idx * 3.1) * jit_amp
                    j_val[-1] = 0.0  # keep head anchored to Zwoop
                    pts = pts + norm * j_val[:, None]

                grad_u = u_age if grad_dir != "velocity" else np.clip(spd / 700.0, 0.0, 1.0)
                strand_hue = (s_idx * 38.0) if n_strands > 1 else 0.0
                cols, stop_a = _eval_layer_colors(
                    layer,
                    grad_u,
                    spd / 600.0,
                    now_t,
                    theme_name=theme_name,
                    hue_jitter=np.full(m_pts, strand_hue, dtype=np.float32),
                )
                cols *= depth_shade[:, None]
                pt_alpha = np.clip(age_env * stop_a * depth_shade, 0.0, 1.0)

                s_radii = radii * (0.75 if n_strands > 1 else 1.0)
                self._rasterize_polyline(
                    gx, gy, ox, oy, rs, layer_rgb, layer_a,
                    pts, s_radii, cols, pt_alpha, sharp, soft_edge, falloff,
                )

                # Procedural side branches for 'branching' family (Storm Arc / Fractal Echo)
                if fam == "branching" and m_pts >= 5:
                    self._render_branches(
                        gx, gy, ox, oy, rs, layer_rgb, layer_a,
                        pts, norm, s_radii, cols, pt_alpha, now_t, reduced_motion,
                    )

    def _rasterize_polyline(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        pts: np.ndarray,
        radii: np.ndarray,
        cols: np.ndarray,
        alphas: np.ndarray,
        sharpness: float,
        soft_edge: float,
        falloff: float,
    ) -> None:
        """Rasterize a variable-radius, variable-color polyline using tight segment bboxes."""
        h, w = gx.shape
        n_seg = len(pts) - 1
        if n_seg <= 0:
            return

        # Coalesce very tiny sub-pixel segments when dense
        step = 1 if n_seg <= 90 else 2
        inv_rs = 1.0 / rs
        core_frac = float(np.clip(sharpness * (1.0 - 0.45 * soft_edge), 0.08, 0.88))
        p_exp = float(np.clip(falloff, 0.4, 3.5))

        for i in range(0, n_seg, step):
            j = min(n_seg, i + step)
            a_re = float(alphas[i])
            b_re = float(alphas[j])
            if a_re < 0.01 and b_re < 0.01:
                continue

            ax, ay = float(pts[i, 0]), float(pts[i, 1])
            bx, by = float(pts[j, 0]), float(pts[j, 1])
            ra = max(float(radii[i]), rs * 0.65)
            rb = max(float(radii[j]), rs * 0.65)
            rmax = max(ra, rb) + rs

            ix0 = max(0, int((min(ax, bx) - rmax - ox) * inv_rs))
            ix1 = min(w, int((max(ax, bx) + rmax - ox) * inv_rs) + 2)
            iy0 = max(0, int((min(ay, by) - rmax - oy) * inv_rs))
            iy1 = min(h, int((max(ay, by) + rmax - oy) * inv_rs) + 2)
            if ix1 <= ix0 or iy1 <= iy0:
                continue

            sgx = gx[iy0:iy1, ix0:ix1]
            sgy = gy[iy0:iy1, ix0:ix1]

            abx = bx - ax
            aby = by - ay
            ab2 = abx * abx + aby * aby
            if ab2 > 1e-4:
                t = np.clip(((sgx - ax) * abx + (sgy - ay) * aby) / ab2, 0.0, 1.0)
            else:
                t = np.zeros_like(sgx)

            cx = ax + t * abx
            cy = ay + t * aby
            dist = np.hypot(sgx - cx, sgy - cy)
            r_loc = ra + t * (rb - ra)

            mask = dist < r_loc
            if not np.any(mask):
                continue

            u_rad = np.clip(dist / np.maximum(r_loc, 1e-4), 0.0, 1.0)
            # Cross-sectional profile: flat 1.0 inside core_frac, smooth power falloff outside
            rim_u = np.clip((u_rad - core_frac) / max(1.0 - core_frac, 1e-4), 0.0, 1.0)
            prof = np.power(1.0 - rim_u, p_exp) * (1.0 - rim_u * rim_u * 0.25)

            seg_a = (a_re + t * (b_re - a_re)) * prof
            cur_a = layer_a[iy0:iy1, ix0:ix1]
            better = seg_a > cur_a
            if np.any(better):
                c0 = cols[i]
                c1 = cols[j]
                seg_rgb = c0[None, None, :] + t[..., None] * (c1 - c0)[None, None, :]
                # Brighten inner core slightly for crisp beams/ribbons
                if sharpness > 0.6:
                    core_boost = (1.0 - u_rad) ** 2 * (sharpness - 0.4) * 0.45
                    seg_rgb = np.minimum(1.0, seg_rgb + core_boost[..., None])

                sub_rgb = layer_rgb[iy0:iy1, ix0:ix1]
                # Smoothly blend colors where segments overlap, take max alpha so joints never seam
                w_new = np.clip(seg_a / np.maximum(cur_a + seg_a, 1e-5), 0.0, 1.0)[..., None]
                sub_rgb[:] = np.where(
                    (cur_a > 0.01)[..., None],
                    sub_rgb * (1.0 - w_new) + seg_rgb * w_new,
                    np.where(better[..., None], seg_rgb, sub_rgb),
                )
                cur_a[:] = np.maximum(cur_a, seg_a)

    def _render_branches(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        pts: np.ndarray,
        norm: np.ndarray,
        radii: np.ndarray,
        cols: np.ndarray,
        alphas: np.ndarray,
        now_t: float,
        reduced_motion: bool,
    ) -> None:
        """Render secondary fractal/electric fork branches off the main spine."""
        n = len(pts)
        stride = max(3, n // 7)
        t_seed = int(now_t * (3.0 if reduced_motion else 9.0))
        for idx in range(2, n - 2, stride):
            if alphas[idx] < 0.08:
                continue
            h_val = math.sin(idx * 37.7 + t_seed * 13.1)
            if abs(h_val) < 0.25:
                continue
            sign = 1.0 if h_val >= 0 else -1.0
            root = pts[idx]
            tang = pts[min(n - 1, idx + 1)] - pts[max(0, idx - 1)]
            tn = float(np.linalg.norm(tang)) or 1.0
            tang = tang / tn
            nrm = norm[idx] * sign

            b_len = float(radii[idx]) * (2.6 + 1.2 * abs(h_val))
            mid = root + (tang * 0.55 + nrm * 0.82) * (b_len * 0.55)
            tip = mid + (tang * 0.35 + nrm * 0.94) * (b_len * 0.55)
            b_pts = np.array([root, mid, tip], dtype=np.float32)
            b_rad = np.array([radii[idx] * 0.55, radii[idx] * 0.35, 1.2], dtype=np.float32)
            b_col = np.array([cols[idx], cols[idx], cols[idx]], dtype=np.float32)
            b_alp = np.array([alphas[idx] * 0.85, alphas[idx] * 0.55, 0.0], dtype=np.float32)
            self._rasterize_polyline(
                gx, gy, ox, oy, rs, layer_rgb, layer_a,
                b_pts, b_rad, b_col, b_alp, 0.75, 0.35, 1.4,
            )

    # ------------------------------------------------------------ segmented
    def _render_segmented_family(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        layer: dict[str, Any],
        history: TrailHistory,
        mod: ReactiveModulation,
        now_t: float,
        quality_cfg: dict[str, Any],
        theme_name: str,
    ) -> None:
        max_life = float(quality_cfg.get("max_lifetime_s", 4.5))
        life_s = min(max_life, float(layer.get("lifetime_s", 1.8)) * mod.length_mult)
        spacing = max(6.0, float(layer.get("segment_spacing_px", 24.0)))
        len_cap = float(layer.get("length_cap_px", 900.0))
        strokes = history.get_strokes(now_t, life_s, length_cap_px=len_cap)
        if not strokes:
            return

        scale = float(layer.get("size_scale", 1.0)) * mod.width_mult
        base_r = max(2.5, float(layer.get("width_px", 14.0)) * 0.65 * scale)
        taper = float(layer.get("taper", 0.75))
        shape = layer.get("particles", {}).get("shape", "diamond")
        fade_in_u = float(layer.get("fade_in_s", 0.04)) / max(life_s, 0.1)
        fade_curve = layer.get("fade_curve", "smooth")
        wave_amp = float(layer.get("motion", {}).get("wave_amplitude", 0.0))

        for stroke in strokes:
            n_max = int(np.clip(len_cap / spacing, 8, 90))
            rs_data = resample_stroke(stroke, now_t=now_t, lifetime_s=life_s, max_points=n_max)
            if rs_data is None or rs_data["total_len"] < 4.0:
                continue

            total_len = rs_data["total_len"]
            n_marks = max(1, min(70, int(total_len / spacing)))
            idx = np.linspace(0, len(rs_data["pos"]) - 1, n_marks).astype(int)
            pts = rs_data["pos"][idx].copy()
            nrm = rs_data["norm"][idx]
            u_age = rs_data["u_age"][idx]
            u_arc = rs_data["u_arc"][idx]
            spd = rs_data["speed"][idx]

            # Alternating lateral offset & rotation
            alt = np.where(np.arange(n_marks) % 2 == 0, 1.0, -1.0).astype(np.float32)
            if wave_amp > 0.5:
                pts += nrm * (alt * wave_amp * 0.45)[:, None]

            radii = base_r * np.power(np.clip(1.0 - u_arc, 0.15, 1.0), max(0.1, taper))
            alphas = apply_fade_curve(u_age, fade_in_u, fade_curve)
            hue_jit = alt * float(layer.get("hue_variance", 0.1)) * 90.0
            cols, stop_a = _eval_layer_colors(
                layer, u_age, spd / 600.0, now_t, theme_name=theme_name, hue_jitter=hue_jit
            )
            alphas = np.clip(alphas * stop_a, 0.0, 1.0)
            rots = (np.arange(n_marks, dtype=np.float32) * 35.0 + now_t * 60.0) % 360.0

            self._splat_marks(
                gx, gy, ox, oy, rs, layer_rgb, layer_a,
                pts, radii, cols, alphas, rots, shape=shape,
                vel=None, is_smoke=False,
            )

    # ------------------------------------------------------------------ echo
    def _render_echo_family(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        layer: dict[str, Any],
        history: TrailHistory,
        mod: ReactiveModulation,
        now_t: float,
        quality_cfg: dict[str, Any],
        theme_name: str,
    ) -> None:
        """Render ghostly deformation-preserving afterimage silhouettes of Zwoop."""
        max_life = float(quality_cfg.get("max_lifetime_s", 4.5))
        life_s = min(max_life, float(layer.get("lifetime_s", 1.6)) * mod.length_mult)
        echo_count = int(layer.get("echo_count", 6))
        spacing_px = max(12.0, float(layer.get("segment_spacing_px", 36.0)))
        scale = float(layer.get("size_scale", 1.0))

        # Collect spaced historical samples from newest backward
        selected: list[TrailSample] = []
        last_pos: tuple[float, float] | None = None
        for s in reversed(history.samples):
            age = now_t - s.t
            if age < 0.04:
                continue
            if age > life_s:
                break
            if last_pos is None or math.hypot(s.x - last_pos[0], s.y - last_pos[1]) >= spacing_px:
                selected.append(s)
                last_pos = (s.x, s.y)
                if len(selected) >= echo_count:
                    break

        if not selected:
            return

        selected.reverse()  # oldest first so newer echoes layer on top
        u_ages = np.array([np.clip((now_t - s.t) / max(life_s, 0.1), 0.0, 1.0) for s in selected], dtype=np.float32)
        spds = np.array([s.speed for s in selected], dtype=np.float32)
        fade_in_u = float(layer.get("fade_in_s", 0.04)) / max(life_s, 0.1)
        env = apply_fade_curve(u_ages, fade_in_u, layer.get("fade_curve", "smooth"))
        cols, stop_a = _eval_layer_colors(layer, u_ages, spds / 600.0, now_t, theme_name=theme_name)
        env = np.clip(env * stop_a, 0.0, 1.0)

        h, w = gx.shape
        inv_rs = 1.0 / rs
        taper = float(layer.get("taper", 0.5))

        for k, s in enumerate(selected):
            a_echo = float(env[k]) * 0.65
            if a_echo < 0.015:
                continue
            echo_scale = scale * (1.0 - 0.35 * taper * float(u_ages[k]))
            r_outer = 38.0 * echo_scale
            ix0 = max(0, int((s.x - r_outer - ox) * inv_rs))
            ix1 = min(w, int((s.x + r_outer - ox) * inv_rs) + 2)
            iy0 = max(0, int((s.y - r_outer - oy) * inv_rs))
            iy1 = min(h, int((s.y + r_outer - oy) * inv_rs) + 2)
            if ix1 <= ix0 or iy1 <= iy0:
                continue

            sgx = gx[iy0:iy1, ix0:ix1] - s.x
            sgy = gy[iy0:iy1, ix0:ix1] - s.y

            # Use deformed soft-body particle ring if available, else analytical stretched ring
            if s.body_rel is not None and len(s.body_rel) > 1:
                # Sample core + every 2nd outer particle for fast silhouette fidelity
                rel = s.body_rel[::2] * echo_scale
                fld = np.zeros_like(sgx)
                for p in rel:
                    dx = sgx - p[0]
                    dy = sgy - p[1]
                    fld += 190.0 * (echo_scale ** 2) / (dx * dx + dy * dy + 220.0 * (echo_scale ** 2))
                sil = np.clip((fld - 0.65) / 0.85, 0.0, 1.0)
                # Hollow-ish ghostly rim + soft core
                rim = sil * (1.15 - 0.45 * np.clip((fld - 1.3) / 1.2, 0.0, 1.0))
                mask_a = np.clip(rim * a_echo, 0.0, 1.0)
            else:
                d = np.hypot(sgx, sgy) / max(r_outer * 0.75, 1.0)
                sil = np.clip(1.0 - d * d, 0.0, 1.0)
                rim = sil * (0.65 + 0.55 * np.clip(d, 0.0, 1.0))
                mask_a = np.clip(rim * a_echo, 0.0, 1.0)

            cur_a = layer_a[iy0:iy1, ix0:ix1]
            better = mask_a > cur_a
            if np.any(better):
                c = cols[k]
                sub_rgb = layer_rgb[iy0:iy1, ix0:ix1]
                w_new = np.clip(mask_a / np.maximum(cur_a + mask_a, 1e-5), 0.0, 1.0)[..., None]
                sub_rgb[:] = sub_rgb * (1.0 - w_new) + c[None, None, :] * w_new
                cur_a[:] = np.maximum(cur_a, mask_a)

    # ------------------------------------------------------------- particles
    def _render_particles_family(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        layer: dict[str, Any],
        psys: ParticleSystem,
        mod: ReactiveModulation,
        now_t: float,
        quality_cfg: dict[str, Any],
        theme_name: str,
    ) -> None:
        n = psys.count
        if n == 0:
            return
        fam = layer.get("family", "particles")
        pcfg = layer.get("particles", {})
        shape = pcfg.get("shape", "puff" if fam == "smoke" else ("streak" if fam == "sparks" else "circle"))

        u_age = np.clip(psys.age / np.maximum(psys.life, 1e-4), 0.0, 1.0)
        fade_in_u = float(layer.get("fade_in_s", 0.04)) / max(float(layer.get("lifetime_s", 1.5)), 0.1)
        alphas = apply_fade_curve(u_age, fade_in_u, layer.get("fade_curve", "smooth"))

        # Sparkle / flicker modulation
        sparkle = float(pcfg.get("sparkle", 0.25))
        if quality_cfg.get("reduced_flashing", False):
            sparkle *= 0.15
        if sparkle > 0.02 and fam != "smoke":
            twinkle = 0.65 + 0.35 * np.sin(now_t * 16.0 + psys.phase * 3.7)
            alphas *= (1.0 - sparkle) + sparkle * twinkle

        cols, stop_a = _eval_layer_colors(
            layer,
            u_age,
            psys.birth_speed / 600.0,
            now_t,
            theme_name=theme_name,
            hue_jitter=psys.hue_jit,
        )
        alphas = np.clip(alphas * stop_a, 0.0, 1.0)
        if fam == "smoke":
            alphas *= 0.55  # soft translucent vapor

        self._splat_marks(
            gx, gy, ox, oy, rs, layer_rgb, layer_a,
            psys.pos, psys.size, cols, alphas, psys.rot,
            shape=shape, vel=psys.vel, is_smoke=(fam == "smoke"),
            now_t=now_t,
        )

    def _splat_marks(
        self,
        gx: np.ndarray,
        gy: np.ndarray,
        ox: float,
        oy: float,
        rs: float,
        layer_rgb: np.ndarray,
        layer_a: np.ndarray,
        pts: np.ndarray,
        sizes: np.ndarray,
        cols: np.ndarray,
        alphas: np.ndarray,
        rots: np.ndarray,
        shape: str = "circle",
        vel: np.ndarray | None = None,
        is_smoke: bool = False,
        now_t: float = 0.0,
    ) -> None:
        h, w = gx.shape
        inv_rs = 1.0 / rs

        for i in range(len(pts)):
            ai = float(alphas[i])
            if ai < 0.015:
                continue
            px, py = float(pts[i, 0]), float(pts[i, 1])
            sz = max(float(sizes[i]), rs * 0.75)
            pad = sz * (2.2 if shape == "streak" else 1.35)

            ix0 = max(0, int((px - pad - ox) * inv_rs))
            ix1 = min(w, int((px + pad - ox) * inv_rs) + 2)
            iy0 = max(0, int((py - pad - oy) * inv_rs))
            iy1 = min(h, int((py + pad - oy) * inv_rs) + 2)
            if ix1 <= ix0 or iy1 <= iy0:
                continue

            dx = gx[iy0:iy1, ix0:ix1] - px
            dy = gy[iy0:iy1, ix0:ix1] - py

            if shape == "streak" and vel is not None:
                vx, vy = float(vel[i, 0]), float(vel[i, 1])
                vnorm = math.hypot(vx, vy)
                if vnorm > 8.0:
                    ux, uy = vx / vnorm, vy / vnorm
                else:
                    ang = math.radians(float(rots[i]))
                    ux, uy = math.cos(ang), math.sin(ang)
                along = dx * ux + dy * uy
                perp = -dx * uy + dy * ux
                stretch = min(2.4, 1.0 + vnorm / 220.0)
                d_norm = np.hypot(along / (sz * stretch), perp / max(sz * 0.42, 1.2))
                kern = np.clip(1.0 - d_norm, 0.0, 1.0) ** 1.5
            elif shape == "star":
                ang = math.radians(float(rots[i]))
                ca, sa = math.cos(ang), math.sin(ang)
                rx = np.abs(dx * ca + dy * sa) / sz
                ry = np.abs(-dx * sa + dy * ca) / sz
                d_eu = np.hypot(rx, ry)
                spike = np.maximum(
                    np.clip(1.0 - rx * 2.8, 0.0, 1.0) * np.clip(1.0 - ry * 0.75, 0.0, 1.0),
                    np.clip(1.0 - ry * 2.8, 0.0, 1.0) * np.clip(1.0 - rx * 0.75, 0.0, 1.0),
                )
                core = np.clip(1.0 - d_eu * 1.4, 0.0, 1.0) ** 2
                kern = np.maximum(spike, core)
            elif shape in ("diamond", "shard"):
                ang = math.radians(float(rots[i]))
                ca, sa = math.cos(ang), math.sin(ang)
                rx = np.abs(dx * ca + dy * sa) / sz
                ry = np.abs(-dx * sa + dy * ca) / (sz * (0.55 if shape == "shard" else 0.85))
                kern = np.clip(1.0 - (rx + ry), 0.0, 1.0) ** 1.3
            elif shape == "ring":
                # Bubble / hollow ring with specular top-left highlight
                d_norm = np.hypot(dx, dy) / sz
                inside = np.clip((1.05 - d_norm) * 3.5, 0.0, 1.0)
                rim = np.exp(-((d_norm - 0.78) ** 2) / 0.035)
                spec = np.clip((-dx - dy) / (sz * 1.4), 0.0, 1.0) ** 2 * 0.55
                kern = inside * np.clip(0.18 + 0.82 * rim + spec, 0.0, 1.0)
            else:  # circle / puff
                d_norm = np.hypot(dx, dy) / sz
                if is_smoke or shape == "puff":
                    # Organic billowing cloud texture
                    wisp = 0.82 + 0.18 * np.sin((dx + px) * 0.09 + now_t * 1.5) * np.cos((dy + py) * 0.09)
                    kern = (np.clip(1.0 - d_norm * d_norm, 0.0, 1.0) ** 1.8) * wisp
                else:
                    kern = np.clip(1.0 - d_norm, 0.0, 1.0) ** 1.6

            pa = kern * ai
            cur_a = layer_a[iy0:iy1, ix0:ix1]
            mask = pa > 0.008
            if not np.any(mask):
                continue

            c = cols[i]
            sub_rgb = layer_rgb[iy0:iy1, ix0:ix1]
            # Additive-friendly color accumulation within particle layer
            w_new = np.clip(pa / np.maximum(cur_a + pa, 1e-5), 0.0, 1.0)[..., None]
            sub_rgb[:] = sub_rgb * (1.0 - w_new) + c[None, None, :] * w_new
            cur_a[:] = np.clip(cur_a + pa * (1.0 - cur_a * 0.65), 0.0, 1.0)
