# MarioKarts - a pseudo-3D rear-view kart racer for the Thumby family.
#
# Runs unmodified on all three targets:
#   * Thumby      (RP2040, 72x40, 1-bit 4-level dither, no audio)
#   * ThumbyColor (RP2350, 128x128 RGB565, IMA-ADPCM audio)
#   * PC          (thumby_engine.pc - a CPython/pygame emulation of the
#                  ThumbyColor firmware; started via tool/run_pc.py)
#
# OutRun-style segment renderer: karts live in track space (progress
# along the centerline + lateral offset), the camera rides the course
# tangent behind the player, and the road is painted strip by strip,
# far to near, with division-free projection (the INV16 table). Every
# sprite is depth-sorted and drawn once. The AI is a lateral-error
# controller that follows traffic instead of rubber-banding; the title
# screen is an attract mode (a live CPU race behind the panel).
#
# Three laps against CPU rivals; items: mushroom (boost), star
# (invincibility), banana (trap), pokey (throw). Color targets get
# sound, vibration and a full HUD via color_enhancements.py.

from thumby_engine.platform import (display, IS_THUMBY_COLOR, PC,
                                    create_sprite, play_cutscene_animation,
                                    create_cancel_callback, audio_load,
                                    audio_play, audio_stop, audio_set_loop,
                                    audio_clear_end_callback, audio_play_id,
                                    rumble, buttonA, buttonB, buttonU,
                                    buttonD, buttonL, buttonR, buttonLB,
                                    buttonRB, buttonMENU, inputJustPressed)

from thumby_engine.util.fpmath import fpmul, fpsin, fpcos

# Game-specific constants (extend the shared PC object)
import constants  # noqa: F401

try:
    from micropython import const
except ImportError:
    const = lambda x: x

# Boot: set CPU frequency, show the target's intro while we load.
if not IS_THUMBY_COLOR:
    from machine import freq
    freq(150_000_000)
    import intro
    intro.init()
    intro.start()
else:
    from engine import freq
    freq(300_000_000)
    play_cutscene_animation("assets/intro_128_80.COL.bin", 21,
                            create_cancel_callback())

from thumbyHardware import reset
from random import randint
from time import sleep
from array import array
from gc import collect, mem_free
import json

# --- Sprite loading ----------------------------------------------------------
# The 1-bit assets use "both bit-planes off" (value 0) as the hole-punch
# key and load in-memory (no open file handles on the Thumby); the
# color .COL.bin assets use the magenta KEY_MAGIC instead.
def _sprite(col_file, bit_file, shd_file, w, h):
    if IS_THUMBY_COLOR:
        return create_sprite(0, 0, col_file, 0, 0, PC.KEY_MAGIC)
    return create_sprite(w, h, (bit_file, shd_file), 0, 0, 0)


KARTS = [
    _sprite("assets/kart%d_40_34.COL.bin" % i,
            "assets/kart%d_20_17.BIT.bin" % i,
            "assets/kart%d_20_17.SHD.bin" % i, 20, 17) for i in range(8)]
ITEMS = [
    _sprite("assets/%s_32_32.COL.bin" % n,
            "assets/%s_8_8.BIT.bin" % n,
            "assets/%s_8_8.SHD.bin" % n, 8, 8)
    for n in ("mushroom", "star", "banana", "pokey")]
DECOS = [
    _sprite("assets/cactus_28_36.COL.bin", "assets/cactus_14_18.BIT.bin",
            "assets/cactus_14_18.SHD.bin", 14, 18),
    _sprite("assets/tree_32_32.COL.bin", "assets/tree_16_16.BIT.bin",
            "assets/tree_16_16.SHD.bin", 16, 16),
    _sprite("assets/streetlamp_14_34.COL.bin",
            "assets/streetlamp_7_17.BIT.bin",
            "assets/streetlamp_7_17.SHD.bin", 7, 17)]

# --- Distance-rendering helpers ---------------------------------------------
# The camera's heading swing moves the raw view depth by tens of units
# while the true distance stays steady; feeding the scale and fade from
# the raw value re-shuffled the pixel grid every other frame. A running
# average (alpha 1/4) removes the swing; approach still closes steadily.
_ZSD = {}


@micropython.native
def _damp(zs, zq):
    """One step of depth damping; first sighting passes the raw depth.
    Small deviations (the heading swing) are damped with alpha 1/4; a
    jump beyond 96 units (re-entry, fast approach) snaps so the first
    drawn frame matches the true projection instead of converging from
    a stale distance."""
    if zs is None:
        return zq
    d = zq - zs
    if d > 96 or d < -96:
        return zq
    return (zs * 3 + zq) >> 2


@micropython.native
def _damped_zc(st, key, zc):
    """Quantize a raw view-space depth onto the 4-unit grid used for
    sprite scaling, then damp it with the running average above.  st is
    the object's dict (or the shared _ZSD for static decos) and keeps
    the previous damped value under key."""
    zq = ((zc + 2) >> 2) << 2
    if zq > PC.FOG_FAR8:
        zq = PC.FOG_FAR8
    zs = _damp(st.get(key), zq)
    st[key] = zs
    return zs


# Gate hysteresis margin for karts, in pixels.
HYST_S = const(8)


@micropython.native
def _kart_gate(k, x8, y8, cam, W, H):
    """Project one kart for the sprite pass, with hysteresis on the
    near plane and the screen margins.

    The camera's heading swing moves a kart's raw depth across NEAR8
    and its screen point across the +-64 margins for a tick or two,
    which made the plain gate flick karts in and out (blinks at the
    bottom of the screen). The kart's damped depth (the same average
    the scale uses) decides visibility: a single-tick dip keeps the
    kart drawn and only a depth that truly leaves the band culls it.
    Under the near plane the kart is pinned to the bottom row at
    clamped size. Returns (zc_eff, sx, sy) - the painter's order key -
    or None when the kart is culled.
    """
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    dx = x8 - camx8
    dy = y8 - camy8
    zc = (dx * hx + dy * hy) >> 16
    xc = (dx * rx + dy * ry) >> 16
    # A raw-depth jump of more than 256 units in one tick is never
    # physical (fastest close is a few dozen units/tick, the swing is
    # tens): it is the lap-seam wrap or a spin knockback. Reading it as
    # a pass-behind blinked every kart at every crossing; during the
    # jump the kart keeps painting at its last projection, frozen at
    # most four ticks, and the stored raw depth holds its pre-jump
    # value so the return tick compares against the truth.
    pzc = k.get('zcr')
    if pzc is not None and (zc - pzc > 256 or pzc - zc > 256):
        nnt = k.get('nnt', 0) + 1
        if nnt <= 4:
            k['nnt'] = nnt
            ld = k.get('lastd')
            return ld if ld is not None else None
    k['zcr'] = zc
    k['nnt'] = 0
    # Karts keep a CONTINUOUS depth: the 4-unit grid stepped the scale
    # of close rivals into discrete jumps; damping alone keeps the
    # pixel grid steady, so their size glides instead of stepping.
    zq = zc if zc < PC.FOG_FAR8 else PC.FOG_FAR8
    # The lateral offset gets the same running average: a few degrees
    # of swing move sx by twenty-odd pixels, far past the +-8 px
    # hysteresis; damped, a swing steps a few pixels and the gate holds.
    xcs = _damp(k.get('xcs'), xc)
    k['xcs'] = xcs
    prev = k.get('zs')
    if prev is None:
        # First sighting: the plain gate; no hysteresis to trade yet.
        # Re-entry from the fog cull must pull clear of the line (a
        # mere dip re-lit the dot for one tick - horizon flicker).
        if k.get('fog'):
            if zc > PC.FOG_FAR8 - 24:
                k['zin'] = False
                k['lastd'] = None
                return None
            k['fog'] = False
        if zc <= 0 or zc > PC.FOG_FAR8:
            k['zin'] = False
            k['lastd'] = None
            return None
        if zc < PC.NEAR8:
            # Closer than the near plane: pin at the bottom row, full
            # size, never culled. The margin test is skipped in the
            # pin zone (a squeeze past reads as parked behind the
            # player; the old margin cull blinked a full-size re-pop).
            # The scaled blit clips at the real screen edge, so the
            # rival slides out continuously.
            ix = PC.INV16[PC.NEAR8]
            sx = cx + ((xcs * PC.FOV_F * ix) >> 16)
            sy = H - 1
            # Depth pinned to the near plane for BOTH the sprite scale
            # and the painter's key: letting the raw dip ride into the
            # draw pass clamped a slid-past rival to full size where
            # the eye read much farther - the re-pop blink.
            k['zs'] = PC.NEAR8
            k['zin'] = True
            k['rc'] = 0
            k['lastd'] = (PC.NEAR8, sx, sy)
            return k['lastd']
        ix = PC.INV16[zc]
        sx = cx + ((xcs * PC.FOV_F * ix) >> 16)
        sy = cy + ((fch * ix) >> 16)
        if sx < -64 or sx > W + 64 or sy < -64 or sy > H + 64:
            k['zin'] = False
            k['rc'] = 0
            k['lastd'] = None
            return None
        # Re-acquire after any cull is debounced for two in-range
        # frames (a one-tick dip back inside the margins read as an
        # edge blink). The default of 2 lets a genuine first sighting
        # light immediately (rc was never armed by a cull).
        rc = k.get('rc', 2) + 1
        if rc < 2:
            k['rc'] = rc
            k['zin'] = False
            k['zs'] = zq
            k['lastd'] = None
            return None
        k['zs'] = zq
        k['zin'] = True
        k['rc'] = 0
        k['lastd'] = (zc, sx, sy)
        return k['lastd']
    zs = _damp(prev, zq)
    k['zs'] = zs
    # On a genuine cull the damped depth must be dropped: a stale zs
    # past the cull made the next sighting re-enter drawn at clamped
    # full size, then shrink ("jumping by dimensions"). Clearing it
    # lets the re-entry run the first-sighting path, from the raw
    # quantized depth - correct for the true distance.
    if zc > PC.FOG_FAR8:
        nnf = k.get('nnf', 0) + 1
        if nnf < 3:
            # The swing pushes the raw depth over the fog end for a
            # tick or two while the kart is still inside; staying
            # drawn here (damped depth kept) avoids the horizon
            # blink. Only three straight ticks past the line mean the
            # kart has run into the fog for good.
            k['nnf'] = nnf
        else:
            # The latch remembers the cull so the swing cannot flip
            # the kart back on: re-entry must pull 24 units clear of
            # the fog line first.
            k['zin'] = False
            k['fog'] = True
            k['zs'] = None
            k['nnf'] = 0
            k['lastd'] = None
            return None
    else:
        k['nnf'] = 0
    if zs < PC.NEAR8 or zc < PC.NEAR8:
        # The pin zone is ALWAYS drawn - no margin test, no debounce.
        # At the near-plane scale a squeeze past is nearly stationary
        # in sx: it looks parked behind the player slot while being
        # many lanes off-side, and the scaled blit clips at the real
        # screen edge, so it slides out continuously. A behind-camera
        # dip is LATCHED AND DRAWN: the point sits off frame beside
        # the lens anyway, so the squeeze never re-sights and never
        # blinks. Only a dip that holds three straight ticks means
        # the kart truly passed behind the lens for good - then the
        # damped depth is dropped so the re-entry runs the first-
        # sighting path and sizes from the raw distance, never from
        # a stale near value (clamping full size from the raw tiny
        # depth was the re-pop blink).
        if zc <= 0:
            nnc = k.get('nnc', 0) + 1
            if nnc >= 3:
                k['zin'] = False
                k['zs'] = None
                k['nnc'] = 0
                k['rc'] = 0
                k['lastd'] = None
                return None
            k['nnc'] = nnc
        else:
            k['nnc'] = 0
        ix = PC.INV16[PC.NEAR8]
        sx = cx + ((xcs * PC.FOV_F * ix) >> 16)
        sy = H - 1
        k['zin'] = True
        k['rc'] = 0
        # Pin the stored depth to the near plane while drawing here:
        # the scale and fade read k['zs'] and a mid-dip damped value
        # would index the reciprocal table below zero. At the pin
        # position the clamped slot size is the squeeze look anyway,
        # and the ramp stays smooth on the way out.
        k['zs'] = PC.NEAR8
        k['lastd'] = (PC.NEAR8, sx, sy)
        return k['lastd']
    # The gate position rides the damped depth, not the raw one: the
    # swing moved sx by tens of pixels per tick, far beyond the +-8 px
    # hysteresis, so close rivals toggled across the margins; the
    # damped point is steady for the margin test.
    ix = PC.INV16[zs]
    sx = cx + ((xcs * PC.FOV_F * ix) >> 16)
    sy = cy + ((fch * ix) >> 16)
    if k.get('zin'):
        lo = -64 - HYST_S
        hi = W + 64 + HYST_S
        loy = -64 - HYST_S
        hiy = H + 64 + HYST_S
    else:
        lo = -64
        hi = W + 64
        loy = -64
        hiy = H + 64
    if sx < lo or sx > hi or sy < loy or sy > hiy:
        k['zin'] = False
        k['rc'] = 0
        k['lastd'] = None
        return None
    if not k.get('zin'):
        # Same two-tick debounce as the first-sighting path: a kart
        # that slid off frame may dip back inside for a single tick -
        # a plain relight blinked at the edge. A genuine re-entry
        # holds the inside for several ticks and passes.
        rc = k.get('rc', 0) + 1
        if rc < 2:
            k['rc'] = rc
            k['lastd'] = None
            return None
    k['zin'] = True
    k['rc'] = 0
    # The pin branch above already returned for every depth under the
    # near plane, so zc is in-band here and can be returned raw.
    k['lastd'] = (zc, sx, sy)
    return k['lastd']


if IS_THUMBY_COLOR:
    # Representative color per kart sprite, sampled from the center
    # column: a 1-pixel-wide scaled blit samples only the magenta key
    # and draws nothing, so the fade's final "single pixel" is painted
    # by hand in the kart's own color. First non-key pixel wins (the
    # helmet); an all-key column falls back to the horizon fog.
    def _kart_dot_color(sp):
        key = PC.KEY_MAGIC
        fv = sp.frame_view
        w = sp.width
        cx = w // 2
        cy = sp.height // 2
        for dy in range(-cy, cy + 1):
            i = ((cy + dy) * w + cx) * 2
            val = fv[i] | (fv[i + 1] << 8)
            if val != key:
                return val
        return PC.SKY_H

    KART_DOT = [_kart_dot_color(sp) for sp in KARTS]

# --- Key / state / timing constants -----------------------------------------
KEY_LEFT = const(0)
KEY_RIGHT = const(1)
KEY_UP = const(2)
KEY_DOWN = const(3)
KEY_OK = const(4)
KEY_BACK = const(5)

RC_COUNT = const(0)   # 3-2-1-GO
RC_RUN = const(1)
RC_FINISH = const(2)  # player done, field coasts to the results

DT = (1 << 16) // PC.FPS_RACE
BUMP_FRAMES = int(0.4 * PC.FPS_RACE)
# Q8 (the kart totals are Q8): how far the pack leader must pull ahead
# of the attract camera's kart before the camera switches to it
LEAD_MARGIN8 = 12 << 8

