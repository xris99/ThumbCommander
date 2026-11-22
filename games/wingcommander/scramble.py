# scramble.py - the hard-coded launch and landing scenes (docs/06 6.2):
# the run to the hangar, climbing into the fighter on the flight deck,
# and the landing where the deck crew comments on the damage.
#
# Verbatim ports of (wc1-re, GPL-3.0):
#   PlayScrambleHangarScene  src/cutscene.c:281  (0x4079C0)
#   AnimateScrambleWalk      src/cutscene.c:200  (0x407750)
#   scramble                 src/cutscene.c:620  (0x408200)
#   DrawScrambleActor        src/cutscene.c:378  (0x407C90)
#   ConfigureScrambleActor   src/cutscene.c:437  (0x407D90)
#   DrawScrambleFrame        src/cutscene.c:456  (0x407E10)
#   landing                  src/cutscene.c:801  (0x408650)
# on the sprite sets tool/wc1_convert.py writes from SCRAMBLE.VGA
# (scr<NN>.wcs) and PCSHIP.V0N section 8 (cksc<N>.wcs).
#
# The original draws into stSceneBuffer, the 320 x 128 conversation
# picture (InitializeConversationViewport, src/main.c:501-515); on the
# device that is rows 16..77, the same band the conversation and the
# MIDGAME scenes use. Original pixel positions map through _x8 / _y8
# (scene.py:59-73, reused here) and the hot spot lands at the object's
# position exactly like _Drawer does (scene.py:342-398). One step per
# displayed frame at 16 fps, 62 ms (docs/01 ch. 1.4); the original
# counts frames of nFrameSkip = 1 (init.c:202), so every loop pass
# renders and every pass applies the position deltas - the port does
# the same. Any button breaks a sequence, as every loop checks
# bEscapePressedFlag (e.g. cutscene.c:274-275). When the sprite files
# are missing the whole sequence is skipped and the game behaves the
# way it did before this chapter.

from struct import unpack_from
from time import ticks_ms, ticks_diff
from thumby_engine.platform import (display, buttonA, buttonB, buttonMENU)
import os
import ui
import wcdata as D
import wcgfx as G
import wcmath as M

PIC_Y0 = 16
PIC_Y1 = 78
STEP_MS = 62
VIEW_N = 128 * 96            # scratch: the biggest converted piece


def _x8(v):
    return (v * 512 + 5) // 10            # scene.py:59-65


def _y8(v):
    return (v * 6144 + 50) // 100         # scene.py:68-73


def _cx(v):
    return (_x8(v) + 64) // 128           # scene.py:353


def _cy(v):
    return (_y8(v) + 64) // 128 + PIC_Y0  # scene.py:354


def _key():
    """Any button, as WaitForSceneAdvance reads them (disk.c:509-548)."""
    return (buttonA.justPressed() or buttonB.justPressed() or
            buttonMENU.justPressed())


def _advance(ms):
    """scene.py:593-601 (WaitForSceneAdvance, disk.c:509-548)."""
    t0 = ticks_ms()
    while ticks_diff(ticks_ms(), t0) < ms:
        display.update()
        if _key():
            break
    ui.wait_release()


def _rnd(bits):
    """os.urandom for the original's RandomWord / RandomInRange picks
    (cutscene.c:302-303, 823-830). Always draws at least one byte: a
    5-bit mask on zero bytes would otherwise repeat forever in
    _pick_slots' redraw loop (the landing scene's damage decals)."""
    n = max(1, bits >> 3)
    try:
        return int.from_bytes(os.urandom(n), 'little')
    except (OSError, NotImplementedError):
        return 0


# --- sprite sets ------------------------------------------------------------

_sets = {}
_scratch = bytearray(VIEW_N)       # cutscenes may allocate (docs/06 6.1)


def _set(name):
    """A .wcs sprite set, or None when its file was not built."""
    if not D.exists(name):
        return None
    ss = _sets.get(name)
    if ss is None:
        ss = _sets[name] = D.SpriteSet(name)
    return ss


