#!/usr/bin/env python3
"""
WC2Thumb — Wing Commander Unity → ThumbCommander Sprite Converter
=================================================================

Converts sprite sheets from Howard Day's WCUnity project into the binary
sprite formats used by ThumbCommander (Thumby and ThumbyColor).

Supported output formats:
  - Thumby:      BIT.bin + SHD.bin  (4-level grayscale, column-major page layout)
  - ThumbyColor: COL.bin            (RGB565, 8-byte header)

Supported asset types:
  - ships      : 17 pitch files × 32 yaw sub-frames → 7×7 orientation grid (49 frames)
  - debris     : single PNG → 13-frame rotation strip
  - explosions : animation sequence → N-frame strip
  - cockpits   : single PNG → single frame
  - weapons    : single PNG → single frame
  - backgrounds: single PNG → single frame (tiled/cropped)
  - custom     : user-defined frame extraction

Usage:
  python wc2thumb.py --help
  python wc2thumb.py ship Dralthi --source-dir ./WCUnity/Assets/Art/Ships/Dralthi
  python wc2thumb.py ship Dralthi --source-dir ./Ships/Dralthi --variant ACE
  python wc2thumb.py ship Dralthi --source-dir ./Ships/Dralthi --platform both --preview
  python wc2thumb.py debris --source ./Debris01.png --frames 13
  python wc2thumb.py explosion --source-dir ./VFX --pattern "Explode_{frame:04d}.png"

Requirements:
  pip install Pillow numpy
"""

import argparse
import json
import math
import os
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    import numpy as np
except ImportError:
    print("ERROR: This tool requires Pillow and numpy.")
    print("  pip install Pillow numpy")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants & Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# ThumbCommander sprite resolutions
THUMBY_ENEMY_SIZE     = (40, 34)    # Standard enemy sprite
THUMBY_ASTEROID_SIZE  = (32, 27)    # Asteroid sprite
THUMBY_EXPLODE_SIZE   = (32, 31)    # Explosion sprite
TCOLOR_ENEMY_SIZE     = (70, 59)    # ThumbyColor enemy
TCOLOR_ASTEROID_SIZE  = (56, 47)    # ThumbyColor asteroid
TCOLOR_EXPLODE_SIZE   = (56, 54)    # ThumbyColor explosion

# ThumbCommander orientation system
# 13 orientations per axis, 7 unique stored frames per axis, rest via mirroring
TC_ORIENTATION = [-512, -427, -341, -256, -171, -85, 0, 85, 171, 256, 341, 427, 512]
TC_X_INDEX     = [24, 25, 26, 27, 26, 25, 24, 23, 22, 21, 22, 23, 24]
TC_X_MIRROR    = [False, False, False, False, True, True, True, True, True, False, False, False, False]
TC_Y_SHIFT     = [0, -7, -14, -21, -14, -7, 0, 7, 14, 21, 14, 7, 0]
TC_Y_MIRROR    = [True, False, False, False, False, False, True, True, True, True, True, True, True]

# WCUnity sprite sheet layout
WC_YAW_FRAMES   = 32   # horizontal rotation frames per pitch file
WC_PITCH_FILES   = 17   # number of pitch (elevation) files
WC_SHEET_COLS    = 8    # sub-frame columns per sheet
WC_SHEET_ROWS    = 4    # sub-frame rows per sheet
WC_YAW_STEP      = 360.0 / WC_YAW_FRAMES   # 11.25° per yaw step
WC_PITCH_STEP    = 180.0 / (WC_PITCH_FILES - 1)  # 11.25° per pitch step

# WCUnity per-ship sprite sizes (width×height of each sub-frame)
WC_SHIP_SIZES = {
    "Hornet":    (256, 256),
    "Dralthi":   (256, 256),
    "Krant":     (256, 256),
    "Salthi":    (128, 128),
    "Scimitar":  (300, 300),
    "Strakha":   (300, 300),
    "Talon":     (256, 256),
    "Valtar":    (256, 256),
    "Grikath":   (256, 256),
}

# WCUnity file naming patterns
WC_SHIP_PREFIXES = {
    "Hornet":    "ArneHornet",
    "Dralthi":   "HowieDralthi",
    "Krant":     "HowieKrant",
    "Salthi":    "HowieSalthi",
    "Scimitar":  "HowieScimitar",
    "Strakha":   "HowieStrakha",
    "Talon":     "HowieTalon",
    "Valtar":    "HowieFirekkan",
    "Grikath":   "HowieGrikath",
}

WC_SHIP_ACE_PREFIXES = {
    "Hornet":    "ArneHornetAce",
    "Dralthi":   "HowieDralthiACE",
    "Salthi":    "HowieSalthiACE",
    "Strakha":   "HowieStrakhaAce",
}

# 4-level grayscale palette for Thumby
# Index: 0=black, 1=white, 2=darkgray, 3=lightgray
GRAY4_PALETTE = [0, 255, 85, 170]


# ═══════════════════════════════════════════════════════════════════════════════
# Angle Mapping: WCUnity ↔ ThumbCommander
# ═══════════════════════════════════════════════════════════════════════════════

def tc_orient_to_degrees(orient_idx: int) -> float:
    """Convert ThumbCommander orientation index (0-12) to degrees."""
    return TC_ORIENTATION[orient_idx] * 90.0 / 512.0


def build_stored_frame_angles():
    """
    Determine the viewing angle each stored frame (7×7 grid) represents.

    Returns list of 49 tuples: (yaw_degrees, pitch_degrees)
    where yaw is horizontal rotation and pitch is vertical tilt.

    ThumbCommander stores 7 columns × 7 rows = 49 frames.
    The remaining orientations (13×13 = 169 total) are obtained via mirroring.

    For each column/row, we find the orientation that maps to it WITHOUT mirroring
    (the "canonical" angle), which tells us what the stored frame depicts.
    """

    # ThumbCommander's orientation system maps 13 game orientations to 7 stored
    # frames per axis, reusing frames with mirroring. Multiple game angles may
    # share a single stored frame (e.g., -60° and -30° pitch both use row 1).
    #
    # For the conversion, we want each stored frame position to show a DISTINCT
    # viewing angle that gives good visual variety. We use:
    #   - Column yaw: based on the PRIMARY non-mirrored orientation per column
    #   - Row pitch: evenly distributed from -45° to +45° in 15° steps
    #     (this gives 7 distinct pitch levels, matching the WCUnity data range)

    # Column yaw angles: use the primary (first non-mirrored) orientation
    # Col 0: orient 9 (+45°) — 3/4 rear-left view
    # Col 1: orient 10 (+60°) — near-side left
    # Col 2: orient 11 (+75°) — almost left profile
    # Col 3: orient 0/12 (±90°) — full side profile
    # Col 4: orient 1 (-75°) — almost right profile
    # Col 5: orient 2 (-60°) — near-side right
    # Col 6: orient 3 (-45°) — 3/4 rear-right view
    col_angles = [45.0, 60.0, 75.0, 90.0, -75.0, -60.0, -45.0]

    # Row pitch angles: evenly distributed for maximum visual variety
    # Row 0: looking from above (top of ship visible)
    # Row 3: level view (combat standard)
    # Row 6: looking from below (bottom of ship visible)
    row_angles = [-45.0, -30.0, -15.0, 0.0, 15.0, 30.0, 45.0]

    # Build the full 7×7 angle grid
    angles = []
    for row in range(7):
        for col in range(7):
            angles.append((col_angles[col], row_angles[row]))

    return angles, col_angles, row_angles


