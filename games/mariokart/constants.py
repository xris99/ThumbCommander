# MarioKarts - game-specific constants.
#
# This module extends the engine's shared `PC` object (the
# PlatformConstants singleton, created for the detected target by
# thumby_engine.platform) in place with everything this game needs:
# course geometry (computed once at import time), kart stats, item
# rules, screen layout, fonts, FPS and colors. The engine itself only
# knows the screen size and the platform palette; everything below is
# MarioKarts business.
#
# Must be imported AFTER thumby_engine.platform (MainGame.py guarantees
# order). Because it mutates the same object the engine bound, every
# module holding the PC object sees the game fields too.

from math import atan2, cos, sin, sqrt, pi
from array import array

from thumby_engine.platform import IS_THUMBY_COLOR, PC

try:
    from micropython import const
except ImportError:
    const = lambda x: x

# --- Keymap ------------------------------------------------------------------
# Actions remappable in the settings menu.
#   LEFT/RIGHT steer, UP throttle, DOWN brake, OK use item, BACK forfeit
PC.KEY_NAMES = ("LEFT", "RIGHT", "UP", "DOWN", "OK", "BACK")
PC.DEFAULT_KEYS = ('L', 'R', 'U', 'D', 'A', 'B')

# --- Karts -------------------------------------------------------------------
# Contact sheet order: kart0..kart7
PC.KART_NAMES = ("RED", "BLUE", "ORANGE", "GREEN",
                 "PINK", "MINT", "TEAL", "YELLOW")
# Per kart: (max speed units/s, accel units/s^2, turn rate angle-idx/s)
PC.KART_STATS = (
    (120, 85, 380),
    (126, 70, 330),
    (112, 105, 430),
    (118, 80, 360),
    (128, 60, 310),
    (108, 115, 450),
    (122, 75, 340),
    (116, 90, 370),
)

# --- Items -------------------------------------------------------------------
PC.ITEM_MUSHROOM = const(0)
PC.ITEM_STAR = const(1)
PC.ITEM_BANANA = const(2)
PC.ITEM_POKEY = const(3)
PC.ITEM_NAMES = ("MUSHROOM", "STAR", "BANANA", "POKEY")
# Box drop weights (total 100)
PC.ITEM_WEIGHTS = (40, 15, 25, 20)

PC.LAPS = const(3)

# --- Physics tunables (plain units/s; MainGame converts to Q16) ---------------
# Ported from the reference pseudo-3D racer: every kart lives in track
# space (progress along the centerline + lateral offset), so there is
# no free heading - steering is a small angle relative to the course
# tangent and the AI is a pure lateral-error controller that follows
# traffic instead of rubber-banding.
PC.BRAKE = 220.0
PC.COAST = 40.0
PC.OFFROAD_MAXF = 0.38    # max speed on grass, fraction of top speed
PC.OFFROAD_DRAG = 72.0
PC.STUCK_MULT = 0.45      # max speed while stuck (banana / pokey hit)
PC.BOOST_TIME = 0.75
PC.BOOST_MULT = 1.5
PC.BOOST_ACCEL = 1.9
PC.STAR_TIME = 6.5
PC.STAR_MULT = 1.32
PC.STAR_ACCEL = 1.6
PC.STEER_MAX = 0.52       # rad, full lock at the best handling
PC.STEER_LERP = 6.5       # 1/s, steering response rate
PC.STUCK_TIME = 0.9
PC.BANANA_INVULN = 1.2
PC.POKEY_TIME = 6.0
PC.POKEY_SPEED = 120.0
PC.POKEY_STUCK = 0.85
PC.POKEY_INVULN = 1.6
PC.POKEY_BOUNCE_STUCK = 1.2
PC.BANANA_TIME = 8.0
PC.BOX_RESPAWN = 9.0