def _read(ss, frame):
    """One .wcs frame into the scratch buffer: (w, h, hx, hy) or None,
    mirroring the empty-slot guard of _Drawer (scene.py:348-349)."""
    if ss is None or frame < 0 or frame >= ss.n:
        return None
    off, w, h, hx, hy = unpack_from('<IBBbb', ss.table, frame * 8)
    n = w * h
    if off == 0 or n == 0 or n > VIEW_N:
        return None
    ss.read(off, memoryview(_scratch)[0:n])
    return w, h, hx, hy


def _draw(fb, ss, frame, x, y, y1=PIC_Y1):
    """DrawSpriteDefault: hot spot at the original position (x, y),
    unrotated, unscaled, screen scale (gr.c:740-746)."""
    e = _read(ss, frame)
    if e is None:
        return
    w, h, hx, hy = e
    G.blit_indexed(fb, ui.pal, _scratch, _cx(x) - hx, _cy(y) - hy,
                   w, h, PIC_Y0, y1)


# scene.py:309-322, verbatim (wcmath integer trig, anisotropic device
# scale, flip bits folded into signed scale like gr.c:541-551)
def _coeffs(scale, rot, flip):
    sx = scale << 8
    sy = scale << 8
    if flip & 0x10:
        sx = -sx
    if flip & 0x20:
        sy = -sy
    cos16 = M.icos(rot) * 4
    sin16 = M.isin(rot) * 4
    a = (cos16 * 65536) // sx
    b = (sin16 * 65536 * 5) // (sx * 6)
    c = (-sin16 * 65536 * 6) // (sy * 5)
    d = (cos16 * 65536) // sy
    return a, b, c, d


_P = [0] * 12


def _draws(fb, ss, frame, x, y, angle, scale, flip, y1=PIC_Y1):
    """DrawSpriteScaled (gr.c:1291-1297): rotation in tenths of degrees,
    scale 256 = original size. Sprite sets stored finer than the screen
    (the flight .wcs at res 80) divide the scale by res/64. The box and
    clipping mirror _Drawer (scene.py:364-383)."""
    e = _read(ss, frame)
    if e is None:
        return
    w, h, hx, hy = e
    if scale == 256 and angle == 0 and flip == 0:
        G.blit_indexed(fb, ui.pal, _scratch, _cx(x) - hx, _cy(y) - hy,
                       w, h, PIC_Y0, y1)
        return
    k = (scale * 64) // ss.res
    if k < 1:
        return
    s16 = k << 8
    if (max(w, h) * s16) >> 16 < 2:
        return
    ex = max(hx, w - hx)
    ey = max(hy, h - hy)
    rad = ((M.mag(ex, ey, 0) * s16) >> 16) + 2
    cx = _cx(x)
    cy = _cy(y)
    x0 = cx - rad
    if x0 < 0:
        x0 = 0
    x1 = cx + rad + 1
    if x1 > 128:
        x1 = 128
    y0 = cy - rad
    if y0 < PIC_Y0:
        y0 = PIC_Y0
    y1b = cy + rad + 1
    if y1b > y1:
        y1b = y1
    if x0 >= x1 or y0 >= y1b:
        return                        # RotateRLEImage's empty-box return
    a, b, c, d = _coeffs(k, angle % 360, flip)
    p = _P
    p[0] = cx
    p[1] = cy
    p[2] = (hx << 16) + 0x8000
    p[3] = (hy << 16) + 0x8000
    p[4] = a
    p[5] = b
    p[6] = c
    p[7] = d
    p[8] = x0
    p[9] = y0
    p[10] = x1
    p[11] = y1b
    G.blit_rs(fb, ui.pal, _scratch, w, h, p)


def _steps(n, draw, step):
    """n rendered frames one every STEP_MS. draw presents the picture,
    step(i) applies the per-pass position deltas (the original applies
    them on every loop pass and renders on every pass as well, with
    nFrameSkip = 1). Returns True if a button broke the loop."""
    t0 = ticks_ms()
    for i in range(n):
        draw()
        display.update()
        step(i)
        while ticks_diff(ticks_ms(), t0) < (i + 1) * STEP_MS:
            if _key():
                return True
            display.update()
    return _key()


# --- the actor engine (cutscene.c:378-434) -----------------------------------

