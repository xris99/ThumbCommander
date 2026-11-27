# ejectseq.py - the ejection and the stranded ending (docs/06 6.2):
# the seat fires through the canopy, the cockpit slides away, the camera
# pulls out behind the tumbling pilot and his ship explodes behind him,
# and - if the carrier was lost - the pilot drifts to the campaign's end.
#
# Verbatim ports of (wc1-re, GPL-3.0):
#   ejection_sequence   src/eject.c:32    (0x4046A0) - stages 1 and 2
#                                                 and the 3-D chase (:143-181)
#   stranded_sequence   src/eject.c:202   (0x404BE0)
#   check_stranded      src/cockpt.c:3013 (0x417B30)
#   any_enemy           src/logic.c:906   (0x423070)
#   distance_from_*     src/geom.c:687-703 (0x419240/0x419260)
# the chase's scripted view (parse_view_script :38, update_scripted_view
# :111, initialize_scripted_view :193), the eye camera (spc.c cases 4
# :213, 10 :412, 11 :419, force_view :470, new_view :478,
# rotate_eye_to_goal :129), the per-pass object upkeep and movement
# (house_keep_objects spc.c:873, update_objects_in_space :1022, called
# by Update_3Space main.c:555), the projection culls
# (transform_objects_to_your_view geom.c:1227), the roll alignment
# (match_roll_orientation geom.c:762) and the explosion
# (ship.c Explosion :1363, ShipExplosion :1325). Built on the same
# sprite sets tool/wc1_convert.py writes from PILOTANM.VGA section 1
# (pil01.wcs, the ejection seat, eject.c:50), section 2 (pil02.wcs, the
# ejected pilot, eject.c:97-99) and PCSHIP.V0N sections 0/3/5
# (ckint<N>, ckbg<N>, ckslide<N>.wcs), plus the flight's own
# sh<NN>.wcs and fx02.wcs sets through the shared MainGame frame cache.
#
# Both sprite scenes fill the whole picture (rows 16..111, clip bottom
# 112); scramble.py's _draw places every piece with the verified mapping.
# One step every STEP_MS; any button breaks a loop (eject.c:75-76,
# 133-134, 221-222). An escape in stage 1 skips stage 2 and the pilot,
# as the guard at eject.c:85 does; an escape in stage 2 also skips the
# chase, as the guard at :142 does. The space picture is cleared every
# pass: RefreshCockpitStatus (main.c:2136-2142) clears whenever
# nFrameSkipCounter <= 1 and every cutscene loop sets it to 1
# (eject.c:55, :124, :162, init.c:202), so the original draws every
# pass and deletes what passed by - the port fills rows 16..111 with
# black at the head of every pass and every chase pass.
#
# Not ported, documented in docs/06 6.2:
#  - the music (track 0x1f) and the seat sounds (sfx 0x21, 0x22, the
#    explosion at chase frame 10 with sfx 4);
#  - the palette fade to black at the end of both scenes: the port
#    dims with G.dim_rows and clears black, as elsewhere in the port.
#  - the stranded text uses the ui.text font, not pIntroFont: the
#    TITLE.VGA intro font is not converted yet (docs/06 6.2 phase 3);
#    the line rows below are print_subtitle's layout (mono.c:213-217)
#    mapped through the picture, and ui.text.centre stands in for the
#    original's GetLineLength centring.
#
# The chase (eject.c:143-181) is the original's 201-frame scripted 3-D
# sequence - the pilot tumbling past the camera, the ship blowing up
# behind him, and the camera chasing in for the fly-by. The port runs
# the same camera, script and projection maths on three local objects
# (pilot, ship, one fireball); deviations are listed in the module
# comments at each site, the standing ones being: no audio, no debris,
# no shock wave, no mission state, the rest of the world frozen and
# undrawn (the chase never touches the live world, so the stranding
# check at MainGame.py:583 stays correct), per-pass velocities instead
# of per-turn ones - with the pass now held to the turn's 100 ms
#(PASS_MS = TURN_MS), they are the per-turn numbers themselves, and
# the star field that cannot respawn while the eye neither pitches nor
# yaws.

import world as W
from time import ticks_ms, ticks_diff
from math import acos
from array import array
from gc import collect
from thumby_engine.platform import display
import ui
import wcgfx as G
import wcmath as M
import wcdata as D
# scramble, sky and the flight module are not imported with this one.
# The chase mirrors the flight's projection constants and its fixed
# divide itself (see the block after PASS_MS), so the room a flight
# leaves does not pay the flight's code again: the device log
# 2026-11-27 died inside _dirv allocating 1,488 bytes with FREE 6,400 -
# the 72,400 the flight had released, minus exactly what `import
# ejectseq` had claimed by landing its module-top imports: ejectseq
# 8.5 KB, scramble and its 12,288-byte scratch 22.2, sky 5.9, flight
# 15.2, ai 14.8. The scenes import what they draw with inside, for
# themselves, guarded: no room, the scene that does not need it plays
# instead of an out-of-memory. docs/12 12.1, 12.4.

FULL_Y1 = 112

# asEjectionPrimaryFrames[8] - eject.c:11-13 (0x00465550)
EJECT_PRIMARY = [0, 1, 1, 3, 3, 0, 0, 0]
# asEjectionSecondaryFrames[8] - eject.c:15-17 (0x00465560)
EJECT_SECONDARY = [-1, -1, 2, -1, 4, 0, 0, 0]

# pStrandedMessage - eject.c:23-25 (0x00465588), without the leading
# newline (print_subtitle counts it into the empty first row, mono.c:207)
STRANDED_LINES = (b'With your carrier',
                  b'destroyed, you drift',
                  b'endlessly through',
                  b'the void...')
# print_subtitle's line rows for the 5-line message (mono.c:207-216):
# y = (128 - 5 * 16) / 2 = 24, the lines run 40, 56, 72, 88; mapped
# through the picture (_y8 + 16) they are the device rows below
STRANDED_ROWS = [35, 43, 51, 58]
# "THE END" is one line at y = (128 - 16) / 2 = 56 (mono.c:213)
THE_END_ROW = 43

# --- chase constants ---------------------------------------------------------
# the ejection's view script - eject.c:19-21 (0x00465570): mode 11 for
# 70 passes, mode 10 for 80, mode 4 until the end (cmd -1 stops the
# script right after force_view(4))
EJECT_SCRIPT = (3, 11, 14, 70, 3, 10, 14, 80, 3, 4, -1, 0)
# the chase draws frames 0..200 (eject.c:165, :176 break when frame > 200)
CHASE_FRAMES = 200