# Tunables as Q16 (the PC constants are floats - convert with
# multiplication; a << on a float is a TypeError on every target)
BRAKE_Q = int(PC.BRAKE * 65536)
COAST_Q = int(PC.COAST * 65536)
OFFROAD_DRAG_Q = int(PC.OFFROAD_DRAG * 65536)
OFFROAD_SMUL_Q = int(PC.OFFROAD_MAXF * 65536)
STUCK_SMUL_Q = int(PC.STUCK_MULT * 65536)
BOOST_TIME_Q = int(PC.BOOST_TIME * 65536)
BOOST_SMUL_Q = int(PC.BOOST_MULT * 65536)
BOOST_ACCEL_Q = int(PC.BOOST_ACCEL * 65536)
STAR_TIME_Q = int(PC.STAR_TIME * 65536)
STAR_SMUL_Q = int(PC.STAR_MULT * 65536)
STAR_ACCEL_Q = int(PC.STAR_ACCEL * 65536)
POKEY_TIME_Q = int(PC.POKEY_TIME * 65536)
POKEY_SPEED_Q = int(PC.POKEY_SPEED * 65536)
POKEY_STUCK_Q = int(PC.POKEY_STUCK * 65536)
POKEY_INVULN_Q = int(PC.POKEY_INVULN * 65536)
POKEY_BOUNCE_Q = int(PC.POKEY_BOUNCE_STUCK * 65536)
BANANA_TIME_Q = int(PC.BANANA_TIME * 65536)
BANANA_INVULN_Q = int(PC.BANANA_INVULN * 65536)
STUCK_TIME_Q = int(PC.STUCK_TIME * 65536)
BOX_RESPAWN_Q = int(PC.BOX_RESPAWN * 65536)
STEER_LERP_Q = int(PC.STEER_LERP * DT / 256 + 0.5)
# Free-heading yaw (the player kart in a race): the nose rotates in
# world space under the steering lock, da = (steer * dt) >> YAW_SHIFT.
# k['steer'] already ramps with speed, so the nose rate is proportional
# to both speed and lock and vanishes at a standstill.  YAW_SHIFT lands
# the steady full lock at top speed on the YAW_MAX cap, roughly 120
# deg/s - fast enough to hold the hairpins at full throttle with room
# to spare, slow enough that a straight-line miss reads clearly.
# YAW_MAX caps the swing of a tick so a drift-widened lock cannot spin
# the kart off its own tail.
YAW_SHIFT = 21
YAW_MAX = 6

# Lap-crossing gate: the largest forward step (Q8) a kart can cover in
# a single tick, top speed plus boost/star/drift slack.  A projected
# position hop bigger than this is a jump of the projection, not the
# kart crossing the start line, and must never be credited as a lap.
LAP_STEP8 = 64

# Drift / mini-turbo conversions (the color target is the one that
# drifts; on the original Thumby these values are simply never used)
DRIFT_CHARGE_MAX_Q = int(PC.DRIFT_MAX_CHARGE * 65536)
DRIFT_RATE_Q = int(PC.DRIFT_RATE * 65536 / 256 + 0.5)
DRIFT_STAGE1_Q = int(PC.DRIFT_STAGE1 * 65536)
DRIFT_STAGE2_Q = int(PC.DRIFT_STAGE2 * 65536)
DRIFT_BOOST_MIN_Q = int(PC.DRIFT_BOOST_MIN * 65536)
DRIFT_BOOST_RATE_Q = int(PC.DRIFT_BOOST_RATE * 65536)
DRIFT_BOOST_CAP_Q = int(PC.DRIFT_BOOST_CAP * 65536)
DRIFT_BOOST_BASE_Q = int(PC.DRIFT_BOOST_BASE * 65536)
# boost-duration gain converted so a full charge lands exactly on the
# PC.DRIFT_BOOST_GAIN seconds
DRIFT_BOOST_GAIN_Q = int(PC.DRIFT_BOOST_GAIN * 65536 * 65536 /
                         PC.DRIFT_MAX_CHARGE + 0.5)
DRIFT_LAT_MUL_Q = int(PC.DRIFT_LAT_MUL * 65536)
DRIFT_STEER_MUL_Q = int(PC.DRIFT_STEER_MUL * 65536)
DRIFT_SLOW_Q = int(PC.DRIFT_SLOW * 65536)

# Q8 track-space limits (8 = 1 world unit)
HW8 = PC.ROAD_HW * 8
LAT_MAX8 = 492    # 2.2 road half widths - the grass wall
OFFROAD8 = 26 * 8

# --- Keymaps (remappable, persisted to keymap.json) -------------------------
DEFAULT_KEYS = array('O', PC.DEFAULT_KEYS)


def button_exists(button):
    try:
        return bool(("button" + button) in globals())
    except Exception:
        return False


def load_keymaps():
    try:
        with open("keymap.json", "r") as f:
            d = json.loads(f.read())
        keys = array('O', DEFAULT_KEYS)
        for i in range(len(PC.KEY_NAMES)):
            nm = PC.KEY_NAMES[i]
            if nm in d and button_exists(d[nm]):
                keys[i] = d[nm]
        return keys
    except Exception:
        return array('O', DEFAULT_KEYS)


def save_keymaps(keymap):
    try:
        d = {}
        for i in range(len(PC.KEY_NAMES)):
            d[PC.KEY_NAMES[i]] = keymap[i]
        with open("keymap.json", "w") as f:
            f.write(json.dumps(d))
    except Exception:
        pass


KEYMAPS = load_keymaps()
BUTTONS = [eval("button" + KEYMAPS[i]) for i in range(len(KEYMAPS))]


def rebuild_buttons():
    global BUTTONS
    BUTTONS = [eval("button" + KEYMAPS[i]) for i in range(len(KEYMAPS))]


@micropython.native
def keylabel(action):
    """Remap-aware, target-aware key name for hints."""
    k = KEYMAPS[action]
    if IS_THUMBY_COLOR:
        return k
    return {'LB': 'L', 'RB': 'R', 'MENU': 'B'}.get(k, k)


def get_pressed_key():
    if buttonA.pressed():
        return 'A'
    if buttonB.pressed():
        return 'B'
    if buttonU.pressed():
        return 'U'
    if buttonD.pressed():
        return 'D'
    if buttonL.pressed():
        return 'L'
    if buttonR.pressed():
        return 'R'
    if buttonLB.pressed():
        return 'LB'
    if buttonRB.pressed():
        return 'RB'
    if buttonMENU.pressed():
        return 'MENU'
    return ''

# --- Text / audio helpers ----------------------------------------------------
@micropython.native
def text_width(s):
    return len(s) * (PC.FONT_WIDTH + PC.FONT_SPACE) - PC.FONT_SPACE


@micropython.native
def center_x(s):
    return (PC.WIDTH - text_width(s)) // 2


def _menu_music():
    if IS_THUMBY_COLOR:
        audio_load("assets/music_title.ima")
        audio_play()
        audio_set_loop(True)


def _audio_off():
    if IS_THUMBY_COLOR:
        audio_clear_end_callback()
        audio_stop()


FX = None  # lazily created FXEngine (color only), shared across races


@micropython.native
def _fx():
    global FX
    if IS_THUMBY_COLOR and FX is None:
        FX = FXEngine()
    return FX


def _select_sfx():
    if rumble:
        rumble(15)
    f = _fx()
    if f:
        f.play(FXEngine.SELECT)


@micropython.native
def draw_sprite(sp):
    """Draw a sprite at its own x/y; use the scaled path only when a
    scale/mirror is actually in play (color drawSprite can't mirror)."""
    if IS_THUMBY_COLOR:
        if sp.scale != 65536 or sp.mirrorX or sp.mirrorY:
            display.drawSpriteWithScale(sp)
        else:
            display.drawSprite(sp)
    else:
        if sp.scale != 65536:
            display.drawSpriteWithScale(sp)
        else:
            display.drawSprite(sp)