def tc_yaw_to_wc_yaw(tc_yaw_deg: float) -> int:
    """
    Convert ThumbCommander yaw (degrees) to WCUnity yaw frame index (0-31).

    ThumbCommander yaw: angle of ship relative to player's view direction
      - Positive = ship turned right (player sees left side)
      - Negative = ship turned left (player sees right side)
      - 0° = head-on or tail (depending on context)
      - ±90° = side view

    WCUnity yaw: frame index in sprite sheet
      - 0 = rear view (engines/tail)
      - 8 = left/port side
      - 16 = front view (nose)
      - 24 = right/starboard side

    The mapping: ThumbCommander's "orientation" is the ship's heading offset.
    When TC orient = -90° (orient 0), the ship faces 90° left of the player,
    meaning the player sees the ship's RIGHT side.

    TC yaw  →  What player sees    →  WC yaw frame
    -90°    →  right side of ship  →  24 (right/starboard)
    -45°    →  3/4 rear-right      →  28 (between right and rear)
     0°     →  rear (tail)         →  0  (rear)
    +45°    →  3/4 rear-left       →  4  (between rear and left)
    +90°    →  left side of ship   →  8  (left/port)
    """
    # TC: -90..+90 maps to player seeing right..rear..left side
    # WC: 0=rear, 8=left, 16=front, 24=right (counterclockwise looking down)
    # TC -90° (right side) = WC 24, TC 0° (rear) = WC 0, TC +90° (left) = WC 8
    # Linear: wc_angle = (tc_yaw + 90) * 8/90 + 24, wrapped mod 32... but let's be precise:
    # TC yaw in degrees → WC yaw in degrees from rear: wc_deg = -(tc_yaw) mapped to 0..360
    # Actually: TC +90° = WC left (90° CCW from rear) = WC frame 8
    #           TC -90° = WC right (270° CCW from rear) = WC frame 24
    #           TC 0° = WC rear = WC frame 0
    # So: wc_frame = (tc_yaw * 8 / 90) mod 32... let's verify:
    # tc=+90 → 8, tc=-90 → -8 mod 32 = 24, tc=0 → 0. Correct!

    wc_frame = (tc_yaw_deg / WC_YAW_STEP) % WC_YAW_FRAMES
    return int(round(wc_frame)) % WC_YAW_FRAMES


def tc_pitch_to_wc_pitch(tc_pitch_deg: float) -> int:
    """
    Convert ThumbCommander pitch (degrees) to WCUnity pitch file index (0-16).

    WCUnity: file 0 = top-down (+90°), file 8 = level (0°), file 16 = bottom-up (-90°)
    ThumbCommander: -45° to +45° stored pitch range (rows 0-6)

    TC pitch → WC pitch file:
      TC -45° (looking down at ship) → WC file ~4 (moderately from above)
      TC  0°  (level)                → WC file 8  (level)
      TC +45° (looking up at ship)   → WC file ~12 (moderately from below)
    """
    # WC: file = 8 - (pitch_deg / 11.25), where positive pitch = looking from above
    # TC: negative pitch = looking from above (top of ship visible)
    # So: wc_file = 8 + (tc_pitch / 11.25)
    # tc=-45 → 8 + (-45/11.25) = 8 - 4 = 4, tc=0 → 8, tc=+45 → 12. Correct!
    wc_file = 8.0 + (tc_pitch_deg / WC_PITCH_STEP)
    return max(0, min(WC_PITCH_FILES - 1, int(round(wc_file))))


# ═══════════════════════════════════════════════════════════════════════════════
# WCUnity Asset Loading
# ═══════════════════════════════════════════════════════════════════════════════

class WCUnityShipLoader:
    """Loads and extracts sub-frames from WCUnity ship sprite sheets."""

    def __init__(self, source_dir: str, ship_name: str, variant: str = "standard"):
        self.source_dir = Path(source_dir)
        self.ship_name = ship_name
        self.variant = variant

        # Determine file prefix
        if variant.upper() == "ACE" and ship_name in WC_SHIP_ACE_PREFIXES:
            self.prefix = WC_SHIP_ACE_PREFIXES[ship_name]
        elif ship_name in WC_SHIP_PREFIXES:
            self.prefix = WC_SHIP_PREFIXES[ship_name]
        else:
            # Custom prefix - try to auto-detect
            self.prefix = ship_name

        # Per-frame size
        self.frame_size = WC_SHIP_SIZES.get(ship_name, (256, 256))

        # Cache loaded sheets
        self._sheet_cache = {}

    def _find_sheet_file(self, pitch_idx: int) -> Optional[Path]:
        """Find the sprite sheet PNG for a given pitch index."""
        candidates = [
            self.source_dir / f"{self.prefix}{pitch_idx}.png",
            self.source_dir / f"{self.prefix}_{pitch_idx}.png",
            self.source_dir / f"{self.prefix}{pitch_idx:02d}.png",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def _load_sheet(self, pitch_idx: int) -> Optional[Image.Image]:
        """Load and cache a sprite sheet."""
        if pitch_idx in self._sheet_cache:
            return self._sheet_cache[pitch_idx]

        path = self._find_sheet_file(pitch_idx)
        if path is None:
            print(f"  WARNING: Sheet not found for pitch {pitch_idx} "
                  f"(tried {self.prefix}{pitch_idx}.png)")
            return None

        img = Image.open(path).convert("RGBA")
        self._sheet_cache[pitch_idx] = img
        return img

    def extract_subframe(self, yaw_idx: int, pitch_idx: int) -> Optional[Image.Image]:
        """
        Extract a single sub-frame from the sprite sheets.

        Args:
            yaw_idx: WCUnity yaw index (0-31)
            pitch_idx: WCUnity pitch file index (0-16)

        Returns:
            RGBA PIL Image of the sub-frame, or None if not found.
        """
        sheet = self._load_sheet(pitch_idx)
        if sheet is None:
            return None

        fw, fh = self.frame_size
        col = yaw_idx % WC_SHEET_COLS
        row = yaw_idx // WC_SHEET_COLS

        x0 = col * fw
        y0 = row * fh
        x1 = x0 + fw
        y1 = y0 + fh

        # Verify bounds
        if x1 > sheet.width or y1 > sheet.height:
            print(f"  WARNING: Sub-frame ({yaw_idx},{pitch_idx}) out of bounds: "
                  f"need ({x1},{y1}), sheet is ({sheet.width},{sheet.height})")
            return None

        return sheet.crop((x0, y0, x1, y1))

    def get_available_pitches(self) -> list:
        """List which pitch files are available."""
        available = []
        for i in range(WC_PITCH_FILES):
            if self._find_sheet_file(i) is not None:
                available.append(i)
        return available

    def list_files(self):
        """List all discovered sprite sheet files."""
        files = []
        for i in range(WC_PITCH_FILES):
            path = self._find_sheet_file(i)
            if path:
                files.append((i, path))
        return files


class WCUnityGenericLoader:
    """Loads generic assets (debris, explosions, cockpits, etc.) from PNG files."""

    def __init__(self, source_path: str, pattern: str = None):
        self.source_path = Path(source_path)
        self.pattern = pattern

    def load_single(self) -> Optional[Image.Image]:
        """Load a single PNG image."""
        if self.source_path.is_file():
            return Image.open(self.source_path).convert("RGBA")
        return None

    def load_sequence(self, count: int = None) -> list:
        """Load a numbered sequence of images."""
        frames = []
        if self.source_path.is_dir():
            if self.pattern:
                # Use pattern with {frame} placeholder
                for i in range(count or 100):
                    fname = self.pattern.format(frame=i)
                    path = self.source_path / fname
                    if path.exists():
                        frames.append(Image.open(path).convert("RGBA"))
                    elif count and i < count:
                        print(f"  WARNING: Missing frame {i}: {path}")
                        break
                    else:
                        break
            else:
                # Auto-detect numbered files
                pngs = sorted(self.source_path.glob("*.png"))
                for p in pngs[:count]:
                    frames.append(Image.open(p).convert("RGBA"))
        return frames

    def load_spritesheet(self, cols: int, rows: int, frame_w: int, frame_h: int,
                         count: int = None) -> list:
        """Extract frames from a sprite sheet grid."""
        img = self.load_single()
        if img is None:
            return []

        frames = []
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if count and idx >= count:
                    break
                x0 = c * frame_w
                y0 = r * frame_h
                frame = img.crop((x0, y0, x0 + frame_w, y0 + frame_h))
                frames.append(frame)
                idx += 1
        return frames


# ═══════════════════════════════════════════════════════════════════════════════
# Image Processing
# ═══════════════════════════════════════════════════════════════════════════════

def trim_transparent(img: Image.Image, padding: int = 1) -> Image.Image:
    """Trim transparent border from an RGBA image, keeping a small padding."""
    arr = np.array(img)
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 10, axis=1)
    cols = np.any(alpha > 10, axis=0)

    if not rows.any() or not cols.any():
        return img  # fully transparent, return as-is

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # Add padding
    rmin = max(0, rmin - padding)
    rmax = min(img.height - 1, rmax + padding)
    cmin = max(0, cmin - padding)
    cmax = min(img.width - 1, cmax + padding)

    return img.crop((cmin, rmin, cmax + 1, rmax + 1))