# Drift / mini-turbo (color target gameplay, ported from the reference
# racer: hold the drift key + steer at speed to charge, release for a
# boost scaled by the charge). MainGame converts these to Q16.
PC.DRIFT_MAX_CHARGE = 2.2     # charge ceiling (seconds of full lock)
PC.DRIFT_RATE = 1.15          # charge per second at full steering lock
PC.DRIFT_STAGE1 = 0.8         # first mini-turbo threshold
PC.DRIFT_STAGE2 = 1.6         # second threshold (stronger flame)
PC.DRIFT_BOOST_MIN = 0.55     # release multiplier at empty charge
PC.DRIFT_BOOST_RATE = 0.28    # multiplier gain per charge unit
PC.DRIFT_BOOST_CAP = 1.15     # release multiplier ceiling
PC.DRIFT_BOOST_BASE = 0.5     # boost duration (s) base
PC.DRIFT_BOOST_GAIN = 0.35    # ... plus this much at a full charge
PC.DRIFT_LAT_MUL = 1.3        # extra lateral slide while drifting
PC.DRIFT_STEER_MUL = 1.4      # wider steering lock while drifting
PC.DRIFT_SLOW = 0.9           # top speed fraction while drifting

PC.COLL_R = 7.0           # kart-kart collision radius (units)
PC.TRAFFIC_AHEAD = 40.0   # AI following window (units ahead)
PC.TRAFFIC_LAT = 17.0     # AI following window (lateral)

# --- Course ------------------------------------------------------------------
# A closed loop of raw control points in a ~640x480 world box (y down,
# like the framebuffer), running counter-clockwise. Two Chaikin
# smoothing rounds turn the corners into drivable curves; all the
# per-frame quantities the race needs (edges, distances, tangents) are
# precomputed here at import time so the game loop is pure integer
# arithmetic.

COURSE_RAW = (
    (140, 400), (240, 400), (330, 400), (385, 425), (440, 375),
    (500, 400), (580, 400), (635, 365), (655, 290), (630, 210),
    (565, 155), (480, 130), (400, 142), (330, 105), (255, 138),
    (185, 112), (115, 145), (75, 205), (58, 285), (78, 355),
    (110, 392),
)