# --- Track-space helpers (plain integer math on the precomputed arrays) -----
@micropython.native
def _sub_of_prog8(prog8):
    """Subsegment index for a Q8 progress value (wraps; negative
    values stay safe through MicroPython floor-mod). The subsegments
    are nearly equal length, so the coarse estimate is within a few
    of the answer and a short window search suffices."""
    p = prog8 % PC.L8
    n = PC.SUB_N
    s = ((p * n) // PC.L8 - 24) % n
    for i in range(48):
        if p < PC.SCUM[(s + i) % n]:
            return s
    return 0


@micropython.native
def _tp8(prog8, lat8):
    """World position (Q8) of a track-space point: centerline of the
    subsegment plus the right normal times the lateral offset."""
    s = _sub_of_prog8(prog8)
    return (PC.SCX[s] + ((PC.SNX[s] * lat8) >> 16),
            PC.SCY[s] + ((PC.SNY[s] * lat8) >> 16))


@micropython.native
def _kart_world8(k):
    if k['free']:
        return (k['wx8'], k['wy8'])
    return _tp8(k['prog'], k['lat'])


@micropython.native
def _proj_track8(wx8, wy8, s_hint, deep=False):
    """Inverse of _tp8 for a free kart: put an integrated world
    position back onto the course so prog/lat can feed laps, items,
    traffic and the off-road flag. The nearest point on the sub
    chords is searched in a window around the kart's last known
    sub; if the kart left the window, the nearest sub is found
    globally and the window retried once. Returns (prog8, lat8, sub)."""
    n = PC.SUB_N
    bscore = None
    bex = 0
    bprog = 0
    blat = 0
    bs = s_hint
    for off in range(-14, 15):
        s = (s_hint + off) % n
        dx = wx8 - PC.SCX[s]
        dy = wy8 - PC.SCY[s]
        raw = (dx * PC.SDX[s] + dy * PC.SDY[s]) >> 16
        seg = (PC.SCUM[(s + 1) % n] - PC.SCUM[s]) % PC.L8
        if raw < 0:
            t = 0
        elif raw > seg:
            t = seg
        else:
            t = raw
        lat = (dx * PC.SNX[s] + dy * PC.SNY[s]) >> 16
        ex = raw - t
        # Continuity bias: a chord further from the hint's position
        # pays a penalty so the along-road coordinate keeps walking
        # with the hint. Without it the plain minimum can latch onto
        # the wrong chord family on a hairpin and collapse prog.
        d2 = ex * ex + lat * lat + off * off * 400
        if bscore is None or d2 < bscore:
            bscore = d2
            bex = ex
            bprog = (PC.SCUM[s] + t) % PC.L8
            blat = lat
            bs = s
    if bex > 400 or bex < -400:
        # the nearest point sat outside the window along the road:
        # find the nearest sub globally and retry with deep=True so
        # the retry cannot chain a third pass
        if deep:
            return (bprog, blat, bs)
        gd = None
        gbs = 0
        for s in range(n):
            dx = wx8 - PC.SCX[s]
            dy = wy8 - PC.SCY[s]
            d2 = dx * dx + dy * dy
            if gd is None or d2 < gd:
                gd = d2
                gbs = s
        return _proj_track8(wx8, wy8, gbs, True)
    return (bprog, blat, bs)


@micropython.native
def _camera(v):
    """Camera behind the followed kart (v['cam_idx']: the player in a
    real race, the leader in attract mode), looking along the course
    tangent at the kart's own sub - never the steered heading.
    Returns (hx, hy, rx, ry, camx8, camy8, cx, cy, fch): the Q16 view
    direction, the Q16 right vector, the Q8 camera position and the
    projection constants (screen center x, horizon row, FOV*height).

    The heading comes from the kart's own sub, never a point behind
    it: looking along an old tangent put the view axis off the road
    on every curve and slid the road sideways across the screen.
    The kart's own tangent keeps the road centered at the bottom,
    curving away with perspective as the reference racer does."""
    p = v['karts'][v['cam_idx']]
    s = _sub_of_prog8(p['prog'])
    if p['free']:
        # A free kart looks along its nose, not the course tangent:
        # running straight through a bend the road curves away, as
        # a camera bolted to the kart should. The nose starts on the
        # spawn tangent, so the countdown looks like the tangent cam.
        hx = fpcos(p['ang'])
        hy = fpsin(p['ang'])
    else:
        hx = PC.SDX[s]
        hy = PC.SDY[s]
    x8, y8 = _kart_world8(p)
    camx8 = x8 - ((hx * PC.CAM_BEHIND8) >> 16)
    camy8 = y8 - ((hy * PC.CAM_BEHIND8) >> 16)
    rx = -hy
    ry = hx
    return (hx, hy, rx, ry, camx8, camy8,
            PC.WIDTH // 2, PC.HORIZON, PC.FCH)


@micropython.native
def _proj(x8, y8, cam):
    """Project a Q8 world point to (sx, sy, zc) or None when behind
    the near plane or past the fog. The world is flat, so the screen
    row depends only on the depth: sy = cy + FCH/zc."""
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    dx = x8 - camx8
    dy = y8 - camy8
    zc = (dx * hx + dy * hy) >> 16
    if zc < PC.NEAR8 or zc > PC.FOG_FAR8:
        return None
    xc = (dx * rx + dy * ry) >> 16
    ix = PC.INV16[zc]
    sx = cx + ((xc * PC.FOV_F * ix) >> 16)
    sy = cy + ((fch * ix) >> 16)
    return (sx, sy, zc)


@micropython.native
def _kart_update(k, steer_in, thr, dt):
    """One physics step.

    steer_in: Q8, -256..256 (full lock either way); 0 = straight.
    thr:      Q16; >0 accelerate, <0 brake, 0 coast.

    Two movement models share the speed and steering chains: a free
    kart (the player in a live race) turns its nose in world space
    and drives along it, so an unsteered kart keeps going straight
    and leaves the road when the road curves away; an on-rail kart
    (every AI kart and the attract demo) moves along the course
    tangent - always forward, there is no reverse - and across it by
    a small steering offset that ramps in with speed and is lerped
    for a weighted feel. Positions are Q8, the angle tables come from
    the engine fpmath module.
    """
    if k['boost'] > 0:
        k['boost'] -= dt
        if k['boost'] < 0:
            k['boost'] = 0
    if k['star'] > 0:
        k['star'] -= dt
        if k['star'] < 0:
            k['star'] = 0
    if k['stuck'] > 0:
        k['stuck'] -= dt
        if k['stuck'] < 0:
            k['stuck'] = 0
    if k['invuln'] > 0:
        k['invuln'] -= dt
        if k['invuln'] < 0:
            k['invuln'] = 0
    if k['bump'] > 0:
        k['bump'] -= dt
        if k['bump'] < 0:
            k['bump'] = 0
    # max speed: the effect chain applied in order
    sm = k['sm']
    if k['ai']:
        sm = (sm * k['skill']) >> 16
    if k['star'] > 0:
        sm = (sm * STAR_SMUL_Q) >> 16
    if k['boost'] > 0:
        sm = (sm * k['bp']) >> 16
    if k['off']:
        sm = (sm * OFFROAD_SMUL_Q) >> 16
    if k['stuck'] > 0:
        sm = (sm * STUCK_SMUL_Q) >> 16
    if k['drift']:
        sm = (sm * DRIFT_SLOW_Q) >> 16
    # power-slide charge: builds while drifting, scaled by the steering
    # lock, capped at the ceiling (Q16 seconds)
    if k['drift'] == 1:
        ch = k['drcharge'] + ((abs(steer_in) * dt * DRIFT_RATE_Q) >> 16)
        if ch > DRIFT_CHARGE_MAX_Q:
            ch = DRIFT_CHARGE_MAX_Q
        k['drcharge'] = ch
    # acceleration: boost/star multiply the kart's own value
    ac = k['ac']
    if k['boost'] > 0:
        ac = (ac * BOOST_ACCEL_Q) >> 16
    elif k['star'] > 0:
        ac = (ac * STAR_ACCEL_Q) >> 16
    if thr > 0:
        k['s'] += fpmul(ac, dt)
    elif thr < 0:
        k['s'] -= fpmul(BRAKE_Q, dt)
    else:
        k['s'] -= fpmul(COAST_Q, dt)
    if k['off']:
        k['s'] -= fpmul(OFFROAD_DRAG_Q, dt)
    if k['s'] < 0:
        k['s'] = 0
    elif k['s'] > sm:
        k['s'] = sm
    # steering: turn authority ramps in with speed, better handling
    # (hn) allows a wider lock; the lerp smooths the response
    fac = 18022 + ((k['hn'] * 14746) >> 16)
    if k['drift']:
        # a power slide turns wider than grip alone allows
        fac = (fac * DRIFT_STEER_MUL_Q) >> 16
    maxang = (17039 * fac) >> 15
    tgt = (steer_in * maxang) >> 8
    g = (k['s'] * 546) >> 16
    if g > 32768:
        g = 32768
    tgt = (tgt * g) >> 15
    k['steer'] += ((tgt - k['steer']) * STEER_LERP_Q) >> 8
    d = fpmul(k['s'], dt)
    if k['free']:
        # Free heading (player kart in a live race): the nose turns
        # in world space under the steering lock and the kart drives
        # along it - with no steering the kart keeps going straight
        # and leaves the road when the road curves away, exactly like
        # the reference racer. prog/lat are re-derived by inverse
        # projection, so laps, items, traffic and the off-road flag
        # run off the real world position.
        da = (k['steer'] * dt) >> YAW_SHIFT
        if da > YAW_MAX:
            da = YAW_MAX
        elif da < -YAW_MAX:
            da = -YAW_MAX
        k['ang'] = (k['ang'] + da) & 1023
        # Round the world advance to the nearest 1/8 unit as the rail
        # model does; truncation would freeze a slow kart in place.
        wx = k['wx8'] + ((fpmul(d, fpcos(k['ang'])) + (1 << 12)) >> 13)
        wy = k['wy8'] + ((fpmul(d, fpsin(k['ang'])) + (1 << 12)) >> 13)
        prog, lat, s = _proj_track8(wx, wy, k['latsub'])
        if lat > LAT_MAX8:
            # the grass wall: snap back onto the chord's normal
            lat = LAT_MAX8
            wx, wy = _tp8(prog, lat)
        elif lat < -LAT_MAX8:
            lat = -LAT_MAX8
            wx, wy = _tp8(prog, lat)
        k['wx8'] = wx
        k['wy8'] = wy
        k['latsub'] = s
        old = k['prog']
        k['prog'] = prog
        k['lat'] = lat
        k['off'] = (lat > OFFROAD8 or lat < -OFFROAD8)
        # total is the along-road distance: take the wrapped forward
        # step; turning back relative to the road adds nothing (no
        # reverse). The wrap is symmetric so a projection hop of
        # half a lap reads as the small step actually taken.
        dd = ((prog - old + (PC.L8 >> 1)) % PC.L8) - (PC.L8 >> 1)
        if dd < 0:
            dd = 0
        k['total'] += dd
        k['x'] = wx << 13
        k['y'] = wy << 13
        return
    # On the rail (every AI kart and the attract-mode demo): move
    # along the tangent, then across it.  fpmul keeps Q16 (1/65536
    # of a unit); >> 13 lands in Q8 (1/8 unit), the world's unit.
    st = k['steer']
    if st < 0:
        st = -st
    idx = (st * 326) >> 16
    # Round the forward advance to the nearest 1/8 unit instead of
    # truncating: at 60 fps a tick moves under a full unit below
    # ~7.5 units/s and truncation froze slow karts, which re-shuffled
    # the strip painter's order on every subsegment crossing.
    adv = (fpmul(d, fpcos(idx)) + (1 << 12)) >> 13
    k['prog'] = (k['prog'] + adv) % PC.L8
    k['total'] += adv
    lat = fpmul(d, fpsin(idx))
    if k['drift']:
        # the slide breaks traction: the kart drifts out wider
        lat = (lat * DRIFT_LAT_MUL_Q) >> 16
    if k['steer'] >= 0:
        k['lat'] += lat >> 13
    else:
        k['lat'] -= lat >> 13
    if k['lat'] > LAT_MAX8:
        k['lat'] = LAT_MAX8
    elif k['lat'] < -LAT_MAX8:
        k['lat'] = -LAT_MAX8
    k['off'] = (k['lat'] > OFFROAD8 or k['lat'] < -OFFROAD8)
    # world position (Q16) for the minimap
    wx8, wy8 = _kart_world8(k)
    k['x'] = wx8 << 13
    k['y'] = wy8 << 13


@micropython.native
def _ai_decide(k, v):
    """The AI brain: a pure lateral-error controller with traffic
    follow. Aims at its lane target (or straight back at the
    centerline when well off the road) and matches the speed of the
    kart it is following. Returns (steer Q8 -256..256, throttle
    Q16 0 or 65536)."""
    if k['lat'] > 156 or k['lat'] < -156:
        target = 0
    else:
        target = k['err']
    diff = target - k['lat']
    if diff > 230:
        si = 230
    elif diff < -230:
        si = -230
    else:
        si = (diff * 230) >> 8
    tv = k['sm']
    if k['ai']:
        tv = (tv * k['skill']) >> 16
    # Traffic cap keeps a pack from ramming the car ahead; in attract
    # the field is already spread, so the cap is skipped there.
    if not v['attract']:
        for o in v['karts']:
            if o is k or o['finish']:
                continue
            dt = o['total'] - k['total']
            if 0 < dt < 320:  # a rival just ahead, in the same lane zone
                dl = o['lat'] - k['lat']
                if -136 < dl < 136:
                    cap = (o['s'] * 98) >> 7
                    if tv > cap:
                        tv = cap
    if k['s'] < tv:
        return (si, 65536)
    return (si, 0)


@micropython.native
def _ai_items(k, v, fx):
    """AI item usage: mushrooms always, stars when they matter,
    traps when a rival is lined up."""
    if k['item'] < 0 or k['stuck'] > 0 or k['finish']:
        return
    it = k['item']
    use = False
    if it == PC.ITEM_MUSHROOM:
        use = True
    elif it == PC.ITEM_STAR:
        use = k['stuck'] > 0 or randint(0, 99) < 1
    else:
        for o in v['karts']:
            if o is k or o['finish']:
                continue
            dl = o['lat'] - k['lat']
            if -136 < dl < 136:
                if it == PC.ITEM_BANANA and 0 < k['total'] - o['total'] < 160:
                    use = True
                    break
                if it == PC.ITEM_POKEY and 0 < o['total'] - k['total'] < 320:
                    use = True
                    break
    if use:
        _use_item(k, v, fx)


def _make_kart(design, is_player, slot):
    st = PC.KART_STATS[design]
    skill = 65536
    if not is_player:
        skill = int((0.93 + 0.012 * (slot % 4)
                     + 0.01 * (randint(0, 7) / 7.0)) * 65536)
    k = {
        'i': design, 'ai': not is_player,
        'prog': PC.SPAWN_PROG[slot], 'lat': PC.SPAWN_LAT[slot],
        'total': PC.SPAWN_PROG[slot],
        'x': 0, 'y': 0, 's': 0, 'steer': 0,
        'sm': int(st[0] * 65536), 'ac': int(st[1] * 65536),
        # handling 0..1 (Q16) from the kart's turn-rate stat
        'hn': (st[2] - 300) * 436,
        # AI lane target (Q8); the player steers by buttons
        'err': 0 if is_player else (randint(0, 4) - 2) * 48,
        'item': -1, 'boost': 0, 'star': 0, 'stuck': 0,
        'invuln': 0, 'bump': 0, 'off': False,
        # boost speed multiplier (mushroom = BOOST_SMUL_Q; the drift
        # release sets its own charge-scaled value)
        'bp': BOOST_SMUL_Q,
        # drift state: 0 = no slide, 1 = sliding; charge in Q16 s
        'drift': 0, 'drcharge': 0,
        'lap': PC.SPAWN_PROG[slot] // PC.L8,
        'prevlap': PC.SPAWN_PROG[slot] // PC.L8,
        'prevprog': PC.SPAWN_PROG[slot] % PC.L8,
        'finish': 0, 'pos': slot + 1, 'skill': skill,
        # world-space heading (Q10, full circle 1024) and integrated
        # world position - only used by the free player kart in a
        # race; latsub is the inverse-projection window hint
        'ang': 0, 'wx8': 0, 'wy8': 0, 'free': False, 'latsub': 0,
    }
    wx8, wy8 = _kart_world8(k)
    k['x'] = wx8 << 13
    k['y'] = wy8 << 13
    s = _sub_of_prog8(k['prog'])
    # the nose starts along the course tangent at the spawn sub
    k['ang'] = PC.SANG[s]
    k['latsub'] = s
    k['wx8'] = wx8
    k['wy8'] = wy8
    return k

# --- Items -------------------------------------------------------------------
def _draw_item():
    r = randint(1, 100)
    acc = 0
    for i in range(4):
        acc += PC.ITEM_WEIGHTS[i]
        if r <= acc:
            return i
    return 0


def _use_item(k, v, fx):
    """Activate the held item (player via OK, AI via _ai_items)."""
    item = k['item']
    if item < 0 or k['stuck'] > 0:
        return
    k['item'] = -1
    if item == PC.ITEM_MUSHROOM:
        k['boost'] = BOOST_TIME_Q
        # the mushroom boost uses the standard multiplier, overriding
        # any charge-scaled one a previous drift release left behind
        k['bp'] = BOOST_SMUL_Q
        if k['ai'] is False and fx:
            fx.play(FXEngine.BOOST)
            if rumble:
                rumble(200)
    elif item == PC.ITEM_STAR:
        k['star'] = STAR_TIME_Q
        if k['ai'] is False and fx:
            fx.play(FXEngine.STAR)
    elif item == PC.ITEM_BANANA:
        # dropped a few units behind the thrower, in its own lane
        v['bananas'].append({'prog': k['prog'] - 24, 'lat': k['lat'],
                             't': BANANA_TIME_Q})
        if k['ai'] is False and fx:
            fx.play(FXEngine.BANANA)
    else:
        v['pokeys'].append({
            'prog': k['prog'] + 24, 'lat': k['lat'],
            'v': POKEY_SPEED_Q, 't': POKEY_TIME_Q,
            'stuck': 0, 'owner': k['i']})
        if k['ai'] is False and fx:
            fx.play(FXEngine.HIT)


@micropython.native
def _delta_prog8(k, prog8):
    """Signed track distance (Q8) from the point at prog8 to the
    kart's position, wrapped to (-L/2, L/2]."""
    d = (k['total'] - prog8) % PC.L8
    if d > PC.L8 >> 1:
        d -= PC.L8
    return d


@micropython.native
def _items_update(v, dt, fx):
    karts = v['karts']
    # item boxes: respawn, then pickup (track-space proximity)
    for b in v['boxes']:
        if b['item'] < 0:
            b['t'] -= dt
            if b['t'] <= 0:
                b['item'] = _draw_item()
                b['t'] = BOX_RESPAWN_Q
        else:
            for k in karts:
                if k['item'] >= 0 or k['finish']:
                    continue
                d = _delta_prog8(k, b['prog'])
                if -48 < d < 48:
                    dl = k['lat'] - b['lat']
                    if -48 < dl < 48:
                        k['item'] = b['item']
                        b['item'] = -1
                        b['t'] = BOX_RESPAWN_Q
                        if k['ai'] is False and fx:
                            fx.play(FXEngine.PICKUP)
                        break
    # bananas: static traps, no spin - a hit just stuns and drags
    if v['bananas']:
        alive = []
        for b in v['bananas']:
            b['t'] -= dt
            if b['t'] <= 0:
                continue
            hit = False
            for k in karts:
                if (k['finish'] or k['star'] > 0 or k['invuln'] > 0
                        or k['stuck'] > 0):
                    continue
                d = _delta_prog8(k, b['prog'])
                if -40 < d < 40:
                    dl = k['lat'] - b['lat']
                    if -40 < dl < 40:
                        k['stuck'] = STUCK_TIME_Q
                        k['invuln'] = BANANA_INVULN_Q
                        hit = True
                        if k['ai'] is False and fx:
                            fx.play(FXEngine.SPIN)
                            if rumble:
                                rumble(150)
                        elif fx:
                            fx.play(FXEngine.BANANA)
                        break
            if not hit:
                alive.append(b)
        v['bananas'] = alive
    # pokeys: rolling shells (they keep their lane, bounce off the
    # grass wall, and pause briefly after a bounce)
    if v['pokeys']:
        alive = []
        for p in v['pokeys']:
            p['t'] -= dt
            if p['t'] <= 0:
                continue
            if p['stuck'] > 0:
                p['stuck'] -= dt
            else:
                p['prog'] = (p['prog'] + fpmul(p['v'], dt) >> 13) % PC.L8
                if p['lat'] > 224:
                    p['lat'] = 208
                    p['v'] = (-p['v'] * 35) >> 7
                    p['stuck'] = POKEY_BOUNCE_Q
                elif p['lat'] < -224:
                    p['lat'] = -208
                    p['v'] = (-p['v'] * 35) >> 7
                    p['stuck'] = POKEY_BOUNCE_Q
            for k in karts:
                if (k['i'] == p['owner'] or k['finish'] or k['star'] > 0
                        or k['invuln'] > 0 or k['stuck'] > 0):
                    continue
                d = _delta_prog8(k, p['prog'])
                if -40 < d < 40:
                    dl = k['lat'] - p['lat']
                    if -40 < dl < 40:
                        k['stuck'] = POKEY_STUCK_Q
                        k['invuln'] = POKEY_INVULN_Q
                        break
            else:
                alive.append(p)
        v['pokeys'] = alive


@micropython.native
def _kart_collisions(v, fx):
    """Gentle kart-vs-kart: split the overlap along each kart's own
    right normal (each moves half) and share a small speed loss.
    No spins in this port - karts bump, they do not fly - and
    invulnerable karts pass straight through."""
    karts = v['karts']
    n = len(karts)
    for i in range(n):
        a = karts[i]
        if a['finish'] or a['invuln'] > 0:
            continue
        for j in range(i + 1, n):
            b = karts[j]
            if b['finish'] or b['invuln'] > 0:
                continue
            ax, ay = _kart_world8(a)
            bx, by = _kart_world8(b)
            dx = ax - bx
            dy = ay - by
            d2 = dx * dx + dy * dy
            if d2 >= 3136:  # 56^2 in Q8 (7 units center to center)
                continue
            d = _isqrt_small(d2)
            if d == 0:
                dx = 1
                d = 1
            sa = _sub_of_prog8(a['prog'])
            sb = _sub_of_prog8(b['prog'])
            pa = (dx * PC.SNX[sa] + dy * PC.SNY[sa]) >> 17
            pb = (dx * PC.SNX[sb] + dy * PC.SNY[sb]) >> 17
            if a['free']:
                # a free kart has no rail to shift along: push its
                # world position directly (prog/lat are re-derived on
                # the next step)
                a['wx8'] += pa
                a['wy8'] += pa
            else:
                a['lat'] += pa
            if b['free']:
                b['wx8'] -= pb
                b['wy8'] -= pb
            else:
                b['lat'] -= pb
            overlap = 56 - d
            pen = overlap * 585
            if pen > 9830:
                pen = 9830
            f = 65536 - (pen * 3) // 10
            a['s'] = (a['s'] * f) >> 16
            b['s'] = (b['s'] * f) >> 16
            if (overlap > 22 and fx
                    and (a['ai'] is False or b['ai'] is False)
                    and a['bump'] <= 0 and b['bump'] <= 0):
                a['bump'] = BUMP_FRAMES * DT
                b['bump'] = BUMP_FRAMES * DT
                fx.play(FXEngine.HIT)
                if rumble:
                    rumble(40)


@micropython.native
def _isqrt_small(v):
    """Integer sqrt for v <= 3136 (56^2) - a handful of binary-search
    steps, called only on actual kart contact, so no table needed."""
    lo = 0
    hi = 56
    while lo < hi:
        mid = (lo + hi + 1) >> 1
        if mid * mid <= v:
            lo = mid
        else:
            hi = mid - 1
    return lo

# --- Rendering ---------------------------------------------------------------
# The pseudo-3D pipeline. The world is flat, so a point's screen row
# depends only on its depth (sy = horizon + FCH/depth) and its screen
# x on its side offset (sx = center + side*FOV_F/depth) - the classic
# OutRun projection with the division turned into a lookup in the
# INV16 table. The road is painted one strip per subsegment, far to
# near; every sprite is drawn exactly once, far to near.
@micropython.native
def _scale_for(zc, k2, w8):
    """Sprite scale (Q16) for an asset of world width w8 at depth zc.
    k2 is the precomputed (65536*FOV_F/asset_width >> 8) factor from
    constants; the result is clamped to 1/32..3.0 so sprites near the
    camera do not blow up."""
    s = (k2 * w8 * PC.INV16[zc]) >> 8
    if s < 2048:
        return 2048
    if s > 196608:
        return 196608
    return s


@micropython.native
def _draw_sky(v):
    """The sky above the horizon. Color: five bands, the sun and two
    parallax hill layers that scroll with the camera's heading - they
    sweep across the sky when the road turns and stay put on the
    straights, the far layer at a quarter of the near layer's speed;
    the 128 px patterns wrap with the screen width.
    1-bit: a dotted ridge along the horizon."""
    if IS_THUMBY_COLOR:
        display.drawFilledRectangle(0, 0, PC.WIDTH, 8, PC.SKY1)
        display.drawFilledRectangle(0, 8, PC.WIDTH, 8, PC.SKY2)
        display.drawFilledRectangle(0, 16, PC.WIDTH, 8, PC.SKY3)
        display.drawFilledRectangle(0, 24, PC.WIDTH, 8, PC.SKY4)
        # Horizon haze band from row 32 down to the horizon; its
        # height rides HORIZON so the band stays sky when the
        # horizon is raised.
        display.drawFilledRectangle(0, 32, PC.WIDTH,
                                    PC.HORIZON - 32, PC.SKY_H)
        display.drawFilledRectangle(96, 8, 8, 1, PC.SUN)
        display.drawFilledRectangle(100, 6, 4, 4, PC.SUN)
        ck = v['karts'][v['cam_idx']]
        # Camera heading in Q10 (full circle 1024).  A free kart
        # supplies its own nose angle; an on-rail kart interpolates
        # the two sub tangents inside its own sub, so the scroll is
        # continuous instead of a staircase that jumps once per sub.
        s = _sub_of_prog8(ck['prog'])
        if ck['free']:
            sang = ck['ang']
        else:
            s1 = (s + 1) % PC.SUB_N
            seg = (PC.SCUM[s1] - PC.SCUM[s]) % PC.L8
            f = ck['prog'] % PC.L8 - PC.SCUM[s]
            dl = ((PC.SANG[s1] - PC.SANG[s] + 512) & 1023) - 512
            sang = (PC.SANG[s] + (f * dl) // seg) & 1023
        prev = v.get('sangprev')
        if prev is not None and v.get('camprev') == v['cam_idx']:
            # Unwrap the heading delta onto the sky scroll, landing
            # zero on straights: straights hold the hills, turns
            # sweep them with the far road.  The old convention
            # turned every straight into a +512 step, strobing the
            # near hills.  On a camera switch (attract lead change,
            # attract -> race) skip the delta: the two headings are
            # unrelated and the difference would snap the sky.
            d = ((sang - prev + 512) & 1023) - 512
            # One frame's real turn is a handful of units (the sharpest
            # corner on the whole course is about 3.5).  The attract demo
            # teleports its camera kart along the track (respawn cuts),
            # which used to push a +-310 heading jump through this
            # accumulator and strobe the hills ~20 px a frame - the
            # flicker.  Anything a kart could not physically turn in a
            # single frame is swallowed here.
            if d > 16:
                d = 16
            elif d < -16:
                d = -16
            v['skyoff'] = (v['skyoff'] + d) & 16383
        v['sangprev'] = sang
        v['camprev'] = v['cam_idx']
        off = (-v['skyoff'] >> 6) & 127
        for row, runs in PC.HILL_FAR_RUNS:
            for x0, x1 in runs:
                w = x1 - x0 + 1
                x = x0 - off
                display.drawFilledRectangle(x, row, w, 1, PC.HILL_FAR)
                display.drawFilledRectangle(x + 128, row, w, 1,
                                            PC.HILL_FAR)
        off = (-v['skyoff'] >> 4) & 127
        for row, runs in PC.HILL_NEAR_RUNS:
            for x0, x1 in runs:
                w = x1 - x0 + 1
                x = x0 - off
                display.drawFilledRectangle(x, row, w, 1, PC.HILL_NEAR)
                display.drawFilledRectangle(x + 128, row, w, 1,
                                            PC.HILL_NEAR)
    else:
        display.fill(PC.COLOR_BG)
        for x in range(0, PC.WIDTH, 2):
            display.drawFilledRectangle(x, PC.HORIZON - 1, 1, 1,
                                        PC.COLOR_LINE)
            display.drawFilledRectangle(x + 1, PC.HORIZON - 3, 1, 1,
                                        PC.COLOR_LINE)


@micropython.native
def _line(x0, y0, x1, y1, col):
    """drawLine with direction normalization: the Thumby's 1-bit driver
    turns axis-aligned lines into filled rectangles and early-returns
    on negative sizes, so a line drawn "backwards" draws nothing. The
    color Bresenham does not care, so this is a no-op there."""
    if x0 == x1 and y1 < y0:
        y0, y1 = y1, y0
    elif y0 == y1 and x1 < x0:
        x0, x1 = x1, x0
    display.drawLine(x0, y0, x1, y1, col)


# The row where the 50% fog begins (the horizon on 1-bit, which has
# no fog: full colors all the way to the far plane).
if IS_THUMBY_COLOR:
    FOGMID_Y = PC.HORIZON + ((PC.FCH * PC.INV16[PC.FOG_MID8]) >> 16)
else:
    FOGMID_Y = -1


@micropython.native
def _proj_pt(x8, y8, cam):
    """Project a Q8 world point to (sx, sy, zc) without culling - the
    caller must keep the depth inside the table range."""
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    dx = x8 - camx8
    dy = y8 - camy8
    zc = (dx * hx + dy * hy) >> 16
    if zc < 1:
        zc = 1
    elif zc > 1535:
        zc = 1535
    xc = (dx * rx + dy * ry) >> 16
    ix = PC.INV16[zc]
    sx = cx + ((xc * PC.FOV_F * ix) >> 16)
    sy = cy + ((fch * ix) >> 16)
    return (sx, sy, zc)


@micropython.native
def _depth(x8, y8, cam):
    """View-space depth (Q8) of a world point."""
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    return ((x8 - camx8) * hx + (y8 - camy8) * hy) >> 16


@micropython.native
def _depth_line(cam, x1, y1, x2, y2, col):
    """A line between two Q8 world points, clipped to the
    near..fog depth band."""
    z1 = _depth(x1, y1, cam)
    z2 = _depth(x2, y2, cam)
    if (z1 < PC.NEAR8 and z2 < PC.NEAR8) \
            or (z1 > PC.FOG_FAR8 and z2 > PC.FOG_FAR8):
        return
    if z1 < PC.NEAR8:
        t = (PC.NEAR8 - z1) * 4096 // (z2 - z1)
        p1 = (x1 + (((x2 - x1) * t) >> 12),
              y1 + (((y2 - y1) * t) >> 12))
    else:
        p1 = (x1, y1)
    if z2 > PC.FOG_FAR8:
        t = (PC.FOG_FAR8 - z1) * 4096 // (z2 - z1)
        p2 = (x2 + (((x1 - x2) * t) >> 12),
              y2 + (((y1 - y2) * t) >> 12))
    else:
        p2 = (x2, y2)
    s1 = _proj_pt(p1[0], p1[1], cam)
    s2 = _proj_pt(p2[0], p2[1], cam)
    _line(s1[0], s1[1], s2[0], s2[1], col)


@micropython.native
def _clip_project(a, b, cam):
    """Project the road strip between subsegment a (near) and b
    (far): the four road corners (centerline +- road half width),
    clipped against the near and the fog plane, then projected.
    Returns (screen points, zmin, zlo, zhi) in loop order, or None
    when the strip is out of the visible band.  zmin is the smallest
    depth among the clipped points (the painter's-order key); zlo /
    zhi are the true depth span of the four original corners, so the
    caller can clamp drawing to rows that actually belong to this
    strip instead of rows the clipping artificially added."""
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    pts = []
    zlo = 32000
    zhi = -32000
    for s, side in ((a, -1), (b, -1), (b, 1), (a, 1)):
        x = PC.SCX[s] + ((PC.SNX[s] * (side * HW8)) >> 16)
        y = PC.SCY[s] + ((PC.SNY[s] * (side * HW8)) >> 16)
        zc = ((x - camx8) * hx + (y - camy8) * hy) >> 16
        pts.append(((x, y), zc))
        if zc < zlo:
            zlo = zc
        if zc > zhi:
            zhi = zc
    for plane, keep in ((PC.NEAR8, 1), (PC.FOG_FAR8, -1)):
        out = []
        n = len(pts)
        for i in range(n):
            (pi, zi) = pts[i]
            (pj, zj) = pts[(i + 1) % n]
            ki = (zi >= plane) if keep > 0 else (zi <= plane)
            kj = (zj >= plane) if keep > 0 else (zj <= plane)
            if ki:
                out.append((pi, zi))
            if ki != kj:
                t = (plane - zi) * 4096 // (zj - zi)
                out.append(((pi[0] + (((pj[0] - pi[0]) * t) >> 12),
                             pi[1] + (((pj[1] - pi[1]) * t) >> 12)),
                            plane))
        if len(out) < 3:
            return None
        pts = out
    res = []
    zmin = 1536
    for (p, zc) in pts:
        if zc < 1 or zc > 1535:
            return None
        if zc < zmin:
            zmin = zc
        dx = p[0] - camx8
        dy = p[1] - camy8
        xc = (dx * rx + dy * ry) >> 16
        ix = PC.INV16[zc]
        sx = cx + ((xc * PC.FOV_F * ix) >> 16)
        sy = cy + ((fch * ix) >> 16)
        res.append((sx, sy))
    return (res, zmin, zlo, zhi)


@micropython.native
def _row_xs(pts, y):
    """Min and max x of the (convex) strip polygon at row y."""
    lo = 32000
    hi = -32000
    n = len(pts)
    for i in range(n):
        x1 = pts[i][0]
        y1 = pts[i][1]
        x2 = pts[(i + 1) % n][0]
        y2 = pts[(i + 1) % n][1]
        if y1 == y2:
            continue
        if y1 > y2:
            y1, y2 = y2, y1
            x1, x2 = x2, x1
        if y < y1 or y > y2:
            continue
        # Q8 interpolation factor. NOTE: // binds tighter than <<, so
        # this must stay parenthesized: (y-y1) << 8 // (y2-y1) would
        # parse as (y-y1) << (8 // (y2-y1)) and collapse the scale.
        t = ((y - y1) * 256) // (y2 - y1)
        x = x1 + (((x2 - x1) * t) >> 8)
        if x < lo:
            lo = x
        if x > hi:
            hi = x
    return (lo, hi)


@micropython.native
def _lane_trace(a, b, cam):
    """World-space centerline trace for the strip between subsegments
    a and b: the chord SCX/SCY[a] -> SCX/SCY[b], clipped into the
    visible depth band and projected.  Returns (xN, yN, wN, xF, yF,
    wF, za, zb) - the centerline's screen position and road half-width
    at the near and far end plus the chord's clipped depth span - or
    None when the chord lies entirely outside
    the band.  The lane dashes anchor to this trace instead of the
    clipped span center: the near-plane clip is symmetric about the
    camera axis, which pinned the old center line to the screen center
    (the kart) while the road bent away from it.
    """
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    xa = PC.SCX[a]
    ya = PC.SCY[a]
    xb = PC.SCX[b]
    yb = PC.SCY[b]
    za = ((xa - camx8) * hx + (ya - camy8) * hy) >> 16
    zb = ((xb - camx8) * hx + (yb - camy8) * hy) >> 16
    # Clip the chord into [NEAR8, FOG_FAR8].
    if za < PC.NEAR8:
        if zb <= PC.NEAR8:
            return None
        t = (PC.NEAR8 - za) * 4096 // (zb - za)
        xa = xa + (((xb - xa) * t) >> 12)
        ya = ya + (((yb - ya) * t) >> 12)
        za = PC.NEAR8
    if zb > PC.FOG_FAR8:
        if za >= PC.FOG_FAR8:
            return None
        t = (PC.FOG_FAR8 - za) * 4096 // (zb - za)
        xb = xb + (((xa - xb) * t) >> 12)
        yb = yb + (((ya - yb) * t) >> 12)
        zb = PC.FOG_FAR8
    if za < 1 or zb < 1 or za > 1535 or zb > 1535:
        return None
    end = []
    for (x, y, z) in ((xa, ya, za), (xb, yb, zb)):
        ix = PC.INV16[z]
        xc = ((x - camx8) * rx + (y - camy8) * ry) >> 16
        end.append((cx + ((xc * PC.FOV_F * ix) >> 16),
                    cy + ((fch * ix) >> 16),
                    (HW8 * PC.FOV_F * ix) >> 16))
    return (end[0][0], end[0][1], end[0][2],
            end[1][0], end[1][1], end[1][2], za, zb)


@micropython.native
def _lat_trace(a, b, cam, lat8):
    """The chord of the strip between subsegments a and b offset
    laterally by lat8 (Q8 from the centerline), clipped to the visible
    depth band.  Returns (xN, yN, xF, yF): the boundary's screen
    segment, or None when it lies entirely outside the band.  Used to
    anchor the start/finish checkerboard columns to the WORLD road grid
    - the cells then keep their true perspective when the camera runs
    off the centerline or at an angle to the road, instead of being
    squeezed into equal fractions of the painted span."""
    hx, hy, rx, ry, camx8, camy8, cx, cy, fch = cam
    xa = PC.SCX[a] + ((PC.SNX[a] * lat8) >> 16)
    ya = PC.SCY[a] + ((PC.SNY[a] * lat8) >> 16)
    xb = PC.SCX[b] + ((PC.SNX[b] * lat8) >> 16)
    yb = PC.SCY[b] + ((PC.SNY[b] * lat8) >> 16)
    za = ((xa - camx8) * hx + (ya - camy8) * hy) >> 16
    zb = ((xb - camx8) * hx + (yb - camy8) * hy) >> 16
    if za < PC.NEAR8:
        if zb <= PC.NEAR8:
            return None
        t = (PC.NEAR8 - za) * 4096 // (zb - za)
        xa = xa + (((xb - xa) * t) >> 12)
        ya = ya + (((yb - ya) * t) >> 12)
        za = PC.NEAR8
    if zb > PC.FOG_FAR8:
        if za >= PC.FOG_FAR8:
            return None
        t = (PC.FOG_FAR8 - za) * 4096 // (zb - za)
        xb = xb + (((xa - xb) * t) >> 12)
        yb = yb + (((ya - yb) * t) >> 12)
        zb = PC.FOG_FAR8
    if za < 1 or zb < 1 or za > 1535 or zb > 1535:
        return None
    seg = []
    for (x, y, z) in ((xa, ya, za), (xb, yb, zb)):
        ix = PC.INV16[z]
        xc = ((x - camx8) * rx + (y - camy8) * ry) >> 16
        seg.append((cx + ((xc * PC.FOV_F * ix) >> 16),
                    cy + ((fch * ix) >> 16)))
    return (seg[0][0], seg[0][1], seg[1][0], seg[1][1])


@micropython.native
def _draw_strips(v, cam):
    """Everything below the horizon: the grass base, then the road
    strip by strip from far to near.  The optics follow the reference
    racer (and SevEngine's distance shading): alternating asphalt
    shades with red/white rumble curbs at the road edges, cream lane
    dashes anchored to the world centerline, the 8-column checkered
    start band, and a smooth eight-level distance haze that fades each
    strip toward the horizon color instead of snapping at a fog row.
    """
    W = PC.WIDTH
    H = PC.HEIGHT
    cy = cam[7]
    fch = cam[8]
    COL = IS_THUMBY_COLOR
    display.drawFilledRectangle(0, PC.HORIZON, W, H - PC.HORIZON,
                                PC.COLOR_GRASS_A)
    p = v['karts'][v['cam_idx']]
    s0 = _sub_of_prog8(p['prog'])
    n = PC.SUB_N
    strips = []
    # a few subsegments behind the camera kart as well: the near
    # plane clipping trims whatever projects behind the camera, and
    # the rest fills the road down to the bottom row
    for i in range(-12, PC.DRAW_N):
        a = (s0 + i) % n
        b = (a + 1) % n
        r = _clip_project(a, b, cam)
        if r is None:
            continue
        pts, zmin, zlo, zhi = r
        ytop = H
        ybot = -1
        for x, y in pts:
            if y < ytop:
                ytop = y
            if y > ybot:
                ybot = y
        if ytop < PC.HORIZON:
            ytop = PC.HORIZON
        if ybot > H - 1:
            ybot = H - 1
        # Keep the strip inside the rows its own depth span owns:
        # clipping pushes the polygon beyond its real corners,
        # and painting there would overwrite the road of the
        # strips that actually cover those rows.
        ze_hi = zhi if zhi < PC.FOG_FAR8 else PC.FOG_FAR8
        y_far = cy + ((fch * PC.INV16[ze_hi]) >> 16)
        if ytop < y_far:
            ytop = y_far
        ze_lo = zlo if zlo > PC.NEAR8 else PC.NEAR8
        if ze_lo > 1535:
            continue
        y_near = cy + ((fch * PC.INV16[ze_lo]) >> 16)
        if ybot > y_near:
            ybot = y_near
        if ytop > ybot:
            continue
        tr = _lane_trace(a, b, cam) if COL else None
        # Start/finish band: nine boundary chords of the WORLD
        # road grid (k=0 left edge, k=8 right edge) anchored to
        # lateral offsets like the lane dashes, so the checkerboard
        # keeps true perspective when the camera is off the
        # centerline or yawed, not equal fractions of the span.
        bnd = None
        if (a < 3 or a > n - 3) and i >= 0:
            bnd = []
            for k in range(9):
                bnd.append(_lat_trace(a, b, cam,
                                      -HW8 + ((k * HW8 * 2) >> 3)))
        strips.append((ytop, ybot, pts, a, i, zlo, tr, bnd))
    # Painter's order: far -> near by the TRUE near-corner depth
    # zlo (quantized to an 8 unit grid), ties broken by the loop
    # offset i so a curve fold keeps one owner every frame.  Raw
    # depths let the fold pair trade rows each tick (speckled
    # flicker); clip-polluted zmin collapses several strips to one
    # key near the camera.  Insertion sort in place - no key tuples.
    for j in range(1, len(strips)):
        k = strips[j]
        kz = k[5] >> 3
        ki = k[4]
        p = j - 1
        while p >= 0:
            pz = strips[p][5] >> 3
            if pz < kz or (pz == kz and strips[p][4] < ki):
                strips[p + 1] = strips[p]
                p -= 1
            else:
                break
        strips[p + 1] = k
    toprow = H
    for s in strips:
        if s[0] < toprow:
            toprow = s[0]
    # Row-major paint: every screen row is painted exactly once,
    # so overlapping strip row-ranges (real on curve folds and at
    # the near plane) can no longer wipe each other's road. Road
    # pieces - paint, curbs, dashes - are painted far -> near over
    # the grass stripe, so a nearer quad overwrites a farther dash
    # where the camera ray hits nearer road first.
    # Road edge memory: keeps the last row's clamped edges only to
    # bridge the one- or two-row holes that projection rounding
    # leaves between strip footprints on a curve crest.
    prev_nxl = None
    prev_nxr = None
    last_road = None
    bridge = 0
    blk = PC.STRIP_BLOCK
    claim = []
    dashes = []
    for y in range(PC.HORIZON, H):
        del claim[:]
        for s in strips:
            if s[0] <= y <= s[1]:
                claim.append(s)
        if not claim:
            if prev_nxl is not None and last_road is not None \
                    and bridge > 0:
                display.drawFilledRectangle(prev_nxl, y,
                                            prev_nxr - prev_nxl, 1,
                                            last_road)
                bridge -= 1
            else:
                prev_nxl = prev_nxr = None
            continue
        bridge = 2
        # Occlusion reference = nearest claimant with a REAL span
        # at this row; other claimants may not paint outside it.
        # Without the clamp, fold rows let far claimants spill
        # asphalt onto the grass beside the near road.
        # The reference is NOT simply claim[-1]: the closest quad
        # can turn edge-on at the fold rows.  Walk back until one
        # claimant has a positive span - that strip is the clamp
        # reference and the curb/dash anchor below.
        ci_n = len(claim) - 1
        while ci_n >= 0:
            cxl, cxr = _row_xs(claim[ci_n][2], y)
            if cxl < 0:
                cxl = 0
            if cxr > W - 1:
                cxr = W - 1
            if cxr > cxl:
                break
            ci_n -= 1
        if ci_n >= 0:
            near = claim[ci_n]
            nnxl, nnxr = cxl, cxr
            nn_ok = True
        else:
            # Every claimant is edge-on at this row: nothing valid to
            # occlude, so the walk paints nothing here and the bridge
            # memory carries the row instead.
            near = claim[-1]
            nnxl, nnxr = _row_xs(near[2], y)
            if nnxl < 0:
                nnxl = 0
            if nnxr > W - 1:
                nnxr = W - 1
            nn_ok = nnxr > nnxl
        # Grass stripe: the reference alternates its two greens on
        # the same world blocks that key asphalt and rumble, so
        # the stripes scroll with the road.  World-anchored keying
        # is deliberate: camera-relative keying pins the bands to
        # the screen and the high-contrast curb stripes then flip
        # in place at fixed boundary rows.  The nearest strip's
        # haze level sets the fade of the stripe.
        if COL:
            gz = near[5]
            if gz < PC.NEAR8:
                gz = PC.NEAR8
            elif gz > PC.FOG_FAR8:
                gz = PC.FOG_FAR8
            lg = PC.FOG_LEVEL[gz]
            if ((near[3] // blk) & 1) == 0:
                grass_c = PC.FOGT_GRASS_A[lg]
            else:
                grass_c = PC.FOGT_GRASS_B[lg]
        else:
            grass_c = (PC.COLOR_GRASS_B if ((near[3] // blk) & 1)
                       else PC.COLOR_GRASS_A)
        display.drawFilledRectangle(0, y, W, 1, grass_c)
        del dashes[:]
        road_c = None
        band_cells = False
        painted = False
        crease_gap = False
        pmin = W
        pmax = -1
        for ci, (ytop, ybot, pts, a, i, zlo, tr, bnd) in enumerate(claim):
            xl, xr = _row_xs(pts, y)
            if xl < 0:
                xl = 0
            if xr > W - 1:
                xr = W - 1
            if xr <= xl:
                continue
            if nn_ok and ci != ci_n:
                if xr <= nnxl or xl >= nnxr:
                    # DISJOINT from the near span: visible road
                    # ahead, not occluded grass - paint its own
                    # span and close the seam with the crease fill.
                    crease_gap = True
                else:
                    # A far claimant OVERLAPPING the near road may
                    # not spill past the near edges: beyond them
                    # the camera ray met the near surface first.
                    if xl < nnxl:
                        xl = nnxl
                    if xr > nnxr:
                        xr = nnxr
                    if xr <= xl:
                        continue
            if COL:
                lev = zlo
                if lev < PC.NEAR8:
                    lev = PC.NEAR8
                elif lev > PC.FOG_FAR8:
                    lev = PC.FOG_FAR8
                lev = PC.FOG_LEVEL[lev]
                alt = ((a // blk) & 1) == 0
                road_c = PC.FOGT_ROAD_A[lev] if alt else PC.FOGT_ROAD_B[lev]
                lane_c = PC.FOGT_LANE[lev]
                chk_a = PC.FOGT_CHECK_A[lev]
                chk_b = PC.FOGT_CHECK_B[lev]
            else:
                road_c = PC.COLOR_ROAD
                chk_a = PC.COLOR_CHECK_A
                chk_b = PC.COLOR_CHECK_B
                lane_c = None
            # Road for every claimant, start/finish strips included:
            # the checkerboard is painted in this far -> near walk,
            # keyed on the WORLD grid (the bnd boundary chords built
            # at the strip) so the cells keep their size and true
            # perspective across strips and off-center cameras.
            # Keying the band on one claimant's clamped span made
            # whole rows flicker while ownership rotated between
            # the three line strips.  Strips wrapped behind the
            # camera (loop field < 0) are skipped so a crossing
            # cannot tile the screen.
            display.drawFilledRectangle(xl, y, xr - xl, 1, road_c)
            painted = True
            if xl < pmin:
                pmin = xl
            if xr - 1 > pmax:
                pmax = xr - 1
            if (a < 3 or a > n - 3) and i >= 0 and bnd is not None:
                dyb = ybot - ytop
                if dyb > 0:
                    r = ((ybot - y) * 4) // dyb
                    if r > 3:
                        r = 3
                else:
                    r = 0
                # Screen x of each world-grid boundary at this row:
                # linear along its projected chord, like the road
                # polygon's scanline interpolation.  A screen row
                # is a constant-depth line, so the cell edges land
                # on the true grid intersections.
                xs = [None] * 9
                for k in range(9):
                    bd = bnd[k]
                    if bd is None:
                        continue
                    yN = bd[1]
                    yF = bd[3]
                    if yF == yN:
                        continue
                    t = ((y - yN) * 256) // (yF - yN)
                    if t < 0:
                        t = 0
                    elif t > 256:
                        t = 256
                    xs[k] = bd[0] + (((bd[2] - bd[0]) * t) >> 8)
                for k in range(8):
                    x0 = xs[k]
                    x1 = xs[k + 1]
                    if x0 is None or x1 is None:
                        # Chord behind the near plane at this row
                        # (camera on the line in a hairpin fold):
                        # fall back to the screen fraction.
                        x0 = xl + (((xr - xl) * k) >> 3)
                        x1 = xl + (((xr - xl) * (k + 1)) >> 3)
                    if x1 < x0:
                        x0, x1 = x1, x0
                    if x0 < xl:
                        x0 = xl
                    if x1 > xr:
                        x1 = xr
                    if x1 <= x0:
                        continue
                    cc = chk_a if ((k + r) & 1) == 0 else chk_b
                    display.drawFilledRectangle(x0, y, x1 - x0, 1, cc)
                band_cells = True
            # Dash sources: every claimant's own centerline trace
            # at this row, collected far -> near with its
            # post-occlusion span, sub parity and fog color.
            # Whether the row carries ink is decided once after
            # the walk, on the depth the row itself projects at;
            # the walk must not pick a single claimant - on a
            # curve the nearest chord need not reach the row.
            if COL and tr is not None:
                dashes.append((tr, xl, xr, a, lane_c))
        if painted and (not nn_ok or crease_gap) \
                and not band_cells and pmax > pmin:
            # Curve crease: the near quad turned edge-on or a far
            # ribbon sat disjoint beside the near span, so the walk
            # left green seams between separate spans.  The band
            # the eye follows is their UNION - close every seam
            # inside it with asphalt so the fold reads as one
            # ribbon.  (start/finish band excluded: its tiles own
            # the row).
            display.drawFilledRectangle(pmin, y, pmax - pmin + 1, 1,
                                        road_c)
        if painted:
            # Silhouette memory = union of the asphalt actually
            # painted, not the near strip's own edges: on a fold
            # row the near span is a sliver inside the band.
            prev_nxl = pmin
            prev_nxr = pmax + 1
        elif prev_nxl is not None and bridge > 0 \
                and last_road is not None:
            # All claimants projected edge-on: no asphalt was
            # painted and the row would read as a green hole in
            # the road.  Carry the previous row's road down the
            # gap, and skip markings - curbs and dashes without
            # asphalt read as floating dots.  The memory stays
            # so a second hole row continues the same fill.
            display.drawFilledRectangle(prev_nxl, y,
                                        prev_nxr - prev_nxl, 1,
                                        last_road)
            bridge -= 1
            painted = True
            continue
        else:
            prev_nxl = prev_nxr = None
            continue
        if road_c is not None:
            # Rows whose claimants are all degenerate paint no
            # asphalt; there is no road color to remember for them.
            last_road = road_c
        na = near[3]
        # Lane dashes and curbs yield while this row carries
        # start/finish cells.  Keyed on what was actually painted
        # here, not on which strip owns the row, so the decision
        # holds while ownership rotates every few ticks.
        band_hit = band_cells
        # Lane-ink decision: the row projects at a fixed camera
        # depth z(y) = fch // (y - cy).  Pick the nearest
        # claimant whose chord covers that depth and take the
        # dash parity from ITS sub, not the reference strip.
        # Keying ink on the near sub's parity blanked long far
        # stretches at once, and chord spans and strip spans
        # disagree on curves (polygon corners add the lateral
        # half width), so far rows fell outside and were dropped.
        # When no chord reaches the row, extrapolate from the
        # nearest trace (clamped t) instead of dropping it, so
        # the center line converges at the vanishing point.
        # A chord collapsed to one row (dy == 0) uses t = 0.
        dash = None
        dpar = na
        if dashes:
            z_y = fch // (y - cy) if y > cy else PC.FOG_FAR8 + 1
            bza = 32000
            for cand in dashes:
                za2 = cand[0][6]
                zb2 = cand[0][7]
                if za2 <= z_y <= zb2 and za2 < bza:
                    bza = za2
                    dash = cand
            if dash is None:
                dash = dashes[-1]
            dpar = dash[3]
        if not band_hit and dash is not None and pmax - pmin >= 3 \
                and dpar % 3 != 2:
            # A fold neck this narrow cannot carry lane ink:
            # the marks would cover every asphalt pixel.
            # A single center dash, not a pair hugging the road
            # edges.  Ink on/off follows the owner sub's parity
            # in the 3-sub lattice (ink on 3k and 3k+1, gap on
            # 3k+2), so the dash scrolls at its natural period;
            # one dash per row reads as scrolling dashes.
            # The dash's x rides the owning strip's centerline
            # TRACE, never the clipped span's center: the near-
            # plane clip is symmetric about the camera axis, so
            # span-centered dashes pinned the line to the player
            # kart while the road bent away.  The trace converges
            # at the vanishing point like the asphalt edges.  Ink
            # may never land outside the asphalt painted at this
            # row (span and trace center are clamped into the
            # painted bounds), and narrow rows still get their
            # single center dash rather than blanking.
            tr, dxl, dxr, da, lane_c = dash
            xN, yN, wN = tr[0], tr[1], tr[2]
            xF, yF, wF = tr[3], tr[4], tr[5]
            if dxl < pmin:
                dxl = pmin
            if dxr > pmax + 1:
                dxr = pmax + 1
            if dxr > dxl:
                dy = yF - yN
                if dy == 0:
                    t = 0
                else:
                    t = ((y - yN) * 256) // dy
                    if t < 0:
                        t = 0
                    elif t > 256:
                        t = 256
                cxc = xN + (((xF - xN) * t) >> 8)
                hw = wN + (((wF - wN) * t) >> 8)
                dw = hw // 25
                cap = (dxr - dxl) // 25
                if cap < dw:
                    dw = cap
                if dw < 1:
                    dw = 1
                # Clamp the trace center INTO the painted span:
                # in a curve the far centerline leaves the near
                # span while the asphalt stays wide enough.
                lo = pmin + dw // 2
                hi = pmax + 1 - dw + dw // 2
                if cxc < lo:
                    cxc = lo
                elif cxc > hi:
                    cxc = hi
                display.drawFilledRectangle(
                    cxc - dw // 2, y, dw, 1, lane_c)
        if not band_hit:
            # Rumble curbs belong to the NEAREST road surface:
            # painted at the near claimant's own edges with its
            # own parity color, so they track the road the eye
            # sees and fade with its haze.  Painting them at the
            # union extremes let folds hand the extreme between
            # far claimants - stripes marching down the middle of
            # the road.  Edges projecting past the screen border
            # are skipped (no stripes pinned to the sides).
            # Parity is one sub: longer periods banded the field.
            nrxl, nrxr = _row_xs(near[2], y)
            nxl = nrxl
            nxr = nrxr
            if nxl < 0:
                nxl = 0
            if nxr > W - 1:
                nxr = W - 1
            if nxr <= nxl or nxr - nxl <= 3:
                # No curbs on degenerate or neck-width spans: the
                # marks would cover the sliver entirely.  The
                # painted-union memory survives here, so hole
                # rows below can still be bridged.
                continue
            if COL:
                nlv = near[5]
                if nlv < PC.NEAR8:
                    nlv = PC.NEAR8
                elif nlv > PC.FOG_FAR8:
                    nlv = PC.FOG_FAR8
                nlv = PC.FOG_LEVEL[nlv]
                # Stripe period widens with the haze: one sub
                # covers many rows near the camera (short
                # transverse marks) but barely a row far out,
                # where one-sub parity flipped color every row -
                # dotted noise fading into the sky.  2/4/8 subs
                # far out keep each stripe longer than a row.
                sh = 0 if nlv < 2 else 1 if nlv < 4 \
                    else 2 if nlv < 6 else 3
                # Subdivide each sub into two world-fixed stripes:
                # one sub covers dozens of rows near the camera,
                # so one-sub parity painted whole quads a single
                # color.  Half-sub stripes alternate like the
                # reference rumble, and the stripe index na*2+p
                # stays continuous across the strip border so the
                # pattern scrolls instead of shivering.
                dy0 = near[1] - near[0]
                if dy0 > 0:
                    p = ((y - near[0]) * 2) // dy0
                    if p > 1:
                        p = 1
                else:
                    p = 0
                nalt = (((na * 2 + p) >> sh) & 1) == 0
                nrum = (PC.FOGT_CURB_A[nlv] if nalt
                        else PC.FOGT_CURB_B[nlv])
                rb = (nxr - nxl) // 20
                if rb < 1:
                    rb = 1
                elif rb > 3:
                    rb = 3
                # On a fold row a disjoint far span can reach past
                # a near edge and the crease fill carries asphalt
                # out to that extreme: a curb at the near edge is
                # then an INTERIOR mark, a stripe floating mid-
                # road.  A near edge strictly inside the painted
                # union is not a visible edge - skip that side.
                if nrxl >= 0 and nrxl <= pmin:
                    display.drawFilledRectangle(nxl, y, rb, 1, nrum)
                if nrxr <= W - 1 and nrxr >= pmax + 1:
                    display.drawFilledRectangle(nxr - rb, y, rb, 1,
                                                nrum)
            else:
                nrum = PC.COLOR_LINE
                if nrxl >= 0 and nrxl <= pmin:
                    display.drawFilledRectangle(nxl, y, 1, 1, nrum)
                if nrxr <= W - 1 and nrxr >= pmax + 1:
                    display.drawFilledRectangle(nxr, y, 1, 1, nrum)
            prev_nxl = nxl
            prev_nxr = nxr
    if IS_THUMBY_COLOR and toprow > PC.HORIZON:
        display.drawFilledRectangle(0, PC.HORIZON, W,
                                    toprow - PC.HORIZON, PC.SKY_H)


@micropython.native
def _append_obj(o, kind, ref, cam, W, H, dl):
    """Project a track-space object into the sprite queue with its
    damped depth; off screen, drop the damping so re-entry starts
    from the raw depth."""
    wx, wy = _tp8(o['prog'], o['lat'])
    r = _proj(wx, wy, cam)
    if r is not None and -64 <= r[0] <= W + 64 \
            and -64 <= r[1] <= H + 64:
        zs = _damped_zc(o, 'zs', r[2])
        dl.append((r[2], kind, ref, r[0], r[1], zs))
    else:
        o['zs'] = None


@micropython.native
def _draw_sprites(v, cam):
    """Every object in the world, drawn exactly once, far to near.
    The player's fixed screen slot is drawn last, after every other
    sprite, so nothing can paint over him; the far side of the loop
    projects behind the camera and is simply gone."""
    W = PC.WIDTH
    H = PC.HEIGHT
    dl = []
    # Every object carries its damped depth (zs) into the draw
    # pass: the raw depth wobbles with the heading swing and
    # re-shuffled the pixel scale of distant sprites every other
    # frame.  Damping crosses each boundary once, smoothly.
    for j, d in enumerate(PC.DECOS):
        r = _proj(d[1] * 8, d[2] * 8, cam)
        if r is not None and -64 <= r[0] <= W + 64 \
                and -64 <= r[1] <= H + 64:
            # Damp per deco INDEX, not per asset ref: several
            # decos share a sprite, and a ref-keyed slot mixed
            # their depths (trees drew with the other's scale).
            zs = _damped_zc(_ZSD, j, r[2])
            dl.append((r[2], 0, d[0], r[0], r[1], zs))
        else:
            # Off-screen objects drop the damped depth: re-entry
            # damped from a stale value draws the first frame at
            # the wrong size and then shrinks/grows into place.
            _ZSD[j] = None
    for b in v['boxes']:
        if b['item'] < 0:
            # Spent box: drop the damped depth so a respawn at
            # a new spot does not size itself from the old one.
            b['zs'] = None
            continue
        _append_obj(b, 1, b["item"], cam, W, H, dl)
    for b in v['bananas']:
        _append_obj(b, 2, PC.ITEM_BANANA, cam, W, H, dl)
    for p in v['pokeys']:
        _append_obj(p, 3, PC.ITEM_POKEY, cam, W, H, dl)
    for i in range(len(v['karts'])):
        k = v['karts'][i]
        # Karts go through the hysteresis gate: the raw depth
        # swing crossed the near plane and the margins within a
        # tick or two and the plain gate flicked them in and
        # out - inclusion pops damping cannot reach.
        g = _kart_gate(k, k['x'] >> 13, k['y'] >> 13, cam, W, H)
        if g is not None:
            dl.append((g[0], 4, i, g[1], g[2], k['zs']))
    dl.sort(reverse=True)
    me = None
    for zc, kind, ref, sx, sy, zs in dl:
        if kind == 4:
            k = v['karts'][ref]
            if k['ai'] is False:
                # The player rides a fixed screen slot: the
                # camera sits right behind him, so his depth
                # and scale never oscillate.  Drawn LAST - a
                # rival in the camera-player corridor used to
                # paint right over him.
                me = k
                continue
            # zs arrives 4-unit quantized AND damped from the
            # collection pass: the heading swing is gone, so
            # scale and fade boundaries cross once, smoothly.
            sc = _scale_for(zs, PC.SCALE_K2_KART, PC.KART_W8)
            if sc > PC.KART_RACE_SCALE:
                # A rival never looks bigger than the player's
                # slot kart: below the camera's depth the
                # projection ran to the 3x clamp and a 90-px
                # rival dwarfed the 40-px hero at race start.
                sc = PC.KART_RACE_SCALE
            f = 8
            if zs > PC.FOG_FAR8 - 250:
                # Fade out instead of popping: distant karts
                # shrink smoothly into the fog cutoff.  The old
                # 300-unit window started the shrink too early.
                f = ((PC.FOG_FAR8 - zs) * 8) // 250
                if f < 1:
                    f = 1
                sc = (sc * f) // 8
            sp = KARTS[k['i']]
            w = (sp.width * sc) >> 16
            h = (sp.height * sc) >> 16
            if IS_THUMBY_COLOR and (w < 2 or h < 2):
                # Below two pixels the scaled blit samples the
                # magenta key and draws nothing - the kart
                # blinked out where the fade meant a dot.  Paint
                # the dot by hand in the kart's body color,
                # blended toward the horizon fog as f runs down.
                t = 8 - f
                c = KART_DOT[k['i']]
                cr = c >> 11
                cg = (c >> 5) & 63
                cb = c & 31
                sr = PC.SKY_H >> 11
                sg = (PC.SKY_H >> 5) & 63
                sb = PC.SKY_H & 31
                col = (((cr + (((sr - cr) * t) >> 3)) << 11)
                       | (((cg + (((sg - cg) * t) >> 3)) & 63) << 5)
                       | (cb + (((sb - cb) * t) >> 3)))
                display.drawFilledRectangle(sx, sy - 1, 1, 1, col)
                continue
            if w < 1 or h < 1:
                continue
            _draw_kart_sprite(k, v, sx - w // 2, sy - h, sc)
        else:
            if kind == 0:
                sp = DECOS[ref]
                k2 = PC.SCALE_K2_DECOS[ref]
                w8 = PC.DECO_W8
            else:
                sp = ITEMS[ref]
                k2 = PC.SCALE_K2_ITEM
                w8 = PC.ITEM_W8
            # The damped, 4-unit-quantized depth drives the
            # scale: roadside objects scroll steadily instead
            # of shimmering (no per-frame width re-shuffle).
            sc = _scale_for(zs, k2, w8)
            w = (sp.width * sc) >> 16
            h = (sp.height * sc) >> 16
            sp.setScale(sc)
            sp.mirrorX = False
            sp.x = sx - w // 2
            sp.y = sy - h
            draw_sprite(sp)
    if me is not None:
        # The player's kart sits in his fixed slot, painted on top of
        # everything the loop above just drew.  Clamped rivals can
        # shrink to his size but never cover him.
        sp = KARTS[me['i']]
        sc = PC.KART_RACE_SCALE
        w = (sp.width * sc) >> 16
        h = (sp.height * sc) >> 16
        _draw_kart_sprite(me, v, PC.PX - w // 2, PC.PY + 4 - h, sc)
        if me['drift'] and IS_THUMBY_COLOR:
            _draw_drift_smoke(v, PC.PX, PC.PY + 4)


# Big countdown numerals - 5x7 bitmaps, drawn scaled.
_BIG_DIGITS = {
    '0': (0x3C, 0x42, 0x4A, 0x52, 0x3C),
    '1': (0x08, 0x18, 0x3C, 0x08, 0x08),
    '2': (0x3C, 0x42, 0x3C, 0x24, 0x42),
    '3': (0x3C, 0x42, 0x38, 0x42, 0x3C),
    '4': (0x22, 0x32, 0x3C, 0x02, 0x02),
    '5': (0x7E, 0x40, 0x5C, 0x42, 0x3C),
    '6': (0x3C, 0x40, 0x5C, 0x42, 0x3C),
    '7': (0x7E, 0x04, 0x08, 0x10, 0x10),
    '8': (0x3C, 0x42, 0x3C, 0x42, 0x3C),
    '9': (0x3C, 0x42, 0x3C, 0x02, 0x3C),
    'G': (0x3E, 0x41, 0x40, 0x51, 0x3E),
    'O': (0x3C, 0x42, 0x42, 0x42, 0x3C),
    '!': (0x10, 0x10, 0x10, 0x00, 0x10),
    'L': (0x40, 0x40, 0x40, 0x40, 0x7E),
    'A': (0x1C, 0x22, 0x3E, 0x22, 0x22),
    'P': (0x7C, 0x42, 0x7C, 0x40, 0x40),
    'F': (0x7C, 0x40, 0x40, 0x78, 0x40),
    'I': (0x3E, 0x08, 0x08, 0x08, 0x3E),
    'N': (0x22, 0x32, 0x2A, 0x26, 0x22),
    'S': (0x3E, 0x40, 0x3C, 0x01, 0x3E),
    'H': (0x22, 0x22, 0x3E, 0x22, 0x22),
    'M': (0x42, 0x66, 0x52, 0x42, 0x42),
    'R': (0x7E, 0x42, 0x42, 0x78, 0x48),
    'K': (0x41, 0x44, 0x50, 0x44, 0x41),
    'T': (0x7F, 0x08, 0x08, 0x08, 0x08),
}


@micropython.native
def _big_char(ch, x, y, scale, col):
    # 5-row x 7-column bitmaps, top row first, bit 6 = leftmost column
    rows = _BIG_DIGITS.get(ch)
    if rows is None:
        return
    for ry in range(5):
        r = rows[ry]
        for rx in range(7):
            if r & (1 << (6 - rx)):
                display.drawFilledRectangle(x + rx * scale,
                                            y + ry * scale,
                                            scale, scale, col)


@micropython.native
def _big_text(s, cx, cy, scale, col):
    w = len(s) * (7 * scale + scale) - scale
    x = cx - w // 2
    for ch in s:
        _big_char(ch, x, cy, scale, col)
        x += 8 * scale


@micropython.native
def _draw_drift_smoke(v, sx, sy):
    """Tire smoke trailing the drifting player kart: two small puffs
    swapped side to side as the frame counter ticks, so the trail
    visibly scrolls behind the fixed kart slot."""
    f = v['frame']
    if (f >> 1) & 1:
        c1 = PC.COLOR_DIM
        c2 = PC.COLOR_GRASS_B
    else:
        c1 = PC.COLOR_GRASS_B
        c2 = PC.COLOR_DIM
    display.drawFilledRectangle(sx - 15 - (f & 1), sy - 3, 4, 3, c1)
    display.drawFilledRectangle(sx + 12 + (f & 1), sy - 3, 4, 3, c2)


@micropython.native
def _draw_kart_sprite(k, v, x, y, scale):
    """One kart sprite (its bottom edge at x, y) with its effect
    overlays: the star aura around it, the boost flame under it, the
    mini-turbo charge flame, the wobble while stuck."""
    sp = KARTS[k['i']]
    w = (sp.width * scale) >> 16
    h = (sp.height * scale) >> 16
    # The star aura stays lit (blinking read as flicker) and
    # only from 8 px up: on a tiny distant kart it was a blob
    # bigger than the sprite.  It is an OUTLINE, never a solid
    # fill - a block painted over the road and bled through the
    # sprite's transparent key pixels.
    if k['star'] > 0 and w >= 8:
        if IS_THUMBY_COLOR:
            display.drawRectangle(x - 2, y - 2, w + 4, h + 4,
                                  PC.COLOR_SELECT)
        else:
            display.drawRectangle(x - 2, y - 2, w + 4, h + 4, PC.WHITE)
    if k['stuck'] > 0:
        x += randint(-1, 1)
    sp.setScale(scale)
    sp.mirrorX = False
    sp.x = x
    sp.y = y
    draw_sprite(sp)
    fw = w >> 2
    if fw < 2:
        fw = 2
    fh = h >> 3
    if fh < 2:
        fh = 2
    fx = x + w // 2 - fw // 2
    # The flames get the same size gate: their 2x2 minimum dwarfed a
    # few-pixel kart, and those blobs flickered on the horizon.
    if k['boost'] > 0 and w >= 8:
        col = PC.COLOR_CENTER if IS_THUMBY_COLOR else PC.WHITE
        display.drawFilledRectangle(fx, y + h - fh, fw, fh, col)
    # mini-turbo charge flame under the rear axle: stage 1 yellow,
    # stage 2 white; drift is color-target only so grayscale never
    # reaches this branch
    if IS_THUMBY_COLOR and w >= 8 \
            and k['drcharge'] >= DRIFT_STAGE1_Q:
        col = (PC.COLOR_CHECK_A if k['drcharge'] >= DRIFT_STAGE2_Q
               else PC.SUN)
        display.drawFilledRectangle(fx, y + h + 1, fw, fh, col)


@micropython.native
def _draw_hud(v):
    p = v['karts'][0]
    n = len(v['karts'])
    if IS_THUMBY_COLOR:
        display.drawFilledRectangle(0, 0, PC.WIDTH, 12, PC.COLOR_HUD_BG)
        pos = str(p['pos']) + '/' + str(n)
        col = PC.COLOR_SELECT if p['pos'] == 1 else PC.COLOR_TEXT
        display.drawText(pos, 2, 2, col)
        # The field starts behind the line (internally lap 0 until the
        # first crossing), so clamp the display to at least 1.
        lap = "LAP " + str(max(1, min(p['lap'] + 1, PC.LAPS))) \
            + '/' + str(PC.LAPS)
        display.drawText(lap, center_x(lap), 2, PC.COLOR_TEXT)
        spd = str(p['s'] >> 16)
        display.drawText(spd, PC.WIDTH - text_width(spd) - 2, 2,
                         PC.COLOR_TEXT)
        # item slot
        display.drawFilledRectangle(2, 104, 20, 20, PC.COLOR_HUD_BG)
        display.drawRectangle(2, 104, 20, 20, PC.COLOR_DIM)
        if p['item'] >= 0:
            sp = ITEMS[p['item']]
            sp.setScale(PC.ITEM_RACE_SCALE)
            sp.mirrorX = False
            sp.x = 4
            sp.y = 106
            draw_sprite(sp)
        # minimap
        display.drawFilledRectangle(88, 102, 38, 22, PC.COLOR_HUD_BG)
        display.drawRectangle(88, 102, 38, 22, PC.COLOR_DIM)
        _draw_minimap_color(v)
    else:
        display.drawFilledRectangle(0, 0, PC.WIDTH, 8, PC.COLOR_HUD_BG)
        s = (str(p['pos']) + '/' + str(n) + " L"
             + str(max(1, min(p['lap'] + 1, PC.LAPS))) + '/'
             + str(PC.LAPS) + ' ' + str(p['s'] >> 16))
        display.drawText(s, 1, 0, PC.COLOR_TEXT)
        if p['item'] >= 0:
            sp = ITEMS[p['item']]
            sp.setScale(PC.ITEM_RACE_SCALE)
            sp.mirrorX = False
            sp.x = 2
            sp.y = 9
            draw_sprite(sp)
        _draw_minimap_thumby(v)


@micropython.native
def _draw_minimap_color(v):
    x0, y0 = 90, 104
    pw, ph = 34, 18
    mx0, my0 = 40, 90
    mx1, my1 = 665, 440
    prev = None
    for i in range(0, PC.COURSE_N, 3):
        x = x0 + (PC.CX[i] - mx0) * pw // (mx1 - mx0)
        y = y0 + (PC.CY[i] - my0) * ph // (my1 - my0)
        if prev is not None:
            _line(prev[0], prev[1], x, y, PC.COLOR_MINI)
        prev = (x, y)
    # start tick
    sx = x0 + (PC.CX[0] - mx0) * pw // (mx1 - mx0)
    sy = y0 + (PC.CY[0] - my0) * ph // (my1 - my0)
    display.drawFilledRectangle(sx - 1, sy - 1, 3, 3, PC.COLOR_SELECT)
    # kart dots (course space, player highlighted)
    for k in v['karts']:
        kx = x0 + ((k['x'] >> 16) - mx0) * pw // (mx1 - mx0)
        ky = y0 + ((k['y'] >> 16) - my0) * ph // (my1 - my0)
        if k['ai']:
            display.drawFilledRectangle(kx - 1, ky - 1, 2, 2,
                                        PC.COLOR_MINI)
        else:
            display.drawFilledRectangle(kx - 1, ky - 1, 3, 3,
                                        PC.COLOR_SELECT)


@micropython.native
def _draw_minimap_thumby(v):
    x0, y0 = 50, 23
    pw, ph = 18, 10
    mx0, my0 = 40, 90
    mx1, my1 = 665, 440
    display.drawFilledRectangle(x0 - 1, y0 - 1, pw + 2, ph + 2,
                                PC.COLOR_HUD_BG)
    display.drawRectangle(x0 - 1, y0 - 1, pw + 2, ph + 2, PC.COLOR_MINI)
    prev = None
    for i in range(0, PC.COURSE_N, 4):
        x = x0 + (PC.CX[i] - mx0) * pw // (mx1 - mx0)
        y = y0 + (PC.CY[i] - my0) * ph // (my1 - my0)
        if prev is not None:
            _line(prev[0], prev[1], x, y, PC.COLOR_MINI)
        prev = (x, y)
    for k in v['karts']:
        kx = x0 + ((k['x'] >> 16) - mx0) * pw // (mx1 - mx0)
        ky = y0 + ((k['y'] >> 16) - my0) * ph // (my1 - my0)
        if k['ai']:
            display.drawFilledRectangle(kx, ky, 1, 1, PC.COLOR_MINI)
        else:
            display.drawFilledRectangle(kx - 1, ky - 1, 2, 2,
                                        PC.COLOR_MINI)


@micropython.native
def _race_draw(v, update=True):
    """Draw one race frame. `update=False` skips the trailing
    blit so a caller that overlays its own panel can push the
    composed frame exactly once (two pushes would alternate
    panel and bare race on every tick)."""
    cam = _camera(v)
    _draw_sky(v)
    _draw_strips(v, cam)
    _draw_sprites(v, cam)
    if not v['attract']:
        _draw_hud(v)
    # banners
    if v['state'] == RC_COUNT:
        pc = PC.FPS_RACE
        if v['tick'] < 3 * pc:
            s = str(3 - v['tick'] // pc)
        else:
            s = 'GO!'
        if IS_THUMBY_COLOR:
            _big_text(s, 64, 44, 3, PC.COLOR_SELECT)
        else:
            _big_text(s, 36, 12, 2, PC.WHITE)
    elif v['banner'] and v['banner_t'] > 0:
        if IS_THUMBY_COLOR:
            display.drawText(v['banner'], center_x(v['banner']), 48,
                             PC.COLOR_SELECT)
        else:
            s = v['banner']
            if len(s) > 12:
                s = s[:12]
            display.drawText(s, center_x(s), 16, PC.COLOR_SELECT)
    if v['state'] == RC_FINISH:
        s = 'FINISH'
        if IS_THUMBY_COLOR:
            _big_text(s, 64, 52, 2, PC.COLOR_SELECT)
        else:
            display.drawText(s, center_x(s), 14, PC.COLOR_SELECT)
    if update:
        display.update()


# --- Race --------------------------------------------------------------------
def _race_start(player_kart, attract):
    """Build the race state. attract: an all-CPU field for the title
    screen (no countdown, no finish, the field is kept packed);
    otherwise a real race with the player as kart 0."""
    display.setFPS(PC.FPS_RACE)
    display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                    PC.FONT_SPACE)
    _audio_off()
    if attract:
        designs = tuple(range(PC.RACE_KARTS))
    else:
        designs = [player_kart]
        for i in range(8):
            if i != player_kart:
                designs.append(i)
        designs = designs[:PC.RACE_KARTS]
    karts = []
    for i in range(PC.RACE_KARTS):
        # The player starts on the centerline behind the grid
        # (a dedicated slot); the CPUs fill the grid cells.
        if attract:
            slot = PC.SPAWN_ORDER[i]
        elif i == 0:
            slot = PC.PLAYER_SPAWN_SLOT
        else:
            slot = PC.SPAWN_ORDER[i]
        karts.append(_make_kart(designs[i],
                                 not attract and i == 0, slot))
    if attract:
        # The attract demo starts mid-lap, not on the grid: a
        # grid-packed all-CPU field throttles itself to a crawl
        # and the camera then crosses a subsegment only every
        # couple of dozen frames - each crossing re-shuffles
        # the strip order and flips the whole scene in place.
        for i, k in enumerate(karts):
            k['prog'] = (36 + 54 * i) * 8
            k['total'] = k['prog']
            k['prevprog'] = k['prog']
            k['lap'] = 0
            k['prevlap'] = 0
            k['s'] = (k['sm'] * 3) // 10
            wx8, wy8 = _kart_world8(k)
            k['x'] = wx8 << 13
            k['y'] = wy8 << 13
    if not attract:
        # The HUD shows the initial pos until the first step -
        # the player is on the back row, i.e. last.
        karts[0]['pos'] = PC.RACE_KARTS
    boxes = []
    for i, (pg, la) in enumerate(PC.ITEM_BOXES):
        boxes.append({'prog': pg, 'lat': la,
                      'item': _draw_item() if i % 2 else -1, 't': 0})
    return {
        'karts': karts, 'boxes': boxes,
        'bananas': [], 'pokeys': [],
        'state': RC_RUN if attract else RC_COUNT, 'tick': 0,
        'frame': 0, 'forfeit': False, 'banner': '', 'banner_t': 0,
        'player_pos': 1, 'go_frame': 0,
        'attract': attract, 'cam_idx': 0,
        'skyoff': 0, 'sangprev': None,
    }


@micropython.native
def _race_step(v, dt, fx):
    """One simulation step: input or AI, physics, laps and items.
    Shared by the race loop and the title's attract mode."""
    karts = v['karts']
    p = karts[0]
    if not v['attract'] and not v['forfeit']:
        if (BUTTONS[KEY_BACK].justPressed()
                or buttonMENU.justPressed()):
            v['forfeit'] = True
            p['finish'] = 10 ** 9
            p['s'] = 0
            if fx:
                fx.play(FXEngine.LOSE)
        if BUTTONS[KEY_OK].justPressed():
            _use_item(p, v, fx)
    for k in karts:
        if not k['ai']:
            # The player steers its own nose in world space once
            # the race is live; the attract keeps the parked
            # player kart on the rail.
            k['free'] = not v['attract']
        if k['finish']:
            si, thr = 0, 0      # finished karts coast to a stop
            k['drift'] = 0
            k['drcharge'] = 0
        elif k['ai']:
            si, thr = _ai_decide(k, v)
            _ai_items(k, v, fx)
        else:
            si = 0
            if BUTTONS[KEY_LEFT].pressed():
                si -= 256
            if BUTTONS[KEY_RIGHT].pressed():
                si += 256
            thr = 0
            if BUTTONS[KEY_UP].pressed():
                thr = 65536
            elif BUTTONS[KEY_DOWN].pressed():
                thr = -65536
            # Drift / mini-turbo (color target; RB is the drift
            # key): hold RB with steering above a fifth of top
            # speed to power-slide; releasing cashes the slide
            # time in as a boost - the reference's mechanic.
            if IS_THUMBY_COLOR and not v['attract']:
                held = buttonRB.pressed()
                if k['drift'] == 1:
                    if not held or k['stuck'] > 0:
                        k['drift'] = 0
                        ch = k['drcharge']
                        k['drcharge'] = 0
                        # only cash the charge in if no mushroom boost
                        # is already running - a fresh item outranks
                        # the mini-turbo
                        if ch >= DRIFT_STAGE1_Q and k['boost'] == 0:
                            bp = (DRIFT_BOOST_MIN_Q
                                  + ((ch * DRIFT_BOOST_RATE_Q) >> 16))
                            if bp > DRIFT_BOOST_CAP_Q:
                                bp = DRIFT_BOOST_CAP_Q
                            k['bp'] = bp
                            dur = (DRIFT_BOOST_BASE_Q
                                   + ((ch * DRIFT_BOOST_GAIN_Q) >> 16))
                            if dur > BOOST_TIME_Q:
                                dur = BOOST_TIME_Q
                            if k['boost'] < dur:
                                k['boost'] = dur
                            if fx:
                                fx.play(FXEngine.BOOST)
                                if rumble:
                                    rumble(120)
                elif (held and si != 0 and k['stuck'] == 0 and
                        k['boost'] == 0 and k['s'] * 5 > k['sm']):
                    k['drift'] = 1
        _kart_update(k, si, thr, dt)
    for k in karts:
        if k['finish']:
            continue
        # Crossing the start line forward (the karts never
        # reverse): the wrapped step must be a plausible
        # one-tick advance.  The free player's projection can
        # hop the line by hundreds of units (hairpin slide,
        # grass snap) and such hops used to be credited as laps.
        step = ((k['prog'] - k['prevprog'] + (PC.L8 >> 1))
                % PC.L8) - (PC.L8 >> 1)
        if (k['prevprog'] > k['prog']
                and (k['prevprog'] - k['prog']) > (PC.L8 >> 1)
                and 0 < step <= LAP_STEP8):
            k['lap'] += 1
            if (k['ai'] is False and not v['attract']
                    and k['lap'] < PC.LAPS):
                if k['lap'] == PC.LAPS - 1:
                    v['banner'] = 'FINAL LAP'
                elif k['lap'] > 0:
                    v['banner'] = 'LAP ' + str(k['lap'] + 1) \
                        + '/' + str(PC.LAPS)
                v['banner_t'] = (PC.FPS_RACE * 5) // 2
            if k['lap'] >= PC.LAPS and not v['attract']:
                k['finish'] = v['frame']
        k['prevprog'] = k['prog']
    _kart_collisions(v, fx)
    _items_update(v, dt, fx)
    # positions: finished by time, the rest by progress -
    # finishers must sort AHEAD of the running field.  The old
    # key began with (finish > 0) ascending, so a finished rival
    # jumped ahead of a still-running last-place player.  The
    # forfeit mark (10**9) is not a finish: rank by progress.
    order = karts[:]
    for j in range(1, len(order)):
        k = order[j]
        kf = k['finish']
        kfin = 0 if 0 < kf <= 10 ** 8 else 1
        kt = kf if kfin == 0 else 0
        ktt = -k['total']
        w = j - 1
        while w >= 0:
            o = order[w]
            of = o['finish']
            po = 0 if 0 < of <= 10 ** 8 else 1
            ot = of if po == 0 else 0
            if po > kfin or (po == kfin and (ot > kt or (ot == kt
                    and -o['total'] > ktt))):
                order[w + 1] = order[w]
                w -= 1
            else:
                break
        order[w + 1] = k
    for i, k in enumerate(order):
        k['pos'] = i + 1
    v['player_pos'] = p['pos']
    if v['attract']:
        # Follow the leader and keep the field packed: a laggard
        # a lap behind is teleported a lap ahead.  The camera
        # switches only when the pack leader pulls clear by
        # LEAD_MARGIN8 - side-by-side karts trading the lead
        # every tick would reproject the scene and flip it.
        lead = v['cam_idx']
        lt = karts[lead]['total']
        for i in range(1, len(karts)):
            if karts[i]['total'] > lt:
                lt = karts[i]['total']
        if lt - karts[lead]['total'] > LEAD_MARGIN8:
            for i in range(len(karts)):
                if karts[i]['total'] >= lt:
                    lead = i
                    break
        v['cam_idx'] = lead
        gap = (PC.L8 * 12) // 10
        for k in karts:
            if lt - k['total'] > gap:
                k['total'] += PC.L8
        # 32-bit targets wrap their ints; rebase when the totals grow
        # large (the amount is a multiple of both hill-scroll
        # periods, so the parallax does not jump)
        if lt > 4194304:
            for k in karts:
                k['total'] -= 4194304


@micropython.native
def race(player_kart):
    """One race. Returns (standings, player_pos, forfeit)."""
    global first_race
    display.setFPS(PC.FPS_RACE)
    display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                    PC.FONT_SPACE)
    _audio_off()
    fx = _fx()
    if fx:
        fx.play(FXEngine.CONFIRM)
    if first_race:
        _draw_help()
        # One full frame first: the kart-pick press that started this
        # race is still "just pressed" and would otherwise dismiss the
        # overlay before the player can see it.
        display.update()
        while not inputJustPressed():
            display.update()
        first_race = False
    v = _race_start(player_kart, False)
    last_digit = 4
    pc = PC.FPS_RACE
    while True:
        v['frame'] += 1
        if v['banner_t'] > 0:
            v['banner_t'] -= 1
        if v['state'] == RC_COUNT:
            v['tick'] += 1
            if v['tick'] < 3 * pc:
                digit = 3 - v['tick'] // pc
                if digit != last_digit:
                    last_digit = digit
                    if fx:
                        fx.play(FXEngine.COUNT)
            else:
                if last_digit != 0:
                    last_digit = 0
                    v['go_frame'] = v['frame']
                    if fx:
                        fx.play(FXEngine.GO)
                if v['tick'] >= 3 * pc + pc // 2:
                    v['state'] = RC_RUN
                    v['tick'] = 0
            _race_draw(v)
        elif v['state'] == RC_RUN:
            v['tick'] += 1
            _race_step(v, DT, fx)
            _race_draw(v)
            if v['karts'][0]['finish'] > 0:
                v['state'] = RC_FINISH
                v['tick'] = 0
                if v['forfeit']:
                    v['tick'] = pc * 3   # straight to the results
                if fx:
                    if not v['forfeit']:
                        if v['player_pos'] == 1:
                            fx.play(FXEngine.WIN)
                        else:
                            fx.play(FXEngine.LOSE)
                    if rumble:
                        rumble(300)
        else:  # RC_FINISH
            v['tick'] += 1
            _race_step(v, DT, fx)
            _race_draw(v)
            if v['tick'] >= pc * 3:
                break
    standings = _final_standings(v)
    # The live player_pos was sampled during the post-finish coast,
    # when karts that finished later can still be overtaking - the
    # standings row is the authoritative final position.
    player_pos = v['player_pos']
    for pos, name, tm in standings:
        if '(YOU)' in name:
            player_pos = pos
            break
    _audio_off()
    collect()
    return (standings, player_pos, v['forfeit'])


def _final_standings(v):
    karts = v['karts']
    # The forfeit mark (10**9) is not a real finish: that kart is
    # listed with the ones that did not finish, sorted by progress.
    finished = [k for k in karts if 0 < k['finish'] <= 10 ** 8]
    finished.sort(key=lambda k: k['finish'])
    rest = [k for k in karts if k['finish'] <= 0 or k['finish'] > 10 ** 8]
    rest.sort(key=lambda k: -k['total'])
    rows = []
    for i, k in enumerate(finished + rest):
        if 0 < k['finish'] <= 10 ** 8:
            t = k['finish'] - v['go_frame']
            s = t // PC.FPS_RACE
            d = (t % PC.FPS_RACE) * 10 // PC.FPS_RACE
            tm = str(s) + ':' + ('0' if d < 10 else '') + str(d)
        else:
            tm = 'DNF'
        name = PC.KART_NAMES[k['i']]
        if k['ai'] is False:
            name = name + ' (YOU)'
        rows.append((i + 1, name, tm))
    return rows

# --- Help / title / select / result ------------------------------------------
def _draw_help():
    """First-race how-to overlay (any key dismisses it)."""
    display.fill(PC.COLOR_BG)
    if IS_THUMBY_COLOR:
        lines = ('HOW TO RACE',
                 'HOLD ' + keylabel(KEY_UP) + ' = GAS',
                 keylabel(KEY_LEFT) + '/' + keylabel(KEY_RIGHT) + ' = STEER',
                 'HOLD ' + keylabel(KEY_DOWN) + ' = BRAKE',
                 keylabel(KEY_OK) + ' = USE ITEM',
                 keylabel(KEY_BACK) + ' = FORFEIT',
                 'HOLD RB + STEER = DRIFT',
                 '',
                 'MUSHROOM=BOOST',
                 'STAR=INVINCIBLE',
                 'BANANA=DROP TRAP',
                 'POKEY=THROW',
                 '',
                 'PRESS ANY KEY')
        y = 8
        for ln in lines:
            col = (PC.COLOR_SELECT if ln == 'HOW TO RACE'
                   else PC.COLOR_TEXT)
            display.drawText(ln, center_x(ln), y, col)
            y += 8
    else:
        # five non-overlapping rows (7px font on a 40px screen)
        y = 0
        ln = 'HOW TO RACE'
        display.drawText(ln, center_x(ln), y, PC.COLOR_SELECT)
        y += 8
        ln = 'HOLD ' + keylabel(KEY_UP) + '=GAS'
        display.drawText(ln, center_x(ln), y, PC.COLOR_TEXT)
        y += 8
        ln = keylabel(KEY_LEFT) + '/' + keylabel(KEY_RIGHT) + '=STEER'
        display.drawText(ln, center_x(ln), y, PC.COLOR_TEXT)
        y += 8
        ln = keylabel(KEY_DOWN) + '=BRK ' + keylabel(KEY_OK) + '=ITEM'
        display.drawText(ln, center_x(ln), y, PC.COLOR_TEXT)
        y += 8
        ln = keylabel(KEY_BACK) + '=QUIT'
        display.drawText(ln, center_x(ln), y, PC.COLOR_DIM)


@micropython.native
def title():
    """Attract mode: a live CPU race running behind the panel - the
    camera follows the leader and the field stays packed. Returns
    0 (race) or 1 (options)."""
    display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                    PC.FONT_SPACE)
    v = _race_start(None, True)
    fx = _fx()
    if fx:
        fx.play(FXEngine.CONFIRM)
    t = 0
    while True:
        t += 1
        _race_step(v, DT, fx)
        _race_draw(v, False)   # single update below, after the panel
        if IS_THUMBY_COLOR:
            display.drawFilledRectangle(16, 34, 96, 32, PC.COLOR_HUD_BG)
            display.drawRectangle(16, 34, 96, 32, PC.COLOR_SELECT)
            _big_text('MARIO', 64, 38, 2, PC.COLOR_SELECT)
            _big_text('KARTS', 64, 52, 2, PC.COLOR_TEXT)
            if (t // 20) % 2 == 0:
                display.drawText(keylabel(KEY_OK) + ': RACE', 10, 112,
                                 PC.COLOR_SELECT)
            display.drawText(keylabel(KEY_BACK) + ': OPTS', 72, 112,
                             PC.COLOR_DIM)
        else:
            display.drawFilledRectangle(10, 14, 52, 15, PC.COLOR_BG)
            display.drawText('MARIO', 21, 15, PC.WHITE)
            display.drawText('KARTS', 21, 22, PC.WHITE)
            if (t // 15) % 2 == 0:
                display.drawText(keylabel(KEY_OK) + ':RACE', 2, 33,
                                 PC.WHITE)
            display.drawText(keylabel(KEY_BACK) + ':OPT', 40, 33,
                             PC.LIGHTGRAY)
        display.update()
        if BUTTONS[KEY_OK].justPressed():
            inputJustPressed()
            if rumble:
                rumble(30)
            return 0
        if (BUTTONS[KEY_BACK].justPressed() or buttonMENU.justPressed()):
            inputJustPressed()
            return 1


@micropython.native
def _stat_bar(x, y, w, val, col, bg):
    display.drawFilledRectangle(x, y, w, 3, bg)
    n = int(val * w + 0.5)
    if n > 0:
        display.drawFilledRectangle(x, y, n, 3, col)


@micropython.native
def select_kart():
    """Returns the picked kart index, or None to bail to the title."""
    display.setFPS(PC.FPS_MENU)
    display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                    PC.FONT_SPACE)
    col = 0
    row = 0
    while True:
        sel = row * 4 + col
        display.fill(PC.COLOR_BG)
        if IS_THUMBY_COLOR:
            display.drawText("CHOOSE YOUR KART",
                             center_x("CHOOSE YOUR KART"), 4, PC.COLOR_TEXT)
            for c in range(4):
                for r in range(2):
                    k = r * 4 + c
                    sp = KARTS[k]
                    sp.setScale(PC.KART_SELECT_SCALE)
                    sp.mirrorX = False
                    sp.x = 2 + c * 31
                    sp.y = 16 + r * 28
                    draw_sprite(sp)
                    if k == sel:
                        display.drawRectangle(sp.x - 2, sp.y - 2, 33, 28,
                                              PC.COLOR_SELECT)
            nm = PC.KART_NAMES[sel]
            display.drawText(nm, center_x(nm), 78, PC.COLOR_SELECT)
            st = PC.KART_STATS[sel]
            display.drawText('S', 40, 92, PC.COLOR_DIM)
            _stat_bar(50, 92, 40, (st[0] - 105) / 23.0, PC.COLOR_SELECT,
                      PC.COLOR_DIM)
            display.drawText('A', 40, 100, PC.COLOR_DIM)
            _stat_bar(50, 100, 40, (st[1] - 60) / 55.0, PC.COLOR_SELECT,
                      PC.COLOR_DIM)
            display.drawText('T', 40, 108, PC.COLOR_DIM)
            _stat_bar(50, 108, 40, (st[2] - 300) / 150.0, PC.COLOR_SELECT,
                      PC.COLOR_DIM)
            hint = (keylabel(KEY_LEFT) + '/' + keylabel(KEY_RIGHT)
                    + ':AIM  ' + keylabel(KEY_OK) + ':PICK')
            display.drawText(hint, center_x(hint), 118, PC.COLOR_DIM)
        else:
            nm = PC.KART_NAMES[sel]
            display.drawText(nm, center_x(nm), 0, PC.COLOR_SELECT)
            for c in range(4):
                for r in range(2):
                    k = r * 4 + c
                    sp = KARTS[k]
                    sp.setScale(PC.KART_SELECT_SCALE)
                    sp.mirrorX = False
                    sp.x = 18 + c * 12
                    sp.y = 8 + r * 9
                    draw_sprite(sp)
                    if k == sel:
                        display.drawRectangle(sp.x - 2, sp.y - 2, 12, 8,
                                              PC.COLOR_SELECT)
            st = PC.KART_STATS[sel]
            sv = (st[0] - 105) / 23.0
            av = (st[1] - 60) / 55.0
            tv = (st[2] - 300) / 150.0
            display.drawText('S', 2, 26, PC.COLOR_DIM)
            _stat_bar(9, 26, 26, sv, PC.COLOR_SELECT, PC.COLOR_DIM)
            display.drawText('A', 40, 26, PC.COLOR_DIM)
            _stat_bar(47, 26, 24, av, PC.COLOR_SELECT, PC.COLOR_DIM)
            display.drawText('T', 2, 33, PC.COLOR_DIM)
            _stat_bar(9, 33, 26, tv, PC.COLOR_SELECT, PC.COLOR_DIM)
            display.drawText('B', 40, 33, PC.COLOR_DIM)
            _stat_bar(47, 33, 24, (sv + av + tv) / 3.0,
                      PC.COLOR_SELECT, PC.COLOR_DIM)
        display.update()
        if BUTTONS[KEY_LEFT].justPressed():
            col = (col - 1) % 4
            _select_sfx()
        elif BUTTONS[KEY_RIGHT].justPressed():
            col = (col + 1) % 4
            _select_sfx()
        elif BUTTONS[KEY_UP].justPressed():
            row = (row - 1) % 2
            _select_sfx()
        elif BUTTONS[KEY_DOWN].justPressed():
            row = (row + 1) % 2
            _select_sfx()
        elif BUTTONS[KEY_OK].justPressed():
            inputJustPressed()
            if rumble:
                rumble(40)
            fx = _fx()
            if fx:
                fx.play(FXEngine.CONFIRM)
            return sel
        elif (BUTTONS[KEY_BACK].justPressed() or buttonMENU.justPressed()):
            inputJustPressed()
            return None


@micropython.native
def result(standings, player_pos, forfeit):
    """Shows the final table. Returns True for a rematch, False for
    the title."""
    display.setFPS(PC.FPS_MENU)
    display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                    PC.FONT_SPACE)
    _audio_off()
    if IS_THUMBY_COLOR:
        audio_load("assets/sfx_win.ima" if player_pos == 1
                   else "assets/sfx_lose.ima")
        audio_play()
    t = 0
    while True:
        t += 1
        display.fill(PC.COLOR_BG)
        if IS_THUMBY_COLOR:
            display.drawText("RACE RESULTS", center_x("RACE RESULTS"), 4,
                             PC.COLOR_TEXT)
            y = 18
            for (pos, name, tm) in standings:
                is_you = '(YOU)' in name
                col = PC.COLOR_SELECT if is_you else PC.COLOR_TEXT
                nm = name[:-6] if is_you else name
                if is_you:
                    ln = 'YOU ' + nm
                else:
                    ln = str(pos) + ' ' + nm
                display.drawText(ln, 6, y, col)
                display.drawText(tm, PC.WIDTH - text_width(tm) - 2, y, col)
                y += 10
            hint = (keylabel(KEY_OK) + ':AGAIN  '
                    + keylabel(KEY_BACK) + ':TITLE')
            display.drawText(hint, center_x(hint), 106, PC.COLOR_DIM)
            for i in range(16):
                c = (PC.COLOR_CHECK_A if (i + t) % 2 == 0
                     else PC.COLOR_CHECK_B)
                display.drawFilledRectangle(i * 8, 118, 8, 10, c)
        else:
            # compact five-row layout (7px font on a 40px screen)
            display.drawText('RACE RESULTS', center_x('RACE RESULTS'), 0,
                             PC.COLOR_TEXT)
            s = 'YOU ' + str(player_pos) + ' OF ' + str(len(standings))
            col = PC.WHITE if player_pos == 1 else PC.LIGHTGRAY
            display.drawText(s, center_x(s), 8, col)
            for i in range(2):
                pos, name, tm = standings[i]
                is_you = '(YOU)' in name
                nm = name[:-6] if is_you else name
                ln = str(pos) + ' ' + nm[:5]
                if len(ln) > 11:
                    ln = ln[:11]
                col = PC.WHITE if is_you else PC.LIGHTGRAY
                display.drawText(ln, 1, 16 + i * 8, col)
                display.drawText(tm, PC.WIDTH - text_width(tm) - 1,
                                 16 + i * 8, col)
            hint = keylabel(KEY_OK) + ':AGAIN'
            display.drawText(hint, center_x(hint), 32, PC.COLOR_DIM)
        display.update()
        if BUTTONS[KEY_OK].justPressed():
            _audio_off()
            inputJustPressed()
            return True
        if (BUTTONS[KEY_BACK].justPressed()
                or buttonMENU.justPressed()):
            _audio_off()
            inputJustPressed()
            return False

# --- Settings ----------------------------------------------------------------
class SettingsMenu:
    def __init__(self):
        self.selected = 0
        self.settings_items = self.get_menu_items()
        display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT,
                        PC.FONT_SPACE)

    def get_menu_items(self):
        items = []
        for i in range(len(PC.KEY_NAMES)):
            items.append(PC.KEY_NAMES[i] + ': ' + KEYMAPS[i])
        items.append('RESET DEFAULTS')
        items.append('QUIT')
        items.append('BACK')
        return items

    def update_menu(self):
        self.settings_items = self.get_menu_items()

    def handle_special_action(self, i):
        return None

    def _remap(self, i):
        display.fill(PC.COLOR_BG)
        if IS_THUMBY_COLOR:
            s = "PRESS NEW KEY FOR:"
            display.drawText(s, center_x(s), 4, PC.COLOR_TEXT)
            display.drawLine(0, 14, PC.WIDTH, 14, PC.COLOR_DIM)
            nm = self.settings_items[i]
            display.drawText(nm, center_x(nm), 30, PC.COLOR_SELECT)
        else:
            display.drawText("PRESS NEW KEY FOR:", 2, 0, PC.COLOR_TEXT)
            display.drawLine(0, 6, PC.WIDTH, 6, PC.COLOR_DIM)
            nm = self.settings_items[i]
            display.drawText(nm, 2, 12, PC.COLOR_SELECT)
        display.update()
        while not inputJustPressed():
            display.update()
        k = get_pressed_key()
        if k:
            KEYMAPS[i] = k
            self.update_menu()
            sleep(0.3)
            inputJustPressed()

    @micropython.native
    def run(self):
        display.setFPS(PC.FPS_MENU)
        while True:
            n = len(self.settings_items)
            display.fill(PC.COLOR_BG)
            if IS_THUMBY_COLOR:
                display.drawText("SETTINGS", center_x("SETTINGS"), 4,
                                 PC.COLOR_TEXT)
                display.drawLine(0, 14, PC.WIDTH, 14, PC.COLOR_DIM)
            else:
                display.drawText("SETTINGS", center_x("SETTINGS"), 0,
                                 PC.COLOR_TEXT)
                display.drawLine(0, 6, PC.WIDTH, 6, PC.COLOR_DIM)
            start = self.selected - 2
            if start < 0:
                start = 0
            if start > n - PC.SETTING_ITEMS:
                start = n - PC.SETTING_ITEMS
            for i in range(PC.SETTING_ITEMS):
                j = i + start
                if j >= n:
                    break
                if IS_THUMBY_COLOR:
                    y = 20 + i * 10
                else:
                    y = 9 + i * 6
                prefix = "> " if j == self.selected else "  "
                col = (PC.COLOR_SELECT if j == self.selected
                       else PC.COLOR_DIM)
                display.drawText(prefix + self.settings_items[j], 4, y, col)
            hint = (keylabel(KEY_OK) + ":SET "
                    + keylabel(KEY_BACK) + ":SAVE")
            if IS_THUMBY_COLOR:
                display.drawText(hint, center_x(hint), 102, PC.COLOR_DIM)
            else:
                display.drawText(hint, center_x(hint), 34, PC.COLOR_DIM)
            display.update()
            if BUTTONS[KEY_UP].justPressed():
                self.selected = (self.selected - 1) % n
                if rumble:
                    rumble(15)
            elif BUTTONS[KEY_DOWN].justPressed():
                self.selected = (self.selected + 1) % n
                if rumble:
                    rumble(15)
            elif BUTTONS[KEY_OK].justPressed():
                r = self.handle_special_action(self.selected)
                if r is False:
                    inputJustPressed()
                    return
                if r is True:
                    sleep(0.15)
                    continue
                if self.selected < len(PC.KEY_NAMES):
                    self._remap(self.selected)
                elif self.selected == n - 3:
                    g = globals()
                    g['KEYMAPS'] = array('O', DEFAULT_KEYS)
                    rebuild_buttons()
                    self.update_menu()
                    sleep(0.3)
                elif self.selected == n - 2:
                    inputJustPressed()
                    reset()
                else:
                    save_keymaps(KEYMAPS)
                    inputJustPressed()
                    return
            elif (BUTTONS[KEY_BACK].justPressed()
                  or buttonMENU.justPressed()):
                save_keymaps(KEYMAPS)
                inputJustPressed()
                return
            inputJustPressed()

# --- Module end (ThumbCommander convention) ----------------------------------
first_race = True
collect()
if IS_THUMBY_COLOR:
    print("free RAM:", mem_free())
    import color_enhancements
    color_enhancements.apply(globals())
    collect()
else:
    intro.finish()


def main():
    global first_race
    first_race = True
    while True:
        _menu_music()
        action = title()
        inputJustPressed()
        if action == 0:
            pick = select_kart()
            inputJustPressed()
            if pick is None:
                continue
            while True:
                standings, player_pos, forfeit = race(pick)
                inputJustPressed()
                if not result(standings, player_pos, forfeit):
                    break
                inputJustPressed()
        elif action == 1:
            settings = SettingsMenu()
            settings.run()
            del settings
            collect()
            rebuild_buttons()
            inputJustPressed()
        else:
            reset()


main()

