# introfx.py - the Origin FX opening intro (docs/06 6.2): the orchestra
# on the sky, the ORION logo zooming past the Earth and the fireworks.
#
# Verbatim ports of (wc1-re, GPL-3.0, src/sdl/dos_intro.c):
#   SdlDrawDosIntroSky        :44   (the sky frame and the planet)
#   SdlDrawDosIntroLogo       :55   (logo tiles at scale, C comment :62)
#   SdlPresentDosIntroFrame   :70   (the 320x128 buffer shown in screen
#                                    rows 24-151)
#   SdlDrawDosIntroOrchestra  :85   SdlDrawDosIntroConductorCue :105
#   SdlDrawDosIntroOrchestraPush :129
#   SdlDrawDosIntroLogoReveal :160  SdlResetDosIntroFireworks :183
#   SdlStartDosIntroFirework  :195  SdlDrawDosIntroFireworks :211
#   SdlPlayDosStartupIntro    :239
# on the sprite sets tool/wc1_convert.py writes from TITLE.VGA sections
# 6..17 (ti06..ti17.wcs - section i+6 in dos_intro.c's numbering) and
# section 3 (ti3.wcs, the Earth). The actor table and both animation
# strings are the DOS VROOMM overlay's, transcribed verbatim.
#
# Mapping: the original draws into a 320x128 buffer that is displayed
# in screen rows 24..151. Screen rows map through scramble.py's _cy
# (row 0 -> device row 16), so buffer row y lands at _cy(y + 24) and
# the display clip becomes the device rows 28..88, clip [28, 89).
# Positions stay in original-pixel units and are scaled only at the
# draw site, like every other scene (scramble.py:16-25).
#
# Deliberate deviations, all documented:
#  - music: the port has no music engine, so the original's
#    synchronizedMusic is false and its own unsynchronized fallback
#    (dos_intro.c:328-347) is what runs. The original's opening
#    DrawOrchestra(0) frame is still drawn before the fallback loops,
#    so frame 0 appears twice exactly as in the C.
#  - rate: the original ran the FX music-synchronized, so its length is
#    the Origin FX track's 25 seconds (docs/08-music.md, cue 19; it is
#    measured at about 24). The port has no music, so it paces the same
#    frames evenly across that span: 140 ms a picture, all ~177 of them
#    over 25 seconds. The wait
#    between pictures also watches for buttons so a press can cut the
#    intro immediately - CheckEscaped is continuously true in the
#    original.
#  - input: CheckEscaped reads any button (A/B/MENU), as every loop in
#    every port scene does; the port's `run` flag is the original's
#    `running`, and once it is 0 every remaining phase short-circuits.
#  - sound: dos_intro.c itself plays no effects (its music call is not
#    ported, same convention as funeralseq.py:23-32).
#  - frames stream through scramble.py's shared scratch (S._read); the
#    biggest piece here is the 128x62 sky, within the 128x96 scratch.

import scramble as S
import ui
import wcgfx as G
import wcmath as M
from time import ticks_ms, ticks_diff
from thumby_engine.platform import display

# the display clip of the original (dos_intro.c:77-78): screen rows
# 24..151 -> device rows 28..88
IY0 = S._cy(24)                # 28
IY1 = S._cy(151) + 1           # 89

# one FX picture every: the whole intro spans the Origin FX music's
# 25 s (docs/08 cue 19), its ~177 frames at 140 ms
FX_MS = 140

ACTOR_COUNT = 10               # SDL_PORT_DOS_INTRO_ACTOR_COUNT, :6
SECTION_COUNT = 12             # :7
FIREWORK_COUNT = 30            # :8
INITIAL_FIREWORKS = 5          # :9

