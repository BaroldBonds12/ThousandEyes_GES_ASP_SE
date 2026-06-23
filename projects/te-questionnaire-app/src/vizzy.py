"""
Vizzy — steampunk chibi robot mascot.

Orange armor plating, glowing teal visor-lens eyes, red scarf, brass rivets,
segmented arms with elbow joints, and chunky armored boots.
Stays fully orange with teal eye-glow accent and red scarf.

Usage:
    from src.vizzy import create_vizzy   # → PIL Image
"""

from __future__ import annotations

import math
from typing import Tuple

from PIL import Image, ImageDraw

# ── Colour palette ─────────────────────────────────────────────────────────────

# Orange armor
_ORG_BASE = (235, 108,  12, 255)   # main armor surface
_ORG_HI   = (255, 168,  55, 255)   # highlight plate (brighter)
_ORG_MID  = (198,  82,   5, 255)   # mid-tone plate
_ORG_SH   = (148,  48,   0, 255)   # shadow plate (deeper)
_ORG_EDGE = ( 95,  28,   0, 255)   # panel-line / deep shadow

# Teal visor / eye glow
_TEAL_RIM  = (  0, 145, 130, 255)   # outer ring
_TEAL_MID  = (  0, 205, 185, 255)   # inner glow
_TEAL_CORE = ( 88, 252, 228, 255)   # bright core dot
_TEAL_SHIN = (220, 255, 248, 255)   # specular highlight

# Red scarf
_RED_D = (160,  18,  18, 255)
_RED_M = (210,  42,  32, 255)
_RED_H = (242,  92,  62, 255)

# Brass rivets
_RIVET   = (188, 128,  18, 255)
_RIVET_H = (238, 196,  75, 255)

# Misc
_BLACK  = ( 16,   8,   3, 255)
_YELLOW = (255, 220,  40, 255)

RGBA = Tuple[int, int, int, int]


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _ell(d: ImageDraw.Draw, cx: float, cy: float,
         rx: float, ry: float, fill: RGBA,
         outline: RGBA = None, ow: int = 0) -> None:
    box = [cx - rx, cy - ry, cx + rx, cy + ry]
    if outline:
        d.ellipse(box, fill=fill, outline=outline, width=ow)
    else:
        d.ellipse(box, fill=fill)


def _rr(d: ImageDraw.Draw, x1, y1, x2, y2, r: int, fill: RGBA,
        outline: RGBA = None, ow: int = 0) -> None:
    d.rounded_rectangle([x1, y1, x2, y2], radius=max(1, r),
                        fill=fill, outline=outline, width=ow)


