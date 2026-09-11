#!/usr/bin/env python3
"""
WC2Thumb GUI — Wing Commander Unity → ThumbCommander Sprite Converter
=====================================================================

Interactive GUI for converting sprite sheets from Howard Day's WCUnity
project into the binary sprite formats used by ThumbCommander.

Requirements:
    pip install Pillow numpy

Usage:
    python wc2thumb_gui.py
    python wc2thumb_gui.py --source ./WCUnity/Assets/Art
"""

import argparse
import math
import os
import struct
import sys
import threading
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("ERROR: tkinter is required. On macOS: brew install python-tk@3.11")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageTk, ImageFilter
    import numpy as np
except ImportError:
    print("ERROR: This tool requires Pillow and numpy.")
    print("  pip install Pillow numpy")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

APP_TITLE = "WC2Thumb — Sprite Converter"
APP_MIN_SIZE = (1100, 780)

# ThumbCommander sprite resolutions
THUMBY_SIZES = {
    "enemy":    (40, 34),
    "asteroid": (32, 27),
    "explode":  (32, 31),
    "cockpit":  (72, 40),
    "weapon":   (8, 8),
    "background": (72, 40),
}
TCOLOR_SIZES = {
    "enemy":    (70, 59),
    "asteroid": (56, 47),
    "explode":  (56, 54),
    "cockpit":  (128, 128),
    "weapon":   (14, 14),
    "background": (128, 128),
}

# ThumbCommander orientation system
TC_X_INDEX  = [24,25,26,27,26,25,24,23,22,21,22,23,24]
TC_X_MIRROR = [False,False,False,False,True,True,True,True,True,False,False,False,False]
TC_Y_SHIFT  = [0,-7,-14,-21,-14,-7,0,7,14,21,14,7,0]
TC_Y_MIRROR = [True,False,False,False,False,False,True,True,True,True,True,True,True]

# WCUnity layout
WC_YAW_FRAMES  = 32
WC_PITCH_FILES = 17
WC_SHEET_COLS  = 8
WC_SHEET_ROWS  = 4
WC_YAW_STEP    = 360.0 / WC_YAW_FRAMES
WC_PITCH_STEP  = 180.0 / (WC_PITCH_FILES - 1)

# Direct WCUnity frame mapping for the 7×7 stored grid.
#
# Columns = yaw (horizontal rotation) sub-frame indices within each sheet:
#   Start at yaw 15 (near front), decrease to 0, wrap to 31 (near rear).
#   Sequence: 15, 12, 9, 7, 4, 1, 31
#
# Rows = pitch file indices:
#   Start at pitch 16 (bottom-up), through 8 (level), to 0 (top-down).
#   Sequence: 16, 13, 10, 8, 5, 2, 0
#
# Per-pitch mirroring:
#   Pitches 16, 13, 10, 8: flip top-to-bottom AND left-to-right
#   Pitches 5, 2, 0:       flip left-to-right only (no top-to-bottom)
STORED_COL_YAW   = [15, 12, 9, 7, 4, 1, 31]  # WC yaw frame indices
STORED_ROW_PITCH = [16, 13, 10, 8, 5, 2, 0]   # WC pitch file indices

def flip_for_pitch(img: Image.Image, wc_pitch: int) -> Image.Image:
    """Apply the correct flip transform based on the pitch file index."""
    if wc_pitch in (16, 13, 10, 8):
        # Top-to-bottom + left-to-right
        img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    else:
        # Pitches 5, 2, 0: left-to-right only
        img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return img

# Known WCUnity ships
SHIPS = {
    "Dralthi":   {"prefix": "HowieDralthi",   "ace": "HowieDralthiACE",  "size": (256,256)},
    "Hornet":    {"prefix": "ArneHornet",      "ace": "ArneHornetAce",    "size": (256,256)},
    "Krant":     {"prefix": "HowieKrant",      "ace": None,               "size": (256,256)},
    "Salthi":    {"prefix": "HowieSalthi",     "ace": "HowieSalthiACE",   "size": (128,128)},
    "Scimitar":  {"prefix": "HowieScimitar",   "ace": None,               "size": (300,300)},
    "Strakha":   {"prefix": "HowieStrakha",    "ace": "HowieStrakhaAce",  "size": (300,300)},
    "Talon":     {"prefix": "HowieTalon",      "ace": None,               "size": (256,256)},
    "Valtar":    {"prefix": "HowieFirekkan",   "ace": None,               "size": (256,256)},
    "Grikath":   {"prefix": "HowieGrikath",    "ace": None,               "size": (256,256)},
}

# WCUnity Art directory structure: category → subfolder under Art/
# Each category maps to its known subfolders and the asset_type for conversion.
WC_CATEGORIES = {
    "Ships":    {"path": "Ships",    "asset_type": "ship"},
    "VFX":      {"path": "VFX",      "asset_type": "explosion"},
    "Cockpits": {"path": "Cockpits", "asset_type": "cockpit"},
    "Weapons":  {"path": "Weapons",  "asset_type": "weapon"},
    "Space":    {"path": "Space",    "asset_type": "background"},
    "Menu":     {"path": "Menu",     "asset_type": "background"},
}

# Grayscale palette: index → luminance
GRAY4_LUM = {0: 0, 1: 255, 2: 85, 3: 170}

# Colors for the UI
C_BG       = "#1a1a2e"
C_BG2      = "#16213e"
C_BG3      = "#0f3460"
C_ACCENT   = "#e94560"
C_ACCENT2  = "#533483"
C_TEXT     = "#e0e0e0"
C_TEXT_DIM = "#808090"
C_GRID     = "#2a2a4e"
C_HOVER    = "#e9456040"
C_SELECT   = "#e94560"
C_OK       = "#4ecca3"


# ═══════════════════════════════════════════════════════════════════════════════
# Conversion Core
# ═══════════════════════════════════════════════════════════════════════════════