# ausScrambleActorAnimationA[8] - cutscene.c:30-32 (0x00465788)
ACTOR_ANIM_A = [0, 1, 2, 3, 4, 5, 0x80, 0]
# ausScrambleActorAnimationB[11] - cutscene.c:34-36 (0x00465798)
ACTOR_ANIM_B = [0, 0, 1, 2, 2, 2, 2, 2, 1, 1, 0x80]
# aScrambleAnimationActors[5] base frames - cutscene.c:38-47
ACTOR_BASE = [2, 10, 13, 0, 1]
# actors 3 and 4 carry animationFrame -1: they never animate
# (cutscene.c:45-46)
ACTOR_STATIC = [False, False, False, True, True]


def _new_actor(idx, cfg):
    """ConfigureScrambleActor (cutscene.c:437-452): cfg is
    (x, y, deltaX, deltaY, scale, angle, flip); animationFrame restarts
    at 0 unless the actor is static (cutscene.c:447-448).

    The animation tables are the original's verbatim (cutscene.c:30-36,
    0x00465788 A and 0x00465798 B - B starts exactly where A's 8 shorts
    end, but the walk never uses that adjacency): actor 0 walks A,
    actors 1 and 2 walk B, actors 3 and 4 carry animationFrame -1 and
    never animate (cutscene.c:38-47). The pre-increment walk advances
    the stored frame by one per call, so it lands on the table's own
    0x80 terminator (A:6, B:10) and restarts at entry 0 - the cycle the
    crew animation shows - without running off the end of the table."""
    anim = (ACTOR_ANIM_A if idx == 0 else
            ACTOR_ANIM_B if idx in (1, 2) else None)
    return [cfg[0], cfg[1], cfg[2], cfg[3],      # x y dX dY
            ACTOR_BASE[idx],                     # baseFrame
            -1 if ACTOR_STATIC[idx] else 0,      # animationFrame
            0,                                   # animationState
            anim, cfg[4], cfg[5], cfg[6]]        # scale angle flip


def _actor(fb, ss, a, bg_right, backdrop_y):
    """DrawScrambleActor verbatim (cutscene.c:378-434). Control codes:
    0x00 advance, 0x40 stop here (state to 0), 0x80 | n jump to entry n;
    the frame is the table entry plus baseFrame; position moves by the
    deltas and the background scroll rides along with it."""
    frame = 0
    af = a[5]
    if af != -1:
        if a[6] != 0xa000:
            af += 1
            while True:
                frame = a[7][af]
                ctrl = frame & 0xc0
                if ctrl == 0:
                    # verbatim case 0 (cutscene.c:397-400): the struct's
                    # animationFrame advances by one and nothing writes
                    # the local index back after the loop - so each
                    # control-0 pass ends the call one entry further
                    # than it started. That single step lands the next
                    # call's pre-increment read on the 0x80 terminator
                    # (A:6, B:10) when the walk gets there, which is how
                    # the original restarts the cycle without ever
                    # running off the end of its table.
                    a[5] += 1
                    break
                if ctrl == 0x40:
                    a[6] = 0
                    af -= 1
                else:                     # 0x80: jump to entry frame&0x3f
                    af = frame & 0x3f
                    a[5] = af
        else:
            frame = af
    frame += a[4]
    a[0] += a[2]
    a[1] += a[3]
    _draws(fb, ss, frame, bg_right + a[0], backdrop_y + a[1],
           a[9], a[8], a[10])


# --- hangar walk (PlayScrambleHangarScene, cutscene.c:281-375) --------------

# acScrambleWalkerOverlayFrames[8] - cutscene.c:23-25 (0x00465770)
WALKER_OVERLAY = [3, 4, 5, 3, 4, 6, 6, 3]

# GetShapeFrameExtent(0, 0, pCurrentScrambleHangarShape, frame, 3) -
# the ORIGINAL bottom extents the walk anchors subtract, cutscene.c:226
# and :242 (nSceneScrambleWalkerPositionY = anchor - extent). From
# SCRAMBLE.VGA section 0 (wc1_inspect ground truth): walker frames
# 7..19 all have hot spot top 0, so the extent is height - 1 (59, 80,
# 98, 103, 94, 72, 43, 65, 75, 99, 97, 82, 64 tall). The device
# scr00.wcs frames are 0.48-scaled replicas whose exact originals
# cannot be recovered by upscaling, so like WALKER_OVERLAY above this
# is cited ground truth, not a guess. Index 0..6 unused: the walk
# frames never leave 7..19.
WALKER_BOTTOMS = (0, 0, 0, 0, 0, 0, 0,
                  58, 79, 97, 102, 93, 71, 42, 64, 74, 98, 96, 81, 63)