def resize_sprite(img: Image.Image, target_w: int, target_h: int,
                  fit_mode: str = "contain") -> Image.Image:
    """
    Resize sprite to target dimensions.

    fit_mode:
      "contain" - fit inside target, center, preserve aspect ratio (default)
      "cover"   - fill target, crop excess
      "stretch" - stretch to exact size (not recommended)
    """
    if fit_mode == "stretch":
        return img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Calculate scaling to fit/cover
    scale_x = target_w / img.width
    scale_y = target_h / img.height

    if fit_mode == "contain":
        scale = min(scale_x, scale_y)
    else:  # cover
        scale = max(scale_x, scale_y)

    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))

    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Create target-sized canvas and paste centered
    result = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    result.paste(resized, (offset_x, offset_y), resized)

    return result


def to_grayscale_4level(img: Image.Image) -> np.ndarray:
    """
    Convert RGBA image to 4-level grayscale (0-3).

    0 = black (transparent or dark)
    1 = white (bright)
    2 = dark gray
    3 = light gray

    Uses luminance-based conversion with alpha compositing onto black background.
    """
    arr = np.array(img, dtype=np.float32)

    # Alpha-composite onto black background
    alpha = arr[:, :, 3] / 255.0
    r = arr[:, :, 0] * alpha
    g = arr[:, :, 1] * alpha
    b = arr[:, :, 2] * alpha

    # ITU-R BT.601 luminance
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # Quantize to 4 levels using thresholds optimized for sprite readability
    result = np.zeros_like(lum, dtype=np.uint8)
    # 0 = black (lum < 32)
    # 2 = dark gray (32 <= lum < 96)
    # 3 = light gray (96 <= lum < 180)
    # 1 = white (lum >= 180)
    result[lum >= 32] = 2    # dark gray
    result[lum >= 96] = 3    # light gray
    result[lum >= 180] = 1   # white

    return result


def to_rgb565(img: Image.Image) -> np.ndarray:
    """
    Convert RGBA image to RGB565 (16-bit) values.

    Alpha-composites onto black background first.
    Returns array of uint16 values.
    """
    arr = np.array(img, dtype=np.float32)

    alpha = arr[:, :, 3] / 255.0
    r = (arr[:, :, 0] * alpha).astype(np.uint8)
    g = (arr[:, :, 1] * alpha).astype(np.uint8)
    b = (arr[:, :, 2] * alpha).astype(np.uint8)

    # RGB565: RRRRRGGGGGGBBBBB
    r5 = (r >> 3).astype(np.uint16)
    g6 = (g >> 2).astype(np.uint16)
    b5 = (b >> 3).astype(np.uint16)

    return (r5 << 11) | (g6 << 5) | b5


# ═══════════════════════════════════════════════════════════════════════════════
# Binary Encoding (ThumbCommander formats)
# ═══════════════════════════════════════════════════════════════════════════════

def encode_thumby_bitplane(gray4: np.ndarray, width: int, height: int) -> tuple:
    """
    Encode a 4-level grayscale frame into Thumby's BIT + SHD bitplane format.

    Layout: column-major, page-based (SSD1306 OLED format).
    Each byte = 8 vertical pixels in a column. Bit 0 = top pixel of group.
    Pages of 8 pixels, from top to bottom, then next column.

    Color encoding:
      gray4 value → BIT bit, SHD bit
      0 (black)     → 0, 0
      1 (white)     → 1, 0
      2 (dark gray) → 0, 1
      3 (light gray)→ 1, 1

    Returns (bit_bytes, shd_bytes) as bytes objects.
    """
    pages = math.ceil(height / 8)
    frame_size = width * pages

    bit_data = bytearray(frame_size)
    shd_data = bytearray(frame_size)

    for x in range(width):
        for page in range(pages):
            bit_byte = 0
            shd_byte = 0
            for bit in range(8):
                y = page * 8 + bit
                if y < height:
                    pixel = gray4[y, x]
                    if pixel & 1:  # BIT plane
                        bit_byte |= (1 << bit)
                    if pixel & 2:  # SHD plane
                        shd_byte |= (1 << bit)

            byte_idx = page * width + x
            bit_data[byte_idx] = bit_byte
            shd_data[byte_idx] = shd_byte

    return bytes(bit_data), bytes(shd_data)