# OBJECT_TYPE_EJECTED_PILOT - wcdata.h:111; types.wc:56 gives class 6
# (OBJECT_CLASS_DEBRIS), collision radius 6 and scale 512 (the .wcs
# table carries the original's row, so no port-chosen pilot scale)
PILOT_TYPE = 56
# the ejection kick: ScaleFixedVector(pilot's up, -0x500) (eject.c:107).
# 0x500 = 1280 Q8 units = 5 m: the pilot leaves the seat at 5 m per pass
# along the cockpit's up, which is -5 m per turn in the flight's units -
# the port applies it once per pass, a documented deviation.
KICK = -1280
# the camera's distance behind the pilot: ScaleFixedVector(pilot's up,
# -0x25800) (eject.c:157) and the case-11 clamp (spc.c:426)
PULL_BACK = 153600
# case 4 aims at 700 m behind the pilot along the ship's forward
# (spc.c:224-227, ScaleFixedVector(aShipFwdVec[0], -700 m))
CHASE_GAP = 700
# case 4 closes the gap at 1/25 of it per pass (spc.c:233 divide_vector
# by (25 << 8))
GAP_DIV = 25 * 256
# velocity conversion: one chase pass is S.STEP_MS ms, one flight turn
# is 100 ms (flight.TURN_MS); outside flight a pass is the turn itself,
# so metres-per-turn are metres-per-pass unchanged
PASS_MS = 100
TURN_MS = 100

# --- the flight, mirrored -------------------------------------------------
# The chase's projection is flight.py's own: _draw_obj below mirrors
# flight.py:262-375, _right_shape mirrors flight.py:194-230, _dirv
# mirrors flight.py:103-117. The flight's constants and its truncating
# divide stand here so the ejection never lands the flight module
# again. The numbers are flight.py's: FX and FY at flight.py:50-51,
# the colours :53-54, the explosion sets :65, tdiv :93-95.

FX = 64                 # flight.py:50 focal length in pixels, horizontal
FY = 77                 # flight.py:51 vertical (the original's 1:1.2 pixels)
WHITE = 0xFFFF          # flight.py:53
GREY = 0x8410           # flight.py:54
_EXPL_SET = ('fx01.wcs', 'fx02.wcs', 'fx03.wcs', 'fx09.wcs')  # flight.py:65


def _tdiv(a, b):        # flight.py:93-95: C division, truncates toward
    return a // b if a >= 0 else -((-a) // b)        # zero


def _per_pass(v):
    """One flight velocity (Q8 metres per turn) as metres per pass:
    v * PASS_MS / TURN_MS with both now the turn's 100 ms, truncated
    away from zero like the original's DivideFixed."""
    return _tdiv(v * PASS_MS, TURN_MS)


class _Ob:
    """One chase object: the fields of world.py's Obj that the chase's
    camera, upkeep and projection touch, as a local snapshot. The live
    world is never read past setup and never written: the stranding
    check after the scene (MainGame.py:583, check_stranded below) still
    sees the simulation's own positions."""

    def __init__(self):
        self.cls = 0
        self.typ = 0
        self.m = [0] * 9
        self.x = 0
        self.y = 0
        self.z = 0
        self.vx = 0
        self.vy = 0
        self.vz = 0
        self.radius = 0
        self.scale = 0
        self.rp = 0
        self.ry = 0
        self.rr = 0
        self.special = 0
        self.counter = 0
        self.af = 0
        self.vis = False              # the projection's visibility flag,
        # like world.py:172 (the renderer fills it)


class _ScriptedView:
    """The scripted eye view of view.c: parse_view_script (:38-168),
    update_scripted_view (:171-195) and initialize_scripted_view
    (:198-206), for the ejection's EJECT_SCRIPT. Commands 4..10 and 13
    never run for this script (the cmd -1 entry stops parsing right
    after force_view(4)), so their pitch/yaw goals and rates stay zero.
    force_view (spc.c:470-475) and new_view (:478-533): force_view sets
    the mode to -1 first, so new_view's same-mode toggle of
    bAlternateChaseView (the -500 m / 26 divisor variant) never fires -
    the chase always uses the -700 m / 25 numbers."""

    def __init__(self, script, eye, view_obj):
        self.script = script
        self.ptr = 0
        self.ctr = 0          # asObjectCounterArray[EYE_OBJECT], :165
        self.on = True        # bScriptedView
        self.eye = eye
        self.obj = view_obj   # nScriptedViewObject, eject.c:159
        self.mode = -1        # nCameraViewMode
        # the eye's rotation goals: initialize_scripted_view's init_ijk
        # (geom.c:600-614) zeroes the rotations and the identity basis
        self.pitch_target = 0
        self.yaw_goal = 0
        self.pitch_rate = 0
        self.yaw_rate = 0
        self.roll_rate = 0
        self.roll_target = 0          # nEyeRollTargetValue, set by the
        # match in case 4 (only the cmd 13 test reads it before that)
        self.eye.vx = 0
        self.eye.vy = 0
        self.eye.vz = 0       # zero_vector (:199)
        M.identity(eye.m)     # init_ijk: R=(1,0,0) U=(0,1,0) F=(0,0,1)
        eye.rp = 0
        eye.ry = 0
        eye.rr = 0
        self.parse()          # view.c:204
        eye.radius = 100      # :205, after the parse's radius override

    def force_view(self, view):
        """force_view (spc.c:470-475): nCameraViewMode = -1 then
        new_view(view, nScriptedViewObject). bScriptedView is still 1
        here (the parse flips it only on its way out), so new_view's
        bScriptedView == 0 branch (:519-538, the 1200 m reposition for
        mode 4) never runs for this cutscene."""
        self.mode = -1
        self.mode = view      # new_view :502
        self.eye.radius = max(10, self.obj.radius)    # new_view :506-509

    def parse(self):
        scr = self.script
        n = len(scr)
        while True:
            # view.c:47-51: -1 turns the script off (the :44-45 13-goto
            # can't fire here - this script starts with a 3)
            if scr[self.ptr] == -1:
                self.on = False
                self.obj = None       # nScriptedViewObject = -1, :48
                return
            cmd = scr[self.ptr]
            self.ptr += 1             # switch (*pCurrentViewScriptPtr++)
            if cmd == 3:              # case 3, view.c:88-91
                self.force_view(scr[self.ptr])
                self.ptr += 1
            if self.ptr < n and scr[self.ptr] == 13:    # :162
                return
            # view.c:46-53: the loop-top checks, breaking on 14
            while True:
                if self.ptr >= n:
                    break             # the original reads past the end
                # the cmd 4 the original parses at pass 151 - but this
                # script's -1 entry ends parsing before the trailing 0
                c2 = scr[self.ptr]
                if c2 == -1:
                    self.on = False
                    self.obj = None
                    return            # view.c:47-51, before :165
                if c2 == 14:          # :52-53
                    break
                self.ptr += 1
                if self.ptr < n and scr[self.ptr] == 13:
                    return            # :162 again (the outer loop's
                    # :228 check covers the case-3 step)
            # view.c:165: the counter is the value after the 14
            self.ctr = scr[self.ptr + 1]
            return

    def update(self):
        """update_scripted_view (view.c:171-195). cmd 13 never appears
        in this script; cmd 14 is the countdown that advances the
        pointer and re-parses when the counter runs out."""
        c = self.script[self.ptr]
        if c == 13:                   # :178-184, never reached here
            if (self.yaw_goal == self.pitch_target) != self.roll_target:
                self.ptr += 1
                self.parse()
        elif c == 14:                 # :185-192
            counter = self.ctr        # counter = asObjectCounterArray[61]
            self.ctr -= 1             # asObjectCounterArray[61]--
            if counter < 1:
                self.ptr += 2         # :189-190: skip the 14 and its
                self.parse()          # count and parse the next entry