class _State:
    """The module statics of cutscene.c:20-28 / 294-305, one per run."""

    def __init__(self):
        self.lfr = 7                  # cScrambleLeftWalkerFrame
        self.rfr = 10                 # cScrambleRightWalkerFrame
        self.lx = 70                  # nScrambleLeftWalkerX
        self.rx = 170                 # nScrambleRightWalkerX
        self.bx = 0                   # nScrambleBackgroundX
        self.pair = (_rnd(16) + 3) % 4            # cutscene.c:302-303


def hangar():
    """PlayScrambleHangarScene minus the music and the sound (the port
    has neither yet): walk block, stairs run, walk block again; any
    button cuts it (the bEscapePressedFlag breaks at cutscene.c:308,
    364). Returns True when a button was pressed."""
    ss = _set('scr00.wcs')
    if ss is None:
        return False
    fb = display.buffer
    display.fill(0)
    st = _State()

    def walk(i):
        st.bx -= 12
        st.rx += 3
        st.lx += 2
        st.lfr += 1
        if st.lfr > 19:
            st.lfr = 7
        st.rfr += 1
        if st.rfr > 19:
            st.rfr = 7

    def draw():
        # background tiled 4x, cutscene.c:210-224
        _draw(fb, ss, 0, st.bx, 0)
        _draw(fb, ss, 1, st.bx + 320, 0)
        _draw(fb, ss, 0, st.bx + 640, 0)
        _draw(fb, ss, 1, st.bx + 960, 0)
        # left walker + overlay: the original computes ONE y from the
        # walker frame's bottom extent and passes it to BOTH
        # DrawSpriteDefault calls (cutscene.c:226-240), so the overlay
        # is hot-spot-anchored at the walker's y - its own bottom (top
        # 39/35/43) is not floor-anchored. The walker's hot spot top is
        # 0, so its bottom row lands on the anchor row: feet on the
        # floor, full body drawn.
        y = 127 - WALKER_BOTTOMS[st.lfr]
        _draw(fb, ss, st.lfr, st.lx, y)
        _draw(fb, ss, WALKER_OVERLAY[st.pair * 2], st.lx, y)
        # right walker + overlay: anchor 137 (cutscene.c:242-256) puts
        # its feet on row 137, below the original's 128-row buffer, so
        # the original clips them away there too - head and torso stay
        # visible at the device mapping
        y = 137 - WALKER_BOTTOMS[st.rfr]
        _draw(fb, ss, st.rfr, st.rx, y)
        _draw(fb, ss, WALKER_OVERLAY[st.pair * 2 + 1], st.rx, y)

    esc = _steps(24, draw, walk)                   # cutscene.c:307
    if esc:
        return True
    # the stairs: frames 21..26, background frame 2 three times,
    # walkers at a constant y = -14 (cutscene.c:309-352)
    st.lfr = 21
    st.rfr = 24
    st.lx = 90
    st.rx = 200

    def draw2():
        _draw(fb, ss, 2, st.bx, 0)
        _draw(fb, ss, 2, st.bx + 320, 0)
        _draw(fb, ss, 2, st.bx + 640, 0)
        _draw(fb, ss, st.lfr, st.lx, -14)
        _draw(fb, ss, st.rfr, st.rx, -14)

    def run(i):
        st.bx -= 12
        st.lx += 2
        st.rx += 3
        st.lfr += 1
        if st.lfr > 26:
            st.lfr = 21
        st.rfr += 1
        if st.rfr > 26:
            st.rfr = 21

    esc = _steps(24, draw2, run)                   # cutscene.c:315-362
    if esc:
        return True
    st.lfr = 7                                     # cutscene.c:365-366
    st.rfr = 10
    esc = _steps(24, draw, walk)                   # cutscene.c:367
    return esc


# --- deck scramble (scramble, cutscene.c:620-795) ---------------------------