def encode_tcolor_rgb565(rgb565: np.ndarray) -> bytes:
    """
    Encode RGB565 frame data as raw little-endian bytes.
    Input: 2D array of uint16 RGB565 values (height × width).
    """
    return rgb565.astype('<u2').tobytes()


def write_thumby_files(frames_gray4: list, width: int, height: int,
                       output_base: str):
    """
    Write Thumby BIT + SHD files containing all frames.

    Args:
        frames_gray4: list of numpy arrays (height × width) with values 0-3
        width, height: sprite dimensions
        output_base: base filename (e.g., "enemy2_40_34")
    """
    all_bit = bytearray()
    all_shd = bytearray()

    for frame in frames_gray4:
        bit_data, shd_data = encode_thumby_bitplane(frame, width, height)
        all_bit.extend(bit_data)
        all_shd.extend(shd_data)

    bit_path = f"{output_base}.BIT.bin"
    shd_path = f"{output_base}.SHD.bin"

    with open(bit_path, 'wb') as f:
        f.write(all_bit)
    with open(shd_path, 'wb') as f:
        f.write(all_shd)

    pages = math.ceil(height / 8)
    frame_size = width * pages
    print(f"  Written: {bit_path} ({len(all_bit)} bytes, "
          f"{len(frames_gray4)} frames × {frame_size} bytes)")
    print(f"  Written: {shd_path} ({len(all_shd)} bytes)")

    return bit_path, shd_path


def write_tcolor_file(frames_rgb565: list, width: int, height: int,
                      output_base: str):
    """
    Write ThumbyColor COL file with 8-byte header + raw RGB565 data.

    Header: uint16 LE width, uint16 LE height, uint16 LE frameCount, uint16 LE flags
    """
    frame_count = len(frames_rgb565)
    header = struct.pack('<HHHH', width, height, frame_count, 0)

    all_data = bytearray(header)
    for frame in frames_rgb565:
        all_data.extend(encode_tcolor_rgb565(frame))

    col_path = f"{output_base}.COL.bin"
    with open(col_path, 'wb') as f:
        f.write(all_data)

    frame_bytes = width * height * 2
    print(f"  Written: {col_path} ({len(all_data)} bytes, "
          f"{frame_count} frames × {frame_bytes} bytes + 8 header)")

    return col_path


# ═══════════════════════════════════════════════════════════════════════════════
# Preview Generation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_preview(frames: list, cols: int, label: str, output_path: str,
                     scale: int = 4):
    """
    Generate a PNG preview showing all frames in a grid.

    Args:
        frames: list of PIL RGBA images (all same size)
        cols: number of columns in preview grid
        label: text label for the preview
        output_path: where to save the preview PNG
        scale: upscale factor for visibility
    """
    if not frames:
        return

    fw, fh = frames[0].size
    rows = math.ceil(len(frames) / cols)

    # Create grid with 1px borders
    border = 1
    canvas_w = cols * (fw + border) + border
    canvas_h = rows * (fh + border) + border + 20  # +20 for label

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (40, 40, 40, 255))
    draw = ImageDraw.Draw(canvas)

    for i, frame in enumerate(frames):
        c = i % cols
        r = i // cols
        x = border + c * (fw + border)
        y = border + r * (fh + border)

        # Draw dark background for this cell
        draw.rectangle([x, y, x + fw - 1, y + fh - 1], fill=(20, 20, 20, 255))
        canvas.paste(frame, (x, y), frame)

    # Add label
    try:
        draw.text((border, canvas_h - 18), label, fill=(200, 200, 200, 255))
    except Exception:
        pass

    # Upscale for visibility
    preview = canvas.resize(
        (canvas_w * scale, canvas_h * scale),
        Image.Resampling.NEAREST
    )

    preview.save(output_path)
    print(f"  Preview: {output_path}")


def generate_gray4_preview(frames_gray4: list, width: int, height: int,
                           cols: int, label: str, output_path: str, scale: int = 4):
    """Generate a preview of 4-level grayscale frames."""
    pil_frames = []
    for g4 in frames_gray4:
        # Map gray4 values to RGB
        rgb = np.zeros((height, width, 4), dtype=np.uint8)
        rgb[:, :, 3] = 255  # fully opaque
        for val, lum in enumerate(GRAY4_PALETTE):
            mask = g4 == val
            rgb[mask, 0] = lum
            rgb[mask, 1] = lum
            rgb[mask, 2] = lum
            if val == 0:  # black = transparent background
                rgb[mask, 3] = 128  # semi-transparent for visibility
        pil_frames.append(Image.fromarray(rgb, 'RGBA'))

    generate_preview(pil_frames, cols, label, output_path, scale)


# ═══════════════════════════════════════════════════════════════════════════════
# Ship Conversion Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConversionConfig:
    """Configuration for a sprite conversion job."""
    # Source
    source_dir: str = "."
    ship_name: str = ""
    variant: str = "standard"

    # Target platform
    platform: str = "both"  # "thumby", "tcolor", "both"

    # Output
    output_dir: str = "."
    output_name: str = ""  # auto-generated if empty

    # Sprite dimensions (auto-set from asset type, but overridable)
    thumby_width: int = 0
    thumby_height: int = 0
    tcolor_width: int = 0
    tcolor_height: int = 0

    # Processing options
    trim: bool = True        # auto-trim transparent borders before resize
    fit_mode: str = "contain" # "contain", "cover", "stretch"
    preview: bool = False     # generate preview PNGs
    preview_scale: int = 4    # preview upscale factor

    # Grayscale thresholds (adjustable for better results per ship)
    gray_black_threshold: int = 32
    gray_dark_threshold: int = 96
    gray_light_threshold: int = 180

    # Advanced: custom angle mapping override (JSON file path)
    angle_map_file: str = ""

    # Asset type
    asset_type: str = "ship"  # "ship", "debris", "explosion", "cockpit", etc.

    # For non-ship assets
    frame_count: int = 0     # number of frames to extract
    sheet_cols: int = 0      # sprite sheet columns
    sheet_rows: int = 0      # sprite sheet rows
    source_pattern: str = "" # filename pattern for sequences