# g_aSdlDosIntroActors[10] - dos_intro.c:27-39, verbatim
ACTORS = (
    (58, 94, -1, 1, b'abcdefghijkaakkkkaaaalllllllmmll'),
    (186, 94, 0, 1, b'aaaaaaaabcddeeddccffgghhgghhiiih'),
    (278, 94, 1, 1, b'aaaaaaaaaabbccbbaaccccccccccaccc'),
    (58, 102, -3, 2, b'aaaabbbcccddeeddccffggaaggffcaaa'),
    (186, 102, 0, 2, b'aabbbaacccddddddccddeeeeeeddccca'),
    (278, 102, 3, 2, b'aaaaaabbbaaabbaaaabbbbaabbbbaccc'),
    (58, 110, -5, 3, b'aabbcdbbbeaaaaaaeeaaaaaaaaaabaaa'),
    (186, 110, 0, 3, b'abbbaacccdeeaaeeddaaaaaaaaaadacc'),
    (278, 110, 5, 3, b'aaaaaaaaabbbccbbbbccddddddccaaaa'),
    (158, 74, 0, 4, b'abccdefgghiijjiihhkkllmmllkkhnnn'),
)
# g_szSdlDosIntroConductorFrames - dos_intro.c:41-42, verbatim
CONDUCTOR = b'opoqopoqopoqopoqqrstrq'

# SdlPresentDosIntroFrame shows buffer rows 0..127 in screen rows
# 24..151: a buffer coordinate (x, y) is screen (x, y + 24).
_cxI = S._cx


def _cyI(y):
    return S._cy(y + 24)


def _rr(lo, hi):
    """RandomInRange(lo, hi) verbatim (mathfp.c:49-56): lo +
    rand % (span + 1), span 0 forced to 1."""
    span = hi - lo
    if span == 0:
        span = 1
    return lo + S._rnd(16) % (span + 1)


# --- the draw site -----------------------------------------------------

def _drawI(fb, ss, frame, x, y):
    """DrawSpriteDefault at the intro's mapping (scramble.py:118-126
    with the intro clip band instead of the conversation's)."""
    e = S._read(ss, frame)
    if e is None:
        return
    w, h, hx, hy = e
    G.blit_indexed(fb, ui.pal, S._scratch,
                   _cxI(x) - hx, _cyI(y) - hy, w, h, IY0, IY1)


def _drawsI(fb, ss, frame, x, y, angle, scale, flip):
    """DrawSpriteScaled (scramble.py:150-202, with the intro clip band
    and the +24 row mapping)."""
    e = S._read(ss, frame)
    if e is None:
        return
    w, h, hx, hy = e
    if scale == 256 and angle == 0 and flip == 0:
        G.blit_indexed(fb, ui.pal, S._scratch,
                       _cxI(x) - hx, _cyI(y) - hy, w, h, IY0, IY1)
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
    cx = _cxI(x)
    cy = _cyI(y)
    x0 = cx - rad
    if x0 < 0:
        x0 = 0
    x1 = cx + rad + 1
    if x1 > 128:
        x1 = 128
    y0 = cy - rad
    if y0 < IY0:
        y0 = IY0
    y1b = cy + rad + 1
    if y1b > IY1:
        y1b = IY1
    if x0 >= x1 or y0 >= y1b:
        return
    a, b, c, d = S._coeffs(k, angle % 360, flip)
    p = S._P
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
    G.blit_rs(fb, ui.pal, S._scratch, w, h, p)


def _drawSky(fb, sky, planet, planetY):
    """SdlDrawDosIntroSky verbatim (dos_intro.c:44-53): clear the
    buffer, the sky frame at (0, 0), the planet at (160, planetY)."""
    G.fill_rows(fb, IY0, IY1, 0)        # ClearViewport(cBlackColour)
    _drawI(fb, sky, 0, 0, 0)
    if planet is not None:
        _drawI(fb, planet, 0, 160, planetY)


def _drawLogo(fb, ti06, y, scale):
    """SdlDrawDosIntroLogo verbatim (dos_intro.c:55-68). The C comment
    :62: frame 2 is 118 pixels wide around an origin 57 pixels from
    its left - the converted tile is 48 wide with its hot spot at 23.
    The `/` in the C is truncating: the port's `//` matches."""
    left = 161 - (57 * scale) // 0x100
    right = 162 + (61 * scale) // 0x100
    _drawsI(fb, ti06, 1, left, y, 0, scale, 0)
    _drawsI(fb, ti06, 2, 162, y, 0, scale, 0)
    _drawsI(fb, ti06, 3, right, y, 0, scale, 0)


def _drawOrchestra(fb, sec, planet, sequenceFrame):
    """SdlDrawDosIntroOrchestra verbatim (dos_intro.c:85-103): all ten
    actors, the conductor among them, each on its own section."""
    _drawSky(fb, sec[0], planet, 24)
    for k in range(ACTOR_COUNT):
        frame = ACTORS[k][4][sequenceFrame] - 97     # - 'a'
        _drawI(fb, sec[k + 1], frame, ACTORS[k][0], ACTORS[k][1])