# ConfigureScrambleActor calls, cutscene.c:657-664:
# (x, y, deltaX, deltaY, scale, angle, flip)
DECK_ACTORS = {
    0: (130, 94, 1, 0, 0x100, 0, 0),
    2: (160, 120, 0, 0, 0x100, 0, 0),
    3: (260, 100, -3, 0, 0xff, 0, 0x10),
    4: (260, 100, -3, 0, 0xff, 0, 0x10),
}

# per-ship start positions, cutscene.c:668-702: ship (x, y), the
# cockpit detail's offset from the ship, the initial cockpit angle
SHIP_START = [
    (-40, 96, -55, -25, 316),     # HORNET
    (-30, 80, 15, -4, 0),         # RAPIER
    (-40, 86, 44, -3, 0),         # SCIMITAR
    (-40, 80, 18, -13, 0),        # RAPTOR
]

# the switch in DrawScrambleFrame, cutscene.c:487-571: the ship-body
# frame offset, then the cockpit pieces. A piece is
# (frame, 'S'hip or 'D'etail, dx, dy, angle, scale, flip); angle 'A'
# means "use the state's cockpit angle".
SHIP_DRAW = [
    ((10, -25), [(0, 'S', 0, 0, 0, 256, 0),
                 (1, 'D', 0, 0, 'A', 255, 0)]),        # HORNET
    ((10, -16), [(0, 'S', 0, 0, 0, 256, 0),
                 (2, 'S', 153, 5, 0, 256, 0),
                 (1, 'D', 0, 0, 0, 256, 0)]),          # RAPIER
    ((10, -15), [(0, 'S', 0, 0, 0, 256, 0),
                 (2, 'S', 148, 0, 0, 256, 0),
                 (1, 'D', 0, 0, 0, 256, 0)]),          # SCIMITAR
    ((10, -11), [(0, 'S', 0, 0, 0, 256, 0),
                 (2, 'S', 158, 6, 0, 256, 0),
                 (1, 'D', 0, 0, 0, 256, 0)]),          # RAPTOR
]


def _frame(fb, sets, st, actors):
    """DrawScrambleFrame verbatim (cutscene.c:456-603): the two deck
    halves, the four crew actors, the open canopy, the ship and its
    cockpit pieces per type, damage decals, the closed-canopy overlay."""
    _draw(fb, sets['bg'], 0, st['bgr'] - 1, st['bdy'])       # :466-473
    _draw(fb, sets['bg'], 1, st['bgr'], st['bdy'])
    _actor(fb, sets['crew'], actors[0], st['bgr'], st['bdy'])  # :474-477
    _actor(fb, sets['crew'], actors[3], st['bgr'], st['bdy'])
    _actor(fb, sets['crew'], actors[4], st['bgr'], st['bdy'])
    _actor(fb, sets['crew'], actors[2], st['bgr'], st['bdy'])
    if not st['closed']:                                     # :479-485
        _draw(fb, sets['canopy'], st['canopyoff'],
             st['sx'] + 40, st['sy'] - 40)
    (sdx, sdy), pieces = SHIP_DRAW[st['ship']]               # :487-571
    _draw(fb, sets['ship'], st['shipframe'],
          st['sx'] + sdx, st['sy'] + sdy)
    for fr, ref, pdx, pdy, ang, sc, fl in pieces:
        if ref == 'S':
            px, py = st['sx'], st['sy']
        else:
            px, py = st['dx'], st['dy']
        a = st['angle'] if ang == 'A' else ang
        _draws(fb, sets['ck'], fr, px + pdx, py + pdy, a, sc, fl)
    if st['ndetail']:                                        # :573-591
        row = SHIP_DETAILS[st['ship']]
        for i in range(st['ndetail']):
            fr, ddx, ddy = row[st['slots'][i]]
            _draw(fb, sets['decal'], fr, st['sx'] + ddx, st['sy'] + ddy)
    if st['closed']:                                         # :593-603
        if st['ovx'] != -1000:
            _draw(fb, sets['overlay'], 0, st['ovx'], st['ovy'])
        _draw(fb, sets['lcanopy'], st['canopyoff'], 100, 127)