def convert_ship(config: ConversionConfig):
    """
    Main ship conversion pipeline.

    Loads WCUnity sprite sheets, extracts the appropriate sub-frames for each
    of the 49 stored orientations, converts to ThumbCommander format(s),
    and writes the output files.
    """
    print(f"\n{'='*70}")
    print(f"  Converting ship: {config.ship_name} ({config.variant})")
    print(f"  Source: {config.source_dir}")
    print(f"{'='*70}")

    # Set default sizes
    tw = config.thumby_width or THUMBY_ENEMY_SIZE[0]
    th = config.thumby_height or THUMBY_ENEMY_SIZE[1]
    cw = config.tcolor_width or TCOLOR_ENEMY_SIZE[0]
    ch = config.tcolor_height or TCOLOR_ENEMY_SIZE[1]

    # Generate output name
    name = config.output_name or f"{config.ship_name.lower()}"
    if config.variant.upper() == "ACE":
        name += "_ace"

    # Load the angle mapping
    angles, col_angles, row_angles = build_stored_frame_angles()

    print(f"\n  Stored frame grid (7×7 = 49 frames):")
    print(f"  Column yaw angles:  {[f'{a:.0f}°' for a in col_angles]}")
    print(f"  Row pitch angles:   {[f'{a:.0f}°' for a in row_angles]}")

    # Initialize the loader
    loader = WCUnityShipLoader(config.source_dir, config.ship_name, config.variant)

    available = loader.get_available_pitches()
    print(f"\n  Available pitch files: {available} ({len(available)}/{WC_PITCH_FILES})")

    if not available:
        print("  ERROR: No sprite sheet files found!")
        print(f"  Expected files like: {loader.prefix}0.png ... {loader.prefix}16.png")
        print(f"  In directory: {config.source_dir}")
        return

    # Extract and convert all 49 frames
    frames_rgba = []   # original color frames for COL.bin
    frames_gray4 = []  # 4-level grayscale for BIT+SHD

    print(f"\n  Extracting 49 frames (7 cols × 7 rows)...")
    for row in range(7):
        for col in range(7):
            frame_idx = row * 7 + col
            tc_yaw, tc_pitch = angles[frame_idx]

            # Map to WCUnity indices
            wc_yaw = tc_yaw_to_wc_yaw(tc_yaw)
            wc_pitch = tc_pitch_to_wc_pitch(tc_pitch)

            # Fall back to nearest available pitch if exact not found
            if wc_pitch not in available:
                wc_pitch = min(available, key=lambda p: abs(p - wc_pitch))

            # Extract sub-frame
            subframe = loader.extract_subframe(wc_yaw, wc_pitch)

            if subframe is None:
                # Create an empty frame as fallback
                print(f"    Frame [{row},{col}]: MISSING (yaw={wc_yaw}, pitch={wc_pitch})")
                subframe = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            else:
                # Trim and resize
                if config.trim:
                    subframe = trim_transparent(subframe)

            frames_rgba.append(subframe)

    print(f"  Extracted {len(frames_rgba)} frames successfully.")

    # Process for each platform
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if config.platform in ("thumby", "both"):
        print(f"\n  --- Thumby ({tw}×{th}, 4-level grayscale) ---")
        thumby_frames_g4 = []
        thumby_frames_rgba = []

        for i, frame in enumerate(frames_rgba):
            resized = resize_sprite(frame, tw, th, config.fit_mode)
            g4 = to_grayscale_4level(resized)
            thumby_frames_g4.append(g4)
            thumby_frames_rgba.append(resized)

        base = str(output_dir / f"{name}_{tw}_{th}")
        write_thumby_files(thumby_frames_g4, tw, th, base)

        if config.preview:
            generate_preview(thumby_frames_rgba, 7,
                           f"{name} Thumby source ({tw}×{th})",
                           str(output_dir / f"{name}_thumby_preview_color.png"),
                           config.preview_scale)
            generate_gray4_preview(thumby_frames_g4, tw, th, 7,
                                 f"{name} Thumby 4-gray ({tw}×{th})",
                                 str(output_dir / f"{name}_thumby_preview_gray4.png"),
                                 config.preview_scale)

    if config.platform in ("tcolor", "both"):
        print(f"\n  --- ThumbyColor ({cw}×{ch}, RGB565) ---")
        tcolor_frames_565 = []
        tcolor_frames_rgba = []

        for i, frame in enumerate(frames_rgba):
            resized = resize_sprite(frame, cw, ch, config.fit_mode)
            rgb565 = to_rgb565(resized)
            tcolor_frames_565.append(rgb565)
            tcolor_frames_rgba.append(resized)

        base = str(output_dir / f"{name}_{cw}_{ch}")
        write_tcolor_file(tcolor_frames_565, cw, ch, base)

        if config.preview:
            generate_preview(tcolor_frames_rgba, 7,
                           f"{name} ThumbyColor ({cw}×{ch})",
                           str(output_dir / f"{name}_tcolor_preview.png"),
                           config.preview_scale)

    print(f"\n  Ship conversion complete!")