def _drawCue(fb, sec, planet, cueFrame):
    """SdlDrawDosIntroConductorCue verbatim (dos_intro.c:105-127): the
    nine orchestra actors frozen on their last frame, the conductor on
    its cue."""
    _drawSky(fb, sec[0], planet, 24)
    for k in range(ACTOR_COUNT - 1):
        frame = ACTORS[k][4][31] - 97
        _drawI(fb, sec[k + 1], frame, ACTORS[k][0], ACTORS[k][1])
    frame = CONDUCTOR[cueFrame] - 97
    actor = ACTORS[ACTOR_COUNT - 1]
    _drawI(fb, sec[ACTOR_COUNT], frame, actor[0], actor[1])


def _drawPush(fb, sec, planet, distance):
    """SdlDrawDosIntroOrchestraPush verbatim (dos_intro.c:129-158):
    the whole band drifts at its velocity and grows as it comes at the
    camera (scale 256 + velocityY * distance * 4)."""
    _drawSky(fb, sec[0], planet, 24)
    for k in range(ACTOR_COUNT):
        actor = ACTORS[k]
        if k == ACTOR_COUNT - 1:
            frame = CONDUCTOR[21] - 97
        else:
            frame = actor[4][31] - 97
        x = actor[0] + actor[2] * distance
        y = actor[1] + actor[3] * distance
        scale = 0x100 + actor[3] * distance * 4
        _drawsI(fb, sec[k + 1], frame, x, y, 0, scale, 0)


def _drawReveal(fb, sky, planet, logoY, distance):
    """SdlDrawDosIntroLogoReveal verbatim (dos_intro.c:160-181): the
    Earth and the logo scale as 120000/distance and 256000/distance,
    and whichever of the two is lower draws last (the occlusion)."""
    planetY = 120000 // distance
    scale = 256000 // distance
    logoBottom = logoY + 34 * scale // 0x100
    G.fill_rows(fb, IY0, IY1, 0)
    _drawI(fb, sky, 0, 0, 0)
    if logoBottom < planetY:
        _drawI(fb, planet, 0, 160, planetY)
        _drawLogo(fb, sky, logoY, scale)
    else:
        _drawLogo(fb, sky, logoY, scale)
        _drawI(fb, planet, 0, 160, planetY)


# --- the firework pool (dos_intro.c:183-237) -----------------------------

def _resetFireworks(fw):
    for slot in fw:
        slot[0] = -1


def _startFirework(fw, count):
    """SdlStartDosIntroFirework verbatim (:195-209): the first free
    slot within count, frame 0 at a random spot and variant."""
    i = 0
    while i < count and fw[i][0] != -1:
        i += 1
    if i == count:
        return
    fw[i][0] = 0
    fw[i][1] = _rr(0, 319)
    fw[i][2] = _rr(0, 127)
    fw[i][3] = _rr(0, 2)


def _drawFireworks(fb, sky, fwShape, fw, logoY):
    """SdlDrawDosIntroFireworks verbatim (:211-237): sky, logo at full
    scale, every live firework on frame + variant * 8 of the shape;
    then advance and retire at frame 8."""
    G.fill_rows(fb, IY0, IY1, 0)
    _drawI(fb, sky, 0, 0, 0)
    _drawLogo(fb, sky, logoY, 0x100)
    for slot in fw:
        if slot[0] >= 0:
            _drawI(fb, fwShape, slot[0] + slot[3] * 8, slot[1], slot[2])
            slot[0] += 1
            if slot[0] == 8:
                slot[0] = -1


# --- the driver (SdlPlayDosStartupIntro, dos_intro.c:239-479) ------------