def _roll_target(em, pm):
    """match_roll_orientation (geom.c:762-777): the angle between the
    eye's up and the viewed object's up, measured clockwise. roll.x =
    dot(eye.up, obj.right), roll.y = dot(eye.up, obj.up), z stays 0;
    angle = ArcCos(roll.y), flipped to 360 - angle when roll.x is on
    the right, wrapped into -180..180 (WrapDegrees)."""
    rx = (em[3] * pm[0] + em[4] * pm[1] + em[5] * pm[2]) >> 14
    ry = (em[3] * pm[3] + em[4] * pm[4] + em[5] * pm[5]) >> 14
    n = M.mag(rx, ry, 0)
    if n == 0:                        # Normalize of a zero vector: the
        return 0                      # original's ArcCos then sees 0
    c = ry / n                        # float: the original's ArcCos of
    if c > 1.0:                       # the normalized roll vector
        c = 1.0
    elif c < -1.0:
        c = -1.0
    ang = int(round(acos(c) * 57.29578))
    if rx >= 0:
        ang = 360 - ang               # :774-775
    return M.wrap(ang)                # :776


# --- the chase's projection (transform_objects_to_your_view + the
# flight's verified draw_object, spc.c / geom.c:1227) -------------------------

_DIRV_N = 62


def _dirv():
    """The direction-view bases of init.c's initialize_direction_view_frames
    as flight.py:103-117 built them: the 62 shape directions (12 yaw
    sectors x 5 pitch bands between them, plus straight up and straight
    down) as (right, up) pairs in the direction's own frame, clamped to
    the signed range of the 'h' array."""
    dv = array('h', [0] * (_DIRV_N * 6))
    tmp = [0] * 9
    for idx in range(_DIRV_N):
        if idx == 0:
            yw = 0; pt = 90
        elif idx == 61:
            yw = 0; pt = -90
        else:
            yw = ((idx - 1) % 12) * 30
            pt = 60 - ((idx - 1) // 12) * 30
        M.identity(tmp)
        M.yaw(tmp, yw)
        M.pitch(tmp, pt)
        for k in range(6):
            dv[idx * 6 + k] = min(32767, tmp[k])
    return dv


def _right_shape(T, dv, ob, dx, dy, dz, em, table):
    """get_right_shape (geom.c:1382-1466) exactly as flight.py:194-230
    ports it: the frame and flip from the direction table, and the
    clockwise screen angle of the eye's up against the chosen direction's
    own up. The dying ship is a player fighter, so the chase always
    calls this with the player's table 0."""
    ox, oy, oz = M.to_frame(ob.m, -dx, -dy, -dz)
    yw, pt = M.spherical(ox, oy, oz)
    q = _tdiv(pt, 30)
    rem = pt - q * 30
    band = q + 3
    if rem > 15:
        band = min(band + 1, 6)
    elif rem < -15:
        band = max(band - 1, 0)
    q = _tdiv(yw, 30)
    rem = yw - q * 30
    ys = (12 - q) % 12
    if rem > 15:
        ys = (ys + 11) % 12
    elif rem < -15:
        ys = (ys + 1) % 12
    if band <= 0:
        idx = 0
    elif band >= 6:
        idx = 61
    else:
        idx = band * 12 + ys - 11
    # the eye's up in the object's frame, dotted against the direction's
    # right and up (flight.py:218-222)
    eux, euy, euz = M.to_frame(ob.m, em[3], em[4], em[5])
    b = idx * 6
    px = eux * dv[b] + euy * dv[b + 1] + euz * dv[b + 2]
    py = eux * dv[b + 3] + euy * dv[b + 4] + euz * dv[b + 5]
    ang = M.angle_cw(px >> 8, py >> 8)
    frame = T.dir_frame[idx + table * 62]
    if frame == 0:
        ang -= 90
    elif frame == 36 and table != 1:
        ang += 90
    return frame, T.dir_flip[idx + table * 62], ang % 360


_P13 = [0] * 12               # the blit parameter block (flight.py:99)


_SETS = {}


def _sset(name):
    """The sprite-set loader of flight.py:183-191 (Flight.sset) for the
    chase's own ship and fireball sets. A missing file is 0: flight draws
    such an object as a dot instead (flight.py:320-328)."""
    s = _SETS.get(name)
    if s is None:
        if D.exists(name):
            s = D.SpriteSet(name)
        else:
            s = 0
        _SETS[name] = s
    return s


def _draw_obj(fb, pal, cache, em, eye, ob, T, dv, pss, S):
    """Project and draw one chase object exactly as flight.py:262-375 -
    the port's verified mirror of transform_objects_to_your_view
    (geom.c:1227) - run with the eye at its true position: the cutscene
    has no game turn to preview, so there is no g step-back. flight's
    fixed 60 m z cull stands in for the player's own radius in the
    cockpit; the chase uses the original's two eye-radius culls instead
    (geom.c:1262-1266 and :1276-1280, the * 0x100 scaling being the
    port's metre units) in the original's order - distance first, then
    the view z. At pass 70 the eye rides the pilot, so everything at
    zero distance hides behind him."""
    ob.vis = False                    # flight.py:264
    dx = (ob.x - eye.x) >> 8          # flight.py:267-269 with g = 0:
    dy = (ob.y - eye.y) >> 8          # a cutscene has no step-back
    dz = (ob.z - eye.z) >> 8          # preview
    if dx > 40000 or dx < -40000 or dz > 40000 or dz < -40000:
        return                        # flight.py:270 (no dy bound)
    dist = M.mag(dx, dy, dz)
    if dist < eye.radius:             # geom.c:1262-1266
        return
    vx, vy, vz = M.to_frame(em, dx, dy, dz)    # flight.py:272: the
    if vz < eye.radius:               # delta is NOT negated here -
        return                        # right_shape negates it itself;
    # geom.c:1276-1280 culls on the eye's radius, flight's 60 stands in
    # outside the view cone: skip, unless the object is big enough to
    # reach into the picture from there (a carrier alongside)
    if vz * 256 < dist * 0x94 and ob.radius * 3 < dist:
        return                        # flight.py:276-279
    sx = 64 + FX * vx // vz        # flight.py:280-281 at the picture's
    sy = 64 - FY * vy // vz        # centre (no cockpit: 0..128, 16..112)
    c = ob.cls
    typ = ob.typ
    frame = 0
    flip = 0
    ang = 0
    sset = None
    if c == W.C_EXPLOSION:            # flight.py:299-301
        sset = _sset(_EXPL_SET[min(3, typ - W.OT_EXPLOSION0)])
        frame = ob.counter >> 1       # the original's animate_object step
    elif c >= W.C_SHIP:               # flight.py:290-293, table 0: the
        sset = _sset('sh%02d.wcs' % typ)    # dying ship is a player fighter
        frame, flip, ang = _right_shape(T, dv, ob, dx, dy, dz, em, 0)
    elif c == W.C_DEBRIS:             # the pilot: the original's DEBRIS
        sset = pss                    # branch (geom.c:1339-1341) skips
        frame = ob.af % pss.n         # get_right_shape, so the pilot is
    else:                             # drawn at angle 0 with flip 0 -
        return                        # the tumble is the pil02 animation
    # far off screen: the margin grows with the object's projected size,
    # so a big ship is not dropped while its hull still shows
    mg = 100 + FX * ob.radius // vz        # flight.py:310-315, at the
    if sx < 0 - mg or sx > 128 + mg or \
            sy < S.PIC_Y0 - mg or sy > FULL_Y1 + mg:
        return                        # picture's margins
    ob.vis = 0 <= sx < 128 and S.PIC_Y0 <= sy < FULL_Y1    # flight.py:316
    dd = dist - ob.radius             # geom.c:1286-1289
    if dd < 1:
        dd = 1
    slot = -1                         # flight.py:321-323
    if sset:
        slot = cache.get(sset, frame)
    if slot < 0:
        if ob.vis:                    # flight.py:325-328
            display.setPixel(sx, sy, GREY)
        return
    res = cache.res[slot]
    # 16.16 screen scale of the stored frame (flight.py:331-335; the cap
    # is the original's 0x2000 screen-scale ceiling, geom.c:1298-1299)
    s16 = ((ob.scale * 40 << 8) // (dd * res)) << 8
    cap = (32 * 64 << 16) // res
    if s16 > cap:
        s16 = cap
    w = cache.w[slot]
    h = cache.h[slot]
    hx = cache.hx[slot]
    hy = cache.hy[slot]               # flight.py:336-339
    if (max(w, h) * s16) >> 16 < 2 or s16 < 2048:
        if ob.vis:                    # too far to resolve: a point of
            col = WHITE if c == W.C_EXPLOSION else GREY
            display.setPixel(sx, sy, col)   # flight.py:340-346
        return
    ex = max(hx, w - hx)              # flight.py:347-348
    ey = max(hy, h - hy)
    rad = ((M.mag(ex, ey, 0) * s16) >> 16) + 2       # flight.py:349
    x0 = max(0, sx - rad)             # flight.py:350-353, clamped to
    x1 = min(128, sx + rad + 1)       # the whole picture instead of
    y0 = max(S.PIC_Y0, sy - rad)      # the cockpit's view rect
    y1 = min(FULL_Y1, sy + rad + 1)
    if x0 >= x1 or y0 >= y1:
        return
    inv = (1 << 24) // (s16 >> 8)     # 16.16 source step (flight.py:356)
    cs = M.icos(ang)                  # flight.py:357-358: the rotation
    sn = M.isin(ang)                  # comes straight from right_shape,
    a = ((inv >> 6) * cs) >> 8        # unscaled (flight.py:359-360)
    b = ((inv >> 6) * sn) >> 8
    if flip & 1:                      # flight.py:361-364: flip bit 1
        ua = -a; ub = -b              # mirrors the frame left-right
    else:
        ua = a; ub = b
    if flip & 2:                      # flight.py:365-368: flip bit 2
        va = b; vb = -a               # swaps the scale axes
    else:
        va = -b; vb = a
    p = _P13                          # flight.py:369-373
    p[0] = sx; p[1] = sy
    p[2] = (hx << 16) + 0x8000; p[3] = (hy << 16) + 0x8000
    p[4] = ua; p[5] = ub; p[6] = va; p[7] = vb
    p[8] = x0; p[9] = y0; p[10] = x1; p[11] = y1
    G.blit_rs(fb, pal, cache.buf[slot], w, h, p)   # flight.py:374


# --- the eye's camera cases (spc.c:161-466) ----------------------------------

def _eye_11(eye, view_obj):
    """Camera case 11 (spc.c:419-438): the eye hangs at the pilot's
    distance along the line to him. One-sided clamp - when the gap has
    shrunk below 600 m the eye is pushed out to exactly 600 m (the
    original only tests < 0x25800, so a gap grown past 600 m is left
    alone); the forward row aims at the pilot and fix_objects_ijk
    re-orthonormalises the basis."""
    vx = view_obj.x - eye.x
    vy = view_obj.y - eye.y
    vz = view_obj.z - eye.z
    n = M.mag(vx, vy, vz)
    if n < PULL_BACK:
        if n == 0:
            n = 1                     # guard the division; the original's
        ax = _tdiv(vx * -PULL_BACK, n)   # Normalize of a zero vector
        ay = _tdiv(vy * -PULL_BACK, n)
        az = _tdiv(vz * -PULL_BACK, n)
        eye.x = view_obj.x + ax       # eye += vector + adjustment
        eye.y = view_obj.y + ay       # (:430-433) = pilot + 600 m away
        eye.z = view_obj.z + az
    eye.m[6] = vx                     # :436 F = vector (raw delta, the
    eye.m[7] = vy                     # fix normalizes it below, spc.c
    eye.m[8] = vz                     # :437)
    M.fix(eye.m)                      # fix_objects_ijk (:438)
    eye.x += eye.vx                   # :439-442: the eye drifts with
    eye.y += eye.vy                   # its own velocity - zero all
    eye.z += eye.vz                   # through mode 11
    return 0


def _eye_10(eye, view_obj):
    """Camera case 10 (spc.c:412-418): the eye rides the pilot -
    copy_frame, his velocity, his position, and no position add. The
    pilot is then at zero distance from the eye and the two radius
    culls in _draw_obj hide him: what the camera sees from pass 70 on
    is the ship and its fireball falling behind (the pilot's -5 m/pass
    kick against the coasting ship)."""
    M.copy(view_obj.m, eye.m)         # copy_frame (:414)
    eye.vx = view_obj.vx              # velocity = pilot's (:415)
    eye.vy = view_obj.vy
    eye.vz = view_obj.vz
    eye.x = view_obj.x                # position = pilot's (:416)
    eye.y = view_obj.y
    eye.z = view_obj.z
    return 0                          # :418: no position add


def _eye_4(eye, view_obj, sh, sv, world):
    """Camera case 4 (spc.c:213-258): the fly-by camera. It aims at the
    point 700 m behind the pilot along the ship's forward, moves
    towards it at 1/25 of the gap per pass, keeps its forward row on
    the pilot, and rolls its up row towards the pilot's up row
    (match_roll_orientation + rotate_eye_to_goal); when the roll is
    almost matched it just pins the up row to the ship's (frozen at
    :251-253) and stops the goal. Then the eye drifts with its
    velocity (:255-257)."""
    vx = view_obj.x - eye.x           # viewDirection (:218-219)
    vy = view_obj.y - eye.y
    vz = view_obj.z - eye.z
    # desired position (:224-227): the ship's forward row scaled by
    # -700 m, added to the pilot's position. (row * (D << 8)) >> 14 is
    # the port's metre scaling. bAlternateChaseView stays 0 (force_view
    # clears the mode first, so new_view's toggle never fires), so the
    # -500 / 26 variant is dead here.
    fx = sh.m[6]
    fy = sh.m[7]
    fz = sh.m[8]
    gx = CHASE_GAP << 8
    des_x = view_obj.x + ((fx * -gx) >> 14)
    des_y = view_obj.y + ((fy * -gx) >> 14)
    des_z = view_obj.z + ((fz * -gx) >> 14)
    pdx = des_x - eye.x               # positionDelta (:228-230)
    pdy = des_y - eye.y
    pdz = des_z - eye.z
    eye.vx = _tdiv(pdx, GAP_DIV)    # velocity = delta / (25 << 8)
    eye.vy = _tdiv(pdy, GAP_DIV)    # (:233 divide_vector, the port's
    eye.vz = _tdiv(pdz, GAP_DIV)    # truncating tdiv)
    eye.m[6] = vx                     # F = viewDirection (:235)
    eye.m[7] = vy
    eye.m[8] = vz
    M.fix(eye.m)                      # shrink + fix_objects_ijk (:237-238;
    target = _roll_target(eye.m, view_obj.m)   # M.fix normalizes anyway)
    if target != 0:                   # :241-254
        if abs(target) > 4:           # :244 tests abs(target) > 4
            sv.roll_rate = 4          # nEyeRollRate = 4 (:245)
            # rotate_eye_to_goal (spc.c:129-149): drive the eye's
            # rotations towards the goals at the rates, the pitch and
            # yaw goals stay 0 (the script never sets them)
            total = (abs(eye.rp - sv.pitch_target)
                     + abs(eye.ry - sv.yaw_goal)
                     + abs(eye.rr - target))
            eye.rp, sv.pitch_target = world._match(eye.rp, sv.pitch_target,
                                                   total, sv.pitch_rate)
            eye.ry, sv.yaw_goal = world._match(eye.ry, sv.yaw_goal,
                                               total, sv.yaw_rate)
            eye.rr, target = world._match(eye.rr, target, total,
                                          sv.roll_rate)
            world.rotate_object(eye)  # rotate_object(EYE) (:248)
        else:
            # the up row pinned to ship 0's up (:251-253) - the chase's
            # snapshot ship is the same reference the original uses
            eye.m[3] = sh.m[3]
            eye.m[4] = sh.m[4]
            eye.m[5] = sh.m[5]
            sv.roll_target = 0
    eye.x += eye.vx                   # :255-257
    eye.y += eye.vy
    eye.z += eye.vz
    return 0


def _set_eye(eye, sv, view_obj, sh, world):
    """set_eye_direction_and_position (spc.c:161-466): the scripted
    update runs first (:178-181), so a countdown advancing the script
    dispatches the new mode in the same pass, then the camera case
    (:183 switch on nCameraViewMode). Modes 0..3 and 12..15 never
    appear in the ejection script."""
    if sv.on:
        sv.update()
    mode = sv.mode
    if mode == 11:
        _eye_11(eye, view_obj)
    elif mode == 10:
        _eye_10(eye, view_obj)
    elif mode == 4:
        _eye_4(eye, view_obj, sh, sv, world)


# --- the chase ----------------------------------------------------------------

def _chase(ship, world, T, pal, cache, pss):
    """eject.c:143-181: the 3-D ejection chase, 201 pictures. The eye
    starts 600 m below the pilot (eject.c:155-158: the pilot's up row
    scaled by -0x25800) - with view.c's initialize (init_ijk) resetting
    the eye's basis to identity, the eject.c:145-151 basis-swap lines
    are dead code that the port skips. The scripted view then keeps the
    eye looking at the pilot from ~600 m below for 70 passes (the
    tumbling shot), jumps onto the pilot for 80 passes (the ship and
    its fireball falling away behind him) and chases a point 700 m
    behind the pilot for the fly-by until the picture cuts at frame
    200 (:176). Per pass the port mirrors RefreshCockpitStatus
    (main.c:2136-2142 -> Update_3Space :555 -> Draw_3Space_Frame :2010):
    the pilot's scripted pitch (alter_pitch 4 deg, eject.c:166,
    geom.c:651-656 with its fix), the upkeep of house_keep_objects
    (spc.c:873: the explosion ages, the dying ship counts down, the
    pilot's 32000-pass counter never runs out), the rotation and
    straight-line coast of update_objects_in_space (spc.c:1022: no
    thrust for a dead ship), the camera, the every-pass clear
    (nFrameSkipCounter == 1), the star field and dust of
    update_star_field / spc.c's dust drawing through sky.py, then the
    projection and the depth-sorted draw. Velocities are one pass
    instead of one turn (_per_pass above), which is the cutscene's
    whole 16 fps pacing; the ship's rotation follows the same scale."""
    import scramble as S                # eject() imported it guarded,
    # so it is in sys.modules: this lookup costs nothing and only
    # binds the name for the picture timing and the cut poll below.
    try:
        import sky
    except MemoryError:
        sky = None                      # no room for the star field:
        # the chase runs without stars and dust - the field is
        # cosmetic, the projection is the scene. docs/12 12.4.
    p = world.o[0]
    sh = _Ob()
    sh.cls = W.C_SHIP
    sh.typ = p.typ
    M.copy(p.m, sh.m)
    sh.x = p.x
    sh.y = p.y
    sh.z = p.z
    sh.vx = _per_pass(p.vx)           # per-turn -> per-pass, once here
    sh.vy = _per_pass(p.vy)
    sh.vz = _per_pass(p.vz)
    sh.radius = p.radius              # the collision radius (world.py:378
    # fills it from the T_RADIUS table; world.py:173's rad is the
    # renderer's screen radius - the projection uses radius, geom.c:1287)
    sh.scale = p.scale
    sh.rp = p.rp                      # the pilot's control inputs at
    sh.ry = p.ry                      # the moment of ejection
    sh.rr = p.rr

    pil = _Ob()                       # eject.c:97-115
    pil.cls = T.f[D.T_CLASS][PILOT_TYPE]          # 6, DEBRIS
    pil.typ = PILOT_TYPE
    M.copy(p.m, pil.m)                # copy_frame(0, pilot) (:104)
    pil.x = p.x                       # pos = the ship's (:105)
    pil.y = p.y
    pil.z = p.z
    f = T.f
    pil.radius = f[D.T_RADIUS][PILOT_TYPE]        # 6 (set_objects_data)
    pil.scale = f[D.T_SCALE][PILOT_TYPE]          # 512
    pil.counter = 32000               # asObjectCounterArray (:106)
    pil.af = 0                        # the port's animation counter:
    # the original's pilot frame comes from animate_object (the debris
    # animation machinery); the port steps it once per pass and wraps
    # it into the set's 13 frames - the tumble the pil02 frames carry
    pil.vx = _per_pass(p.vx) + ((pil.m[3] * KICK) >> 14)   # vel = the
    pil.vy = _per_pass(p.vy) + ((pil.m[4] * KICK) >> 14)   # ship's per-pass
    pil.vz = _per_pass(p.vz) + ((pil.m[5] * KICK) >> 14)   # velocity plus the
    # eject.c:107 ScaleFixedVector(pilot's up, -0x500) along the up row

    eye = _Ob()                       # EYE_OBJECT (wcdata.h:1093): the
    # camera as an object, so sky.py (which expects the flight's player
    # fields) can drive it as the eye; radius, position, velocity and
    # rotations are the scripted view's own state
    # eject.c:155-158: 600 m along the pilot's up (frozen at creation)
    off = PULL_BACK
    eye.x = pil.x + ((pil.m[3] * -off) >> 14)
    eye.y = pil.y + ((pil.m[4] * -off) >> 14)
    eye.z = pil.z + ((pil.m[5] * -off) >> 14)
    sv = _ScriptedView(EJECT_SCRIPT, eye, pil)    # eject.c:161; init_ijk
    # resets the eye's basis to identity (see _ScriptedView), so the
    # eye starts with the world's axes and its F row turns onto the
    # pilot on the first case-11 pass

    # the eye doubles as sky.py's player (it needs m, x/y/z, vx/vy/vz,
    # radius and rp/ry); stars cannot respawn during the chase because
    # the eye neither pitches nor yaws - a documented deviation, the
    # original's update_star_field moves the field with the eye's own
    # pitch/yaw too and that stays 0 here
    sky_obj = None
    if sky is not None:
        try:
            sky_obj = sky.Sky(eye, FX, FY,
                              (0, S.PIC_Y0, 128, FULL_Y1, 64, 64))
        except MemoryError:
            sky_obj = None        # the field's arrays are bigger than
            # the hole left: no stars and dust, the chase still runs.
            # docs/12 12.4.

    objects = [pil, sh]
    expl = None
    try:
        dv = _dirv()
    except MemoryError:
        return False                # no hole for the direction bases
        # (the 1,488-byte ask that died in the device log 2026-11-27):
        # the chase is skipped, the seat scenes above still played,
        # and the scene ends instead of ending the game. docs/12 12.1.

    fb = display.buffer
    display.fill(0)                   # free_cockpit (:144): rows 0..15
    # stay black through the scene
    t0 = ticks_ms()
    esc = False
    frame = 0
    while True:
        # eject.c:166 alter_pitch(4, pilot): rotate the pilot's up and
        # forward about its right (geom.c:651-656) - 4 degrees a pass,
        # the scripted tumble
        M.pitch(pil.m, 4)
        M.fix(pil.m)                  # fix_objects_ijk (:655)

        # Update_3Space's upkeep, the chase's three objects only
        if expl is not None:          # spc.c:1162-1166 (explosion aging;
            expl.counter += 1         # the port's own numbers, the
            if expl.counter >= W.EXPLOSION_TURNS[expl.typ - W.OT_EXPLOSION0]:
                objects.remove(expl)  # original removes the object
                expl = None
        if pil.counter > 0:           # house_keep_objects (:885-888)
            pil.counter -= 1          # debris counts down to -1
        if sh.counter > 0:            # house_keep_objects (:940): the
            sh.counter -= 1           # dying fighter's counter
            if sh.counter == 0:
                # SM_DYING at counter 0: the original makes debris
                # chunks and leaves the ship (spc.c:968-969, no debris
                # ported); the port drops it from the chase, like
                # world.py:1235-1237 removes it in flight
                objects.remove(sh)

        # update_objects_in_space (spc.c:1022-1067): rotate the ship by
        # its control rates (rotate_object world.py:1247, scaled to the
        # pass like the velocities), then coast - a dead ship keeps
        # its velocity (accelerate_and_move_object's thrust branch is
        # gone with the controls)
        _rot_step(sh)
        for ob in (pil, sh, expl):
            if ob is None:
                continue
            ob.x += ob.vx             # positions advance by the pass
            ob.y += ob.vy             # velocities, both in Q8
            ob.z += ob.vz
        pil.af += 1                   # the pilot's animation step
        if sky_obj is not None:
            sky_obj.turn(eye)         # the eye as the flight's player:
            # dust that is out of reach is set up ahead again, stars
            # wait for a pitch or yaw that never comes

        # the camera (set_eye_direction_and_position, spc.c:161)
        _set_eye(eye, sv, pil, sh, world)

        # RefreshCockpitStatus's clear (main.c:2139-2140): the space
        # buffer is wiped every pass because nFrameSkipCounter is 1
        # (eject.c:162), so pieces that passed by are deleted
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)

        # Draw_3Space_Frame (main.c:2010-2037): the stars (the original's
        # update_star_field :2019), the dust, then the objects sorted
        # far to near (sort_object_depth :2025 - the port's Manhattan
        # approximation, as in flight.py:389-403)
        if sky_obj is not None:
            sky_obj.draw(fb, display, eye.m, eye.x, eye.y, eye.z,
                         eye, True)
            sky_obj.draw(fb, display, eye.m, eye.x, eye.y, eye.z,
                         eye, False)
        # far to near: the same sort flight.py:386-402 uses - collect
        # the Manhattan distances, sort ascending, draw from the far end
        # in so the nearer objects land on top. eventmgr.c's
        # sort_object_depth (:912 and :938 compare strictly) keeps the
        # first slot among equal distances, so a tied group is placed in
        # slot order and drawn in that order from the far end
        # (draw_sorted_objects_to_buffer :964-966): the LATER slot is
        # drawn last and lands on top. The chase's local list stands in
        # for the slots, so ties break by insertion index - the second
        # element is the negative index (integers always compare, unlike
        # _Ob, and the ship and its fireball sit at exactly the ship's
        # position), so a later entry sorts first and is drawn last,
        # over the earlier one: the fireball covers the ship, as in the
        # original.
        order = []
        idx = 0
        for ob in objects:
            order.append((abs(ob.x - eye.x) + abs(ob.y - eye.y)
                          + abs(ob.z - eye.z), -idx, ob))
            idx += 1
        order.sort()
        k = len(order) - 1
        while k >= 0:
            _draw_obj(fb, pal, cache, eye.m, eye, order[k][2], T, dv,
                      pss, S)
            k -= 1
        display.update()              # dump_buffer_to_screen (:168)
        collect()                     # the garbage one pass wide, the
        # titleseq._pace rule: the sort tuples and the cull lists die
        # here instead of piling up over the 201 passes - the chase
        # room is small (docs/12 12.2) and the scene cannot pay for
        # two hundred passes of retained tuples.

        # eject.c:169-174: the switch runs on the current frame, before
        # frame++, so the fireball born here first shows on the NEXT
        # picture
        if frame == 10:               # Explosion(0) - ship.c:1363:
            sh.special = W.SM_DYING   # set_special(obj, 9) (:1398)
            sh.counter = 8            # asObjectCounterArray = 8 (:1399)
            # mission-ship state 3 (:1373-1375), the personality's
            # death, the shock wave (:1422-1427) and sfx 4 (:1429-1434)
            # are not ported. The onboard explosions of spc.c:955-956
            # belong to capitals only, so a dying fighter shows exactly
            # this one fireball.
            expl = _Ob()              # ShipExplosion (ship.c:1325-1360):
            expl.cls = W.C_EXPLOSION  # frame, position, velocity and
            expl.typ = W.OT_EXPLOSION1  # owner copied from the ship
            M.copy(sh.m, expl.m)      # copy_frame (:1335)
            expl.x = sh.x             # positions (:1336)
            expl.y = sh.y
            expl.z = sh.z
            expl.vx = sh.vx           # velocities (:1337)
            expl.vy = sh.vy
            expl.vz = sh.vz
            expl.radius = T.f[D.T_RADIUS][W.OT_EXPLOSION1]   # 0: the
            expl.scale = (T.f[D.T_SCALE][W.OT_EXPLOSION1] * sh.scale) >> 8
            # the original's scale (:1354): 256 x the ship's own scale
            expl.counter = 0
            objects.append(expl)      # the frame animation is the
        # flight's own, fx02 blooming then fading over 12 passes
        frame += 1                    # :175
        if frame > CHASE_FRAMES or esc:   # :176
            break
        # DIBslam + DIBslamReal (:178-179): hold the frame boundary,
        # polling for a cut
        while ticks_diff(ticks_ms(), t0) < frame * S.STEP_MS:
            display.update()
            if S._key():
                esc = True
    # eject.c:182: a button cut also leaves nFrameSkipCounter stale;
    # every other cutscene loop resets it, the port holds it at 1 only
    # while its own chase loop ran
    return esc


def _rot_step(ob):
    """rotate_object (world.py:1247-1255) at the chase's pass scale:
    the pass is the turn's 100 ms now, so _per_pass is the identity
    and the spin runs at the flight's rate exactly."""
    m = ob.m
    if ob.rp:
        M.pitch(m, _per_pass(ob.rp))
    if ob.ry:
        M.yaw(m, _per_pass(ob.ry))
    if ob.rr:
        M.roll(m, _per_pass(ob.rr))
    M.fix(m)


def eject(ship, world=None, T=None, pal=None, cache=None):
    """ejection_sequence. Stage 1 (eject.c:52-80): the seat bursts down
    the cockpit, drawn three layers deep (primary frame, optional
    secondary, and frame 5 one row lower every pass) while the descent
    accelerates from 4 to 20; RefreshCockpitStatus (:57) clears the
    space buffer every pass - invisible under the full ckbg, the seat
    just redraws lower each frame. Stage 2 (eject.c:117-139): the
    cockpit interior and the slide panel scroll away at the stage-1 end
    speed (20), cleared and redrawn every pass (:126) so they scroll
    over black and the stage-1 seat is deleted, not stacked. Between
    them the ejected pilot is created (eject.c:97-115) when the world,
    the type table and the frame cache are passed in, and after stage 2
    comes the 3-D chase (:143-181) - the ported one, see _chase. Only
    the four WC1 cockpits; missing files skip the scene. Returns True
    when a button cut it."""
    try:
        import scramble as S
    except MemoryError:
        return False                # no room for the sprite helpers:
        # the seat scene cannot be drawn, as the original skips on a
        # missing file (:48-51's early return). docs/12 12.4.
    if ship not in (0, 1, 2, 3):
        return False
    bg = S._set('ckbg%d.wcs' % ship)      # eject.c:48-49 (sec 3)
    seat = S._set('pil01.wcs')            # eject.c:50 (PILOTANM sec 1)
    int_bg = S._set('ckint%d.wcs' % ship)  # eject.c:117-118 (sec 0)
    slide = S._set('ckslide%d.wcs' % ship)  # eject.c:119-120 (sec 5)
    if bg is None or seat is None:
        return False
    if int_bg is None or slide is None:
        return False
    fb = display.buffer
    display.fill(0)

    # stage 1: eject.c:52-80 - y starts at the picture's bottom (199 ->
    # device row 111), speed at 4, the acceleration every pass from
    # frame 2 on (:71-74)
    t0 = ticks_ms()
    y = 199
    speed = 4
    esc = False
    frame = 0
    while frame < 10:
        # RefreshCockpitStatus (eject.c:57) clears the space buffer
        # every pass (nFrameSkipCounter = 1, :55; main.c:2138-2140);
        # invisible here - ckbg paints the whole picture anyway
        G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
        S._draw(fb, bg, 0, 0, 0, FULL_Y1)               # :58
        sf = min(frame, 4)                              # :59
        S._draw(fb, seat, EJECT_PRIMARY[sf], 160, y, FULL_Y1)   # :60-62
        sec = EJECT_SECONDARY[sf]                       # :63-66
        if sec != -1:
            S._draw(fb, seat, sec, 160, y, FULL_Y1)
        S._draw(fb, seat, 5, 160, y + 1, FULL_Y1)       # :67-68
        display.update()                                # :69
        if frame > 1:                                   # :71-74
            y -= speed
            speed = min(speed + 4, 20)
        while ticks_diff(ticks_ms(), t0) < (frame + 1) * S.STEP_MS:
            if S._key():
                esc = True
            display.update()
        if esc:                                         # :75-76
            break
        frame += 1                                      # :77

    # the pilot is created only after a clean stage 1 (eject.c:85's
    # guard wraps the pilot, stage 2 and the chase); it needs the live
    # world for the ship's snapshot, the type table for the pilot's
    # class/radius/scale and the shared cache for the .wcs frames.
    # Without any of them the chase cannot run and the scene is the
    # sprite-only one; the ejection's own art still shows.
    pss = None
    if not esc and frame == 10 and world is not None and T is not None \
            and pal is not None and cache is not None:
        pss = S._set('pil02.wcs')       # PILOTANM.VGA sec 2, eject.c:97-99
    # stage 2 only after a clean stage 1 (eject.c:85)
    if not esc and frame == 10:
        t0 = ticks_ms()
        y = 40                                          # :122
        frame = 0
        while frame < 10:                               # :125-139
            # RefreshCockpitStatus (:126) clears the space buffer every
            # pass (nFrameSkipCounter = 1, :124) - the stage-1 seat is
            # erased by it and the panels scroll over black, stacked
            # pieces would not match the original's deleted picture
            G.fill_rows(fb, S.PIC_Y0, FULL_Y1, 0)
            # _draw(fb, ss, frame, x, y, y1): the pieces sit at x = 0 and
            # scroll DOWN with y - there is no horizontal motion in the
            # original (x is the literal 0 of eject.c:127 and :129)
            S._draw(fb, int_bg, 0, 0, y, FULL_Y1)       # :127-128
            S._draw(fb, slide, 0, 0, y - 1, FULL_Y1)    # :129-130
            display.update()                            # :131
            while ticks_diff(ticks_ms(), t0) < (frame + 1) * S.STEP_MS:
                if S._key():
                    esc = True
                display.update()
            if esc:                                     # :133-134
                break
            y += speed                                  # :135 (20 by now)
            frame += 1                                  # :137
    # the chase (eject.c:143-181) only after a clean stage 2 (:142's
    # guard); it draws its own pictures and takes its own cut
    if not esc and pss is not None:
        esc = _chase(ship, world, T, pal, cache, pss)
    ui.wait_release()
    # eject.c:190-194: fade to black and clear the screen
    for _ in range(10):
        G.dim_rows(fb, 0, FULL_Y1)
        display.update()
    G.fill_rows(fb, 0, FULL_Y1, 0)
    return esc


def check_stranded(world):
    """check_stranded (cockpt.c:3013-3020), run on an ejection before
    the campaign continues (gameflow.c:373). The carrier's mission ship
    is destroyed - ship_state 3, set by world.py:589 and 729 when the
    carrier dies; the port's carrier is the mission ship home_ship
    (flight.py:853). no nTrainSimActive in the port, so that test is
    always true (cockpt.c:3015). any_enemy (logic.c:906-928) skips
    SPECIAL_MANEUVER_UNKNOWN_9, which is SM_DYING = 9 (world.py:44),
    and measures the surface distance: distance_from_object (geom.c:687-
    703) is centre distance minus both collision radii; world.dist
    (world.py:338-340) is the centre distance, so the same subtraction
    gives the port's copy. The chase runs on local snapshots and never
    moves the live ship, so this check sees the simulation's own
    positions."""
    p = world.o[0]
    if world.mis.ship_state[world.mis.home_ship] != 3:
        return False
    for i in range(1, W.NSHIP):
        ob = world.o[i]
        if ob.cls < W.C_SHIP or ob.special == W.SM_DYING:
            continue
        if ob.side == p.side:
            continue
        if world.dist(p, ob) - p.radius - ob.radius < 30000:
            return False
    return True


def stranded():
    """stranded_sequence (eject.c:202-235): the black void, the drifting
    message from frame 160, THE END from 300, 400 frames unless a button
    cuts it. Text colours are the original's subtitle palette indices -
    50 for the message, 56 for THE END (eject.c:214-218)."""
    try:
        import scramble as S
    except MemoryError:
        S = None            # the scene draws no sprites - only the
        # picture's first row and the frame timing are taken from it,
        # and both fall back to scramble's own numbers below.
    fb = display.buffer
    display.fill(0)
    t0 = ticks_ms()
    esc = False
    drawn = 0
    pic0 = S.PIC_Y0 if S is not None else 16    # scramble.py:41
    step = S.STEP_MS if S is not None else 100  # scramble.py:43
    for frame in range(400):                    # eject.c:210, 226
        if drawn == 0 and frame >= 160:         # :216-218
            ui.text.centre(fb, STRANDED_LINES[0], STRANDED_ROWS[0],
                           ui.pal565(50))
            ui.text.centre(fb, STRANDED_LINES[1], STRANDED_ROWS[1],
                           ui.pal565(50))
            ui.text.centre(fb, STRANDED_LINES[2], STRANDED_ROWS[2],
                           ui.pal565(50))
            ui.text.centre(fb, STRANDED_LINES[3], STRANDED_ROWS[3],
                           ui.pal565(50))
            drawn = 1
        elif drawn == 1 and frame >= 300:       # :213-215
            G.fill_rows(fb, pic0, FULL_Y1, 0)
            ui.text.centre(fb, b'THE END', THE_END_ROW, ui.pal565(56))
            drawn = 2
        display.update()                        # :219
        while ticks_diff(ticks_ms(), t0) < (frame + 1) * step:
            if S is not None and S._key():
                esc = True
            display.update()
        if esc:                                 # :221-222
            break
    ui.wait_release()
    # eject.c:229-233: fade and clear (the screen is black already)
    G.fill_rows(fb, 0, FULL_Y1, 0)
    return esc


def cleanup():
    """Let go of the cached sets between flights."""
    try:
        import scramble as S
    except MemoryError:
        return            # nothing to let go of: the module never
        # landed, so its scratch and sets never existed.
    S.cleanup()