def trim_transparent(img: Image.Image, pad: int = 1) -> Image.Image:
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 10, axis=1)
    cols = np.any(alpha > 10, axis=0)
    if not rows.any() or not cols.any():
        return img
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    rmin = max(0, rmin - pad); rmax = min(img.height-1, rmax + pad)
    cmin = max(0, cmin - pad); cmax = min(img.width-1, cmax + pad)
    return img.crop((cmin, rmin, cmax+1, rmax+1))

def resize_contain(img: Image.Image, tw: int, th: int) -> Image.Image:
    scale = min(tw / img.width, th / img.height)
    nw = max(1, int(img.width * scale))
    nh = max(1, int(img.height * scale))
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    result.paste(resized, ((tw-nw)//2, (th-nh)//2), resized)
    return result

def to_gray4(img: Image.Image, t_black=32, t_dark=96, t_light=180) -> np.ndarray:
    arr = np.array(img, dtype=np.float32)
    alpha = arr[:,:,3] / 255.0
    lum = (0.299*arr[:,:,0] + 0.587*arr[:,:,1] + 0.114*arr[:,:,2]) * alpha
    out = np.zeros(lum.shape, dtype=np.uint8)
    out[lum >= t_black] = 2
    out[lum >= t_dark]  = 3
    out[lum >= t_light] = 1
    return out

def gray4_to_rgba(g4: np.ndarray) -> Image.Image:
    h, w = g4.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for val, lum in GRAY4_LUM.items():
        mask = g4 == val
        rgba[mask, 0] = lum
        rgba[mask, 1] = lum
        rgba[mask, 2] = lum
        rgba[mask, 3] = 255 if val != 0 else 0
    return Image.fromarray(rgba, "RGBA")

def to_rgb565(img: Image.Image) -> np.ndarray:
    arr = np.array(img, dtype=np.float32)
    a = arr[:,:,3] / 255.0
    r = (arr[:,:,0]*a).astype(np.uint8)
    g = (arr[:,:,1]*a).astype(np.uint8)
    b = (arr[:,:,2]*a).astype(np.uint8)
    return ((r>>3).astype(np.uint16)<<11) | ((g>>2).astype(np.uint16)<<5) | (b>>3).astype(np.uint16)

def encode_thumby_bitplane(g4: np.ndarray, w: int, h: int):
    pages = math.ceil(h / 8)
    bit_d = bytearray(w * pages)
    shd_d = bytearray(w * pages)
    for x in range(w):
        for pg in range(pages):
            bb = sb = 0
            for bi in range(8):
                y = pg*8 + bi
                if y < h:
                    px = g4[y, x]
                    if px & 1: bb |= (1 << bi)
                    if px & 2: sb |= (1 << bi)
            idx = pg * w + x
            bit_d[idx] = bb
            shd_d[idx] = sb
    return bytes(bit_d), bytes(shd_d)

def write_thumby(frames_g4, w, h, base):
    ab = bytearray(); ash = bytearray()
    for f in frames_g4:
        b, s = encode_thumby_bitplane(f, w, h)
        ab.extend(b); ash.extend(s)
    bp = f"{base}.BIT.bin"; sp = f"{base}.SHD.bin"
    with open(bp,'wb') as f: f.write(ab)
    with open(sp,'wb') as f: f.write(ash)
    return bp, sp, len(ab)

def write_tcolor(frames_565, w, h, base):
    hdr = struct.pack('<HHHH', w, h, len(frames_565), 0)
    data = bytearray(hdr)
    for f in frames_565:
        data.extend(f.astype('<u2').tobytes())
    cp = f"{base}.COL.bin"
    with open(cp,'wb') as f: f.write(data)
    return cp, len(data)


# ═══════════════════════════════════════════════════════════════════════════════
# Ship Sprite Loader
# ═══════════════════════════════════════════════════════════════════════════════

class ShipLoader:
    def __init__(self, source_dir: str, ship_name: str, variant: str = "standard"):
        self.source_dir = Path(source_dir)
        self.ship_name = ship_name
        info = SHIPS.get(ship_name, {})
        if variant.upper() == "ACE" and info.get("ace"):
            self.prefix = info["ace"]
        else:
            self.prefix = info.get("prefix", ship_name)
        self.frame_size = info.get("size", (256, 256))
        self._cache = {}

    def _find(self, pitch: int) -> Optional[Path]:
        for pat in [f"{self.prefix}{pitch}.png", f"{self.prefix}_{pitch}.png"]:
            p = self.source_dir / pat
            if p.exists(): return p
        return None

    def load_sheet(self, pitch: int) -> Optional[Image.Image]:
        if pitch in self._cache:
            return self._cache[pitch]
        p = self._find(pitch)
        if p is None: return None
        img = Image.open(p).convert("RGBA")
        self._cache[pitch] = img
        return img

    def extract(self, yaw: int, pitch: int) -> Optional[Image.Image]:
        sheet = self.load_sheet(pitch)
        if sheet is None: return None
        fw, fh = self.frame_size
        c = yaw % WC_SHEET_COLS
        r = yaw // WC_SHEET_COLS
        x0, y0 = c*fw, r*fh
        if x0+fw > sheet.width or y0+fh > sheet.height: return None
        return sheet.crop((x0, y0, x0+fw, y0+fh))

    def available_pitches(self) -> list:
        return [i for i in range(WC_PITCH_FILES) if self._find(i)]

    def clear_cache(self):
        self._cache.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# GUI Application
# ═══════════════════════════════════════════════════════════════════════════════

class WC2ThumbApp:

    def __init__(self, root: tk.Tk, initial_source: str = ""):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.minsize(*APP_MIN_SIZE)
        self.root.configure(bg=C_BG)

        # State
        self.art_root = tk.StringVar(value=initial_source)  # Art/ directory root
        self.category = tk.StringVar(value="")              # Ships, VFX, Cockpits, ...
        self.object_name = tk.StringVar(value="")           # Dralthi, Hornet, Debris01, ...
        self.variant = tk.StringVar(value="standard")       # standard, ACE
        self.pitch_idx = tk.IntVar(value=8)
        self.output_dir = tk.StringVar(value=os.path.expanduser("~"))
        self.output_name = tk.StringVar(value="")
        self.thumby_w = tk.IntVar(value=40)
        self.thumby_h = tk.IntVar(value=34)
        self.tcolor_w = tk.IntVar(value=70)
        self.tcolor_h = tk.IntVar(value=59)
        self.do_trim = tk.BooleanVar(value=True)
        self.t_black = tk.IntVar(value=32)
        self.t_dark = tk.IntVar(value=96)
        self.t_light = tk.IntVar(value=180)
        self.preview_mode = tk.StringVar(value="color")  # color, gray, mirror

        self.loader: Optional[ShipLoader] = None
        self.source_frames: List[Optional[Image.Image]] = []
        self.output_frames_rgba: List[Image.Image] = []
        self.output_frames_g4: List[np.ndarray] = []
        self.hover_src = -1
        self.hover_out = -1
        self.selected_out = -1
        self._photo_refs = []
        self._scanned_objects: dict = {}  # category → list of object names

        self._build_ui()
        self._apply_theme()

        if initial_source:
            self.root.after(200, self._scan_art_root)

    # ───────────────────────────────────────────────────────────────────────
    # UI Construction
    # ───────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Main container
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True, padx=6, pady=6)

        # ── Top bar: source selection ──
        top = ttk.Frame(main)
        top.pack(fill="x", pady=(0, 4))
        self._build_source_bar(top)

        # ── Middle: split source / output previews ──
        mid = ttk.PanedWindow(main, orient="horizontal")
        mid.pack(fill="both", expand=True, pady=4)

        left_frame = ttk.Frame(mid)
        right_frame = ttk.Frame(mid)
        mid.add(left_frame, weight=2)
        mid.add(right_frame, weight=3)

        self._build_source_panel(left_frame)
        self._build_output_panel(right_frame)

        # ── Bottom: detail + settings + actions ──
        bot = ttk.Frame(main)
        bot.pack(fill="x", pady=(4, 0))
        self._build_detail_bar(bot)
        self._build_settings_bar(bot)
        self._build_action_bar(bot)

    def _build_source_bar(self, parent):
        row1 = ttk.Frame(parent)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="Art Root:").pack(side="left", padx=(0,4))
        ttk.Entry(row1, textvariable=self.art_root, width=50).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Button(row1, text="Browse", command=self._browse_source, width=8).pack(side="left", padx=2)

        row2 = ttk.Frame(parent)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="Category:").pack(side="left", padx=(0,4))
        self.cb_category = ttk.Combobox(row2, textvariable=self.category, width=12, state="readonly",
                                         values=[])
        self.cb_category.pack(side="left", padx=2)
        self.cb_category.bind("<<ComboboxSelected>>", lambda e: self._on_category_change())

        ttk.Label(row2, text="Object:").pack(side="left", padx=(12,4))
        self.cb_object = ttk.Combobox(row2, textvariable=self.object_name, width=14, state="readonly",
                                       values=[])
        self.cb_object.pack(side="left", padx=2)
        self.cb_object.bind("<<ComboboxSelected>>", lambda e: self._on_object_change())

        self.lbl_variant = ttk.Label(row2, text="Variant:")
        self.lbl_variant.pack(side="left", padx=(12,4))
        self.cb_variant = ttk.Combobox(row2, textvariable=self.variant, width=10, state="readonly",
                                        values=["standard", "ACE"])
        self.cb_variant.pack(side="left", padx=2)
        self.cb_variant.bind("<<ComboboxSelected>>", lambda e: self._on_object_change())

        self.lbl_status_top = ttk.Label(row2, text="", foreground=C_TEXT_DIM)
        self.lbl_status_top.pack(side="left", padx=8)

    def _build_source_panel(self, parent):
        ttk.Label(parent, text="SOURCE SPRITES", font=("Helvetica", 11, "bold")).pack(pady=(4,2))

        # Pitch selector
        pf = ttk.Frame(parent)
        pf.pack(fill="x", padx=4, pady=2)
        ttk.Button(pf, text="◀", width=3, command=lambda: self._change_pitch(-1)).pack(side="left")
        self.lbl_pitch = ttk.Label(pf, text="Pitch 8 (level)", width=24, anchor="center")
        self.lbl_pitch.pack(side="left", fill="x", expand=True)
        ttk.Button(pf, text="▶", width=3, command=lambda: self._change_pitch(1)).pack(side="left")

        # Pitch slider
        self.pitch_scale = ttk.Scale(parent, from_=0, to=16, orient="horizontal",
                                      variable=self.pitch_idx, command=self._on_pitch_slide)
        self.pitch_scale.pack(fill="x", padx=8, pady=2)

        # Canvas for source sprite grid (8 cols × 4 rows)
        cf = ttk.Frame(parent)
        cf.pack(fill="both", expand=True, padx=4, pady=4)

        self.src_canvas = tk.Canvas(cf, bg=C_BG2, highlightthickness=0, cursor="hand2")
        self.src_canvas.pack(fill="both", expand=True)
        self.src_canvas.bind("<Motion>", self._on_src_hover)
        self.src_canvas.bind("<Leave>", self._on_src_leave)
        self.src_canvas.bind("<Configure>", lambda e: self._draw_source())

    def _build_output_panel(self, parent):
        ttk.Label(parent, text="OUTPUT PREVIEW", font=("Helvetica", 11, "bold")).pack(pady=(4,2))

        # Preview mode selector
        mf = ttk.Frame(parent)
        mf.pack(fill="x", padx=4, pady=2)
        for val, label in [("color", "Color"), ("gray", "Grayscale"), ("mirror", "All 13×13")]:
            ttk.Radiobutton(mf, text=label, variable=self.preview_mode, value=val,
                           command=self._draw_output).pack(side="left", padx=6)

        self.lbl_outinfo = ttk.Label(mf, text="", foreground=C_TEXT_DIM)
        self.lbl_outinfo.pack(side="right", padx=4)

        # Canvas for output grid
        cf = ttk.Frame(parent)
        cf.pack(fill="both", expand=True, padx=4, pady=4)

        self.out_canvas = tk.Canvas(cf, bg=C_BG2, highlightthickness=0, cursor="hand2")
        self.out_canvas.pack(fill="both", expand=True)
        self.out_canvas.bind("<Motion>", self._on_out_hover)
        self.out_canvas.bind("<Leave>", self._on_out_leave)
        self.out_canvas.bind("<Button-1>", self._on_out_click)
        self.out_canvas.bind("<Configure>", lambda e: self._draw_output())

    def _build_detail_bar(self, parent):
        df = ttk.LabelFrame(parent, text="Detail", padding=4)
        df.pack(fill="x", pady=(0,4))

        row = ttk.Frame(df)
        row.pack(fill="x")

        # Zoomed frame preview
        self.detail_canvas = tk.Canvas(row, width=120, height=100, bg=C_BG2, highlightthickness=1,
                                       highlightbackground=C_GRID)
        self.detail_canvas.pack(side="left", padx=(0,8))

        # Info labels
        info = ttk.Frame(row)
        info.pack(side="left", fill="both", expand=True)

        self.lbl_detail1 = ttk.Label(info, text="Select a frame to inspect", foreground=C_TEXT_DIM)
        self.lbl_detail1.pack(anchor="w")
        self.lbl_detail2 = ttk.Label(info, text="", foreground=C_TEXT_DIM)
        self.lbl_detail2.pack(anchor="w")
        self.lbl_detail3 = ttk.Label(info, text="", foreground=C_TEXT_DIM)
        self.lbl_detail3.pack(anchor="w")
        self.lbl_detail4 = ttk.Label(info, text="", foreground=C_TEXT_DIM)
        self.lbl_detail4.pack(anchor="w")

    def _build_settings_bar(self, parent):
        sf = ttk.LabelFrame(parent, text="Settings", padding=4)
        sf.pack(fill="x", pady=(0,4))

        row = ttk.Frame(sf)
        row.pack(fill="x")

        ttk.Label(row, text="Thumby:").pack(side="left")
        ttk.Entry(row, textvariable=self.thumby_w, width=4).pack(side="left", padx=1)
        ttk.Label(row, text="×").pack(side="left")
        ttk.Entry(row, textvariable=self.thumby_h, width=4).pack(side="left", padx=1)

        ttk.Label(row, text="   TColor:").pack(side="left")
        ttk.Entry(row, textvariable=self.tcolor_w, width=4).pack(side="left", padx=1)
        ttk.Label(row, text="×").pack(side="left")
        ttk.Entry(row, textvariable=self.tcolor_h, width=4).pack(side="left", padx=1)

        ttk.Checkbutton(row, text="Trim", variable=self.do_trim).pack(side="left", padx=(16,4))

        ttk.Label(row, text="   Gray thresholds:").pack(side="left")
        ttk.Entry(row, textvariable=self.t_black, width=4).pack(side="left", padx=1)
        ttk.Label(row, text="/").pack(side="left")
        ttk.Entry(row, textvariable=self.t_dark, width=4).pack(side="left", padx=1)
        ttk.Label(row, text="/").pack(side="left")
        ttk.Entry(row, textvariable=self.t_light, width=4).pack(side="left", padx=1)

        ttk.Button(row, text="Refresh Preview", command=self._regenerate_output).pack(side="left", padx=(16,0))

    def _build_action_bar(self, parent):
        af = ttk.Frame(parent)
        af.pack(fill="x", pady=(0,2))

        # Output directory
        ttk.Label(af, text="Output:").pack(side="left")
        ttk.Entry(af, textvariable=self.output_dir, width=30).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(af, text="Browse", command=self._browse_output, width=8).pack(side="left", padx=2)

        ttk.Label(af, text="  Name:").pack(side="left")
        ttk.Entry(af, textvariable=self.output_name, width=16).pack(side="left", padx=4)

        ttk.Button(af, text="Convert Thumby", command=lambda: self._convert("thumby"),
                   style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(af, text="Convert ThumbyColor", command=lambda: self._convert("tcolor"),
                   style="Accent.TButton").pack(side="left", padx=4)
        ttk.Button(af, text="Convert Both", command=lambda: self._convert("both"),
                   style="Accent.TButton").pack(side="left", padx=4)

        # Status bar
        self.status_frame = ttk.Frame(parent)
        self.status_frame.pack(fill="x")
        self.lbl_status = ttk.Label(self.status_frame, text="Ready — select a source directory and load an asset.",
                                     foreground=C_TEXT_DIM)
        self.lbl_status.pack(side="left")

        self.progress = ttk.Progressbar(self.status_frame, mode="determinate", length=200)
        self.progress.pack(side="right", padx=4)

    def _apply_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=C_BG, foreground=C_TEXT, fieldbackground=C_BG2)
        style.configure("TFrame", background=C_BG)
        style.configure("TLabel", background=C_BG, foreground=C_TEXT)
        style.configure("TLabelframe", background=C_BG, foreground=C_TEXT)
        style.configure("TLabelframe.Label", background=C_BG, foreground=C_ACCENT)
        style.configure("TButton", background=C_BG3, foreground=C_TEXT, padding=4)
        style.map("TButton", background=[("active", C_ACCENT2)])
        style.configure("Accent.TButton", background=C_ACCENT, foreground="white", padding=6)
        style.map("Accent.TButton", background=[("active", "#c83050")])
        style.configure("TEntry", fieldbackground=C_BG2, foreground=C_TEXT)
        style.configure("TCombobox", fieldbackground=C_BG2, foreground=C_TEXT)
        style.configure("TCheckbutton", background=C_BG, foreground=C_TEXT)
        style.configure("TRadiobutton", background=C_BG, foreground=C_TEXT)
        style.configure("TScale", background=C_BG, troughcolor=C_BG2)
        style.configure("TPanedwindow", background=C_BG)
        style.configure("Horizontal.TProgressbar", background=C_OK, troughcolor=C_BG2)

    # ───────────────────────────────────────────────────────────────────────
    # Event Handlers
    # ───────────────────────────────────────────────────────────────────────

    def _browse_source(self):
        d = filedialog.askdirectory(title="Select WCUnity Art directory")
        if d:
            self.art_root.set(d)
            self._scan_art_root()

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self.output_dir.set(d)

    def _scan_art_root(self):
        """Scan the Art root directory and populate category/object dropdowns."""
        root = Path(self.art_root.get())
        if not root.is_dir():
            self._set_status("Art root directory not found.", error=True)
            return

        self._scanned_objects.clear()
        found_categories = []

        for cat_name, cat_info in WC_CATEGORIES.items():
            cat_path = root / cat_info["path"]
            if not cat_path.is_dir():
                continue

            objects = []
            if cat_info["asset_type"] == "ship":
                # Ships: each subfolder is a ship
                for sub in sorted(cat_path.iterdir()):
                    if sub.is_dir():
                        objects.append(sub.name)
            else:
                # Other categories: list PNG files and subfolders
                for item in sorted(cat_path.iterdir()):
                    if item.is_dir():
                        objects.append(item.name)
                    elif item.suffix.lower() == ".png":
                        objects.append(item.name)  # keep full filename for non-ships

            if objects:
                self._scanned_objects[cat_name] = objects
                found_categories.append(cat_name)

        if not found_categories:
            self._set_status("No recognized categories found in Art root.", error=True)
            return

        self.cb_category.configure(values=found_categories)
        # Auto-select Ships if available
        if "Ships" in found_categories:
            self.category.set("Ships")
        else:
            self.category.set(found_categories[0])
        self._on_category_change()
        self._set_status(f"Found {len(found_categories)} categories in Art root.")

    def _on_category_change(self):
        """Populate the object dropdown based on the selected category."""
        cat = self.category.get()
        objects = self._scanned_objects.get(cat, [])
        self.cb_object.configure(values=objects)

        cat_info = WC_CATEGORIES.get(cat, {})
        is_ship = cat_info.get("asset_type") == "ship"

        # Show/hide variant selector
        self.cb_variant.configure(state="readonly" if is_ship else "disabled")
        self.lbl_variant.configure(foreground=C_TEXT if is_ship else C_TEXT_DIM)

        # Update default sizes
        atype = cat_info.get("asset_type", "")
        size_key = {"ship": "enemy", "debris": "asteroid", "explosion": "explode"}.get(atype, atype)
        tw, th = THUMBY_SIZES.get(size_key, (32, 32))
        cw, ch = TCOLOR_SIZES.get(size_key, (56, 56))
        self.thumby_w.set(tw); self.thumby_h.set(th)
        self.tcolor_w.set(cw); self.tcolor_h.set(ch)

        # Auto-select first object
        if objects:
            self.object_name.set(objects[0])
            self._on_object_change()
        else:
            self.object_name.set("")

    def _on_object_change(self):
        """Load the selected object when selection changes."""
        self._load_asset()

    def _change_pitch(self, delta):
        new = max(0, min(16, self.pitch_idx.get() + delta))
        self.pitch_idx.set(new)
        self._update_pitch_display()
        self._load_source_frames()
        self._draw_source()

    def _on_pitch_slide(self, val):
        self.pitch_idx.set(int(float(val)))
        self._update_pitch_display()
        self._load_source_frames()
        self._draw_source()

    def _update_pitch_display(self):
        p = self.pitch_idx.get()
        elev = (8 - p) * 11.25
        if p == 8:
            desc = "level"
        elif p < 8:
            desc = f"{abs(elev):.1f}° from above"
        else:
            desc = f"{abs(elev):.1f}° from below"
        self.lbl_pitch.config(text=f"Pitch {p} ({desc})")

    def _on_src_hover(self, event):
        idx = self._src_cell_at(event.x, event.y)
        if idx != self.hover_src:
            self.hover_src = idx
            self._draw_source()
            if idx >= 0:
                yaw_deg = idx * 11.25
                self.lbl_detail1.config(text=f"Source frame: yaw {idx} ({yaw_deg:.1f}° from rear)")
            else:
                self.lbl_detail1.config(text="")

    def _on_src_leave(self, event):
        self.hover_src = -1
        self._draw_source()

    def _on_out_hover(self, event):
        idx = self._out_cell_at(event.x, event.y)
        if idx != self.hover_out:
            self.hover_out = idx
            self._draw_output()
            self._update_detail_for_output(idx)

    def _on_out_leave(self, event):
        self.hover_out = -1
        self._draw_output()

    def _on_out_click(self, event):
        idx = self._out_cell_at(event.x, event.y)
        if idx >= 0:
            self.selected_out = idx
            self._draw_output()
            self._show_detail(idx)

    def _update_detail_for_output(self, idx):
        mode = self.preview_mode.get()
        if mode == "mirror":
            cols = 13
        else:
            cols = 7

        if idx < 0:
            self.lbl_detail2.config(text="")
            self.lbl_detail3.config(text="")
            return

        if mode == "mirror":
            x_orient = idx % 13
            y_orient = idx // 13
            yaw_deg = x_orient * 15 - 90
            pitch_deg = y_orient * 15 - 90

            frame_idx = TC_X_INDEX[x_orient] - 21 + ((TC_Y_SHIFT[y_orient] + 21) // 7) * 7
            mx = TC_X_MIRROR[x_orient]
            my = TC_Y_MIRROR[y_orient]
            self.lbl_detail2.config(
                text=f"Orientation: yaw {yaw_deg:+d}°  pitch {pitch_deg:+d}°")
            self.lbl_detail3.config(
                text=f"Stored frame #{frame_idx}  mirrorX={mx}  mirrorY={my}")
        else:
            col = idx % 7
            row = idx // 7
            wc_yaw = STORED_COL_YAW[col]
            wc_pitch = STORED_ROW_PITCH[row]
            yaw_deg = wc_yaw * WC_YAW_STEP
            pitch_deg = (8 - wc_pitch) * WC_PITCH_STEP
            self.lbl_detail2.config(
                text=f"Grid [{row},{col}]  WC yaw {wc_yaw} ({yaw_deg:.1f}°)  pitch {wc_pitch} ({pitch_deg:+.1f}°)")
            self.lbl_detail3.config(
                text=f"Source: sheet {wc_pitch}, sub-frame {wc_yaw}  (flipped top-bottom)")

    def _show_detail(self, idx):
        mode = self.preview_mode.get()
        self.detail_canvas.delete("all")

        img = None
        if mode == "mirror":
            img = self._get_mirror_frame(idx)
        elif mode == "gray":
            if idx < len(self.output_frames_g4):
                img = gray4_to_rgba(self.output_frames_g4[idx])
        else:
            if idx < len(self.output_frames_rgba):
                img = self.output_frames_rgba[idx]

        if img is None:
            return

        # Scale to fit detail canvas
        cw = self.detail_canvas.winfo_width() or 120
        ch = self.detail_canvas.winfo_height() or 100
        scale = min(cw / img.width, ch / img.height)
        scale = max(1, int(scale))
        zoomed = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)

        photo = ImageTk.PhotoImage(zoomed)
        self._photo_refs.append(photo)
        self.detail_canvas.create_image(cw//2, ch//2, image=photo, anchor="center")

        self._update_detail_for_output(idx)
        tw, th = self.thumby_w.get(), self.thumby_h.get()
        cw2, ch2 = self.tcolor_w.get(), self.tcolor_h.get()
        self.lbl_detail4.config(text=f"Thumby: {tw}×{th}   TColor: {cw2}×{ch2}")

    # ───────────────────────────────────────────────────────────────────────
    # Asset Loading
    # ───────────────────────────────────────────────────────────────────────

    def _load_asset(self):
        root = Path(self.art_root.get())
        cat = self.category.get()
        obj = self.object_name.get()

        if not root.is_dir() or not cat or not obj:
            self._set_status("Please select Art root, category, and object.", error=True)
            return

        cat_info = WC_CATEGORIES.get(cat, {})
        atype = cat_info.get("asset_type", "")

        if atype == "ship":
            self._load_ship()
        else:
            self._load_generic()

    def _load_ship(self):
        root = Path(self.art_root.get())
        cat_info = WC_CATEGORIES.get(self.category.get(), {})
        obj = self.object_name.get()
        var = self.variant.get()

        ship_dir = root / cat_info.get("path", "Ships") / obj

        if obj not in SHIPS:
            self._set_status(f"Unknown ship '{obj}' — not in SHIPS database.", error=True)
            return

        self.loader = ShipLoader(str(ship_dir), obj, var)
        available = self.loader.available_pitches()

        if not available:
            prefix = SHIPS.get(obj, {}).get("prefix", obj)
            self._set_status(f"No sprite sheets found! Expected {prefix}0..16.png in {ship_dir}", error=True)
            return

        # Update output name
        name = obj.lower()
        if var.upper() == "ACE":
            name += "_ace"
        self.output_name.set(name)

        self._set_status(f"Loaded {obj} ({var}) — {len(available)}/{WC_PITCH_FILES} pitch files")
        self.lbl_status_top.config(text=f"{obj} ({var}): {len(available)} pitch files found")

        # Set pitch to level (8) or nearest available
        if 8 in available:
            self.pitch_idx.set(8)
        else:
            self.pitch_idx.set(available[len(available)//2])

        self._update_pitch_display()
        self._load_source_frames()
        self._draw_source()
        self._regenerate_output()

    def _load_generic(self):
        self._set_status(f"Generic asset loading — use the source directory with PNG files")
        self.source_frames.clear()
        self.output_frames_rgba.clear()
        self.output_frames_g4.clear()
        self._draw_source()
        self._draw_output()

    def _load_source_frames(self):
        """Load all 32 yaw frames at the current pitch level."""
        self.source_frames.clear()
        if self.loader is None:
            return

        pitch = self.pitch_idx.get()
        for yaw in range(WC_YAW_FRAMES):
            frame = self.loader.extract(yaw, pitch)
            self.source_frames.append(frame)

    # ───────────────────────────────────────────────────────────────────────
    # Output Generation
    # ───────────────────────────────────────────────────────────────────────

    def _regenerate_output(self):
        """Generate all 49 output frames from the loaded source."""
        if self.loader is None:
            return

        self._set_status("Generating preview...")
        self.progress["value"] = 0
        self.root.update_idletasks()

        tw = self.thumby_w.get()
        th = self.thumby_h.get()
        cw = self.tcolor_w.get()
        ch = self.tcolor_h.get()

        available = self.loader.available_pitches()
        self.output_frames_rgba.clear()
        self.output_frames_g4.clear()

        for row in range(7):
            for col in range(7):
                wc_yaw = STORED_COL_YAW[col]
                wc_pitch = STORED_ROW_PITCH[row]

                if wc_pitch not in available:
                    wc_pitch = min(available, key=lambda p: abs(p - wc_pitch))

                subframe = self.loader.extract(wc_yaw, wc_pitch)

                if subframe is None:
                    subframe = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
                else:
                    subframe = flip_for_pitch(subframe, wc_pitch)
                    if self.do_trim.get():
                        subframe = trim_transparent(subframe)

                # Generate color version (at ThumbyColor resolution for best preview)
                color_frame = resize_contain(subframe, cw, ch)
                self.output_frames_rgba.append(color_frame)

                # Generate grayscale version (at Thumby resolution)
                gray_frame = resize_contain(subframe, tw, th)
                g4 = to_gray4(gray_frame, self.t_black.get(), self.t_dark.get(), self.t_light.get())
                self.output_frames_g4.append(g4)

                self.progress["value"] = (row * 7 + col + 1) / 49 * 100
                self.root.update_idletasks()

        self.progress["value"] = 100
        self._set_status(f"Preview ready — 49 frames generated")
        self._draw_output()

    def _get_mirror_frame(self, mirror_idx: int) -> Optional[Image.Image]:
        """Get a frame from the 13×13 mirror grid."""
        x_orient = mirror_idx % 13
        y_orient = mirror_idx // 13

        col = TC_X_INDEX[x_orient] - 21
        row = (TC_Y_SHIFT[y_orient] + 21) // 7
        stored_idx = row * 7 + col

        mode = self.preview_mode.get()
        if mode == "gray" or mode == "mirror":
            if stored_idx < len(self.output_frames_g4):
                img = gray4_to_rgba(self.output_frames_g4[stored_idx])
            else:
                return None
        else:
            if stored_idx < len(self.output_frames_rgba):
                img = self.output_frames_rgba[stored_idx].copy()
            else:
                return None

        if TC_X_MIRROR[x_orient]:
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if TC_Y_MIRROR[y_orient]:
            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        return img

    # ───────────────────────────────────────────────────────────────────────
    # Canvas Drawing
    # ───────────────────────────────────────────────────────────────────────

    def _draw_source(self):
        canvas = self.src_canvas
        canvas.delete("all")
        self._photo_refs = [ref for ref in self._photo_refs if ref is not None]

        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        cols, rows = 8, 4
        pad = 2
        cell_w = (cw - pad * (cols + 1)) // cols
        cell_h = (ch - pad * (rows + 1)) // rows
        if cell_w < 4 or cell_h < 4:
            return

        for i in range(min(32, len(self.source_frames))):
            c = i % cols
            r = i // cols
            x0 = pad + c * (cell_w + pad)
            y0 = pad + r * (cell_h + pad)

            # Cell background
            fill = C_BG3 if i == self.hover_src else C_BG2
            canvas.create_rectangle(x0, y0, x0+cell_w, y0+cell_h, fill=fill, outline=C_GRID)

            frame = self.source_frames[i]
            if frame is not None:
                # Resize to fit cell
                thumb = resize_contain(frame, cell_w - 4, cell_h - 4)
                photo = ImageTk.PhotoImage(thumb)
                self._photo_refs.append(photo)
                canvas.create_image(x0 + cell_w//2, y0 + cell_h//2, image=photo, anchor="center")

            # Yaw label
            yaw_deg = i * 11.25
            canvas.create_text(x0 + 3, y0 + 3, text=f"{i}", fill=C_TEXT_DIM,
                             anchor="nw", font=("Helvetica", 8))

        # Highlight source frames used by output grid
        if self.hover_out >= 0 and self.preview_mode.get() != "mirror":
            col = self.hover_out % 7
            row = self.hover_out // 7
            wc_yaw = STORED_COL_YAW[col]
            # Highlight the corresponding source cell
            if 0 <= wc_yaw < 32:
                c = wc_yaw % cols
                r = wc_yaw // cols
                x0 = pad + c * (cell_w + pad)
                y0 = pad + r * (cell_h + pad)
                canvas.create_rectangle(x0-1, y0-1, x0+cell_w+1, y0+cell_h+1,
                                       outline=C_SELECT, width=2)

        # Store layout for hit testing
        self._src_layout = (cols, rows, pad, cell_w, cell_h)

    def _draw_output(self):
        canvas = self.out_canvas
        canvas.delete("all")

        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        mode = self.preview_mode.get()
        if mode == "mirror":
            cols, rows = 13, 13
            frames = [self._get_mirror_frame(i) for i in range(169)]
        else:
            cols, rows = 7, 7
            if mode == "gray":
                frames = [gray4_to_rgba(g4) for g4 in self.output_frames_g4] if self.output_frames_g4 else []
            else:
                frames = list(self.output_frames_rgba)

        if not frames:
            canvas.create_text(cw//2, ch//2, text="Load an asset to see preview",
                             fill=C_TEXT_DIM, font=("Helvetica", 12))
            return

        pad = 2
        cell_w = (cw - pad * (cols + 1)) // cols
        cell_h = (ch - pad * (rows + 1)) // rows
        if cell_w < 4 or cell_h < 4:
            return

        for i, frame in enumerate(frames):
            c = i % cols
            r = i // cols
            x0 = pad + c * (cell_w + pad)
            y0 = pad + r * (cell_h + pad)

            is_hover = (i == self.hover_out)
            is_selected = (i == self.selected_out)
            fill = C_BG3 if is_hover else C_BG2
            outline = C_SELECT if is_selected else (C_ACCENT if is_hover else C_GRID)
            w = 2 if (is_hover or is_selected) else 1

            canvas.create_rectangle(x0, y0, x0+cell_w, y0+cell_h, fill=fill, outline=outline, width=w)

            if frame is not None:
                thumb = resize_contain(frame, cell_w - 2, cell_h - 2)
                photo = ImageTk.PhotoImage(thumb)
                self._photo_refs.append(photo)
                canvas.create_image(x0 + cell_w//2, y0 + cell_h//2, image=photo, anchor="center")

        # Axis labels
        if mode != "mirror":
            for col in range(7):
                x = pad + col * (cell_w + pad) + cell_w // 2
                yaw = STORED_COL_YAW[col]
                canvas.create_text(x, ch - 2, text=f"y{yaw}", fill=C_TEXT_DIM,
                                 anchor="s", font=("Helvetica", 7))
            for row in range(7):
                y = pad + row * (cell_h + pad) + cell_h // 2
                pitch = STORED_ROW_PITCH[row]
                canvas.create_text(2, y, text=f"p{pitch}", fill=C_TEXT_DIM,
                                 anchor="w", font=("Helvetica", 7))

        total = len(frames)
        self.lbl_outinfo.config(text=f"{cols}×{rows} = {total} frames")
        self._out_layout = (cols, rows, pad, cell_w, cell_h)

    def _src_cell_at(self, mx, my) -> int:
        if not hasattr(self, '_src_layout'):
            return -1
        cols, rows, pad, cw, ch = self._src_layout
        for i in range(cols * rows):
            c = i % cols; r = i // cols
            x0 = pad + c * (cw + pad)
            y0 = pad + r * (ch + pad)
            if x0 <= mx <= x0 + cw and y0 <= my <= y0 + ch:
                return i
        return -1

    def _out_cell_at(self, mx, my) -> int:
        if not hasattr(self, '_out_layout'):
            return -1
        cols, rows, pad, cw, ch = self._out_layout
        for i in range(cols * rows):
            c = i % cols; r = i // cols
            x0 = pad + c * (cw + pad)
            y0 = pad + r * (ch + pad)
            if x0 <= mx <= x0 + cw and y0 <= my <= y0 + ch:
                return i
        return -1

    # ───────────────────────────────────────────────────────────────────────
    # Conversion
    # ───────────────────────────────────────────────────────────────────────

    def _convert(self, platform: str):
        if not self.output_frames_rgba:
            self._set_status("No frames loaded — load an asset first!", error=True)
            return

        out_dir = self.output_dir.get()
        if not out_dir or not os.path.isdir(out_dir):
            self._set_status("Please select a valid output directory!", error=True)
            return

        name = self.output_name.get() or "sprite"
        tw = self.thumby_w.get()
        th = self.thumby_h.get()
        cw = self.tcolor_w.get()
        ch = self.tcolor_h.get()

        def do_convert():
            try:
                results = []

                if platform in ("thumby", "both"):
                    self._set_status_safe("Converting for Thumby...")
                    self._progress_safe(10)

                    # Re-generate at correct Thumby resolution
                    frames_g4 = []
                    available = self.loader.available_pitches() if self.loader else []

                    for row in range(7):
                        for col in range(7):
                            wc_yaw = STORED_COL_YAW[col]
                            wc_pitch = STORED_ROW_PITCH[row]
                            if available and wc_pitch not in available:
                                wc_pitch = min(available, key=lambda p: abs(p - wc_pitch))

                            subframe = self.loader.extract(wc_yaw, wc_pitch) if self.loader else None
                            if subframe is None:
                                subframe = Image.new("RGBA", (tw, th), (0,0,0,0))
                            else:
                                subframe = flip_for_pitch(subframe, wc_pitch)
                                if self.do_trim.get():
                                    subframe = trim_transparent(subframe)

                            resized = resize_contain(subframe, tw, th)
                            g4 = to_gray4(resized, self.t_black.get(), self.t_dark.get(), self.t_light.get())
                            frames_g4.append(g4)
                            self._progress_safe(10 + (row*7+col+1) / 49 * 40)

                    base = os.path.join(out_dir, f"{name}_{tw}_{th}")
                    bp, sp, sz = write_thumby(frames_g4, tw, th, base)
                    results.append(f"Thumby: {os.path.basename(bp)} + {os.path.basename(sp)} ({sz} bytes each)")

                if platform in ("tcolor", "both"):
                    self._set_status_safe("Converting for ThumbyColor...")
                    self._progress_safe(55)

                    frames_565 = []
                    available = self.loader.available_pitches() if self.loader else []

                    for row in range(7):
                        for col in range(7):
                            wc_yaw = STORED_COL_YAW[col]
                            wc_pitch = STORED_ROW_PITCH[row]
                            if available and wc_pitch not in available:
                                wc_pitch = min(available, key=lambda p: abs(p - wc_pitch))

                            subframe = self.loader.extract(wc_yaw, wc_pitch) if self.loader else None
                            if subframe is None:
                                subframe = Image.new("RGBA", (cw, ch), (0,0,0,0))
                            else:
                                subframe = flip_for_pitch(subframe, wc_pitch)
                                if self.do_trim.get():
                                    subframe = trim_transparent(subframe)

                            resized = resize_contain(subframe, cw, ch)
                            rgb565 = to_rgb565(resized)
                            frames_565.append(rgb565)
                            self._progress_safe(55 + (row*7+col+1) / 49 * 40)

                    base = os.path.join(out_dir, f"{name}_{cw}_{ch}")
                    cp, csz = write_tcolor(frames_565, cw, ch, base)
                    results.append(f"TColor: {os.path.basename(cp)} ({csz} bytes)")

                self._progress_safe(100)
                msg = "Conversion complete!  " + "  |  ".join(results)
                self._set_status_safe(msg)

                self.root.after(0, lambda: messagebox.showinfo("Conversion Complete",
                    f"Files saved to:\n{out_dir}\n\n" + "\n".join(results)))

            except Exception as e:
                self._set_status_safe(f"ERROR: {e}", error=True)
                self.root.after(0, lambda: messagebox.showerror("Conversion Error",
                    f"An error occurred:\n\n{traceback.format_exc()}"))

        threading.Thread(target=do_convert, daemon=True).start()

    # ───────────────────────────────────────────────────────────────────────
    # Status & Progress (thread-safe)
    # ───────────────────────────────────────────────────────────────────────

    def _set_status(self, text, error=False):
        color = C_ACCENT if error else C_TEXT_DIM
        self.lbl_status.config(text=text, foreground=color)

    def _set_status_safe(self, text, error=False):
        self.root.after(0, lambda: self._set_status(text, error))

    def _progress_safe(self, value):
        self.root.after(0, lambda: self.progress.configure(value=value))


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--source", default="", help="Initial source directory")
    args = parser.parse_args()

    root = tk.Tk()

    # Center on screen
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w, h = APP_MIN_SIZE
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    app = WC2ThumbApp(root, initial_source=args.source)
    root.mainloop()


if __name__ == "__main__":
    main()
