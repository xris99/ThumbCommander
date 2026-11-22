# scene.py - the scripted cutscene interpreter: the "Meanwhile..."
# scenes between series (docs/06 6.1).
#
# Interpreter semantics are a verbatim port of
#   UpdateSceneAnimationObject  wc1-re src/logic.c:2291 (0x424EF0)
#   PlaySceneAnimation          wc1-re src/logic.c:2592 (0x425500)
#   ShowMeanwhileTransition     wc1-re src/pilot.cpp:36-75
#   SceneDirector               wc1-re src/screens.c:1344-1462
# on the device forms written by tool/wc1_convert.py: object records
# '<BBiiHhh' and a flat 4-byte '<BBh' instruction stream
# (wc1_convert.py _compile_script). X/Y positions live in the original
# pixel space and integrate by integer addition exactly like the
# original (logic.c:2431-2450); they are scaled to the device's 8.7
# units (128 units per device pixel) only at the draw site (_x8/_y8),
# so goals and completion are exact integer tests like the original's
# and the picture is placed by the same rounding every frame.
#
# One deliberate difference from a naive re-implementation: object state
# is per variant and persists across animations, including across a
# replay of the same animation number - the scene packets replay
# animation numbers pervasively (docs/06, tool/wc1_scene probe).
# PlaySceneAnimation rebinds only the script cursor per call
# (logic.c:2616-2627); delay, repeatCursor, positions, frame, scale,
# rotation, deltas and goals all survive a replay.

import struct
from struct import unpack_from
from time import ticks_ms, ticks_diff, ticks_add
from thumby_engine.platform import (display, buttonA, buttonB, buttonMENU)
import ui
import wcdata as D
import wcgfx as G
import wcmath as M

# the ISA the converter emits (wc1_convert.py:838-919): ord bytes
K = 0x4B                    # stands for the script's terminating NUL
N = 0x4E                    # closes a 'D' group (the 0xFF byte's place)
E = 0x45                    # closes an 'E' group, stays on the group
D_O = 0x44                  # draw entries (both group kinds)
B = 0x42                    # label (the converter resolved jumps already)
G_O = 0x47                  # goto
J = 0x4A                    # jump, ends the turn
R_O = 0x52                  # copy x/y/rotation/scale/frame from an object
W = 0x57                    # global wait
A = 0x41                    # add a property
L = 0x4C                    # load a property
Q = 0x51                    # set a goal
P = 0x50                    # end the turn (never emitted by the converter)

# property bytes (logic.c:2300-2360)
PX = 0x58
PY = 0x59
PT = 0x54
PF = 0x46
PR = 0x52
PS = 0x53


def _x8(v):
    """Original pixels -> the device's 8.7 units: floor(v * 512 / 10 +
    1 / 2) is round(v * SCREEN_SX * 128) with SCREEN_SX = 2/5
    (tool/wc1/gfx.py:22). The tenth of the product never lands on a
    .5 tie (2v is always even), so this integer form and round()
    agree for every v."""
    return (v * 512 + 5) // 10


def _y8(v):
    """Original pixels -> the device's 8.7 units: floor(v * 6144 / 100
    + 1 / 2) is round(v * SCREEN_SY * 128) with SCREEN_SY = 12/25
    (tool/wc1/gfx.py:23). 44v mod 100 is never 50 (44 and 100 share
    the factor 4, 50 does not), so again no tie: this is round()."""
    return (v * 6144 + 50) // 100


# the picture viewport of a conversation/scene: rows 16..77 clip at y1 78,
# the subtitle text starts at y = 79 (docs/05 5.3, docs/06 "y = 160" of
# the 200-row original)
PIC_Y0 = 16
PIC_Y1 = 78
TXT_Y = 79

# one pass of PlaySceneAnimation's loop is one displayed frame; outside
# flight the rate is 16 per second, 62 ms (docs/01 ch 1.4, docs/06)
STEP_MS = 62

# scratch buffer for one shape frame: the biggest converted pri tile is
# 128x61, the biggest sec frame 107x61 (docs/06 storage plan)
VIEW_N = 128 * 62