def _sets_for(ship, landing):
    """The sprite sets a deck scene needs, or None if any is missing."""
    names = {'bg': 'scr01.wcs', 'ship': 'scr03.wcs', 'crew': 'scr04.wcs',
             'ck': 'cksc%d.wcs' % ship}
    if landing:
        names['canopy'] = 'scr06.wcs'
        names['overlay'] = 'scr05.wcs'
        names['lcanopy'] = 'scr06.wcs'
        names['decal'] = 'scr09.wcs'
    else:
        names['canopy'] = 'scr02.wcs'
    ss = {}
    for k, n in names.items():
        s = _set(n)
        if s is None:
            return None
        ss[k] = s
    return ss


def deck(ship):
    """scramble(): climbing into the fighter. Only the four WC1 cockpits
    have converted pieces; any other player ship (SM2's Dralthi) skips
    the sequence. Returns True when a button cut it."""
    if ship not in (0, 1, 2, 3):
        return False
    sets = _sets_for(ship, False)
    if sets is None:
        return False
    fb = display.buffer
    display.fill(0)
    sx, sy, ddx, ddy, angle = SHIP_START[ship]
    st = {'sx': sx, 'sy': sy, 'dx': sx + ddx, 'dy': sy + ddy,
          'angle': angle, 'bgr': 64, 'bdy': 0,      # cutscene.c:653-655
          'canopyoff': 0, 'shipframe': 0, 'closed': False,
          'ovx': -1000, 'ovy': 0, 'ship': ship, 'ndetail': 0,
          'slots': None}
    # ConfigureScrambleActor is called for indices 0, 2, 3, 4 only
    # (cutscene.c:657-664); the zeroed entry at index 1 is never drawn -
    # DrawScrambleFrame uses actors 0, 3, 4, 2 (cutscene.c:474-477).
    actors = [_new_actor(i, DECK_ACTORS[i]) if i in DECK_ACTORS else
              _new_actor(i, (0, 0, 0, 0, 0, 0, 0)) for i in range(5)]

    def draw():
        _frame(fb, sets, st, actors)

    # phase 1: 10 frames, ship slides in, cutscene.c:704-719
    def adv1(i):
        st['sy'] -= 2
        st['dy'] -= 2
        st['sx'] += 4
        st['dx'] += 4
        st['bgr'] -= 1
    esc = _steps(10, draw, adv1)
    if esc:
        return True

    # phase 2: 27 frames, canopy rises, cutscene.c:721-734
    def adv2(i):
        st['sx'] += 4
        st['dx'] += 4
        st['bgr'] -= 1
        st['canopyoff'] += 1
        if st['shipframe'] < 25:
            st['shipframe'] += 1
    esc = _steps(27, draw, adv2)
    if esc:
        return True

    # canopy hydraulics: one step back (cutscene.c:737)
    st['canopyoff'] -= 1

    # phase 3: 23 frames, cockpit swings in, cutscene.c:739-767
    def adv3(i):
        if st['ship'] == 0:
            st['angle'] += 2
        elif st['ship'] in (1, 3):
            st['dx'] -= 2
        elif st['ship'] == 2:
            # scimitar: the cockpit drops one row at frame 21 only,
            # otherwise it slides left (cutscene.c:755-761)
            if i == 21:
                st['dy'] += 1
            else:
                st['dx'] -= 2
        if st['shipframe'] < 35:
            st['shipframe'] += 1
    esc = _steps(23, draw, adv3)
    if esc:
        return True
    _advance(60 * 1000 // 60)                       # cutscene.c:771-772
    return False


# --- landing (landing, cutscene.c:801-995) -----------------------------------

# anLandingDamageDetailCounts[4] - cutscene.c:124-126 (0x00465aa8)
LAND_COUNTS = [0, 8, 16, 24]

# apszLandingDamageComments[4] - cutscene.c:128-133
LAND_COMMENTS = (b'You got away pretty clean, sir!',
                 b'Looks like it got a little hot out there, sir!',
                 b'You sure got yourself shot up, sir!',
                 b'Glad to see you made it back alive, sir.')

# the canopy frame lists - cutscene.c:135-148; 0x40 is the stop marker
LAND_CANOPY_HEAVY = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10,
                     10, 10, 8, 7, 6, 5, 4, 3, 2, 1, 0, 0x40]