def _chaikin(pts):
    """One Chaikin corner-cutting round on a closed loop."""
    out = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        out.append(((3 * ax + bx) // 4, (3 * ay + by) // 4))
        out.append(((ax + 3 * bx) // 4, (ay + 3 * by) // 4))
    return out


_course = COURSE_RAW
for _ in (0, 1):
    _course = _chaikin(_course)

PC.COURSE_N = const(len(_course))
PC.CX = array('h', [p[0] for p in _course])
PC.CY = array('h', [p[1] for p in _course])

# Cumulative distance at each point + total lap length
_cum = array('l')
_cum.append(0)
for _i in range(1, PC.COURSE_N):
    _a = _course[_i - 1]
    _b = _course[_i]
    _cum.append(_cum[_i - 1] +
                int(sqrt((_b[0] - _a[0]) ** 2 + (_b[1] - _a[1]) ** 2) + 0.5))
PC.CUM = _cum
PC.L = _cum[PC.COURSE_N - 1] + int(sqrt(
    (_course[0][0] - _course[-1][0]) ** 2 +
    (_course[0][1] - _course[-1][1]) ** 2) + 0.5)

# Tangent direction (angle index, 0 = +x) at each point
PC.ANG = array('h')
for _i in range(PC.COURSE_N):
    _a = _course[(_i - 1) % PC.COURSE_N]
    _b = _course[(_i + 1) % PC.COURSE_N]
    PC.ANG.append(int(atan2(_b[1] - _a[1], _b[0] - _a[0]) * 1024 / (2 * pi))
                  & 1023)

# Road half width + object widths (Q8: 8 = 1 world unit)
PC.L8 = PC.L * 8
PC.ROAD_HW = const(28)
# 75 units is ~16.7% of the road width: at the camera depth
# (CAM_BEHIND8 = 60) the color projection gives 32*75/60 = 40
# px, matching the player slot (KART_RACE_SCALE) exactly.
PC.KART_W8 = const(75)
PC.ITEM_W8 = const(36)
PC.DECO_W8 = const(144)

# Subsegments: 4 per course point, so the track is SUB_N short steps of
# equal length. Every position is Q8 (1/8 units). Subsegment s spans
# point s -> point s+1 (wraps). SDX/SDY are the Q16 tangent, SNX/SNY the
# Q16 right normal (y-down: tangent rotated +90 degrees), so a positive
# lat offset projects to the right of the screen when looking along
# the tangent.
PC.SUB_N = const(PC.COURSE_N * 4)

# Stride color blocks: the reference alternates asphalt/grass/
# rumble every two segments of its SEG_L=200 course (n=73),
# so a block is round(2/73*SUB_N)=9 substeps, period 18.
# Per-substep alternation ran 9x fast and flickered curbs.
PC.STRIP_BLOCK = const(9)
PC.SCX = array('h')
PC.SCY = array('h')
PC.SCUM = array('l')
PC.SANG = array('h')
# Q16 vectors need 17 bits (-65536..+65536), so 'l' not 'h'
# (the engine sin table uses the same trick).
PC.SDX = array('l')
PC.SDY = array('l')
PC.SNX = array('l')
PC.SNY = array('l')
for _i in range(PC.COURSE_N):
    _a = _course[_i]
    _b = _course[(_i + 1) % PC.COURSE_N]
    _d = (PC.CUM[(_i + 1) % PC.COURSE_N] - PC.CUM[_i]) % PC.L
    _da = ((PC.ANG[(_i + 1) % PC.COURSE_N] - PC.ANG[_i] + 512) & 1023) - 512
    for _k in range(4):
        PC.SCX.append(_a[0] * 8 + (_b[0] - _a[0]) * _k * 2)
        PC.SCY.append(_a[1] * 8 + (_b[1] - _a[1]) * _k * 2)
        PC.SCUM.append(PC.CUM[_i] * 8 + _d * _k * 2)
        _ang = (PC.ANG[_i] + _da * _k // 4) & 1023
        PC.SANG.append(_ang)
        _t = _ang * 2 * pi / 1024
        _tx = int(cos(_t) * 65536 + 0.5)
        _ty = int(sin(_t) * 65536 + 0.5)
        PC.SDX.append(_tx)
        PC.SDY.append(_ty)
        PC.SNX.append(-_ty)
        PC.SNY.append(_tx)


def _course_at(dist):
    """(x, y, angle index) at a distance along the loop (wraps)."""
    d = dist % PC.L
    i = 0
    while i < PC.COURSE_N - 1 and PC.CUM[i + 1] < d:
        i += 1
    i0 = i
    i1 = (i + 1) % PC.COURSE_N
    seg = PC.CUM[i1] - PC.CUM[i0]
    if seg <= 0:
        seg = PC.L - PC.CUM[i0]
    t = (d - PC.CUM[i0]) / seg
    x = PC.CX[i0] + (PC.CX[i1] - PC.CX[i0]) * t
    y = PC.CY[i0] + (PC.CY[i1] - PC.CY[i0]) * t
    a = int(atan2(PC.CY[i1] - PC.CY[i0], PC.CX[i1] - PC.CX[i0]) *
            1024 / (2 * pi)) & 1023
    return (int(x + 0.5), int(y + 0.5), a)


def _hill_runs(base, amp, k, w=128):
    """Run-length rows for a parallax hill silhouette (import time).

    The profile is a sum of two sines whose periods divide w, so the
    result wraps cleanly when scrolled at runtime. Returns a tuple of
    (row, ((x0, x1), ...)) for every row the silhouette covers; base
    is the row the hills sit on (full width), the top row is
    base - amp."""
    out = []
    for r in range(base - amp, base + 1):
        thr = (base - r) / amp
        runs = []
        x0 = None
        for x in range(2 * w):
            t = 2 * pi * x / w
            p = 0.5 + 0.3 * sin(k * t) + 0.2 * sin(4 * k * t + 1.7)
            if p >= thr and x0 is None:
                x0 = x
            elif p < thr and x0 is not None:
                runs.append((x0, x - 1))
                x0 = None
        if x0 is not None:
            runs.append((x0, 2 * w - 1))
        row = []
        for a, b in runs:
            if a >= w:
                row.append((a - w, b - w))
            elif b < w:
                row.append((a, b))
            elif a == 0:
                row.append((0, w - 1))
            else:
                row.append((a, w - 1))
                row.append((0, b - w))
        if row:
            out.append((r, tuple(row)))
    return tuple(out)


# Item boxes along the lap, in track space: (Q8 distance, lat 0)
BOX_FRACS = (0.10, 0.26, 0.44, 0.60, 0.76, 0.90)
PC.ITEM_BOXES = [(int(_f * PC.L8), 0) for _f in BOX_FRACS]

# Decorations just off the road:
# (fraction of lap, side +1 right / -1 left, offset, kind)
# kind: 0 cactus, 1 tree, 2 streetlamp
# Twenty-two placements at ~70 unit spacing keep a steady
# stream of scenery on both sides, alternating sides/kinds.
DECOS_RAW = (
    (0.02, 1, 46, 0), (0.06, -1, 50, 1), (0.11, 1, 48, 2),
    (0.15, -1, 52, 1), (0.20, 1, 45, 0), (0.24, -1, 49, 2),
    (0.29, 1, 47, 1), (0.33, -1, 51, 0), (0.38, 1, 44, 2),
    (0.42, -1, 50, 1), (0.47, 1, 46, 0), (0.51, -1, 48, 2),
    (0.56, 1, 45, 1), (0.60, -1, 52, 0), (0.65, 1, 47, 2),
    (0.69, -1, 50, 1), (0.74, 1, 44, 0), (0.78, -1, 49, 2),
    (0.83, 1, 46, 1), (0.87, -1, 51, 0), (0.92, 1, 48, 2),
    (0.96, -1, 47, 1),
)
PC.DECOS = []
for _f, _side, _off, _kind in DECOS_RAW:
    _x, _y, _a = _course_at(int(_f * PC.L))
    _r = _a * 2 * pi / 1024
    _s = 1 if _side > 0 else -1
    PC.DECOS.append((_kind,
                     int(_x - sin(_r) * _off * _s + 0.5),
                     int(_y + cos(_r) * _off * _s + 0.5)))

# Spawn grid behind the start line (the bottom straight
# heading east), in track space: 2 rows x 4 lanes, staggered
# so the field starts spread. The player (kart 0) takes the
# centerline slot 8 behind the grid; SPAWN_ORDER hands the
# CPUs the grid cells. All offsets are Q8.
PC.SPAWN_PROG = tuple(-(28 + (i // 4) * 34) * 8 for i in range(8)) \
    + (-(28 + 34) * 8,)
PC.SPAWN_LAT = tuple((-14, -5, 5, 14)[i % 4] * 8 for i in range(8)) \
    + (0,)
PC.SPAWN_ORDER = (0, 4, 1, 5, 2, 6, 3, 7)
PC.PLAYER_SPAWN_SLOT = 8

# Reciprocal table for division-free perspective projection:
# INV16[z] ~ 65536 / z for 16-bit depths in /8 units (index 0 is
# unused; the closest depth ever used is NEAR8).
PC.INV16 = array('H', [0] * 1536)
for _z in range(1, 1536):
    PC.INV16[_z] = 65535 if _z == 1 else 65536 // _z

# --- Per-target layout, fonts, FPS, colors ------------------------------------
if not IS_THUMBY_COLOR:
    # Original Thumby (72x40, 1-bit 4-level dither, no audio)
    PC.FONT_FILE = "/lib/font5x7.bin"
    PC.FONT_WIDTH = const(5)
    PC.FONT_HEIGHT = const(7)
    PC.FONT_SPACE = const(1)
    PC.SETTING_ITEMS = const(4)

    PC.FPS_MENU = const(30)
    PC.FPS_RACE = const(30)

    # View: half scale of the color target, player anchored low
    PC.VIEW_SCALE = const(32768)
    PC.PX = const(36)
    PC.PY = const(34)

    # Sprite scales (Q16; 65536 = 100%)
    PC.KART_RACE_SCALE = const(36864)   # 40x34 at 0.5625 -> 22x19:
    # matches the projection of KART_W8 at the camera depth for
    # FOV_F = 18 (18*75/60 = 22.5 px)
    PC.ITEM_RACE_SCALE = const(65536)
    PC.DECO_RACE_SCALE = const(32768)
    PC.KART_SELECT_SCALE = const(32768)

    # Race field size
    PC.RACE_KARTS = const(4)

    # Perspective camera + sprite scaling (Q8 world, Q16 vectors)
    PC.FOV_F = const(18)
    PC.HORIZON = const(12)
    PC.NEAR8 = const(24)
    PC.FOG_FAR8 = const(1000)
    PC.CAM_BEHIND8 = const(60)
    PC.CAM_H8 = const(60)
    PC.FCH = const(1080)
    PC.DRAW_N = const(48)
    PC.SCALE_K2_KART = const(230)
    PC.SCALE_K2_ITEM = const(576)
    PC.SCALE_K2_DECOS = (329, 288, 658)

    # 1-bit palette values (0 off, 1 white, 2 dark, 3 mid)
    PC.COLOR_BG = PC.BLACK
    PC.COLOR_TEXT = PC.WHITE
    PC.COLOR_DIM = PC.LIGHTGRAY
    PC.COLOR_SELECT = PC.WHITE
    PC.COLOR_GRASS_A = PC.LIGHTGRAY
    PC.COLOR_GRASS_B = PC.DARKGRAY
    PC.COLOR_ROAD = PC.BLACK
    PC.COLOR_LINE = PC.WHITE
    PC.COLOR_CENTER = PC.WHITE
    PC.COLOR_CHECK_A = PC.WHITE
    PC.COLOR_CHECK_B = PC.BLACK
    PC.COLOR_HUD_BG = PC.BLACK
    PC.COLOR_MINI = PC.WHITE
else:
    # ThumbyColor / PC (128x128, RGB565, audio). Text always uses the
    # built-in 8x8 font on this target (setFont is a no-op), so the
    # font file is never opened.
    PC.FONT_FILE = "/lib/font5x7.bin"
    PC.FONT_WIDTH = const(8)
    PC.FONT_HEIGHT = const(8)
    PC.FONT_SPACE = const(0)
    PC.SETTING_ITEMS = const(6)

    PC.FPS_MENU = const(30)
    PC.FPS_RACE = const(60)

    PC.VIEW_SCALE = const(65536)
    PC.PX = const(64)
    # The player slot sits low so the road runs under the
    # kart the way the reference racers paint it.
    PC.PY = const(113)

    PC.KART_RACE_SCALE = const(65536)   # 40x34 asset at 1.0 -> 40x34:
    # equals the projection of a KART_W8 kart at the camera depth
    # (32*75/60 = 40 px), so the player slot and an AI kart passing
    # at the same depth render at the same size.
    PC.ITEM_RACE_SCALE = const(32768)   # 32x32 asset at 0.5 -> 16x16
    PC.DECO_RACE_SCALE = const(32768)
    PC.KART_SELECT_SCALE = const(49152)  # 40x34 at 0.75 -> 30x25

    PC.RACE_KARTS = const(8)

    # Perspective camera + sprite scaling (Q8 world, Q16 vectors)
    PC.FOV_F = const(32)
    # Horizon 34: rows 34-39 freed by the green-band fix let
    # the road project into them instead of going to sky.
    PC.HORIZON = const(34)
    PC.NEAR8 = const(24)
    PC.FOG_FAR8 = const(1500)
    PC.FOG_MID8 = const(900)
    PC.CAM_BEHIND8 = const(60)
    PC.CAM_H8 = const(122)
    PC.FCH = const(3904)
    PC.DRAW_N = const(96)
    # k2 keeps drawn width == perspective projection for an
    # asset width: w/w_proj = asset_w*k2/(FOV_F*256), so
    # k2 = FOV_F*256/asset_w; the 40 px kart needs 8192/40
    # -> 204 (the old 224 drew rivals ~10% too wide).
    PC.SCALE_K2_KART = const(204)
    PC.SCALE_K2_ITEM = const(256)
    PC.SCALE_K2_DECOS = (292, 256, 585)

    # UI colors (RGB565)
    PC.COLOR_BG = const(0x0008)
    PC.COLOR_TEXT = const(0xFFFF)
    PC.COLOR_DIM = const(0x94EA)
    PC.COLOR_SELECT = const(0xFFE0)
    # World colors - derived from the reference racer's "sunny" theme
    # (road #6f737c/#676b74, curbs #e33e3e/#f5f5f5, grass #63c548/
    # #57b83f, lane #efe9d8), quantized to RGB565.
    PC.COLOR_GRASS_A = const(0x6629)
    PC.COLOR_GRASS_B = const(0x55C7)
    PC.COLOR_ROAD = const(0x6B8F)      # base asphalt (also the bright)
    PC.COLOR_ROAD_A = const(0x6B8F)    # bright asphalt (even bands)
    PC.COLOR_ROAD_B = const(0x634E)    # dark asphalt (odd bands)
    PC.COLOR_RUMBLE_A = const(0xE1E7)  # red curb
    PC.COLOR_RUMBLE_B = const(0xF7BE)  # white curb
    PC.COLOR_LANE = const(0xEF5B)      # cream lane dashes
    PC.COLOR_LINE = const(0xFFFF)
    PC.COLOR_CENTER = const(0xFFE0)
    PC.COLOR_CHECK_A = const(0xFFFF)
    PC.COLOR_CHECK_B = const(0x1060)
    PC.COLOR_HUD_BG = const(0x0008)
    PC.COLOR_MINI = const(0xFFFF)

    # Sky: 5 horizontal bands, top to bottom; SKY_H is the
    # horizon color and doubles as full-fog beyond FOG_FAR8.
    # Blue gradient zenith to steel-blue horizon: every band
    # keeps b > g so the sky never reads as a green wall.
    PC.SKY1 = const(0x0010)
    PC.SKY2 = const(0x214D)
    PC.SKY3 = const(0x3A30)
    PC.SKY4 = const(0x4AD2)
    PC.SKY_H = const(0x5C54)   # light steel-blue horizon haze:
    # the aerial-perspective endpoint must read as sky - the
    # old green 0x4EE8 melted road and lane ink into grass.
    PC.SUN = const(0xFFC0)

    # Parallax hills: precomputed run-length rows over 0..WIDTH-1,
    # scrolled with the player's lap progress (near layer faster).
    PC.HILL_FAR = const(0x3650)
    PC.HILL_NEAR = const(0x2214)
    PC.HILL_FAR_RUNS = _hill_runs(33, 9, 4)
    PC.HILL_NEAR_RUNS = _hill_runs(33, 6, 8)

    # 50% fog: each world color blended per-channel halfway toward
    # SKY_H, in the order the strip renderer uses them.
    def _fog50(c):
        s = PC.SKY_H
        r = (c >> 11) + (s >> 11)
        g = ((c >> 5) & 63) + ((s >> 5) & 63)
        b = (c & 31) + (s & 31)
        return (((r >> 1) << 11) | (((g >> 1) & 63) << 5) | (b >> 1))
    PC.FOG50 = (_fog50(PC.COLOR_ROAD), _fog50(PC.COLOR_GRASS_A),
               _fog50(PC.COLOR_GRASS_B), _fog50(PC.COLOR_LINE),
               _fog50(PC.COLOR_CENTER), _fog50(PC.COLOR_CHECK_A),
               _fog50(PC.COLOR_CHECK_B))
    del _fog50

    # Distance haze (SevEngine-style): every world color faded toward
    # the horizon in eight levels, so far strips melt into the sky
    # smoothly instead of snapping at a binary fog row. _fogt blends
    # each channel linearly toward SKY_H; level 7 is exactly SKY_H.
    def _fogt(c, levels=8):
        s = PC.SKY_H
        r = c >> 11
        g = (c >> 5) & 63
        b = c & 31
        rs = s >> 11
        gs = (s >> 5) & 63
        bs = s & 31
        out = []
        for k in range(levels):
            t = k * 65536 // (levels - 1)
            rv = r + (((rs - r) * t) >> 16)
            gv = g + (((gs - g) * t) >> 16)
            bv = b + (((bs - b) * t) >> 16)
            out.append((rv << 11) | ((gv & 63) << 5) | bv)
        return tuple(out)

    PC.FOGT_ROAD_A = _fogt(PC.COLOR_ROAD_A)
    PC.FOGT_ROAD_B = _fogt(PC.COLOR_ROAD_B)
    PC.FOGT_RUMBLE_A = _fogt(PC.COLOR_RUMBLE_A)
    PC.FOGT_RUMBLE_B = _fogt(PC.COLOR_RUMBLE_B)
    PC.FOGT_GRASS_A = _fogt(PC.COLOR_GRASS_A)
    PC.FOGT_GRASS_B = _fogt(PC.COLOR_GRASS_B)
    PC.FOGT_CHECK_A = _fogt(PC.COLOR_CHECK_A)
    PC.FOGT_CHECK_B = _fogt(PC.COLOR_CHECK_B)

    # Rumble curbs fade toward a dusty red and a warm pale, not
    # the sky: fading the edge line toward the horizon melted
    # it into grass and far curbs vanished entirely.
    PC.CURB_HAZE_A = const(0xA288)  # dusty red endpoint
    PC.CURB_HAZE_B = const(0xD67A)  # warm pale endpoint

    def _fog2(c, e, levels=8):
        cr = c >> 11
        cg = (c >> 5) & 63
        cb = c & 31
        er = e >> 11
        eg = (e >> 5) & 63
        eb = e & 31
        out = []
        for k in range(levels):
            t = k * 65536 // (levels - 1)
            out.append(((cr + (((er - cr) * t) >> 16)) << 11)
                       | (((cg + (((eg - cg) * t) >> 16)) & 63) << 5)
                       | (cb + (((eb - cb) * t) >> 16)))
        return tuple(out)

    PC.FOGT_CURB_A = _fog2(PC.COLOR_RUMBLE_A, PC.CURB_HAZE_A)
    PC.FOGT_CURB_B = _fog2(PC.COLOR_RUMBLE_B, PC.CURB_HAZE_B)
    # Lane ink fades to the same warm pale as the white curbs:
    # the old _fogt table gave it the road's own haze beyond
    # level 6 and the center line disappeared in the distance.
    PC.FOGT_LANE = _fog2(PC.COLOR_LANE, PC.CURB_HAZE_B)
    del _fog2

    del _fogt

    # FOG_LEVEL[zc] gives the haze level for a view-space depth:
    # level L starts at z = FOG_FAR8 * (L/8)^(2/3), approximating the
    # reference fog curve pow(zc/fogDist, 1.5) without any pow()/sqrt.
    _FOG_BOUNDS = (375, 595, 780, 945, 1095, 1238, 1374)
    PC.FOG_LEVEL = array('B', bytearray(PC.FOG_FAR8 + 1))
    for _z in range(PC.FOG_FAR8 + 1):
        _lv = 0
        for _b in _FOG_BOUNDS:
            if _z < _b:
                break
            _lv += 1
        PC.FOG_LEVEL[_z] = _lv
    del _FOG_BOUNDS

    # Transparent pixel in the .COL.bin sprites (from the asset tool)
    PC.KEY_MAGIC = const(0xF81F)