def _rivet(d: ImageDraw.Draw, cx: float, cy: float, r: int) -> None:
    """Brass rivet with shadow ring + highlight spot."""
    _ell(d, cx, cy, r + 1, r + 1, fill=_BLACK)
    _ell(d, cx, cy, r, r, fill=_RIVET)
    _ell(d, cx - max(1, r // 3), cy - max(1, r // 3),
         max(1, r // 3), max(1, r // 3), fill=_RIVET_H)


def _star(d: ImageDraw.Draw, cx: float, cy: float,
          r: float, fill: RGBA) -> None:
    pts = []
    for i in range(8):
        ang    = math.pi * i / 4 - math.pi / 4
        radius = r if i % 2 == 0 else r * 0.38
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    d.polygon(pts, fill=fill)


# ── Visor eyes ────────────────────────────────────────────────────────────────

# Glow-core offset per expression (fractions of eye half-size)
_EYE_DIR = {
    "idle":        ( 0.00,  0.00),
    "blink":       ( 0.00,  0.00),
    "checking":    (-0.20, -0.22),   # scanning upper-left
    "working":     (-0.14,  0.00),   # focused left
    "downloading": ( 0.18,  0.10),
    "happy":       ( 0.00, -0.20),
    "done":        ( 0.00, -0.26),
}


def _draw_visor_eyes(d: ImageDraw.Draw, cx: int, head_cy: int,
                     head_r: int, expression: str) -> None:
    """
    Teal lens-style eyes set inside a dark visor housing with brass rivets.
    Each eye is a stack of concentric ovals going from dark teal → bright core.
    """
    ew  = int(head_r * 0.295)     # each eye's half-width
    eh  = int(head_r * 0.215)     # each eye's half-height (wider than tall)
    off = int(head_r * 0.36)      # cx ± off = each eye centre
    eye_cy = head_cy - int(head_r * 0.08)

    # Visor housing — recessed dark band behind both eyes
    vp = int(head_r * 0.10)       # housing padding around eyes
    hx1 = cx - off - ew - vp
    hx2 = cx + off + ew + vp
    hy1 = eye_cy - eh - vp
    hy2 = eye_cy + eh + vp
    _rr(d, hx1, hy1, hx2, hy2, eh + vp // 2,
        fill=_ORG_EDGE, outline=_BLACK, ow=2)

    # Rivets at four corners of housing
    rv = max(2, int(head_r * 0.053))
    for sx in (-1, +1):
        for sy in (-1, +1):
            _rivet(d,
                   cx + sx * (off + ew + vp - rv - 1),
                   eye_cy + sy * (eh + vp - rv - 1),
                   rv)

    dx_f, dy_f = _EYE_DIR.get(expression, (0.0, 0.0))
    core_xo = int(dx_f * ew * 0.46)
    core_yo = int(dy_f * eh * 0.46)

    # ── Blink: visor sliding shut ─────────────────────────────────────────
    if expression == "blink":
        slit = max(2, int(eh * 0.22))
        for sign in (-1, +1):
            ex = cx + sign * off
            _ell(d, ex, eye_cy, ew + 1, slit + 1, fill=_BLACK)
            _ell(d, ex, eye_cy, ew, slit, fill=_TEAL_RIM)
            _ell(d, ex, eye_cy, int(ew * 0.55), max(1, slit // 2), fill=_TEAL_CORE)
        return

    # ── Lens eyes ─────────────────────────────────────────────────────────
    core_scale = 1.28 if expression in ("happy", "done") else 1.0

    for sign in (-1, +1):
        ex = cx + sign * off

        # Outer frame ring
        _ell(d, ex, eye_cy, ew + 2, eh + 2, fill=_BLACK)

        # Outer teal ring
        _ell(d, ex, eye_cy, ew, eh, fill=_TEAL_RIM)

        # Mid glow
        _ell(d, ex + core_xo, eye_cy + core_yo,
             int(ew * 0.70), int(eh * 0.70), fill=_TEAL_MID)

        # Bright core
        _ell(d, ex + core_xo, eye_cy + core_yo,
             int(ew * 0.40 * core_scale), int(eh * 0.40 * core_scale),
             fill=_TEAL_CORE)

        # Specular shine dot (top-left)
        _ell(d, ex - int(ew * 0.28), eye_cy - int(eh * 0.30),
             int(ew * 0.17), int(eh * 0.13), fill=_TEAL_SHIN)


# ── Mouth (steampunk grille style) ────────────────────────────────────────────

def _draw_mouth(d: ImageDraw.Draw, cx: int, mouth_y: int,
                head_r: int, expression: str) -> None:
    """
    Replace the blob smile with steampunk speaker-grille slots.
    Happy/done → arc + grin. Checking → smirk. Others → grille bars.
    """
    mw    = int(head_r * 0.34)
    mh    = int(head_r * 0.18)
    thick = max(2, int(head_r * 0.075))
    slot  = max(2, int(head_r * 0.055))

    if expression in ("happy", "done"):
        # Wide grin arc
        d.arc([cx - mw, mouth_y - mh, cx + mw, mouth_y + mh],
              start=10, end=170, fill=_BLACK, width=thick)
        # Grille slots inside grin
        sy = mouth_y + int(mh * 0.28)
        n_slots = 5
        for i in range(n_slots):
            sx = cx - int(mw * 0.55) + i * int(mw * 1.10 / (n_slots - 1))
            d.line([(sx, sy - slot), (sx, sy + slot)],
                   fill=_BLACK, width=max(2, slot // 2))

    elif expression == "checking":
        d.arc([cx - mw // 2, mouth_y - int(mh * 0.55),
               cx + mw,       mouth_y + int(mh * 0.55)],
              start=200, end=340, fill=_BLACK, width=thick)

    elif expression in ("working", "downloading"):
        # Focused grille — 3 horizontal bars
        for i, dy in enumerate((-slot, 0, slot)):
            bx = int(mw * (0.60 if i == 1 else 0.44))
            d.line([cx - bx, mouth_y + dy, cx + bx, mouth_y + dy],
                   fill=_BLACK, width=max(2, slot // 2))

    else:
        # Idle — 2 horizontal grille bars
        for dy in (-slot, slot):
            d.line([cx - int(mw * 0.48), mouth_y + dy,
                    cx + int(mw * 0.48), mouth_y + dy],
                   fill=_BLACK, width=max(2, slot // 2))


# ── Main character generator ───────────────────────────────────────────────────

def create_vizzy(expression: str = "idle", size: int = 110) -> Image.Image:
    """
    Return a PIL RGBA Image of steampunk-chibi Vizzy.

    Orange armor plating, teal lens eyes, red scarf, brass rivets,
    segmented arms with elbow joints, chunky armored boots.

    size       : pixel width; height ≈ 1.72× width
    expression : idle | checking | working | downloading | happy | done | blink
    """
    W  = size
    H  = int(size * 1.72)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    cx  = W // 2
    rv  = max(2, size // 32)         # standard rivet radius
    ol  = max(2, size // 42)         # thin outline stroke

    # ── Pre-compute head geometry ──────────────────────────────────────────────
    head_r  = int(W * 0.410)
    head_cx = cx
    head_cy = int(H * 0.330)
    ol_h    = max(2, int(head_r * 0.068))

    # Body top / bottom
    bw   = int(head_r * 0.46)        # body half-width
    bh   = int(H * 0.095)
    by1  = head_cy + head_r - int(head_r * 0.09)
    by2  = by1 + bh
    arm_y = by1 + bh // 2

    # ── LEGS (drawn first — behind everything) ─────────────────────────────────
    boot_w  = int(size * 0.115)
    boot_h  = int(H * 0.100)
    shin_h  = int(H * 0.095)
    shin_w  = max(4, size // 16)

    for sign in (-1, +1):
        lx = cx + sign * int(bw * 0.48)
        shin_ty = by2
        shin_by = shin_ty + shin_h
        boot_cx = lx + sign * 3

        # Shin outline + fill
        d.line([lx, shin_ty, boot_cx, shin_by],
               fill=_BLACK, width=shin_w + 4)
        d.line([lx, shin_ty, boot_cx, shin_by],
               fill=_ORG_MID, width=shin_w)

        # Boot block
        bx1 = boot_cx - boot_w
        bx2 = boot_cx + boot_w
        _rr(d, bx1 - ol, shin_by - ol, bx2 + ol, shin_by + boot_h + ol,
            boot_h // 4, fill=_BLACK)
        _rr(d, bx1, shin_by, bx2, shin_by + boot_h,
            boot_h // 4, fill=_ORG_SH)
        # Boot highlight strip
        _rr(d,
            bx1 + int(boot_w * 0.30), shin_by + int(boot_h * 0.18),
            bx2 - int(boot_w * 0.30), shin_by + int(boot_h * 0.52),
            int(boot_h * 0.16), fill=_ORG_MID)
        # Boot toe cap
        _rr(d,
            boot_cx + sign * int(boot_w * 0.20) - int(boot_w * 0.42),
            shin_by + int(boot_h * 0.55),
            boot_cx + sign * int(boot_w * 0.20) + int(boot_w * 0.42),
            shin_by + boot_h - 1,
            int(boot_h * 0.22), fill=_ORG_EDGE)
        # Boot rivet
        _rivet(d, boot_cx, shin_by + int(boot_h * 0.28), rv)

    # ── BODY ──────────────────────────────────────────────────────────────────
    _rr(d, cx - bw - ol, by1 - ol, cx + bw + ol, by2 + ol,
        bh // 3, fill=_BLACK)
    _rr(d, cx - bw, by1, cx + bw, by2,
        bh // 3, fill=_ORG_MID)
    # Chest highlight
    _rr(d,
        cx - int(bw * 0.58), by1 + int(bh * 0.20),
        cx + int(bw * 0.58), by1 + int(bh * 0.60),
        int(bh * 0.18), fill=_ORG_BASE)
    # Chest panel line
    for sy in (-1, +1):
        d.line([cx - int(bw * 0.35), arm_y + sy * int(bh * 0.22),
                cx + int(bw * 0.35), arm_y + sy * int(bh * 0.22)],
               fill=_ORG_EDGE, width=max(1, ol - 1))
    # Chest rivets
    for sign in (-1, +1):
        _rivet(d, cx + sign * int(bw * 0.64), arm_y, rv)

    # ── ARMS (drawn before head so head overlaps) ──────────────────────────────
    seg_w = max(5, size // 13)

    _ARM = {
        "idle":        ((-bw - 18, +14), (+bw + 18, +14)),
        "checking":    ((-bw - 15, +9),  (+bw +  9, -20)),
        "working":     ((-bw - 22, +2),  (+bw + 22,  +2)),
        "downloading": ((-bw - 16, -5),  (+bw + 16,  -5)),
        "happy":       ((-bw - 16, -23), (+bw + 16, -23)),
        "done":        ((-bw - 14, -27), (+bw + 14, -27)),
    }
    (ldx, ldy), (rdx, rdy) = _ARM.get(expression, _ARM["idle"])

    for i, ((ox, oy), (hdx, hdy)) in enumerate((
        ((cx - bw, arm_y), (ldx, ldy)),
        ((cx + bw, arm_y), (rdx, rdy)),
    )):
        hx, hy = ox + hdx, oy + hdy
        # Elbow midpoint — slight bend outward
        mid_x = (ox + hx) // 2 + (-3 if i == 0 else 3)
        mid_y = (oy + hy) // 2 - 3

        # Upper arm — outline then fill
        d.line([ox, oy, mid_x, mid_y], fill=_BLACK, width=seg_w + 4)
        d.line([ox, oy, mid_x, mid_y], fill=_ORG_MID, width=seg_w)

        # Elbow joint ball
        ej_r = seg_w // 2 + 1
        _ell(d, mid_x, mid_y, ej_r + 2, ej_r + 2, fill=_BLACK)
        _ell(d, mid_x, mid_y, ej_r, ej_r, fill=_ORG_SH)
        _rivet(d, mid_x, mid_y, max(2, rv - 1))

        # Lower arm — slightly lighter
        d.line([mid_x, mid_y, hx, hy], fill=_BLACK, width=seg_w + 4)
        d.line([mid_x, mid_y, hx, hy], fill=_ORG_BASE, width=seg_w)

        # Gauntlet fist — chunky
        fist_r = seg_w // 2 + 4
        _ell(d, hx, hy, fist_r + 2, fist_r + 2, fill=_BLACK)
        _ell(d, hx, hy, fist_r, fist_r, fill=_ORG_SH)
        # Knuckle rivet
        koff = -2 if i == 0 else 2
        _rivet(d, hx + koff, hy - 2, max(2, rv - 1))

    # ── HEAD ──────────────────────────────────────────────────────────────────

    # Drop shadow
    _ell(d, head_cx + int(head_r * 0.05), head_cy + int(head_r * 0.07),
         head_r + ol_h, int((head_r + ol_h) * 0.96), fill=(0, 0, 0, 48))

    # Outline ring
    _ell(d, head_cx, head_cy, head_r + ol_h, head_r + ol_h, fill=_BLACK)

    # Main head fill
    _ell(d, head_cx, head_cy, head_r, head_r, fill=_ORG_BASE)

    # Highlight dome — top-left brighter plate
    _ell(d,
         head_cx - int(head_r * 0.22), head_cy - int(head_r * 0.26),
         int(head_r * 0.36), int(head_r * 0.22), fill=_ORG_HI)

    # Lower shadow arc
    _ell(d,
         head_cx, head_cy + int(head_r * 0.30),
         int(head_r * 0.78), int(head_r * 0.38), fill=_ORG_SH)

    # Horizontal panel groove across upper face
    pan_y = head_cy - int(head_r * 0.15)
    pan_rx = int(head_r * 0.80)
    d.arc([head_cx - pan_rx, pan_y - int(head_r * 0.06),
           head_cx + pan_rx, pan_y + int(head_r * 0.06)],
          start=182, end=358, fill=_ORG_EDGE,
          width=max(1, int(head_r * 0.038)))

    # ── EAR / SIDE ARMOR PLATES ───────────────────────────────────────────────
    ear_rw = int(head_r * 0.21)
    ear_rh = int(head_r * 0.27)
    ear_cy  = head_cy - int(head_r * 0.08)

    for sign in (-1, +1):
        ear_cx = head_cx + sign * (head_r - int(ear_rw * 0.28))
        _ell(d, ear_cx, ear_cy, ear_rw + ol_h, ear_rh + ol_h, fill=_BLACK)
        _ell(d, ear_cx, ear_cy, ear_rw, ear_rh, fill=_ORG_MID)
        # Ear highlight
        _ell(d,
             ear_cx - int(ear_rw * 0.18), ear_cy - int(ear_rh * 0.22),
             int(ear_rw * 0.38), int(ear_rh * 0.30), fill=_ORG_HI)
        # Ear panel line
        d.line([ear_cx - int(ear_rw * 0.55), ear_cy,
                ear_cx + int(ear_rw * 0.55), ear_cy],
               fill=_ORG_EDGE, width=max(1, ol - 1))
        # Ear rivet
        _rivet(d, ear_cx, ear_cy + int(ear_rh * 0.30), rv)

    # ── ANTENNA ───────────────────────────────────────────────────────────────
    ant_bx = head_cx + int(head_r * 0.26)
    ant_by = head_cy - head_r - ol_h + 3
    ant_tx = ant_bx + int(head_r * 0.07)
    ant_ty = ant_by - int(head_r * 0.33)
    ant_w  = max(2, ol_h - 1)

    d.line([(ant_bx, ant_by), (ant_tx, ant_ty)], fill=_BLACK, width=ant_w + 2)
    d.line([(ant_bx, ant_by), (ant_tx, ant_ty)], fill=_ORG_MID, width=ant_w)
    # Ball tip
    ball_r = int(head_r * 0.072)
    _ell(d, ant_tx, ant_ty, ball_r + 1, ball_r + 1, fill=_BLACK)
    _ell(d, ant_tx, ant_ty, ball_r, ball_r, fill=_TEAL_CORE)

    # ── FOREHEAD RIVETS ───────────────────────────────────────────────────────
    for rfx, rfy in [(-0.60, -0.54), (0.60, -0.54),
                     (-0.68,  0.08), (0.68,  0.08)]:
        px = int(head_cx + head_r * rfx)
        py = int(head_cy + head_r * rfy)
        if (px - head_cx) ** 2 + (py - head_cy) ** 2 < (head_r - rv - 3) ** 2:
            _rivet(d, px, py, rv)

    # ── VISOR EYES ────────────────────────────────────────────────────────────
    _draw_visor_eyes(d, head_cx, head_cy, head_r, expression)

    # ── MOUTH (steampunk grille) ───────────────────────────────────────────────
    mouth_y = head_cy + int(head_r * 0.50)
    _draw_mouth(d, head_cx, mouth_y, head_r, expression)

    # ── SCARF (drawn after head so it wraps visibly over the neck) ────────────
    # Positioned just below the head circle, draping over the body top.
    scarf_top = head_cy + head_r - int(head_r * 0.08)
    scarf_h   = int(head_r * 0.30)
    scarf_w   = int(head_r * 0.62)

    # Main scarf band — outline + fill
    _rr(d, cx - scarf_w - ol, scarf_top - ol,
           cx + scarf_w + ol, scarf_top + scarf_h + ol,
        scarf_h // 2, fill=_BLACK)
    _rr(d, cx - scarf_w, scarf_top,
           cx + scarf_w, scarf_top + scarf_h,
        scarf_h // 2, fill=_RED_M)
    # Scarf highlight stripe along top
    _rr(d,
        cx - int(scarf_w * 0.70), scarf_top + int(scarf_h * 0.12),
        cx + int(scarf_w * 0.70), scarf_top + int(scarf_h * 0.46),
        int(scarf_h * 0.22), fill=_RED_H)
    # Hanging tail shadow on right side
    _rr(d,
        cx + int(scarf_w * 0.22), scarf_top + int(scarf_h * 0.10),
        cx + int(scarf_w * 0.70), scarf_top + scarf_h - 1,
        int(scarf_h * 0.20), fill=_RED_D)
    # Centre knot
    kn_r = int(scarf_h * 0.52)
    _ell(d, cx, scarf_top + scarf_h // 2, kn_r + ol, kn_r + ol, fill=_BLACK)
    _ell(d, cx, scarf_top + scarf_h // 2, kn_r, kn_r, fill=_RED_D)
    _ell(d,
         cx - kn_r // 3, scarf_top + scarf_h // 2 - kn_r // 3,
         kn_r // 3, kn_r // 3, fill=_RED_H)

    # ── CELEBRATION SPARKLES ──────────────────────────────────────────────────
    if expression in ("happy", "done"):
        ssz = max(4, size // 23)
        for sx, sy in [(W - 13, 4), (8, 7), (W - 7, head_cy - head_r - 5)]:
            _star(d, sx, sy, ssz, _YELLOW)
        # Teal eye-glow sparks
        _star(d, head_cx - int(head_r * 0.60),
              head_cy - int(head_r * 0.66), ssz - 1, _TEAL_CORE)

    return img


def create_vizzy_photo(expression: str = "idle", size: int = 110):
    """Return an ImageTk.PhotoImage ready for use in a tkinter Label."""
    from PIL import ImageTk
    return ImageTk.PhotoImage(create_vizzy(expression=expression, size=size))