LAND_CANOPY_LIGHT = [0, 1, 2, 3, 11, 12, 13, 14, 14, 14, 14, 14,
                     14, 14, 13, 12, 11, 3, 2, 1, 0, 0x40, 0, 0]
LAND_CANOPY_MODERATE = [0, 15, 16, 17, 18, 19, 19, 18,
                        17, 16, 15, 0, 0x40, 0, 0, 0]
# apLandingCanopyFrames[4] selection - cutscene.c:150-155
LAND_CANOPY = [LAND_CANOPY_LIGHT, LAND_CANOPY_MODERATE,
               LAND_CANOPY_HEAVY, LAND_CANOPY_HEAVY]

# ConfigureScrambleActor calls for landing, cutscene.c:859-866
LAND_ACTORS = {
    3: (140, 88, 2, 0, 0x80, 0, 0),
    4: (139, 88, 2, 0, 0x80, 0, 0),
    0: (240, 94, -1, 0, 0x100, 0, 0x10),
    2: (160, 120, 0, 0, 0x100, 0, 0),
}

# landing positions per ship - cutscene.c:871-900
LAND_SHIP = [(124, 140, 69, 115, 360),    # HORNET (angle 360)
             (124, 130, 94, 125, 0),      # RAPIER
             (124, 134, 124, 132, 0),     # SCIMITAR
             (124, 126, 96, 113, 0)]      # RAPTOR (and SDL Dralthi)

# aaScrambleShipDetails[4][32] - cutscene.c:49-122 (0x00465828), verbatim:
# (frame, x, y) offsets of the damage decals, one row per player fighter
SHIP_DETAILS = [
    # HORNET, cutscene.c:50-67
    [(2, 23, 5), (3, -112, 16), (6, -94, -23), (6, -26, 5),
     (7, -58, -11), (7, -98, 5), (7, -14, 13), (7, 60, 6),
     (7, 149, 24), (9, -112, -24), (9, -99, -9), (9, -116, 18),
     (9, -81, 15), (9, -41, 9), (9, -54, 1), (9, -12, -14),
     (9, 45, 18), (9, 75, 11), (9, 130, 14), (9, 166, 24),
     (0, -68, -35), (0, -19, -9), (0, 68, 13), (8, -76, -18),
     (8, -33, -1), (8, 97, 31), (10, -86, 10), (10, -117, 47),
     (10, 9, 0), (1, -111, 52), (1, -50, 15), (1, 75, 5)],
    # RAPIER, cutscene.c:68-85
    [(3, -88, 20), (6, -57, 29), (7, -139, 63), (7, -72, 5),
     (7, -14, 28), (9, -91, -34), (9, -113, -14), (9, -132, 33),
     (9, -95, 34), (9, -60, 12), (9, -155, 52), (9, -66, 51),
     (9, -56, 44), (9, 44, 35), (9, 57, 25), (9, 59, -1),
     (9, 123, 41), (9, 148, 30), (0, -135, -2), (0, -100, 59),
     (8, -40, 11), (10, -157, -19), (10, -77, 35), (6, 248, 17),
     (7, 300, 41), (9, 172, 27), (9, 194, 12), (9, 291, 17),
     (9, 290, 35), (0, 233, 20), (8, 206, 17), (10, 187, 42)],
    # SCIMITAR, cutscene.c:86-103
    [(3, -97, -6), (3, 89, 9), (6, 151, -4), (7, -91, -39),
     (7, -78, -16), (7, -56, 41), (7, 124, 1), (7, -118, 0),
     (9, -107, -37), (9, -127, 38), (9, -102, 21), (9, -67, 35),
     (9, -54, -14), (9, 12, 34), (9, 35, 39), (9, 31, 21),
     (9, 130, 35), (9, 185, 10), (0, -42, -3), (0, 75, 35),
     (0, 177, 42), (8, -126, -39), (10, -16, 37), (10, 148, 5),
     (1, -3, 45), (6, 160, 38), (7, 154, 16), (9, 188, 3),
     (9, 150, 37), (9, 214, 31), (9, 302, 16), (8, 200, 15)],
    # RAPTOR, cutscene.c:104-121
    [(6, 103, 18), (7, -114, 4), (7, -142, 39), (7, 48, 23),
     (7, 88, 44), (9, -67, -30), (9, -134, -24), (9, -82, -1),
     (9, -45, 19), (9, -153, 46), (9, -8, 48), (9, 11, 24),
     (9, 64, 27), (9, 141, 38), (9, 154, 12), (0, -105, -20),
     (0, 18, 14), (0, 134, 20), (8, -153, -11), (10, -76, 64),
     (10, 33, 18), (1, -85, -28), (1, -154, 14), (1, 148, 21),
     (3, 198, 23), (6, 260, 14), (7, 238, 19), (9, 165, 14),
     (9, 221, 22), (0, 246, 16), (8, 221, 33), (1, 282, 22)],
]