def play():
    """The whole intro, phase by phase, in the C's order. True returns
    when the intro was shown; False when its assets are missing, the
    same skip every hard scene does. A button (the original's
    CheckEscaped) drops `run`, the port's `running`, and every phase
    after it short-circuits on its loop condition, exactly like C's."""
    fb = display.buffer
    sec = []
    for i in range(SECTION_COUNT):
        ss = S._set('ti%02d.wcs' % (i + 6))
        if ss is None:
            return False
        sec.append(ss)
    planet = S._set('ti3.wcs')
    if planet is None:
        return False

    G.fill_rows(fb, 0, 128, 0)     # DrawFilledViewportRect black (:285)
    ui.wait_release()              # ClearInputKeyState + Flush (:287-288)

    # no music engine: introMusic is 0 and synchronizedMusic is 0, so
    # every music gate in the C is never reached and the unsynchronized
    # paths run (the original's own fallback).
    run = [True]                   # the original's `running`
    t0 = ticks_ms()
    frameNo = [0]                  # the port's presentation schedule

    def present():
        """SdlPresentDosIntroFrame (:70-83): the picture is already in
        the buffer; copy+slam is display.update, then CheckEscaped. The
        port paces the next presentation at FX_MS and watches for a
        button through the wait, so a press cuts in immediately."""
        display.update()
        if run[0] and S._key():
            run[0] = False
        nxt = frameNo[0] + 1
        while ticks_diff(ticks_ms(), t0) < nxt * FX_MS:
            if run[0] and S._key():
                run[0] = False
                break
            display.update()
        frameNo[0] = nxt

    _drawOrchestra(fb, sec, planet, 0)
    present()                      # :299-300

    # :328-347, the unsynchronized orchestra: 0..31, then 31..12, then
    # 12..31 again. The first pass re-draws frame 0 - the C drew it at
    # :300 before falling into this path too.
    af = 0
    while run[0] and af < 32:
        _drawOrchestra(fb, sec, planet, af)
        present()
        af += 1
    af = 31
    while run[0] and af >= 12:
        _drawOrchestra(fb, sec, planet, af)
        present()
        af -= 1
    af = 12
    while run[0] and af < 32:
        _drawOrchestra(fb, sec, planet, af)
        present()
        af += 1

    # :349-354: the conductor's cues. Cue 20 would follow a music sync
    # wait (:355-371); without music the C never reaches it.
    cf = 0
    while run[0] and cf < 20:
        _drawCue(fb, sec, planet, cf)
        present()
        cf += 1

    # :373-378: the push. distance += distance / 4 + 1 is C integer
    # truncation; the port's // matches.
    dist = 1
    while run[0] and dist < 120:
        _drawPush(fb, sec, planet, dist)
        present()
        dist += dist // 4 + 1

    # :380-391: the logo reveal, 5000 down to 1000 by 100, the logo
    # bobbing down while distance > 3000 and up after.
    logoY = 59
    dist = 5000
    while run[0] and dist >= 1000:
        if dist > 3000:
            logoY -= 2
        else:
            logoY += 2
        _drawReveal(fb, sec[0], planet, logoY, dist)
        present()
        dist -= 100

    # :406-446: the fireworks. Without music the start condition at
    # :415 is always true, so one firework is launched on every pass
    # until the first five slots are all busy; "finishing" begins at
    # frame 11 (:430-432, the unsynchronized branch) and the loop
    # breaks when those five have all retired (:433-445).
    fw = [[-1, 0, 0, 0] for _ in range(FIREWORK_COUNT)]
    ff = 0
    finishing = 0
    while run[0]:
        if not finishing:
            _startFirework(fw, INITIAL_FIREWORKS)
        _drawFireworks(fb, sec[0], sec[SECTION_COUNT - 1], fw, logoY)
        present()
        ff += 1
        if ff > 10:
            finishing = 1
        if finishing:
            empty = 0
            for i in range(INITIAL_FIREWORKS):
                if fw[i][0] == -1:
                    empty += 1
            if empty == INITIAL_FIREWORKS:
                break

    # :447-463: the final burst, all thirty at once, eight frames.
    if run[0]:
        for i in range(FIREWORK_COUNT):
            fw[i][0] = 0
            fw[i][1] = _rr(0, 319)
            fw[i][2] = _rr(0, 127)
            fw[i][3] = _rr(0, 2)
        ff = 0
        while run[0] and ff < 8:
            _drawFireworks(fb, sec[0], sec[SECTION_COUNT - 1],
                           fw, logoY)
            present()
            ff += 1

    # :469-478 minus the music release: black screen, let the packets
    # go, and a clear input state before the title reads its buttons.
    G.fill_rows(fb, 0, 128, 0)     # ClearViewport(stScreenView, black)
    S.cleanup()                    # ReleasePacketHandle, all 13
    ui.wait_release()              # :477-478
    return True


def cleanup():
    """Let go of the intro sets (the title loads its own fresh)."""
    S.cleanup()