# object state, one list of ints per object (index meanings):
#   0 x (orig px)  1 y (orig px)   2 scale   3 rotation (deg)
#   4 frame (the draw site uses it as the flip bits, gr.c:541-551)
#   5 layer (0 pri, 1 sec, 2 not drawn)
#   6..10 deltas X Y R S F      11..15 goals X Y R S F   16 goal flags
#   17 delay        18 script start      19 script cursor
#   20 repeat cursor (the first draw entry of the last group)
# The runtime scratch matches the original: the converter writes zero
# delay/goals/deltas because the shipped data starts every object that
# way (probe: initial delay, goals and deltas are all zero).

def _rotation_wrap(r):
    """The two wrap expressions of the 'R' property verbatim
    (logic.c:2338): rotate into 0..359."""
    if r < 0:
        r = (((0x167 - r) & 0xFFFF) // 0x168) * 0x168 + r
    if r >= 0x168:
        r = r - ((r & 0xFFFF) // 0x168) * 0x168
    return r


def goal_reached(delta, current, goal):
    """SceneAnimationGoalReached verbatim (logic.c:2275)."""
    if delta < 0:
        return 1 if current <= goal else 0
    if delta > 0:
        return 1 if current >= goal else 0
    return 1 if current == goal else 0


def _apply2(prop, value, obj, local, add):
    """The property bodies of 'A' and 'L' verbatim (logic.c:2300-2360).
    local carries the delay set this turn (the 'T' property works on the
    local value, logic.c:2326-2330)."""
    if prop == PX:
        if add:
            obj[0] += value
        else:
            obj[0] = value
        obj[6] = value
    elif prop == PY:
        if add:
            obj[1] += value
        else:
            obj[1] = value
        obj[7] = value
    elif prop == PT:
        local[0] = local[0] + value if add else value
    elif prop == PF:
        if add:
            obj[4] += value
        else:
            obj[4] = value
        obj[10] = value
    elif prop == PR:
        if add:
            obj[3] = _rotation_wrap(obj[3] + value)
        else:
            obj[3] = _rotation_wrap(value)
        obj[8] = value
    elif prop == PS:
        if add:
            obj[2] += value
        else:
            obj[2] = value
        if obj[2] < 0x40:
            obj[2] = 0x40
        elif obj[2] > 0x1FFF:
            obj[2] = 0x1FFF
        obj[9] = value


def _goal(prop, value, obj):
    """'Q' goal flags and values verbatim (logic.c:2348-2360)."""
    if prop == PF:
        obj[16] |= 0x10
        obj[15] = value
    elif prop == PR:
        obj[16] |= 1
        obj[14] = value
    elif prop == PS:
        obj[16] |= 2
        obj[13] = value
    elif prop == PX:
        obj[16] |= 4
        obj[11] = value
    elif prop == PY:
        obj[16] |= 8
        obj[12] = value


def _read(ins, pos):
    """(opcode, b1, h) of one device instruction."""
    op = ins[4 * pos]
    b1 = ins[4 * pos + 1]
    h = unpack_from('<h', ins, 4 * pos + 2)[0]
    return op, b1, h


def _update(objs, ins, ninstrs, per, obj, frame_skip, draw, state):
    """UpdateSceneAnimationObject verbatim (logic.c:2291) on the device
    instruction stream. The 'D' / 'E' groups are runs of draw entries
    closed by 'N' / 'E'; re-entering the repeat cursor re-runs exactly
    the original group (wc1_convert.py:838-843). Only 'N'-closed groups
    claim the repeat cursor - the original's 'E' never writes it
    (logic.c:2393-2410)."""
    complete = 0
    delay = obj[17]
    stop = 0
    local = [delay]
    pos = obj[20] if delay != 0 else obj[19]

    while pos < ninstrs and ins[4 * pos] != K and stop == 0:
        op, b1, h = _read(ins, pos)
        pos += 1
        if op == A:
            _apply2(b1, h, obj, local, 1)
        elif op == L:
            _apply2(b1, h, obj, local, 0)
        elif op == Q:
            _goal(b1, h, obj)
        elif op == B:
            pass                        # the label itself does nothing
        elif op == D_O:
            # a group entered at its first draw entry: the entry the
            # dispatch just read IS the first DRAW - it took the place
            # the original 'D' opcode had (wc1_convert.py:839-841), so
            # it must draw too, just like the original's loop draws
            # every frame between the opcode and the 0xFF byte
            # (logic.c:2379-2389). Re-entering at obj[20] reaches this
            # same instruction, so every pass draws the whole group.
            slot = pos - 1
            held = obj[20]
            obj[20] = slot              # logic.c:2376 (the 'D' write)
            if obj[5] != 2 and frame_skip <= 0:
                draw(obj, _x8(obj[0]) + h * 128, _y8(obj[1]), b1)
            while pos < ninstrs and ins[4 * pos] == D_O:
                fbyte, fx = ins[4 * pos + 1], unpack_from(
                    '<h', ins, 4 * pos + 2)[0]
                if obj[5] != 2 and frame_skip <= 0:
                    draw(obj, _x8(obj[0]) + fx * 128, _y8(obj[1]), fbyte)
                pos += 1
            if pos < ninstrs:
                term = ins[4 * pos]
                if term == N:
                    pos += 1            # the 0xFF byte's place
                elif term == E:
                    # the original's 'E' command never touches
                    # repeatCursor (logic.c:2393-2410): the original
                    # dispatches 'E' itself and only 'D' writes the
                    # cursor, so an E group entered through this
                    # dispatched draw entry must leave the repeat
                    # cursor where the last 'D' group put it - a
                    # delayed step re-runs that group exactly like
                    # the original's re-entry (logic.c:2316)
                    obj[20] = held
                    complete = 1
                    pos = unpack_from(
                        '<h', ins, 4 * pos + 2)[0]   # stay on the group
                stop += 1
        elif op == E:
            complete = 1
            pos = h
            stop += 1
        elif op == N:
            obj[20] = h
            stop += 1
        elif op == G_O:
            pos = h                     # continue in the same turn
        elif op == J:
            pos = h
            stop += 1
        elif op == R_O:                 # copy another object (logic.c:2515)
            src = objs[per * b1 + h]
            obj[0] = src[0]
            obj[1] = src[1]
            obj[2] = src[2]
            obj[3] = src[3]
            obj[4] = src[4]
        elif op == W:
            state[0] = h                # nSceneAnimationDelayFrames
            state[1] = 1                # bSceneAnimationWaitCommand
        elif op == P:
            stop += 1

    # The persistence order is deliberate: with an old delay the cursor
    # and the goal test are both skipped (logic.c:2562-2565), so the
    # group under repeatCursor just re-ran and holds the picture.
    if obj[17] != 0:
        obj[17] -= 1
        return 0
    obj[19] = pos
    obj[17] = local[0]
    gf = obj[16]
    if complete == 0 and gf != 0:
        if gf & 0x10:
            complete |= goal_reached(obj[10], obj[4], obj[15])
        if gf & 4:
            complete |= goal_reached(obj[6], obj[0], obj[11])
        if gf & 8:
            complete |= goal_reached(obj[7], obj[1], obj[12])
        if gf & 2:
            complete |= goal_reached(obj[9], obj[2], obj[13])
        if gf & 1:
            complete |= goal_reached(obj[8], obj[3], obj[14])
    return complete


# the inverse-matrix coefficients of RotateRLEImage (screens_portable.inc:
# 634-661) re-expressed in device pixels. The original fetches
#   u = (relX*cos + relY*sin)/scaleX ; v = (-relX*sin + relY*cos)/scaleY
# with relX/relY in ORIGINAL pixels; the port's destination and source
# grids are scaled by SCREEN_SX=2/5 and SCREEN_SY=12/25 instead, so the
# cross terms pick up the anisotropy factors: x->u carries 5/6, y->v
# carries 6/5. 16.16 trig comes from the device's integer sine table
# (wcmath ONE=16384, times 4 = 16.16). Flip is the object's frame bits
# (logic.c:2382 passes it to DrawSpriteScaled; gr.c:541-551 folds the
# bits into signed scaleX/scaleY - the data only ever holds 0 and 0x10).
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


_P = [0] * 12     # reused parameter list for blit_rs (no per-draw alloc)


class _Drawer:
    """Draws one animation's object: reads the shape frame into the
    scratch buffer and blits it. layer 2 objects are never drawn; an
    empty table slot mirrors the DrawSpriteTransformed guard
    (gr.c:531-535)."""

    def __init__(self, S, variant, sec_tbl, view, fb):
        self.S = S
        self.v = variant
        self.tbl = sec_tbl
        self.view = view
        self.fb = fb
        self.pal = ui.pal

    def __call__(self, obj, x8, y8, frame):
        layer = obj[5]
        if layer == 0:
            e = self.S.pri_frame(frame, self.view)
        else:
            e = self.S.sec_frame(self.v, frame, self.tbl, self.view)
        if e is None:
            return
        w, h, hx, hy = e
        # the hot spot lands at (cx, cy): x, y are 8.7 units, rounded to
        # device pixels; the picture sits 16 rows down
        cx = (x8 + 64) // 128
        cy = (y8 + 64) // 128 + PIC_Y0
        scale = obj[2]
        rot = obj[3]
        flip = obj[4] & 0x30
        if scale == 256 and rot == 0 and flip == 0:
            # RotateRLEImage's fast path (screens_portable.inc:543-547):
            # a plain transparent paste at the hot spot
            G.blit_indexed(self.fb, self.pal, self.view,
                           cx - hx, cy - hy, w, h, PIC_Y0, PIC_Y1)
            return
        s16 = scale << 8                # 16.16 screen scale
        if (max(w, h) * s16) >> 16 < 2:
            return                      # smaller than one pixel
        ex = max(hx, w - hx)
        ey = max(hy, h - hy)
        rad = ((M.mag(ex, ey, 0) * s16) >> 16) + 2
        x0 = cx - rad
        if x0 < 0:
            x0 = 0
        x1 = cx + rad + 1
        if x1 > 128:
            x1 = 128
        y0 = cy - rad
        if y0 < PIC_Y0:
            y0 = PIC_Y0
        y1 = cy + rad + 1
        if y1 > PIC_Y1:
            y1 = PIC_Y1
        if x0 >= x1 or y0 >= y1:
            return                      # RotateRLEImage's empty-box return
        a, b, c, d = _coeffs(scale, rot, flip)
        p = _P
        p[0] = cx
        p[1] = cy
        p[2] = (hx << 16) + 0x8000      # the +0x8000 source rounding
        p[3] = (hy << 16) + 0x8000
        p[4] = a
        p[5] = b
        p[6] = c
        p[7] = d
        p[8] = x0
        p[9] = y0
        p[10] = x1
        p[11] = y1
        G.blit_rs(self.fb, self.pal, self.view, w, h, p)


class Animation:
    """One PlaySceneAnimation call (logic.c:2592). Objects belong to the
    whole variant table; the animation drives only its slice. The reset
    scope matches the original: script cursor only - everything else the
    object has accumulated survives (replay of the same animation
    number)."""

    def __init__(self, objs, ins, ninstrs, per, animation):
        self.objs = objs
        self.ins = ins
        self.ninstrs = ninstrs
        self.per = per
        self.lo = animation * per
        self.hi = self.lo + per
        for i in range(self.lo, self.hi):
            self.objs[i][19] = self.objs[i][18]   # scriptCursor = start
        self.state = [-1, 0]            # delayFrames, waitCommand
        self.complete = 0
        self.frame_skip = 1

    def step(self, draw):
        self.frame_skip -= 1
        for i in range(self.lo, self.hi):
            self.complete |= _update(self.objs, self.ins, self.ninstrs,
                                     self.per, self.objs[i],
                                     self.frame_skip, draw, self.state)
        if self.state[0] != -1:
            if self.state[0] != 0:
                self.state[0] -= 1
            else:
                self.complete += 1
        if self.frame_skip == 0:
            self.frame_skip = 1


def _skip(a, draw_none):
    """The Esc fast-forward verbatim (logic.c:2663-2681): run the objects
    without drawing until the animation is done or the W command was
    seen, then cut the global wait to zero."""
    while a.complete == 0 and a.state[1] == 0:
        for i in range(a.lo, a.hi):
            a.complete |= _update(a.objs, a.ins, a.ninstrs, a.per,
                                  a.objs[i], 2, draw_none, a.state)
    a.state[0] = 0


# --- text ------------------------------------------------------------------

def expand(st, ai, out, raw, series=None):
    """AddPCName's substitutions (cmpgn.c:102-140) - the same table the
    conversation uses (talk.py expand). $K / $L report the mission that
    just ended, passed in via the Outcome; $S wants the series name."""
    buf = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        i += 1
        if c != 0x24 or i >= n:                 # '$'
            buf.append(c)
            continue
        k = raw[i]
        i += 1
        if k == 0x43:                           # C callsign
            buf.extend(st.callsign.encode())
        elif k == 0x4E or k == 0x50:            # N, P name
            buf.extend(st.name.encode())
        elif k == 0x4B:                         # K kills this mission
            buf.extend(str(out.kills if out else 0).encode())
        elif k == 0x4C:                         # L wingman kills
            buf.extend(str(out.wing_kills if out else 0).encode())
        elif k == 0x44 or k == 0x45:            # D, E date
            buf.extend(('%04d.%03d' % (st.year, st.day)).encode())
        elif k == 0x54:                         # T time
            buf.extend(('%02d:00' % (6 + st.missions % 12)).encode())
        elif k == 0x52:                         # R rank
            r = ai.ranks[min(4, st.rank)]
            if i < n and raw[i] == 0x2E and r[-1:] == b'.':
                r = r[:-1]
            buf.extend(r)
        elif k == 0x41:                         # A medal
            buf.extend(ai.medals[max(0, min(4, out.medal if out else -1))])
        elif k == 0x53:                         # S system name
            if series is not None:
                buf.extend(series)
            else:
                buf.append(k)
        elif k == 0x57:                         # W<n> wingman name
            if i < n:
                p = raw[i] - 0x30
                i += 1
                if 0 <= p < 8:
                    buf.extend(ai.pilots[p][0])
        else:
            buf.append(k)                       # unknown: leave the letter
    return bytes(buf)


def subtitle(fb, line, colour):
    """The subtitle below the picture (PlaySceneAnimation prints it at
    y = 160 of the 200-row original, logic.c:2605-2610): the text
    viewport is cleared first (the ClearViewport call right before)."""
    G.fill_rows(fb, TXT_Y, 128, 0)
    lines = []
    for part in line.split(b'\n'):
        lines.extend(ui.text.wrap(part, 122))
    y = TXT_Y
    room = (120 - y) // 9
    for ln in lines[:room]:
        ui.text.draw(fb, ln, 3, y, colour)
        y += 9


# --- the animation driver ---------------------------------------------------

def play(S, variant, tbl, objs, ins, ninstrs, per, nanim, animation,
         duration, view):
    """PlaySceneAnimation(text, shot - 50, duration) minus the subtitle
    (the caller drew it). Returns 'done', 'ff' (A fast-forwarded) or
    'skip' (B / MENU). The step clock is time-based (docs/06 runtime):
    one script step every 62 ms, drawn after each step; if a step takes
    longer, the steps that became due run without presenting and only
    the last picture shows."""
    if animation >= nanim:
        return 'done'                   # nothing was recorded for it
    fb = display.buffer
    a = Animation(objs, ins, ninstrs, per, animation)
    drawer = _Drawer(S, variant, tbl, view, fb)
    ff = False
    nxt = ticks_ms()
    while a.complete == 0:
        while ticks_diff(ticks_ms(), nxt) < 0:
            display.update()
            if buttonA.justPressed():
                _skip(a, None)
                ff = True
                break
            if buttonB.justPressed() or buttonMENU.justPressed():
                return 'skip'
        if a.complete != 0:
            break
        a.step(drawer)
        display.update()
        nxt = ticks_add(nxt, STEP_MS)
    # after completion: without a W the animation holds for duration / 2
    # (in 1/60 s ticks) or until a key cuts it (logic.c:2683-2690)
    if a.state[0] == -1 and not ff:
        wait_ms = duration * 1000 // 120
        t0 = ticks_ms()
        while ticks_diff(ticks_ms(), t0) < wait_ms:
            display.update()
            if buttonA.justPressed():
                ff = True
                break
            if buttonB.justPressed() or buttonMENU.justPressed():
                return 'skip'
    if ff:
        ui.wait_release()
    return 'ff' if ff else 'done'


# --- the scene --------------------------------------------------------------

def load_variant(S, v):
    """Everything the scene needs from one variant: the object state
    (16-byte records), the instruction stream, the secondary shape
    table and the scene packet."""
    cnt, off = S.variant(v)
    per, nanim, nobjs, ninstrs, nsec, pktlen = cnt
    recs = S.objects(v) if nobjs else b''
    objs = []
    for i in range(nobjs):
        layer, frame, x, y, scale, start, rot = unpack_from(
            '<BBiiHhh', recs, i * S.OBJ_SIZE)
        objs.append([x, y, scale, rot, frame, layer,
                     0, 0, 0, 0, 0,           # deltas X Y R S F
                     0, 0, 0, 0, 0,           # goals X Y R S F
                     0,                       # goal flags
                     0,                       # delay
                     start, start, 0])        # start, cursor, repeat
    ins = S.instructions(v) if ninstrs else b''
    tbl = S.sec_table(v) if nsec else b''
    pkt = S.packet(v) if pktlen else b''
    return per, nanim, ninstrs, objs, ins, tbl, pkt


def _key():
    """Any button, as WaitForSceneAdvance reads them (disk.c:509-548)."""
    return (buttonA.justPressed() or buttonB.justPressed() or
            buttonMENU.justPressed())


def advance(ms):
    """WaitForSceneAdvance: the duration runs out or any button cuts it,
    then let go of the buttons before the next screen reads them."""
    t0 = ticks_ms()
    while ticks_diff(ticks_ms(), t0) < ms:
        display.update()
        if _key():
            break
    ui.wait_release()


def show(scene, variant, st, ai, out=None, series=None):
    """ShowMeanwhileTransition verbatim (pilot.cpp:36-75), minus the
    music track (0x21 + variant) - the port has no music yet. Empty
    variants (no packet, no animations) show the word and fade."""
    fb = display.buffer
    S = D.Scene(scene)
    per, nanim, ninstrs, objs, ins, tbl, pkt = load_variant(S, variant)

    display.fill(0)                        # step 3's clear (pilot.cpp:47)
    ui.backdrop('meanwhile_128_62.COL.bin', PIC_Y0)   # step 2's word
    advance(100 * 1000 // 60)              # WaitForSceneAdvance(100, 0)

    view = bytearray(VIEW_N)
    prev_colour = -2                       # screens.c:1247
    colour = ui.WHITE
    if pkt:
        scene_off = unpack_from('<I', pkt, 0)[0]
        text_base = unpack_from('<I', pkt, 4)[0]
        o = scene_off
        skip = False
        while True:
            shot, col, _talker, dur, _tests, toff, _moff, _foff = \
                unpack_from('<bbbhhhhh', pkt, o)
            if shot == -2:
                break
            # shots 50-59 are scene animations; every record of these
            # packets is one (screens.c:1344-1356, probe)
            if 0 <= col < 14 and col != prev_colour and col != -1:
                prev_colour = col
                if col < 12:
                    c = ai.colours[col]
                elif col == 12:
                    c = 9
                else:
                    c = 13
                colour = ui.pal565(c)
            raw = D.cstr(pkt, text_base + toff)
            if raw:
                subtitle(fb, expand(st, ai, out, raw, series), colour)
                r = play(S, variant, tbl, objs, ins, ninstrs, per, nanim,
                         shot - 50, dur, view)
                if r == 'skip':
                    skip = True
            o += 13
            if skip:
                break                      # screens.c:1461
        G.fill_rows(fb, TXT_Y, 128, 0)     # the director's final clear

    # step 4: fade to black. A fade on an RGB565 buffer is dim_rows over
    # the picture rows (docs/06 6.3), then the black fill
    for _ in range(8):
        G.dim_rows(fb, PIC_Y0, PIC_Y1)
        display.update()
    G.fill_rows(fb, PIC_Y0, PIC_Y1, 0)
    display.update()
    ui.wait_release()