def _pick_slots(n):
    """cutscene.c:820-832: n distinct detail slots drawn at random from
    0..31, re-drawn until they differ from all earlier picks."""
    slots = []
    for _ in range(n):
        while True:
            d = _rnd(5) & 31
            if d not in slots:
                break
        slots.append(d)
    return slots


def landing(damage, ship):
    """landing(damageLevel): the fighter settles on the deck, the canopy
    comes up, and the deck crew comments on the damage. WC1 cockpits
    only; missing files skip the scene. Returns True when cut."""
    if ship not in (0, 1, 2, 3):
        return False
    sets = _sets_for(ship, True)
    if sets is None:
        return False
    fb = display.buffer
    display.fill(0)
    sx, sy, dx, dy, angle = LAND_SHIP[ship]
    st = {'sx': sx, 'sy': sy, 'dx': dx, 'dy': dy, 'angle': angle,
          'bgr': 32, 'bdy': 0,                            # :858
          'canopyoff': 0, 'shipframe': 34,                # :867-868
          'closed': True,
          'ovx': -1000, 'ovy': 0,                         # :869
          'ship': ship, 'ndetail': LAND_COUNTS[damage],   # :818-819
          'slots': _pick_slots(LAND_COUNTS[damage])}      # :820-832
    # ConfigureScrambleActor is called for indices 3, 4, 0, 2 only
    # (cutscene.c:859-866); the zeroed entry at index 1 is never drawn
    # (cutscene.c:474-477).
    actors = [_new_actor(i, LAND_ACTORS[i]) if i in LAND_ACTORS
              else _new_actor(i, (0, 0, 0, 0, 0, 0, 0)) for i in range(5)]

    def draw():
        _frame(fb, sets, st, actors)

    # phase 1: 30 frames, the ship comes down, cutscene.c:902-915
    def adv1(i):
        st['sy'] -= 2
        st['dy'] -= 2
    esc = _steps(30, draw, adv1)
    if esc:
        return True

    # canopy loop: 30 frames, the scroll overlay slides across,
    # cutscene.c:918-964
    st['ovx'] = st['sx'] + 180
    st['ovy'] = st['sy'] + 50
    frames = LAND_CANOPY[damage]
    fi = 0

    # canopyFrame drives the scimitar branch and the canopy-index guard
    # (cutscene.c:950-961), not fi - fi is the moving pointer into the
    # frame table.
    def adv2(i):
        nonlocal fi
        st['ovy'] -= 1
        st['ovx'] -= 4
        if st['ship'] == 0:
            st['angle'] -= 2
        elif st['ship'] in (1, 3):
            st['dx'] += 2
        elif st['ship'] == 2:
            if i == 0:
                st['dy'] -= 1
            else:
                st['dx'] += 2
        if i > 6 and frames[fi] != 0x40:       # :958-961
            st['canopyoff'] = frames[fi]
            fi += 1
    esc = _steps(30, draw, adv2)
    if esc:
        return True

    # the deck crew's comment, cutscene.c:967-977: black text band,
    # the line at (0, 160) in cBlueColour (init.c:14), held 300 ticks
    G.fill_rows(fb, 79, 128, 0)
    ui.small.draw(fb, LAND_COMMENTS[damage], _cx(0), _cy(160),
                  ui.pal565(0x25))
    display.update()
    _advance(300 * 1000 // 60)                 # WaitForSceneAdvance(300)
    G.fill_rows(fb, 79, 128, 0)
    return False


def cleanup():
    """Let go of the sprite sets between flights."""
    _sets.clear()