# ═══════════════════════════════════════════════════════════════════════════════
# Generic Asset Conversion Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def convert_debris(config: ConversionConfig):
    """Convert debris/asteroid sprites (single rotation axis, 13 frames)."""
    print(f"\n{'='*70}")
    print(f"  Converting debris: {config.source_dir}")
    print(f"{'='*70}")

    tw = config.thumby_width or THUMBY_ASTEROID_SIZE[0]
    th = config.thumby_height or THUMBY_ASTEROID_SIZE[1]
    cw = config.tcolor_width or TCOLOR_ASTEROID_SIZE[0]
    ch = config.tcolor_height or TCOLOR_ASTEROID_SIZE[1]
    frame_count = config.frame_count or 13

    name = config.output_name or "debris"

    # Load source frames
    loader = WCUnityGenericLoader(config.source_dir, config.source_pattern)

    if config.sheet_cols and config.sheet_rows:
        # From sprite sheet
        src_fw = int(loader.load_single().width / config.sheet_cols)
        src_fh = int(loader.load_single().height / config.sheet_rows)
        frames = loader.load_spritesheet(config.sheet_cols, config.sheet_rows,
                                         src_fw, src_fh, frame_count)
    else:
        source_path = Path(config.source_dir)
        if source_path.is_file():
            # Single image — generate rotation frames
            img = loader.load_single()
            if img:
                frames = []
                for i in range(frame_count):
                    angle = i * 360.0 / frame_count
                    rotated = img.rotate(-angle, resample=Image.Resampling.BICUBIC,
                                        expand=False)
                    frames.append(rotated)
            else:
                frames = []
        else:
            frames = loader.load_sequence(frame_count)

    if not frames:
        print("  ERROR: No source frames found!")
        return

    print(f"  Loaded {len(frames)} frames")
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def convert_explosion(config: ConversionConfig):
    """Convert explosion animation sequences."""
    print(f"\n{'='*70}")
    print(f"  Converting explosion: {config.source_dir}")
    print(f"{'='*70}")

    tw = config.thumby_width or THUMBY_EXPLODE_SIZE[0]
    th = config.thumby_height or THUMBY_EXPLODE_SIZE[1]
    cw = config.tcolor_width or TCOLOR_EXPLODE_SIZE[0]
    ch = config.tcolor_height or TCOLOR_EXPLODE_SIZE[1]
    frame_count = config.frame_count or 7  # ThumbCommander uses 7 explosion frames

    name = config.output_name or "explode"

    loader = WCUnityGenericLoader(config.source_dir, config.source_pattern)
    source_frames = loader.load_sequence(100)  # load all available

    if not source_frames:
        print("  ERROR: No explosion frames found!")
        return

    # Resample to target frame count if needed
    if len(source_frames) != frame_count:
        print(f"  Resampling {len(source_frames)} source frames → {frame_count} frames")
        indices = [int(i * len(source_frames) / frame_count)
                   for i in range(frame_count)]
        frames = [source_frames[i] for i in indices]
    else:
        frames = source_frames

    print(f"  Using {len(frames)} frames")
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def convert_cockpit(config: ConversionConfig):
    """Convert cockpit images (single frame)."""
    print(f"\n{'='*70}")
    print(f"  Converting cockpit: {config.source_dir}")
    print(f"{'='*70}")

    # Cockpits are typically full-screen overlays
    tw = config.thumby_width or 72   # Thumby screen width
    th = config.thumby_height or 40  # Thumby screen height
    cw = config.tcolor_width or 128  # ThumbyColor screen width
    ch = config.tcolor_height or 128 # ThumbyColor screen height

    name = config.output_name or "cockpit"

    loader = WCUnityGenericLoader(config.source_dir)
    img = loader.load_single()
    if img is None:
        print("  ERROR: Source image not found!")
        return

    frames = [img]
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def convert_weapon(config: ConversionConfig):
    """Convert weapon/projectile sprites (single or few frames)."""
    print(f"\n{'='*70}")
    print(f"  Converting weapon: {config.source_dir}")
    print(f"{'='*70}")

    tw = config.thumby_width or 8
    th = config.thumby_height or 8
    cw = config.tcolor_width or 14
    ch = config.tcolor_height or 14

    name = config.output_name or "weapon"

    loader = WCUnityGenericLoader(config.source_dir, config.source_pattern)
    source_path = Path(config.source_dir)

    if source_path.is_file():
        frames = [loader.load_single()]
    else:
        frames = loader.load_sequence(config.frame_count or 10)

    if not frames or frames[0] is None:
        print("  ERROR: No source frames found!")
        return

    print(f"  Loaded {len(frames)} frames")
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def convert_background(config: ConversionConfig):
    """Convert space backgrounds (single large image, cropped/tiled)."""
    print(f"\n{'='*70}")
    print(f"  Converting background: {config.source_dir}")
    print(f"{'='*70}")

    tw = config.thumby_width or 72
    th = config.thumby_height or 40
    cw = config.tcolor_width or 128
    ch = config.tcolor_height or 128

    name = config.output_name or "background"

    loader = WCUnityGenericLoader(config.source_dir)
    img = loader.load_single()
    if img is None:
        print("  ERROR: Source image not found!")
        return

    frames = [img]
    config.fit_mode = "cover"  # backgrounds should fill the screen
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def convert_custom(config: ConversionConfig):
    """Convert custom assets with user-specified parameters."""
    print(f"\n{'='*70}")
    print(f"  Converting custom asset: {config.source_dir}")
    print(f"{'='*70}")

    tw = config.thumby_width or 32
    th = config.thumby_height or 32
    cw = config.tcolor_width or 56
    ch = config.tcolor_height or 56

    name = config.output_name or "custom"

    loader = WCUnityGenericLoader(config.source_dir, config.source_pattern)
    source_path = Path(config.source_dir)

    if config.sheet_cols and config.sheet_rows:
        img = loader.load_single()
        if img:
            src_fw = img.width // config.sheet_cols
            src_fh = img.height // config.sheet_rows
            frames = loader.load_spritesheet(config.sheet_cols, config.sheet_rows,
                                             src_fw, src_fh, config.frame_count)
        else:
            frames = []
    elif source_path.is_file():
        frames = [loader.load_single()]
    else:
        frames = loader.load_sequence(config.frame_count or 100)

    if not frames:
        print("  ERROR: No source frames found!")
        return

    print(f"  Loaded {len(frames)} frames")
    _convert_frames_generic(frames, tw, th, cw, ch, name, config)


def _convert_frames_generic(frames: list, tw: int, th: int, cw: int, ch: int,
                            name: str, config: ConversionConfig):
    """Shared conversion logic for non-ship assets."""
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-process: trim transparent borders
    if config.trim:
        frames = [trim_transparent(f) for f in frames]

    if config.platform in ("thumby", "both"):
        print(f"\n  --- Thumby ({tw}×{th}, 4-level grayscale) ---")
        thumby_g4 = []
        thumby_rgba = []
        for frame in frames:
            resized = resize_sprite(frame, tw, th, config.fit_mode)
            thumby_g4.append(to_grayscale_4level(resized))
            thumby_rgba.append(resized)

        base = str(output_dir / f"{name}_{tw}_{th}")
        write_thumby_files(thumby_g4, tw, th, base)

        if config.preview:
            cols = min(len(frames), 7)
            generate_gray4_preview(thumby_g4, tw, th, cols,
                                 f"{name} Thumby ({tw}×{th})",
                                 str(output_dir / f"{name}_thumby_preview.png"),
                                 config.preview_scale)

    if config.platform in ("tcolor", "both"):
        print(f"\n  --- ThumbyColor ({cw}×{ch}, RGB565) ---")
        tcolor_565 = []
        tcolor_rgba = []
        for frame in frames:
            resized = resize_sprite(frame, cw, ch, config.fit_mode)
            tcolor_565.append(to_rgb565(resized))
            tcolor_rgba.append(resized)

        base = str(output_dir / f"{name}_{cw}_{ch}")
        write_tcolor_file(tcolor_565, cw, ch, base)

        if config.preview:
            cols = min(len(frames), 7)
            generate_preview(tcolor_rgba, cols,
                           f"{name} ThumbyColor ({cw}×{ch})",
                           str(output_dir / f"{name}_tcolor_preview.png"),
                           config.preview_scale)

    print(f"\n  Conversion complete!")


# ═══════════════════════════════════════════════════════════════════════════════
# Batch & Config File Support
# ═══════════════════════════════════════════════════════════════════════════════

def load_config_file(path: str) -> list:
    """
    Load conversion jobs from a JSON config file.

    Format:
    {
      "defaults": {
        "source_root": "./WCUnity/Assets/Art",
        "output_dir": "./output",
        "platform": "both",
        "preview": true
      },
      "jobs": [
        {
          "type": "ship",
          "ship_name": "Dralthi",
          "source_dir": "Ships/Dralthi"
        },
        {
          "type": "ship",
          "ship_name": "Dralthi",
          "variant": "ACE",
          "source_dir": "Ships/Dralthi",
          "output_name": "dralthi_ace"
        },
        {
          "type": "debris",
          "source_dir": "VFX/Debris01.png",
          "output_name": "debris1",
          "frame_count": 13
        }
      ]
    }
    """
    with open(path) as f:
        data = json.load(f)

    defaults = data.get("defaults", {})
    source_root = defaults.get("source_root", ".")
    jobs = []

    for job in data.get("jobs", []):
        cfg = ConversionConfig()

        # Apply defaults
        cfg.platform = defaults.get("platform", "both")
        cfg.output_dir = defaults.get("output_dir", ".")
        cfg.preview = defaults.get("preview", False)
        cfg.preview_scale = defaults.get("preview_scale", 4)
        cfg.trim = defaults.get("trim", True)
        cfg.fit_mode = defaults.get("fit_mode", "contain")

        # Apply job-specific settings
        cfg.asset_type = job.get("type", "ship")

        src = job.get("source_dir", "")
        if not os.path.isabs(src):
            src = os.path.join(source_root, src)
        cfg.source_dir = src

        cfg.ship_name = job.get("ship_name", "")
        cfg.variant = job.get("variant", "standard")
        cfg.output_name = job.get("output_name", "")
        cfg.frame_count = job.get("frame_count", 0)
        cfg.sheet_cols = job.get("sheet_cols", 0)
        cfg.sheet_rows = job.get("sheet_rows", 0)
        cfg.source_pattern = job.get("source_pattern", "")

        # Dimension overrides
        for dim_key in ("thumby_width", "thumby_height", "tcolor_width", "tcolor_height"):
            if dim_key in job:
                setattr(cfg, dim_key, job[dim_key])

        # Grayscale threshold overrides
        for gray_key in ("gray_black_threshold", "gray_dark_threshold", "gray_light_threshold"):
            if gray_key in job:
                setattr(cfg, gray_key, job[gray_key])

        jobs.append(cfg)

    return jobs


def run_conversion(config: ConversionConfig):
    """Dispatch conversion based on asset type."""
    converters = {
        "ship": convert_ship,
        "debris": convert_debris,
        "explosion": convert_explosion,
        "cockpit": convert_cockpit,
        "weapon": convert_weapon,
        "background": convert_background,
        "custom": convert_custom,
    }

    converter = converters.get(config.asset_type)
    if converter is None:
        print(f"ERROR: Unknown asset type '{config.asset_type}'")
        print(f"Supported types: {', '.join(converters.keys())}")
        return

    converter(config)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Interface
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser():
    parser = argparse.ArgumentParser(
        prog="wc2thumb",
        description="Convert WCUnity sprite assets to ThumbCommander format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert a ship
  %(prog)s ship Dralthi --source-dir ./WCUnity/Assets/Art/Ships/Dralthi --preview

  # Convert ACE variant
  %(prog)s ship Dralthi --source-dir ./Ships/Dralthi --variant ACE --output-name dralthi_ace

  # Convert only for ThumbyColor
  %(prog)s ship Hornet --source-dir ./Ships/Hornet --platform tcolor

  # Convert debris with rotation
  %(prog)s debris --source ./VFX/Debris01.png --frames 13 --preview

  # Convert explosion sequence
  %(prog)s explosion --source-dir ./VFX --pattern "Explode_{frame:04d}.png" --frames 7

  # Convert cockpit
  %(prog)s cockpit --source ./Cockpits/Hornet/HornetFront.png

  # Batch convert from config file
  %(prog)s batch --config convert_all.json

  # List known ships
  %(prog)s list-ships
        """)

    subparsers = parser.add_subparsers(dest="command", help="Asset type to convert")

    # === ship ===
    ship_parser = subparsers.add_parser("ship", help="Convert ship sprite sheets")
    ship_parser.add_argument("ship_name", help="Ship name (e.g., Dralthi, Hornet)")
    ship_parser.add_argument("--source-dir", required=True,
                            help="Directory containing the ship's sprite sheets")
    ship_parser.add_argument("--variant", default="standard",
                            help="Variant: standard or ACE (default: standard)")
    _add_common_args(ship_parser)

    # === debris ===
    debris_parser = subparsers.add_parser("debris", help="Convert debris/asteroid sprites")
    debris_parser.add_argument("--source", "--source-dir", dest="source_dir", required=True,
                              help="Source file or directory")
    debris_parser.add_argument("--frames", type=int, default=13,
                              help="Number of rotation frames (default: 13)")
    debris_parser.add_argument("--pattern", default="",
                              help="Filename pattern (e.g., 'Debris_{frame:02d}.png')")
    _add_common_args(debris_parser)

    # === explosion ===
    expl_parser = subparsers.add_parser("explosion", help="Convert explosion sequences")
    expl_parser.add_argument("--source-dir", required=True,
                            help="Directory containing explosion frame PNGs")
    expl_parser.add_argument("--frames", type=int, default=7,
                            help="Target frame count (default: 7)")
    expl_parser.add_argument("--pattern", default="",
                            help="Filename pattern (e.g., 'Explode_{frame:04d}.png')")
    _add_common_args(expl_parser)

    # === cockpit ===
    cock_parser = subparsers.add_parser("cockpit", help="Convert cockpit images")
    cock_parser.add_argument("--source", "--source-dir", dest="source_dir", required=True,
                            help="Source PNG file")
    _add_common_args(cock_parser)

    # === weapon ===
    weap_parser = subparsers.add_parser("weapon", help="Convert weapon/projectile sprites")
    weap_parser.add_argument("--source", "--source-dir", dest="source_dir", required=True,
                            help="Source file or directory")
    weap_parser.add_argument("--frames", type=int, default=0,
                            help="Number of frames (0 = auto-detect)")
    weap_parser.add_argument("--pattern", default="",
                            help="Filename pattern")
    _add_common_args(weap_parser)

    # === background ===
    bg_parser = subparsers.add_parser("background", help="Convert space backgrounds")
    bg_parser.add_argument("--source", "--source-dir", dest="source_dir", required=True,
                          help="Source PNG file")
    _add_common_args(bg_parser)

    # === custom ===
    custom_parser = subparsers.add_parser("custom", help="Convert custom assets")
    custom_parser.add_argument("--source", "--source-dir", dest="source_dir", required=True,
                              help="Source file or directory")
    custom_parser.add_argument("--frames", type=int, default=0,
                              help="Number of frames")
    custom_parser.add_argument("--pattern", default="",
                              help="Filename pattern")
    custom_parser.add_argument("--sheet-cols", type=int, default=0,
                              help="Sprite sheet columns")
    custom_parser.add_argument("--sheet-rows", type=int, default=0,
                              help="Sprite sheet rows")
    _add_common_args(custom_parser)

    # === batch ===
    batch_parser = subparsers.add_parser("batch", help="Batch convert from config file")
    batch_parser.add_argument("--config", required=True,
                             help="JSON configuration file path")

    # === list-ships ===
    subparsers.add_parser("list-ships", help="List known WCUnity ship names and prefixes")

    # === info ===
    info_parser = subparsers.add_parser("info", help="Show sprite format information")
    info_parser.add_argument("format", choices=["thumby", "tcolor", "both"],
                            help="Which format to describe")

    return parser


def _add_common_args(parser):
    """Add common arguments to a sub-parser."""
    parser.add_argument("--output-dir", default=".",
                       help="Output directory (default: current)")
    parser.add_argument("--output-name", default="",
                       help="Output filename base (auto-generated if omitted)")
    parser.add_argument("--platform", choices=["thumby", "tcolor", "both"],
                       default="both",
                       help="Target platform (default: both)")
    parser.add_argument("--preview", action="store_true",
                       help="Generate PNG preview images")
    parser.add_argument("--preview-scale", type=int, default=4,
                       help="Preview upscale factor (default: 4)")
    parser.add_argument("--no-trim", action="store_true",
                       help="Disable auto-trimming of transparent borders")
    parser.add_argument("--fit-mode", choices=["contain", "cover", "stretch"],
                       default="contain",
                       help="Resize mode (default: contain)")
    parser.add_argument("--thumby-size", metavar="WxH",
                       help="Override Thumby sprite size (e.g., 40x34)")
    parser.add_argument("--tcolor-size", metavar="WxH",
                       help="Override ThumbyColor sprite size (e.g., 70x59)")
    parser.add_argument("--gray-thresholds", metavar="B,D,L",
                       help="Grayscale thresholds: black,dark,light (e.g., 32,96,180)")


def parse_size(s: str) -> tuple:
    """Parse a 'WxH' size string."""
    parts = s.lower().split('x')
    return int(parts[0]), int(parts[1])


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list-ships":
        print("\nKnown WCUnity ships:")
        print(f"  {'Ship':<12} {'Prefix':<20} {'Frame Size':<12} {'ACE variant'}")
        print(f"  {'-'*12} {'-'*20} {'-'*12} {'-'*12}")
        for ship, prefix in sorted(WC_SHIP_PREFIXES.items()):
            size = WC_SHIP_SIZES.get(ship, (256, 256))
            ace = "Yes" if ship in WC_SHIP_ACE_PREFIXES else "No"
            print(f"  {ship:<12} {prefix:<20} {size[0]}×{size[1]:<8} {ace}")
        return

    if args.command == "info":
        _print_format_info(args.format)
        return

    if args.command == "batch":
        jobs = load_config_file(args.config)
        print(f"Loaded {len(jobs)} conversion jobs from {args.config}")
        for i, job in enumerate(jobs):
            print(f"\n--- Job {i+1}/{len(jobs)} ---")
            run_conversion(job)
        print(f"\nAll {len(jobs)} jobs complete!")
        return

    # Build config from CLI args
    config = ConversionConfig()
    config.asset_type = args.command

    # Apply common args
    if hasattr(args, 'output_dir'):
        config.output_dir = args.output_dir
    if hasattr(args, 'output_name'):
        config.output_name = args.output_name
    if hasattr(args, 'platform'):
        config.platform = args.platform
    if hasattr(args, 'preview'):
        config.preview = args.preview
    if hasattr(args, 'preview_scale'):
        config.preview_scale = args.preview_scale
    if hasattr(args, 'no_trim') and args.no_trim:
        config.trim = False
    if hasattr(args, 'fit_mode'):
        config.fit_mode = args.fit_mode

    # Size overrides
    if hasattr(args, 'thumby_size') and args.thumby_size:
        config.thumby_width, config.thumby_height = parse_size(args.thumby_size)
    if hasattr(args, 'tcolor_size') and args.tcolor_size:
        config.tcolor_width, config.tcolor_height = parse_size(args.tcolor_size)

    # Grayscale thresholds
    if hasattr(args, 'gray_thresholds') and args.gray_thresholds:
        parts = args.gray_thresholds.split(',')
        config.gray_black_threshold = int(parts[0])
        config.gray_dark_threshold = int(parts[1])
        config.gray_light_threshold = int(parts[2])

    # Asset-specific args
    if args.command == "ship":
        config.ship_name = args.ship_name
        config.source_dir = args.source_dir
        config.variant = args.variant
    elif args.command in ("debris", "cockpit", "weapon", "background"):
        config.source_dir = args.source_dir
        if hasattr(args, 'frames'):
            config.frame_count = args.frames
        if hasattr(args, 'pattern'):
            config.source_pattern = args.pattern
    elif args.command == "explosion":
        config.source_dir = args.source_dir
        config.frame_count = args.frames
        config.source_pattern = args.pattern
    elif args.command == "custom":
        config.source_dir = args.source_dir
        config.frame_count = args.frames
        config.source_pattern = args.pattern
        config.sheet_cols = args.sheet_cols
        config.sheet_rows = args.sheet_rows

    run_conversion(config)


def _print_format_info(fmt: str):
    """Print detailed sprite format information."""
    if fmt in ("thumby", "both"):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  THUMBY SPRITE FORMAT (BIT.bin + SHD.bin)                          ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  Files: <name>_<W>_<H>.BIT.bin  (bitplane 0 — brightness)         ║
║         <name>_<W>_<H>.SHD.bin  (bitplane 1 — shading)            ║
║                                                                    ║
║  Layout: Column-major, page-based (SSD1306 OLED format)            ║
║    • Height divided into pages of 8 pixels                         ║
║    • pages = ceil(height / 8)                                      ║
║    • Frame size = width × pages bytes                              ║
║    • Byte order: page 0 col 0, page 0 col 1, ..., page 1 col 0... ║
║    • Each byte: bit 0 = top pixel, bit 7 = bottom pixel            ║
║                                                                    ║
║  4-Level Grayscale Encoding:                                       ║
║    BIT  SHD  →  Color                                              ║
║     0    0   →  BLACK (transparent)                                ║
║     1    0   →  WHITE                                              ║
║     0    1   →  DARK GRAY                                          ║
║     1    1   →  LIGHT GRAY                                         ║
║                                                                    ║
║  No header — dimensions encoded in filename.                       ║
║  Multi-frame: frames concatenated sequentially.                    ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    if fmt in ("tcolor", "both"):
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  THUMBYCOLOR SPRITE FORMAT (COL.bin)                               ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  File: <name>_<W>_<H>.COL.bin                                     ║
║                                                                    ║
║  8-byte header:                                                    ║
║    Offset 0: uint16 LE — width                                     ║
║    Offset 2: uint16 LE — height                                    ║
║    Offset 4: uint16 LE — frame count                               ║
║    Offset 6: uint16 LE — flags (0)                                 ║
║                                                                    ║
║  Pixel data: Raw RGB565, 2 bytes/pixel, little-endian              ║
║    RGB565: RRRRRGGGGGGBBBBB (5 red, 6 green, 5 blue bits)          ║
║    Frame size = width × height × 2 bytes                           ║
║    Frames stored sequentially after header.                        ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    # Orientation system
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  THUMBCOMMANDER ORIENTATION SYSTEM                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                    ║
║  13 orientations per axis (yaw × pitch), 7 stored per axis.        ║
║  Total: 7×7 = 49 stored frames, covering 13×13 = 169 orientations. ║
║  Remaining orientations obtained via X-mirror and/or Y-mirror.     ║
║                                                                    ║
║  Enemy ships: 49 frames (7 columns × 7 rows)                      ║
║  Asteroids: 13 frames (single rotation axis)                       ║
║  Explosions: 7 frames (animation sequence)                         ║
║                                                                    ║
║  Frame index = X_INDEX[x_orient] + Y_SHIFT[y_orient]              ║
║  Mirror flags: X_MIRROR[x_orient], Y_MIRROR[y_orient]             ║
╚══════════════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
