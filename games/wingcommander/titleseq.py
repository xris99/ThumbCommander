# titleseq.py - the opening cinematic, credits and title menu
# (docs/06 6.2): what the original calls Title_Sequence. In the DOS game
# the "intro" and the title screen are one sequence (title.c), so this
# one module is both remaining scenes of that task. The Origin FX opening
# (the orchestra and the Origin logo over the Earth) is introfx.py,
# wired in MainGame.py before this module runs.
#
# This is the real canned world, not authored choreography. The title
# flies a Mission built from game.c's own title data - the intro camera
# script (asIntroCameraSequence, game.c:110-113), the canned command
# sequences of asCannedSequence32..45 (game.c:116-196), aMissionNavPoints
# [16..19] (game.c:199-226) and aMissionShips[32..45] (game.c:229-290) -
# through world.py's own physics, so the DRALTHI ambush, the HORNET, the
# asteroid field and the credit hazard field move and behave the way the
# original's 3Space world moves them: the ships accelerate along their
# canned headings (world.py's move), the canned command scripts run
# (advance / update, mono.c), the hazard chain of winmain.c spawns,
# turns and recycles rocks and mines, and the intro fleet explodes on
# entry into the asteroid field's nav (set_up_action_sphere's explode-
# on-entry, mission.c) - which is the original's cinematic transition
# into the credits, where the ships vanish and the rocks take over.
#
# Verbatim ports of (wc1-re, GPL-3.0), line numbers verified against the
# originals as each section was written:
#   Title_Sequence   src/title.c       (0x40FB70)
#   DrawTitleLogo    src/title.c:78    (0x40FA40)
#   GetLineLength / print_subtitle   src/mono.c
#   advance_canned_sequence / update_canned_sequence   src/mono.c
#   parse_view_script / update_scripted_view /
#   initialize_scripted_view   src/view.c
#   the eye's turn (set_eye case 15), rotate_eye_to_goal,
#   rotate_object, the object_intelligence canned gate   src/spc.c
#   fire_fixed_projectile_weapon   src/ship.c
#   the hazard chain (init_hazard, try_far_spot, ok_hazard_spot,
#   make_hazard, manage_hazard, match_ship_to_eye, update_hazards,
#   start_hazard_field, add_hazard_field, check_hazards,
#   remove_all_hazards)   src/winmain.c
#   the screenX marker gates   src/geom.c
#   ClampVectorTo30, point_at   src/geom.c
#   intro_drawbackgroundships (the black silhouettes)   src/eventmgr.c
#   set_up_action_sphere (explode-on-entry), is_alive,
#   set_sphere_point, Set_up_ship_info, init_ship,
#   init_intelligence_data   src/mission.c
#   kilrathi_near   src/cockpt.c
#   signed_random, the clamped find_ratio   src/logic.c
#   Update_3Space, house_keep, Draw_3Space_Frame,
#   RenderSpaceViewFrame   src/main.c
#   DrawSpriteDefault / DrawSpriteScaled (through scramble.py's blit)
#   GetShapeFrameExtent   src/cutscene.c
# The picture font is the converted intro font: ti1.wcs (the glyph
# frames of packet 9 section 1, title.c:164) and its width table
# ti1wd.wc, drawn by the print_subtitle port - not ui.text. The logo is
# ti0.wcs with its bounds sidecar ti0geo.wc. The menu is ti4.wcs.
#
# Phase counts are the original's verbatim: 25 opening frames
# (title.c:191), 110 of plain space flight (:221), 100 of the logo zoom
# (:225) with the distance stepping -4 after each draw while it is above
# 16 (:235-236), then one credit block of 70 drawn frames plus 40 of
# rendering (:257, :275) repeated nIntroCreditCount = 11 times (:22),
# and 150 frames of plain flight to close (:289). Total 1595 frames.
#
# Deliberate differences from the original, all documented here:
# - The eye is slot 0: the original's eye is object 61 and the port's
#   world has no slot 61 (world.py's NSHIP is 10). The hazard chain's
#   match_ship_to_eye writes the eye into slot 0 too, so the eye and
#   hazard slot 0 are the same slot, and rotate_eye_to_goal's yaw / roll
#   rates are the script's pitch rate of 1 (only the eye pitch target is
#   in the script; game.c:112).
# - ClampVectorTo30's rotation decay (geom.c) is applied here after
#   world.py's rotate_object, which does not apply it.
# - world.py's find_ratio is unclamped (world.py:103); the title uses a
#   local clamped _find_ratio matching logic.c, which the hazard chain
#   and the rear-sphere spawn distances need.
# - cmd3 (fire) calls world.py's fire_weapon directly: the original's
#   fire_fixed_projectile_weapon loops every enabled PROJECTILE weapon
#   with no shot counter, while world.py's fire_guns carries the shot
#   counter gate.
# - Marker flags and distance-table entries live in parallel lists:
#   world.py's LITE guard forbids new attributes on Lite objects. The
#   port's draw culls (+/-40 000, vz < 60) are kept for drawing only;
#   the verbatim screenX gates (geom.c) drive the markers that the
#   explode-on-entry and the hazard spawn consult.
# - The black ship silhouettes of intro_drawbackgroundships (eventmgr.c)
#   are a second blit pass over the drawn objects with a zeroed palette
#   (DrawSolidColourSpriteScaled, shapeColor 0); the dust streaks keep
#   their colour in the drawing and their black point is painted over.
# - The title menu is driven by buttons, not the mouse (the original's
#   cursor and region hit-tests, title.c): UP / DOWN cycle the
#   selection, A activates, B / MENU leave. The '>' marker stands for
#   the original's option-frame cursor.
# - The original repeats the whole cinematic until a key ends it
#   (title.c:176); the port plays one cycle and goes to the menu.
# - The logo's three tiles are anchored by the ti0geo.wc sidecar - the
#   converter's copy of the original's GetTransformedShapeBounds anchors
#   (title.c:91-112). The 16.16 blit comes from scramble.py.
# - The Kilrathi Saga credits (+9, title.c:156-157) are a Windows build
#   feature; the DOS count of 11 is kept.
# - Continue Campaign has no path in the DOS title (menuOptions[2] stays
#   -1 so the C key is dead, title.c:432-434); the port offers it when a
#   save exists and loads it, which main.c's switch (no case 1) cannot.
# - The world runs one turn per picture frame at the turn's own
#   length, 100 ms (docs/04 4.4.1), the original's nFrameSkip = 1
#   pace, drawing after each turn.
# - Music and sound (title.c's hooks) are not ported.
# - The harness wants a shot of the sphere-entry explosions, so phase D
#   is held for four drawn turns after the entry before the credits
#   begin; the original goes straight from the entry into the first
#   credit.

from thumby_engine.platform import (display, buttonA, buttonB, buttonU,
                                    buttonD, buttonMENU)
from array import array
import ui
import wcgfx as G
import wcdata as D
import world as W
import wcmath as M
import sky
import scramble as S
from struct import unpack_from
from time import ticks_ms, ticks_diff
from gc import collect, mem_free

# title.c:191, :221, :225, :257, :275, :289 - the phase frame counts
PH_OPEN = 25
PH_FLIGHT = 110
PH_ZOOM = 100
PH_CREDIT = 70
PH_RENDER = 40
PH_CLOSE = 150
CREDITS_N = 11                     # title.c:22 (DOS; the saga adds 9)

# aTitleMenuRegions (title.c:48-54) with the SDL re-set left = 49,
# top = 48 + 43*i (title.c:345-346) - the DOS tops 48 / 91 are the same
MENU_X = 49
MENU_Y = 48
MENU_STEP = 43

hold = False        # True while the cinematic runs (for the test harness)
stage = None        # 'A' 'B' 'C' 'D' 'E' 'menu', for stage screenshots
dist = 200          # nTitleDistance while the logo zooms; the harness
                    # photographs the logo only once it is big enough

# --- game.c's own title data, verbatim ---------------------------------------

# asIntroCameraSequence (game.c:110-113)
CAM_SCRIPT = (0, -1000, 0, -4263, 2, 15, 1, 0, 30, 0,
              3, 15, 4, 30, 1, 13, 14, 400, -1, 0)

# asCannedSequence32..45 (game.c:116-196), keyed by record number. Record
# 36 (the asteroid field) carries { 0 } - no canned sequence at all.
SEQS = {
    32: (0, 20, 1, 0, 0, 180, 40, 1, 0, 0, 180, 40, 2, 0, 400, -1),
    33: (0, 20, 0, 20, 1, 0, -15, -60, 50, 0, 400, -1),
    34: (0, 20, 0, 20, 1, 0, 15, 60, 50, 0, 400, -1),
    35: (0, 17, 0, 6, 3, 0, 6, 3, 0, 6, 3, 0, 6, 3,
         0, 6, 3, 0, 6, 3, 0, 6, 3,
         1, 0, 0, 180, 40, 1, 0, 0, 180, 40,
         1, 0, -30, 60, 40, 0, 400, -1),
    36: None,
    37: (0, 100, 1, 0, 30, 0, 50, 0, 20, 2, 0, 400, -1),
    38: (0, 110, 1, 0, 30, 0, 50, 0, 10, 2, 0, 400, -1),
    39: (0, 10, 2, 0, 400, -1),
    40: (0, 40, 3, 1, 0, 0, 90, 60, 3, 1, 0, 0, 90, 60,
         3, 1, 0, 0, 90, 60, 3, 1, 0, 0, 90, 60,
         3, 1, 0, 0, 90, 60, 3, 1, 0, 0, 90, 60, -1),
    41: (0, 400, -1),
    42: (0, 120, 1, 0, 0, 180, 50, 3, 1, 0, 0, 180, 50, 3, -1),
    43: (0, 120, 1, 0, 0, 180, 50, 3, 1, 0, 0, 180, 50, 3,
         1, 0, 0, 180, 50, 3, -1),
    44: (0, 5, 3, 0, 5, 3, 0, 5, 3, 0, 5, 3,
         1, 0, 0, 180, 50, 1, 0, 0, 180, 50,
         1, 0, 0, 180, 50, 1, 0, 0, 180, 50, -1),
    45: (0, 20, 2, -1),
}

# aMissionShips[32..45] (game.c:229-290), keyed by record number, as the
# port's 22-field ship tuple:
# (type, side, leader, field5, missiontype, nav, x, y, z, pitch, yaw,
#  roll, spot, speed, rating, pilot, f2c, f2e, state, leader-index,
#  formation, target). missiontype is MISSION_TYPE_CANNED_SEQUENCE (8).
RECORDS = {
    32: (10, 1, -1, -1, 8, 16, 0, 0, 0, -155, 0, 0, 0, 40, 3,
         0, 0, 0, 0, -1, 0, 0),
    33: (10, 1, -1, -1, 8, 16, -154521, -25600, -232012, -155, 0, 0, 0,
         40, 3, 0, 0, 0, 0, -1, 0, 0),
    34: (10, 1, -1, -1, 8, 16, -61849, 25600, -232012, -155, 0, 0, 0,
         40, 3, 0, 0, 0, 0, -1, 0, 0),
    35: (0, 0, -1, -1, 8, 16, 324582, 0, 696038, -155, 0, 0, 0,
         40, 3, 0, 0, 0, 0, -1, 0, 0),
    36: (22, 0, -1, -1, 8, 17, 0, 0, 0, 0, 0, 0, 0,
         30000, 3, 0, 0, 0, 0, -1, 0, 0),
    37: (12, 1, -1, -1, 8, 18, 102400, -153600, -332800, 0, 0, -30, 0,
         80, 3, 0, 0, 0, 0, -1, 0, 0),
    38: (12, 1, -1, -1, 8, 18, 0, 256000, -332800, 0, 0, 90, 0,
         62, 3, 0, 0, 0, 0, -1, 0, 0),
    39: (12, 1, -1, -1, 8, 18, 0, 256000, -153600, 0, 0, -30, 0,
         80, 3, 0, 0, 0, 0, -1, 0, 0),
    40: (1, 0, -1, -1, 8, 18, 0, 256000, -819200, 0, 0, 30, 0,
         60, 3, 0, 0, 0, 0, -1, 0, 0),
    41: (1, 0, -1, -1, 8, 18, 102400, -153600, -819200, 0, 0, 0, 0,
         80, 3, 0, 0, 0, 0, -1, 0, 0),
    42: (11, 1, -1, -1, 8, 19, -51200, 76800, -1382400, 0, 0, 0, 0,
         50, 3, 0, 0, 0, 0, -1, 0, 0),
    43: (11, 1, -1, -1, 8, 19, 153600, 0, -1280000, 0, 0, 60, 0,
         50, 3, 0, 0, 0, 0, -1, 0, 0),
    44: (11, 1, -1, -1, 8, 19, -249856, 0, 1139200, 155, 0, 0, 0,
         50, 3, 0, 0, 0, 0, -1, 0, 0),
    45: (2, 0, -1, -1, 8, 19, -76800, 0, 768000, 155, 0, 0, 0,
         50, 3, 0, 0, 0, 0, -1, 0, 0),
}

# aMissionNavPoints[16..19] (game.c:199-226): every point is type 1 at
# (0, 0, 0) with radius 50000 and no triggers; only the ship lists
# differ. The type lists ({DRALTHI, HORNET} etc.) matter only to live
# spawn, so they are kept here for documentation.
NAV_SHIPS = {
    16: (32, 33, 34, 35, -1, -1, -1, -1, -1, -1),
    17: (36, -1, -1, -1, -1, -1, -1, -1, -1, -1),
    18: (37, 38, 39, 40, 41, -1, -1, -1, -1, -1),
    19: (42, 43, 44, 45, -1, -1, -1, -1, -1, -1),
}
NAV_TYPES = {16: (10, 0), 17: (22,), 18: (12, 1), 19: (11, 2)}


def _menu(ss4, has_save):
    """The menu loop of title.c:319-497. menuOptions[0] = 0 always and
    [1] = 1 only when a save exists (:334-341); the DOS build keeps
    options 2 and 3 at -1, so frames 2 and 3 of ti4.wcs are never drawn.
    Each option's frame goes at its region left/top (:374-385) as an
    unscaled DrawSpriteDefault - scramble.py's _draw is that draw. The
    selection starts at 0; the fade to black mirrors scene.py's fade of
    FadeViewportPaletteToColour (:492-496)."""
    global hold, stage
    hold = False
    stage = 'menu'
    fb = display.buffer
    options = (0, 1) if has_save else (0,)
    n = len(options)
    sel = 0
    r = -1
    ui.wait_release()             # the press that ended the cinematic
    while True:
        display.fill(0)           # ClearViewport(cBlackColour) :373
        for i, opt in enumerate(options):
            S._draw(fb, ss4, opt, MENU_X, MENU_Y + MENU_STEP * i)
        ui.text.draw(fb, b'>', S._cx(MENU_X) - 9,
                     S._cy(MENU_Y + MENU_STEP * sel) + 3, ui.YELLOW)
        display.update()
        if buttonU.justPressed():
            sel = (sel - 1) % n
        elif buttonD.justPressed():
            sel = (sel + 1) % n
        elif buttonA.justPressed():
            r = options[sel]      # state = menuOptions[selection] + 1,
            break                 # return state - 1 -> the option itself
        elif buttonB.justPressed() or buttonMENU.justPressed():
            break
    for _ in range(8):            # the fade to black (:492)
        G.dim_rows(fb, 0, 128)
        display.update()
    G.fill_rows(fb, 0, 128, 0)    # ClearViewport after the fade (:493)
    display.update()
    ui.wait_release()
    return r

# --- the picture font: GetLineLength and print_subtitle (mono.c) -----------

# GetLineLength (mono.c:167-198): letters 'A'..'z' take the glyph frame
# c - 65 and advance its right extent plus 2; '.' is frame 58 and ',' is
# frame 59 (the original's literal indices, mono.c:183-190); a space
# advances 6; a newline ends the line. Digits and '-' match nothing and
# advance nothing. The extents are the ti1wd.wc width table the converter
# wrote: one byte per glyph frame, the original GetShapeFrameExtent right
# edge (cutscene.c).

def _line_len(wd, text, i=0):
    w = 0
    n = len(text)
    while i < n:
        c = text[i]
        i += 1
        if c == 0:
            break
        if 65 <= c <= 122:
            w = w + wd[c - 65] + 2
        elif c == 46:                      # '.'
            w = w + wd[58] + 2
        elif c == 44:                      # ','
            w = w + wd[59] + 2
        elif c == 32:                      # ' '
            w = w + 6
        elif c == 10:                      # '\n'
            break
    return w


# print_subtitle (mono.c:205-251): the block is centred on the
# original's 200-row screen (y = (200 - 16 * lines) / 2) and every line
# is centred across the 320-pixel screen ((320 - length) >> 1); a
# newline steps y by the font height of 16 and recentres the rest of the
# text. The arithmetic stays in ORIGINAL pixels exactly as mono.c does
# it - y lives in that 0..200 space, not the device's 128 rows; the blit
# maps the anchor into the device's square-pixel space - the space scene
# fills the whole 128 x 112 screen, so the mapping is x * 2 / 5 across
# and y * 14 / 25 down (112 / 200), rounded to nearest, and the converted
# glyph's hot spot lands on that point (DrawSpriteDefault, gr.c:740-746).
# Centring in the 128 device rows instead, as this port did, fed the
# mapping a second time and left the text in the upper third. This is not
# scramble.py's _draw: that maps the conversation band's rows 16..78,
# while the title draws over every row. The colour argument selects
# nothing in the original - the glyphs carry their own palette entries.
# The DIBslam of :248-249 is the device display.update the phase loop
# does after the draw.

# Device deviation: on a device every glyph read is a flash read -
# SpriteSet.read opens, seeks and closes (wcdata.py:194-198), so the
# per-frame glyph pass put some seventy opens and closes into every
# drawn frame and ran phase A at about one frame per second there. The
# port renders each text block once into a full-screen index canvas and
# the drawn frames blit that canvas over the scene: the anchors and the
# mapping below are untouched, each glyph is read once per text, not
# once per frame. The canvas belongs to the title: MainGame claims it
# while the heap is fresh, before importing this module, and hands it
# over; it goes back whole when the title ends. Without one - the PC
# harness - title() tries the heap itself and runs the text-less path
# if the ask fails.
_TXT = None
# The canvas is cleared row by row against this one shared zero row:
# filling with a fresh `bytes` copy of the whole canvas was itself an
# allocation - 14,337 bytes asked for mid-cinematic, with 15,232 free,
# and it died there. Equal slices replace in place; nothing new is
# ever made. (docs/12 12.2)
_ROW0 = bytes(128)


def _sub_glyph_into(ss1, frame, x, y):
    """One glyph at the original anchor (x, y) = the hot spot, mapped to
    the device title space and copied into the canvas."""
    e = S._read(ss1, frame)
    if e is None:
        return
    w, h, hx, hy = e
    dx = (x * 4 + 5) // 10                 # round(x * 2 / 5)
    dy = (y * 28 + 25) // 50               # round(y * 14 / 25)
    x0 = dx - hx
    y0 = dy - hy
    src = S._scratch
    row = 0
    while row < h:
        ry = y0 + row
        if 0 <= ry < 112:
            di = ry * 128
            si = row * w
            col = 0
            while col < w:
                px = x0 + col
                if 0 <= px < 128:
                    _TXT[di + px] = src[si + col]
                col += 1
        row += 1


def _subtitle_prep(ss1, wd, text):
    """Centring the block the way print_subtitle does and copying every
    glyph into the canvas, once per text. The centring arithmetic stays
    in ORIGINAL pixels exactly as mono.c does it."""
    lines = 1
    for c in text:
        if c == 10:
            lines += 1
    lines = lines * 16
    y = (200 - lines) // 2            # original-pixel centring; the
                                      # glyph copy maps y * 14 / 25
    x = (320 - _line_len(wd, text)) >> 1
    if _TXT is False:
        return
    row = 0
    while row < 112:
        o = row * 128
        _TXT[o:o + 128] = _ROW0
        row += 1
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        i += 1
        if 65 <= c <= 122:
            _sub_glyph_into(ss1, c - 65, x, y)
            x = x + wd[c - 65] + 2
        elif c == 32:
            x = x + 6
        elif c == 46:
            _sub_glyph_into(ss1, 58, x, y)
            x = x + wd[58] + 2
        elif c == 44:
            _sub_glyph_into(ss1, 59, x, y)
            x = x + wd[59] + 2
        elif c == 10:
            y = y + 16
            x = (320 - _line_len(wd, text, i)) >> 1


def _subtitle(fb):
    """The drawn-frame half of the port's print_subtitle: one full
    canvas transparent blit over the redrawn scene per drawn frame."""
    if _TXT is False:
        return
    G.blit_indexed(fb, ui.pal, _TXT, 0, 0, 128, 112, 0, 112)


# --- the canned interpreter (mono.c) ----------------------------------------

# advance_canned_sequence (mono.c:254-283) and update_canned_sequence
# (:286-312), verbatim. apCannedSequenceList[obj] becomes the object's
# SEQS tuple and a command index held in the _Canned state; the yaw /
# pitch / roll targets go on the object's gy / gp / gr and the speed on
# obj.speed, 24.8 raw exactly as anShipSpeed = *command++ << 8. The
# chained speed test compares the 0 / 1 result of the first comparison
# with the upper bound, exactly as mono.c:300-302 does - it is always
# true - and it reads aShipVelocity[0], the eye's velocity, which is the
# port's slot 0 too. cmd2 is the explode(-1, obj) of :271; cmd3 fires
# every enabled PROJECTILE weapon with no shot counter
# (fire_fixed_projectile_weapon, ship.c); cmd4 is the afterburner special
# maneuver of :277-278. Any command outside 0..4 (the -1 terminator) is
# consumed and the pointer advances past it; the sequence then idles,
# since update_canned_sequence has no matching case.

class _Canned:
    """One object's interpreter state. The goals and the speed live on
    the object itself (gy / gp / gr / speed); the pointer does not, since
    world.py's LITE guard would forbid a new attribute on the Lite
    asteroid records this slot also holds."""

    def __init__(self, seq):
        self.seq = seq
        self.ptr = 0
        self.cmd = -2          # nothing advanced yet
        self.cnt = 0

    def advance(self, w, o, eye):
        """advance_canned_sequence, mono.c:254-283, verbatim. The port's
        ship objects are the originals' object indices (mono.c:258's
        apCannedSequenceList[obj] is this interpreter's seq; the pointer
        is this state, not the object's field)."""
        s = self.seq
        if s is None:
            return
        if self.ptr >= len(s):
            # the original reads past the terminator's array (undefined
            # in C, harmless garbage); the port stops here - traced
            # through the original's own flow this cannot be reached.
            self.cmd = -1
            return
        cmd = s[self.ptr]
        self.ptr += 1
        self.cmd = cmd
        if cmd == 0:
            self.cnt = s[self.ptr]
            self.ptr += 1
        elif cmd == 1:
            o.gy = s[self.ptr]; self.ptr += 1     # anYawTarget[obj]
            o.gp = s[self.ptr]; self.ptr += 1     # anPitchGoal[obj]
            o.gr = s[self.ptr]; self.ptr += 1     # anRollGoal[obj]
            o.speed = s[self.ptr] << 8            # anShipSpeed[obj]
            self.ptr += 1
        elif cmd == 2:
            w.explode(-1, o.i)                    # explode(-1, obj)
        elif cmd == 3:
            _fire_fixed(w, o)                     # ship.c:2155
        elif cmd == 4:
            # aeSpecialManeuvers = SPECIAL_MANEUVER_AFTERBURNER
            # (mono.c:277-278): the original sets only the maneuver, so
            # world.py's timer gate (move :1302-1308) is fed the flight
            # player's own timer value of 3 turns - the boost ends when
            # the next command takes over, as the original's does once
            # the canned speed command replaces the velocity.
            o.special = W.SM_AFTERBURNER
            o.abtimer = 3

    def update(self, w, o, eye):
        """update_canned_sequence, mono.c:286, verbatim."""
        cmd = self.cmd
        if cmd == 0:
            self.cnt -= 1
            if self.cnt == 0:
                self.advance(w, o, eye)
        elif cmd == 1:
            if o.gy == 0 and o.gp == 0 and o.gr == 0:
                # mono.c:300-302's chained comparison, verbatim
                if ((o.speed - 0x400 <
                     M.mag(eye.vx, eye.vy, eye.vz)) < o.speed + 0x400):
                    self.advance(w, o, eye)
        elif cmd == 3 or cmd == 4:
            self.advance(w, o, eye)
        # cmd 2 advances nothing: the switch has no case 2 (mono.c:288)

# --- the eye and its scripted view (view.c / spc.c / geom.c / ship.c) ------

# initialize_scripted_view (view.c:198-206): bScriptedView = 1, the eye's
# velocity is zeroed, its frame is set to the identity (init_ijk), the
# script is parsed, and the collision radius is 100 - but force_view of
# the script's cmd3 overwrites that with the eye radius of 10
# (new_view, spc.c:497-501: obj == -1 -> radius 10) before the first turn
# is drawn. The eye is the original's object 61; the port's world has no
# slot 61, so the eye lives in its own state object here, and every place
# the originals read aShipPositionsArray[0] for the hazard chain reads
# this eye instead (documented deviation).

class _Eye:
    """The scripted eye of the intro camera. m / x y z / vx vy vz are
    24.8 like world.py's objects; rp / ry / rr are degrees per turn."""

    def __init__(self):
        self.m = [0] * 9
        M.identity(self.m)
        self.x = self.y = self.z = 0
        self.vx = self.vy = self.vz = 0
        self.rp = self.ry = self.rr = 0
        self.radius = 100            # view.c:205, overwritten by cmd3
        self.view = 0
        self.tgt = 0                 # nEyePitchTargetValue
        self.tgy = 0                 # nEyeYawGoalValue
        self.tgr = 0                 # nEyeRollTargetValue
        self.rate = 0                # nEyePitchRate
        self.ratey = 0               # nEyeYawRate (unused by the intro)
        self.rater = 0               # nEyeRollRate (unused)
        self.cnt = 0                 # asObjectCounterArray[61]
        self.ptr = 0
        self.scripted = True


def _match(r, g, te, rate):
    """match_rotation_goal (ship.c:318-356), verbatim, returning the new
    rotation and goal. world.py's _match is the same port used for the
    world's ships; the eye needs this local copy because it is not a
    world object."""
    if te != 0:
        if g > 180:
            g -= 360
        if g < -180:
            g += 360
        step = max(1, (abs(r - g) * rate) // te)
        if g != r or step < abs(r):
            if g > 0:
                r += max(min(min(min(g, step) - r, step), -step), -step)
                # C: MaxShort(MinShort(MinShort(g, step) - r, step), -step)
            else:
                r += min(max(max(g, -step) - r, -step), step)
                # C: MinShort(MaxShort(MaxShort(g, -step) - r, -step), step)
    if g != 0:
        if g > 0:
            g = max(g - r, 0)
        else:
            g = min(g - r, 0)
    return r, g


def _parse_view_script(e):
    """parse_view_script (view.c:38-168) reduced to the commands the
    intro script uses (game.c:110-113: 0, 2, 1, 3, 4 and the 13 / 14
    control), verbatim for those. After every command the parser returns
    when the next value is 13 (view.c:162-163) - the intro script halts
    right after cmd4, so cmd14's counter is armed only later, when the
    eye-pitch settle lets the cmd13 gate fire."""
    s = CAM_SCRIPT
    p = e.ptr
    if s[p] == 13:
        return
    while True:
        if s[p] == -1:
            e.scripted = False           # view.c:47-51
            e.ptr = p
            return
        if s[p] == 14:
            break
        cmd = s[p]
        p += 1
        if cmd == 0:
            e.x = s[p] << 8; p += 1      # positions are 24.8
            e.y = s[p] << 8; p += 1
            e.z = s[p] << 8; p += 1
        elif cmd == 1:
            M.yaw(e.m, s[p]); p += 1     # alter_yaw(*p++, 61)
            M.pitch(e.m, s[p]); p += 1   # alter_pitch(*p++, 61)
            M.roll(e.m, s[p]); p += 1    # alter_roll(*p++, 61)
            M.fix(e.m)
        elif cmd == 2:
            # ScaleFixedVector(&aShipFwdVec[61], *p++ << 8, vel): the
            # port's 14-bit frame rows give (m[i] * (val << 8)) >> 14 -
            # at m = 16384 and val = 15 that is 15 units a turn.
            spd = s[p] << 8; p += 1
            e.vx = (e.m[6] * spd) >> 14
            e.vy = (e.m[7] * spd) >> 14
            e.vz = (e.m[8] * spd) >> 14
        elif cmd == 3:
            # force_view (spc.c:470-475): nCameraViewMode = -1, then
            # new_view(view, nScriptedViewObject). The scripted object
            # is -1 at the start of the intro, so new_view sets the eye
            # radius to 10 (spc.c:501) and view mode 15.
            e.view = s[p]; p += 1
            e.radius = 10
        elif cmd == 4:
            e.tgt = -s[p]; p += 1        # nEyePitchTargetValue = -*p++
            e.rate = s[p]; p += 1        # nEyePitchRate = *p++
        # commands 5..16 are not used by the intro script
        e.ptr = p
        if s[p] == 13:
            return
    # view.c:165: the 14 arms the counter with its second word
    e.cnt = s[p + 1]


def _update_scripted_view(e):
    """update_scripted_view (view.c:171-195), verbatim. The cmd13 gate
    is (nEyeYawGoal == nEyePitchTarget) != nEyeRollTarget - the chained
    comparison of view.c:179-180, kept exactly."""
    if not e.scripted:
        return
    cmd = CAM_SCRIPT[e.ptr]
    if cmd == 13:
        if (e.tgy == e.tgt) != e.tgr:
            e.ptr += 1
            _parse_view_script(e)
    elif cmd == 14:
        cnt = e.cnt
        e.cnt -= 1
        if cnt < 1:
            e.ptr += 2
            _parse_view_script(e)


def _clamp30(v):
    """ClampVectorTo30 (geom.c:1178-1188): a rotation one away from zero
    is pulled one step toward zero; zero stays zero."""
    if v < 0:
        return v + 1
    if 0 < v:
        return v - 1
    return v


def _eye_rotate(e):
    """rotate_object (spc.c:1072-1087) for the eye, plus the
    ClampVectorTo30 decay the port's world.py rotate_object omits."""
    if e.rp != 0:
        M.pitch(e.m, e.rp)
        M.fix(e.m)
        e.rp = _clamp30(e.rp)
    if e.ry != 0:
        M.yaw(e.m, e.ry)
        M.fix(e.m)
        e.ry = _clamp30(e.ry)
    if e.rr != 0:
        M.roll(e.m, e.rr)
        M.fix(e.m)
        e.rr = _clamp30(e.rr)


def _rotate_eye_to_goal(e):
    """rotate_eye_to_goal (spc.c:129-149), verbatim: the eye's pitch /
    yaw / roll walk toward the script's targets with the script's rates.
    The intro script sets only the pitch target and rate; the yaw and
    roll targets stay 0, so their walks are no-ops regardless of the
    rates the globals start with."""
    te = (abs(e.rp - e.tgt) + abs(e.ry - e.tgy) + abs(e.rr - e.tgr))
    e.rp, e.tgt = _match(e.rp, e.tgt, te, e.rate)
    e.ry, e.tgy = _match(e.ry, e.tgy, te, e.ratey)
    e.rr, e.tgr = _match(e.rr, e.tgr, te, e.rater)


def _eye_turn(e):
    """set_eye's case 15 (spc.c:458-463): the eye advances by its
    velocity, rotates, and walks its rotations toward the goals."""
    e.x += e.vx
    e.y += e.vy
    e.z += e.vz
    _eye_rotate(e)
    _rotate_eye_to_goal(e)


def _scale_eye_speed(e, raw):
    """the D setup's ScaleFixedVector(&aShipFwdVec[61], 0x9600)
    (title.c:246-247): 0x9600 = 150 << 8 -> 150 units a turn."""
    e.vx = (e.m[6] * raw) >> 14
    e.vy = (e.m[7] * raw) >> 14
    e.vz = (e.m[8] * raw) >> 14

# --- the hazard chain (winmain.c) --------------------------------------------

# The chain is ported verbatim from winmain.c:134-507. The port's "slot 0"
# for the chain is a mirror object in world.py's slot 0 that is synced
# from the eye by match_ship_to_eye every turn (the original's object 61
# copy into the player slot); the eye itself stays a title-side object
# used for drawing. The tables are winmain.c's globals.

TRAVEL_BY_VIEW = (56, 52, 75, 73, 0, 0, 0, 0)    # winmain.c:24-26
PITCH_RANGE = (-10, 4, -8, 8, -12, 8, -8, 8)     # winmain.c:28-30

haz = [-1] * 20        # abHazardObjects: 20 hazard slots, -1 = empty
ref_speed = 0          # nHazardReferenceSpeed
active = 0             # nActiveHazards
field = None           # pActiveHazardField (None / 0 = no active field)
fields = []            # aHazardFields, filled at the D setup
rendered_space = 0     # nRenderedSpaceFrame (main.c:645-ish)
secondary = False      # bIntroSecondaryScene (title.c:245)

# Marker flags and the distance table of geom.c's screenX live in parallel
# lists by WORLD slot (world.py's LITE guard forbids new attributes on
# Lite objects); _mk[s] is asObjectScreenXList[obj], _dt[s] is
# asObjDistancesTable[obj]. They are rebuilt by the marker pass every
# drawn picture.
_mk = [0] * 64
_dt = [0] * 64


def _align(v, q):
    """align (winmain.c:199-206): v -= v % quantum with the C % (the sign
    follows the dividend; Python's % follows the divisor)."""
    m = abs(v) % q
    if v < 0:
        m = -m
    return v - m


def _difficulty():
    """difficulty (winmain.c:163-166): abs(25 - ref) * 2 - 150 for the
    intro's reference speed of 100."""
    return abs(25 - ref_speed) * 2


def _asteroid_velocity():
    """asteroid_velocity (winmain.c:169-172): min(20, rndle(7) + 10)."""
    return min(20, W.rndle(7) + 10)


def _skew_randomly(o, allow_reverse):
    """skew_randomly (winmain.c:175-196) on the port's 14-bit frame rows:
    right is m[0..2], up is m[3..5], fwd is m[6..8]. The permutations
    keep the frame orthonormal, so no fix is needed (the original does no
    fix either)."""
    if W.rnd(100) < 50:
        saved = o.m[0:3]           # right
        o.m[0:3] = o.m[6:9]        # right = fwd
        o.m[6:9] = o.m[3:6]        # fwd = up
        o.m[3:6] = saved           # up = saved right
    else:
        saved = o.m[3:6]           # up
        o.m[3:6] = o.m[6:9]        # up = fwd
        o.m[6:9] = o.m[0:3]        # fwd = right
        o.m[0:3] = saved           # right = saved up
    if allow_reverse != 0 and W.rnd(100) < 50:
        o.m[6] = -o.m[6]           # negate_vector(&aShipFwdVec[obj])
        o.m[7] = -o.m[7]
        o.m[8] = -o.m[8]


def _init_hazard(o, position, moving):
    """init_hazard (winmain.c:209-286), verbatim. The eye's velocity is
    15 units a turn while the hazard mirror's (slot 0) is the 100 of
    match_ship_to_eye; the travel vector uses the mirror's."""
    global active
    moves = moving
    if field['type'] == W.OT_ASTEROID_FIELD:
        typ = W.OT_ASTEROID1 + W.rndle(5)      # 34 + (0..5)
    else:
        typ = W.OT_MINE                        # 33
    w.set_objects_data(o, typ, -1)
    o.x, o.y, o.z = position                   # 24.8
    p = w.o[0]
    if typ == W.OT_MINE:
        _point_at(o, p.x, p.y, p.z)
        _skew_randomly(o, 1)
        speed = 2
        moves = 0
    elif moves != 0:
        tt = (TRAVEL_BY_VIEW[0] if p.view < 4 else 65) + W.rndle(15)
        tt -= W.rndle(_difficulty())
        tt = max(45, tt) if secondary else max(7, tt)
        # ScaleFixedVector(&aShipVelocity[0], tt << 8, &vector) then
        # AddFixedVectors(pos0, vector): where the hazard sits when the
        # mirror has flown tt turns. 24.8 velocity: (v * (tt << 8)) >> 8.
        sx = (p.vx * (tt << 8)) >> 8
        sy = (p.vy * (tt << 8)) >> 8
        sz = (p.vz * (tt << 8)) >> 8
        vx, vy, vz = p.x + sx, p.y + sy, p.z + sz
        _point_at(o, vx, vy, vz)
        speed = _distance(vx, vy, vz, o.x, o.y, o.z)      # units
        tt = max(3, tt - W.rnd(5))
        speed = speed // tt
    else:
        _point_at(o, field['center'][0], field['center'][1],
                  field['center'][2])
        _skew_randomly(o, 1)
        speed = 0 if W.rnd(100) < 20 else _asteroid_velocity()
    if _kilrathi_near(0, 16000) != 0:
        speed = 0
    o.vx = (o.m[6] * (speed << 8)) >> 14
    o.vy = (o.m[7] * (speed << 8)) >> 14
    o.vz = (o.m[8] * (speed << 8)) >> 14
    if moves == 0:
        # winmain.c:268-277: the type is ASTEROID1..6 / SPACE_MINE here,
        # never ASTEROID_FIELD, so the separation is always rndle(1000)
        # << 8 (24.8 raw) - pull the spawn back along fwd.
        sep = W.rndle(1000) << 8
        o.x -= (o.m[6] * sep) >> 8
        o.y -= (o.m[7] * sep) >> 8
        o.z -= (o.m[8] * sep) >> 8
    if typ == W.OT_MINE:
        # winmain.c:278-282 aligns the integer part of each fixed
        # coordinate (the short cast in the original) to 200 units.
        q = _align(o.x >> 8, 200)
        o.x = (q << 8) | (o.x & 0xff)
        q = _align(o.y >> 8, 200)
        o.y = (q << 8) | (o.y & 0xff)
        q = _align(o.z >> 8, 200)
        o.z = (q << 8) | (o.z & 0xff)
    active += 1
    o.counter = 0
    o.grace = 0                          # acObjCollisionGraceTicks


def _remove_hazard(hazard):
    """remove_hazard (winmain.c:134-147) together with the bookkeeping
    its remove_object call performs (geom.c:1043-1073): the projection
    marker, the zeroed distance table entry and the scan that clears the
    hazard-list slot - the scan is what keeps the slot from dangling
    after manage_hazard's failed-spot branch. The sound-source write is
    not ported; the SDL guard means empty (-1) slots are passed through.
    The nav / wingman resets of geom.c:1051-1054 have no meaning for a
    hazard object and are omitted."""
    global active
    if hazard >= 0:
        _mk[hazard] = 0x8001              # geom.c:1049
        _dt[hazard] = 0                   # geom.c:1050
        for slot in range(20):            # geom.c:1055-1060
            if haz[slot] == hazard:
                haz[slot] = -1
                break
        w.remove(w.o[hazard])             # world.py:402: class NULL,
                                          # invisible, shape gone
    active = max(0, active - 1)           # winmain.c:146


def _remove_all_hazards():
    """remove_all_hazards (winmain.c:150-160): the do-while runs slots
    0..19, and pActiveHazardField is cleared."""
    global field
    for slot in range(20):
        _remove_hazard(haz[slot])
        haz[slot] = -1
    field = None


def _near_field(f, px, py, pz):
    """near_field (winmain.c:289-294): within innerRadius + 4300."""
    return _is_within(f['center'][0], f['center'][1], f['center'][2],
                      px, py, pz, f['inner'] + 4300)


def _within_field(f, px, py, pz):
    """within_field (winmain.c:297-301): within innerRadius."""
    return _is_within(f['center'][0], f['center'][1], f['center'][2],
                      px, py, pz, f['inner'])


def _try_far_spot(spot, moving):
    """try_far_spot (winmain.c:304-348), verbatim. The intro's view mode
    is 15, never 0, so the else branch of the moving gate is the live
    one. The scratch frame and position are the mirror's (the original
    copies the player slot into object 63)."""
    pitch = _signed_random(20)
    yaw = _signed_random(35)
    p = w.o[0]
    if p.view == 0:
        # the live branch for flight; the intro never takes it
        minimum = PITCH_RANGE[0]
        maximum = PITCH_RANGE[1]
        moving[0] = 1 if (minimum < pitch < maximum and
                          abs(yaw) < 19 and W.rnd(100) < 60) else 0
    else:
        moving[0] = 1 if (5 < abs(pitch) < 20 and 5 < abs(yaw) < 20 and
                          W.rnd(100) < 30) else 0
    pitch += _find_ratio(-15, 15, p.rp, -150, 150)
    yaw += _find_ratio(-15, 15, p.ry, -150, 150)
    m = p.m[:]                      # copy_frame(0, 63)
    _rotate_about_j(m, yaw)         # about right, fwd toward right
    _rotate_about_i(m, pitch)       # about up, fwd toward up
    _rel_ijk(spot, p.x, p.y, p.z, m, 3050)
    outside = _is_within(p.x, p.y, p.z, spot[0], spot[1], spot[2], 3000)
    return outside == 0 and _within_field(field, spot[0], spot[1],
                                          spot[2]) != 0


def _rear_sphere():
    """rear_sphere (winmain.c:351-355): find_ratio(0, 20, ref, 4300,
    3100) - 3100 at the intro's reference speed of 100."""
    return _find_ratio(0, 20, ref_speed, 4300, 3100)


def _ok_hazard_spot(o):
    """ok_hazard_spot (winmain.c:358-367): range 4300, or the rear-sphere
    distance for objects the marker flags as behind (0x8001)."""
    p = w.o[0]
    rng = 4300
    if _mk[o.i] == 0x8001:
        rng = _rear_sphere()
    return _is_within(p.x, p.y, p.z, o.x, o.y, o.z, rng)


def _make_hazard():
    """make_hazard (winmain.c:370-381)."""
    spot = [0, 0, 0]
    moving = [0]
    slot = _find_vacant()
    if slot != -1 and _try_far_spot(spot, moving) != 0:
        o = w.o[slot]
        _init_hazard(o, spot, moving[0])
        return slot
    return -1


def _approach(o):
    """approach (winmain.c:391-402): a mine 1500 units out at under 20
    u/turn is pointed at a spot 20 mirror-turns ahead and given 20
    u/turn along its new fwd."""
    p = w.o[0]
    sx = (p.vx * (20 << 8)) >> 8
    sy = (p.vy * (20 << 8)) >> 8
    sz = (p.vz * (20 << 8)) >> 8
    _point_at(o, p.x + sx, p.y + sy, p.z + sz)
    o.vx += (o.m[6] * (20 << 8)) >> 14
    o.vy += (o.m[7] * (20 << 8)) >> 14
    o.vz += (o.m[8] * (20 << 8)) >> 14


def _manage_hazard(slot_obj, slot):
    """manage_hazard (winmain.c:405-418), verbatim."""
    if rendered_space % 20 != slot:
        return
    if _ok_hazard_spot(w.o[slot_obj]) == 0:
        _remove_hazard(slot_obj)
        return
    o = w.o[slot_obj]
    if (o.typ == W.OT_MINE and _mk[o.i] != 0x8001 and
            _dt[o.i] > 1500 and _real_velocity(o) < 20):
        _approach(o)


def _match_ship_to_eye():
    """match_ship_to_eye (winmain.c:421-432): the eye's frame, position
    and forward row are copied into the mirror slot, the reference speed
    is 100, the mirror's velocity is fwd * 100 units a turn, and the
    active field's centre becomes the eye's position."""
    global ref_speed
    p = w.o[0]
    p.m[:] = e.m
    p.x, p.y, p.z = e.x, e.y, e.z
    ref_speed = 100
    p.vx = (p.m[6] * (100 << 8)) >> 14
    p.vy = (p.m[7] * (100 << 8)) >> 14
    p.vz = (p.m[8] * (100 << 8)) >> 14
    field['center'] = (e.x, e.y, e.z)


def _update_hazards():
    """update_hazards (winmain.c:435-454), verbatim. The intro's
    reference speed is 100, so the refill test RandomBelowOrEqual(215) <
    130 is roughly a 60 % chance a turn."""
    global ref_speed
    if secondary:
        _match_ship_to_eye()
    else:
        ref_speed = _real_velocity(w.o[0])
    empty = -1
    for slot in range(20):
        obj = haz[slot]
        if obj != -1:
            _manage_hazard(obj, slot)
        else:
            empty = slot
    if empty != -1 and W.rndle(215) < ref_speed + 30:
        haz[empty] = _make_hazard()


def _start_hazard_field(region):
    """start_hazard_field (winmain.c:457-467): the do-while with the
    post-increment runs for slots 1, 2 and 3 - three hazards."""
    global field
    _remove_all_hazards()
    field = fields[region]
    slot = 1
    while True:
        haz[slot] = _make_hazard()
        if slot >= 3:
            break
        slot += 1


def _add_hazard_field(typ, center, radius):
    """add_hazard_field (winmain.c:470-484): outer and inner radius are
    the same value."""
    global fields
    if len(fields) >= 7:
        return
    fields.append({'type': typ, 'center': center, 'outer': radius,
                   'inner': radius})


def _check_hazards():
    """check_hazards (winmain.c:487-507): dead while the intro secondary
    scene runs; otherwise it starts the nearest field the eye has come
    near, or clears the active field when the eye has left it."""
    if secondary:
        return
    p = w.o[0]
    if field is None:
        for region in range(len(fields)):
            if fields[region] is not None and \
                    _near_field(fields[region], p.x, p.y, p.z):
                _start_hazard_field(region)
                return
    elif _near_field(field, p.x, p.y, p.z) == 0:
        _remove_all_hazards()

# ============================================================
# title.c verbatim: the intro text, the eleven DOS credits, the logo
# draw, and the Title_Sequence flow (title.c re-read in full, 1..499,
# this session; every line number below checked against that read).
# ============================================================

# pszIntroOpeningText (title.c:12-14), verbatim - phase A prints it
# through the print_subtitle port.
OPENING_TEXT = (b"In the distant future,\n"
                b"mankind is locked in a deadly war...")

# nIntroCreditCount = 11 (title.c:22) - the DOS title's count, already
# pinned as CREDITS_N above. The Kilrathi Saga flag would add nine
# Windows-era entries (:156-157); that build feature is not ported
# (documented deviation). apszIntroCredits (title.c:24-45): the eleven
# DOS strings, verbatim - including the trailing newline of the second
# entry, which makes its block nine lines tall: centred on the
# original's 200 rows it starts 28 down and fits there, and the device
# mapping puts its nine line anchors from row 16 to row 87 of 112, the
# glyphs about 7 rows tall - it fits on the device too. What the old
# comment called an original quirk (the block starting above the top)
# was the 128-row centring bug, not the original.
CREDITS = (
    b"Design\nby\nChris Roberts",
    b"Software Engineers\nChris Roberts\nKen Demarest III\nPaul C. Isaac\nSteve Muchow\nHerman Miller\nSteve Beeman\n",
    b"Dogfight Intelligence\nKen Demarest III\n\nDogfight Choreography\nSteve Beeman\nErin Roberts",
    b"3Space System\nby\nChris Roberts\n\nOriginFX Graphic System\nChris Roberts\nJohn Miles",
    b"OriginFX Sound System\nby\nHerman Miller",
    b"Artwork\nDenis Loubet\nGlen Johnson\nDaniel Bourbonnais\nKeith Berdak\nJohn Watson",
    b"Screenplay by Jeff George\n\nAdditional Writing\nSteve Cantrell\nPhilip Brogden",
    b"Soundtrack by\nGeorge A. Sanger and Dave Govett",
    b"Sound Effects by Marc Schaefgen",
    b"Produced by\nChris Roberts and Warren Spector",
    b"Directed by\nChris Roberts",
)

# The rest of apszIntroCredits (:36-44 - Windows 95 team, the rescored
# soundtrack notes, the whiners) is Windows-only and unreachable while
# the count stays 11. szMissingSecretMissionsMessage (:17-21) belongs
# to the secret-missions option, which the DOS title never enables:
# menuOptions[2] stays -1 (:340-341), so frames 2 and 3 of ti4.wcs are
# never drawn and the option is never selectable. Not ported.

# aTitleMenuRegions (title.c:48-54) are mouse hit rectangles carrying
# right / bottom corners; the SDL build re-sets left / top to 49 /
# 48 + 43 * i (:345-346 - the MENU_* constants above) and
# GetShapeFrameBounds re-reads each region's left from its drawn frame
# (:351-367) for the mouse cursor's hit test (:116-132, and the click's
# FindMenuRegionAtPoint, :461-462). The Thumby menu is button-driven;
# _menu above is the documented deviation. The keyboard keys the
# original accepts (:413-446) are not ported either - S / C map to
# options the Thumby menu reaches with UP / DOWN, and M never fires in
# the DOS build since menuOptions[2] is -1 (:435-437).

# aIntroResourceDescriptors (title.c:57-63): the EXPLOSION1 shape set
# (:3, 2) and the DEBRIS_METAL_SHEET shape set (:3, 5) are the intro's
# resource list (:167-168), and DEBRIS_WING's shape set is set to
# METAL_SHEET's (:169-171), restored the same way in the cleanup
# (:307-309). Here the sets arrive through the world's own per-type
# shape loading (documented deviation).

# Packet identities from title.c's fetches: packet 9 item 0 = ti0.wcs,
# the logo (pTitleShape, :186); item 1 = ti1.wcs with its width table,
# the intro font (pIntroFont, :164); item 4 = ti4.wcs, the menu (:330).
# The SDL nLaunchCampaign menu variants (:326-333, with startFrame 2)
# are another build's feature; this port keeps the DOS frames 0 / 1.
# menuOptions (:334-341): option 0 always, option 1 only when a save
# exists, the rest -1 - exactly what _menu's options tuple encodes.

# DrawTitleLogo (title.c:78-113), verbatim in structure: distance <= 10
# returns; scale = 0x1000 / distance; frame 1 draws centred at the view
# centre x with GetTransformedShapeBounds anchoring frame 0 at
# bounds.left - 1 and frame 2 at bounds.right, every tile at y, rot 0,
# scale, drawn with DrawSpriteScaled. The ti0geo.wc sidecar carries the
# converter's copy of the transformed-bounds anchors per frame; the
# scaled blit is scramble.py's. _CX is the screen centre x and
# _cvpy() the current view-centre y, both set by the renderer pass.
def _logo(fb, distance, y):
    global _LOGO_SET
    if distance <= 10:
        return
    scale = 0x1000 // distance
    left, right = _xform_bounds(_LOGO_SET, 1, scale, _CX, y)
    _draw_scaled(fb, _LOGO_SET, 0, scale, left - 1, y)
    _draw_scaled(fb, _LOGO_SET, 1, scale, _CX, y)
    _draw_scaled(fb, _LOGO_SET, 2, scale, right, y)


# --- the cinematic driver: Title_Sequence's first half ---------------------

# Title_Sequence (title.c:135), the whole flow, verbatim in structure
# with the port-side names. The original runs the setup only when
# bEscapePressedFlag == 0 (:158) - no key was already down - then
# repeats the entire cycle until a key ends it (:176); the port plays
# one cycle (documented deviation). The music hook (:159), the event
# pump (:160), the resource-budget bookkeeping (:166-168), the shape
# frees (:304-306) and the joystick / mouse menu plumbing have no
# Thumby equivalent and are skipped; what runs is the world.
# _escaped() mirrors CheckEscaped (bEscapePressedFlag is a level flag,
# so once it fires the later checks keep seeing it, exactly as the
# original's checks do). _Update3Space, _Draw3Space and _RenderView
# come from the renderer pass (main.c).
def _pace(t0, n):
    """Wait until the n-th rendered frame is due, one frame every
    S.STEP_MS - the game turn, 100 ms, presenting the buffer through
    the wait. The original ran the title one game turn per rendered
    frame (nFrameSkip = 1); a turn is 1/10 s (docs/04 4.4.1), so the
    title's 1595 frames land close on the title music's 165 seconds
    (docs/08-music.md, track 23) - the rate every scene outside flight
    keeps here. titleseq.title holds the engine tick at that same rate
    for the cinematic, so one wait is one tick and the picture on the
    screen is re-blitted once per turn, not twice or thrice as at the
    menu's 20 Hz."""
    while ticks_diff(ticks_ms(), t0) < n * S.STEP_MS:
        display.update()
    # MicroPython has no reference counting: what this frame drew -
    # its sorted order tuples and its silhouette records - stays on
    # the heap until a collection sweeps it. One collect per rendered
    # frame keeps the cinematic's garbage to one frame's worth; left
    # alone it piled up until the title could no longer allocate its
    # world, the device crash docs/12 12.1 records.
    collect()


def _mem(tag):
    """MainGame.mem's shape, kept here so the title's own steps show
    where their room goes when the device runs out of it: 'preworld'
    before the cinematic's world, 'font' after its art arrives."""
    collect()
    print('WC mem', tag, mem_free())


def _ttl_read(name):
    """A whole-file read, plain. What the title reads is given back
    when the title module is popped (MainGame.title)."""
    return D.load(name)


def _ttl_set(name):
    """A frame table read plain, the same release at the title's end."""
    return D.SpriteSet(name)


def _cinematic(fb):
    global dist, stage, secondary, w, e, _SS1, _WD

    # setup, title.c:162-174:
    # init_3Space_objects(0) (:162) is the port's _title_world(); the
    # canned gate's mode, nCannedSceneMode = 2 (:163), is worn by every
    # title ship there; pIntroFont = packet(9, 1) (:164) is ti1.wcs
    # with ti1wd.wc; the resource descriptors' sets (:167-171) arrive
    # through the world's shape loading; the key state clears (:172-174)
    # are the ui press state, which ui.wait_release handles before the
    # menu.
    _title_world()                       # mission.c path (forward ref)
    collect()                            # the build's temps go before
    # the art arrives on the heap: the sweep keeps what the world left
    # loose out of the title's last margin
    _SS1, _WD = _load_intro_font()       # forward ref: ti1 font + widths
    _mem('font')                         # the world plus its art spent

    skip = False

    # title.c:178-184, the cycle's own resets - the port rebuilds the
    # world instead of resetting ship states in place, so the :178-180
    # state loop is covered by _title_world:
    dist = 200                           # title.c:181, titleDistance
    _remove_all_hazards()                # title.c:182
    secondary = 0                        # title.c:183, bIntroSecondaryScene
    _set_up_action_sphere(16)            # title.c:184 (mission.c)
    _load_logo()                         # pTitleShape = packet(9, 0), :186
    _init_view()                         # initialize_scripted_view, :188
    # spacetrack(0x17, 2, 1) (:187) and nFrameSkipCounter = 1 (:189) -
    # music is not ported; the 1 frame skip is the port's one turn per
    # picture frame, paced at S.STEP_MS like every scene outside flight.

    # --- phase A: title.c:191-205, 25 frames of black silhouettes with
    # the opening text. CheckEscaped sits inside the draw gate (:200);
    # intro_drawbackgroundships runs after the buffer reaches the screen
    # (:196-199) - on the port's single buffer the silhouettes must be
    # in front of display.update, which is what happens below.
    stage = 'A'
    t0 = ticks_ms()
    _subtitle_prep(_SS1, _WD, OPENING_TEXT)   # :194; the 0x32 block
                                              # rendered once for the
                                              # whole phase
    for i in range(PH_OPEN):
        _Update3Space()
        if _Draw3Space():
            _subtitle(fb)
            _intro_drawbackgroundships(fb)           # colour argument
            display.update()                         # selects nothing
            if _escaped():                           # :200-203
                skip = True
                break
        _pace(t0, i + 1)
    # clear_view_buffer (:206) - the next phase redraws the background
    # over the text, which is what the port's per-frame redraw does.
    if skip:
        return False                     # title.c:207-208

    # --- phase B: title.c:211-221, the do/while of 110 rendering
    # frames. CheckEscaped comes before frame++ and before the slams
    # (:214-217), so an escaped frame never blams.
    stage = 'B'
    t0 = ticks_ms()
    n = 0
    while n < PH_FLIGHT:                 # :221, frame < 110
        _Update3Space()
        _RenderView()
        if _escaped():                   # :214-217
            skip = True
            break
        n += 1
        display.update()                 # :219-220
        _pace(t0, n)
    if skip:
        return False                     # :222-223

    # --- phase C: title.c:225-241, 100 frames of the logo zoom. The
    # distance step (-4 while above 16, :235-236) and the escape check
    # (:237-240) sit outside the draw gate; the logo returns while
    # distance <= 10. dist lands on 16 after 46 steps and stays there.
    stage = 'C'
    t0 = ticks_ms()
    for i in range(PH_ZOOM):
        _Update3Space()
        if _Draw3Space():
            _logo(fb, dist, _cvpy() - 6)             # :228-229
            display.update()                         # :230-232
        if dist > 16:                                # :235-236
            dist -= 4
        if _escaped():                               # :237-240
            skip = True
            break
        _pace(t0, i + 1)
    # FreePacketAndClear(&pTitleShape) (:242): the original frees the
    # logo after the zoom; the converted ti0.wcs stays cached here.
    if skip:
        return False                     # :243-244

    # --- phase D: title.c:246-253, the entry into the asteroid field.
    _scale_eye_speed(e, 0x9600)          # :246-247, fwd * 150 units/turn
    _set_up_action_sphere(17)            # :248 - the on-screen intro
                                         # fleet explodes on entry
    secondary = 1                        # :249, bIntroSecondaryScene
    e.rp = 0                             # :250-252, the slot-0 rotations
    e.ry = 0
    e.rr = 0
    _start_hazard_field(0)               # :253, slots 1..3
    # The original goes straight into the first credit's drawn frames;
    # the port holds four drawn turns so the harness can photograph
    # the entry explosions (documented deviation).
    stage = 'D'
    t0 = ticks_ms()
    for i in range(4):
        _Update3Space()
        _Draw3Space()
        display.update()
        _pace(t0, i + 1)

    # Owner instruction, a documented deviation from title.c:246-247,
    # which holds the hazard entry's 150 units a turn all the way into
    # the credits: this port draws the dust as streaks from the eye's
    # motion (the original's dust was single pixels), and streaks at 150
    # cross the 112-row screen far too fast under credit text. The eye
    # drops to a 40-unit drift for phase E - the speed the title's
    # escort ships fly at, against the intro script's own 15-unit
    # drift. The hazard chain does not feel it: match_ship_to_eye holds
    # the reference speed at 100 for the spawns and the difficulty
    # whatever the eye does; the 150 closing frames inherit the drift.
    _scale_eye_speed(e, 40 << 8)

    # --- phase E: title.c:255-298, the credits and the closing flight.
    # Each credit: 70 frames with Draw_3Space_Frame and the credit text
    # (:257-271), then 40 frames of RenderSpaceViewFrame (:275-284).
    # The escape check after the 70-frame block exits the credit loop
    # (:272-273); note the original has NO state check after the 40
    # rendering frames - an escape there is caught by the next credit's
    # first drawn frame instead. The text redraw happens every drawn
    # frame; clear_view_buffer (:265) means each frame's text is drawn
    # fresh over the redrawn objects.
    stage = 'E'
    for credit in range(CREDITS_N):      # :256
        t0 = ticks_ms()
        _subtitle_prep(_SS1, _WD, CREDITS[credit])   # :260-261, once
                                                     # per credit
        for i in range(PH_CREDIT):       # :257, frame < 70
            _Update3Space()
            if _Draw3Space():
                _subtitle(fb)
                display.update()         # :262-264
            if _escaped():               # :267-270
                skip = True
                break
            _pace(t0, i + 1)
        if skip:
            return False                 # :272-273
        t0 = ticks_ms()
        for j in range(PH_RENDER):       # :275, frame < 40 - no check
                                         # after this loop in the C
            _Update3Space()
            _RenderView()
            display.update()             # :278-279
            if _escaped():               # :280-283
                skip = True
                break
            _pace(t0, j + 1)
    if skip:
        return False                     # :286-287

    # title.c:289-298: 150 frames of plain flight to close.
    t0 = ticks_ms()
    for i in range(PH_CLOSE):
        _Update3Space()
        _RenderView()
        display.update()                 # :292-293
        if _escaped():                   # :294-297
            skip = True
            break
        _pace(t0, i + 1)
    if skip:
        return False

    # title.c:301-316, the cleanup after a completed cycle: the music /
    # sound releases and the shape frees have no Thumby equivalent; the
    # meaningful state resets are these:
    secondary = 0                        # :312
    e.scripted = False                   # :314, bScriptedView = 0
    return True

# ============================================================
# the turn and the drawn frame - Update_3Space, house_keep, the eye /
# hazard tail of set_eye, Draw_3Space_Frame, RenderSpaceViewFrame and
# CheckEscaped (main.c:550-680, :2005-2145 and spc.c:158-953, :1026-1067,
# disk.c:435-465 - all re-read in full this session).
# ============================================================

# nCurrentSpaceFrameValue (main.c:576). nRenderedSpaceFrame is the
# hazard section's rendered_space (Draw_3Space_Frame bumps it only on
# drawn frames, main.c:2017, which is what the hazard manage cadence's
# % 20 gate reads, winmain.c).
space_frame = 0
canned_mode = 2          # nCannedSceneMode (game.c:49 declares -1;
                         # title.c:163 sets 2 for the whole intro)
train_sim = 0            # nTrainSimActive: this port has no train sim

skip_counter = 1         # nFrameSkipCounter. init.c:202 keeps nFrameSkip
                         # at 1; title.c:189 arms the counter with 1 at
                         # the start of each cycle (the port's _init_view
                         # does the same), so after the -- below the
                         # counter is 0 and EVERY frame draws.


def _Update3Space():
    """Update_3Space (main.c:555-578), the order verbatim: house_keep
    (:557), house_keep_objects (:558), update_objects_in_space (:564),
    set_eye_direction_and_position (:573), nCurrentSpaceFrameValue++
    (:576). The SWC flight early-return (:559-563) is that build's code
    and the servicetrack (:574) is music - neither is ported.
    update_objects_in_space is world.py's port of spc.c:1026-1067 (both
    loops, re-read this session and unchanged from the transcription):
    loop one animates class > PLANET, collides / rotates class >=
    PROJECTILE, runs object_intelligence for obj != 0 and the missile's
    rotate_object_to_goal and the ship's weapon replenish; loop two
    moves class > PLANET and replenishes shields / fuel for class >=
    SHIP. The canned command interpreter runs inside loop one's
    object_intelligence gate (spc.c:1616-1626): mode 2 with class >=
    SHIP calls update_canned_sequence - the title's canned world.
    house_keep_objects (spc.c:873-953) is fused into world.py's port:
    its update runs house_keep per object (world.py:1169), so the
    dust / debris counter countdowns, the afterburner and super-brake
    timers and the dying-ship shrink happen inside World.update below and
    no separate house_keep call is made."""
    global space_frame
    _house_keep()
    w.update()                   # update_objects_in_space (spc.c:1026)
                                 # is World.update (world.py:1145), the
                                 # instance method of the title world,
                                 # house_keep_objects fused in
    _set_eye()                   # set_eye_direction_and_position, spc.c:158
    if sk is not None:
        sk.turn(e)               # the star / dust field takes the eye's
                                 # new frame - flight.py's sky.turn after
                                 # the world update (:758), here driven
                                 # by the scripted eye
    space_frame += 1             # main.c:576


def _house_keep():
    """house_keep (main.c:633-668), verbatim. The first block is gated
    on nCannedSceneMode == 0 (:637): the intro wears canned mode 2
    (title.c:163), so neither the stale-nav release (:641) nor the
    hazard-field check_hazards (:644-646) ever runs during the title -
    nCurrentHazardFieldTotal is the port's len(fields). The rocks are
    kept alive by update_hazards at spc.c:857 instead, and check_hazards
    is additionally dead while bIntroSecondaryScene == 1 (the winmain
    gate transcribed above). The second half is the cockpit-view palette
    fade (:653-659) and the damage-alarm flush (:661-666): the intro's
    view mode is 15 (spc.c:496 through the script's cmd3 / new_view),
    and this scene has no cockpit, no sound and no damage - both halves
    are dead here, kept only to show the gate."""
    if canned_mode == 0 and train_sim == 0:     # :637-638
        if (space_frame & 0x1f) == 0:
            _release_stale_nav()                # :641 - not reached
        if len(fields) != 0 and (space_frame & 0xf) == 0:
            _check_hazards()                    # :644-646 - not reached
    # the rest reads nCameraViewMode == 0 (the cockpit): palette fades
    # (:653-660) and the alarm flush (:661-666). The intro's mode is 15;
    # no cockpit, no damage, no sound: nothing to do here.


def _release_stale_nav():
    """ReleaseStaleNavTarget - nav targeting is not ported and this call
    is never reached in the title (the mode-2 gate above)."""


def _set_eye():
    """set_eye_direction_and_position (spc.c:158-858). Two parts of it
    belong to this port: the scripted gate at :167-168 and the view the
    intro script's cmd3 / new_view installs - 15 (spc.c:496). Cases
    0..3 (:171-212) copy the player's slot 0 frame / position / velocity
    into the eye object - the cockpit views - and 4 / 5 (:213-272) are
    chase views: none of them exist in this port, the eye is its own
    _Eye object and the hazard chain reads it directly (documented
    deviation). Case 15, transcribed as _eye_turn, is the eye's turn:
    pos += vel, rotate_object with the ClampVectorTo30 decay, then
    rotate_eye_to_goal (spc.c:458-463 read with the earlier batch). The
    procedural dust of :821-852 - start_dust around the eye's view
    motion - is sky.py's dust field in this port (documented deviation),
    and the hazard tail at :856-857 runs last: with an active hazard
    field, update_hazards (winmain.c:435)."""
    if e.scripted:
        _update_scripted_view(e)            # spc.c:167-168
    _eye_turn(e)                            # case 15 (spc.c:458-463)
    if field is not None:                   # pActiveHazardField != 0
        _update_hazards()                   # spc.c:857 -> winmain.c:435


def _draw_pipeline():
    """The draw pipeline of Draw_3Space_Frame (main.c:2018-2033):
    transform_objects_to_your_view (:2018), draw_stars (:2019),
    draw_exhaust (:2020), the fixed child objects (the turret / wing
    children of capital ships, :2024), the depth sort (:2025) and
    draw_sorted_objects_to_buffer (:2033). This is flight.py's renderer
    port run in the title's space: bk is 0, the eye is e and the picture
    is the whole 128x112 device screen (cx 64, cy 56). The verbatim
    screenX marker gates of geom.c:1234-1325 run first in device space,
    painting the _mk / _dt parallel lists that the explode-on-entry gate
    and the hazard spawn consult.

    Documented deviations: the FUTURION / dust cloud / constellation /
    nav pointer special cases of the transform loop are dead here (those
    object classes never exist in the intro); draw_exhaust's engine
    plumes are not ported (the intro ships fly past in silhouette -
    docs/08); the geom.c scale-cull gate (screenScale <= 4 -> 0x8001) is
    replaced by flight.py's tiny gate, which paints a single point
    pixel instead of culling, so distant ships survive as specks like
    the original does; no capital ships fly in the intro, so the fixed
    children walk finds nothing."""
    fb = display.buffer
    G.fill_rows(fb, 0, 112, 0)            # ClearViewport(cBlackColour)
    ex = e.x; ey = e.y; ez = e.z         # bk is 0, so the eye is the
    em = e.m                             # camera position (eye.bk == 0)
    sk.draw(fb, display, em, ex, ey, ez, e, True)   # draw_stars (:2019)
    sk.draw(fb, display, em, ex, ey, ez, e, False)  # the dust pass
    o = w.o
    mk = _mk
    dt = _dt
    radius = e.radius
    for obj in range(W.NOBJ):
        ob = o[obj]
        if ob.cls == W.C_NULL:           # geom.c:1240-1241
            mk[obj] = 0
            dt[obj] = 0
            continue
        dx = (ob.x - ex) >> 8            # :1244, 24.8 -> world units
        dy = (ob.y - ey) >> 8
        dz = (ob.z - ez) >> 8
        dist = M.mag(dx, dy, dz)         # :1245
        if dist < radius:                # nearer than the eye :1246
            mk[obj] = 0x8001
            dt[obj] = 0
            continue
        vx, vy, vz = M.to_frame(em, dx, dy, dz)   # :1253
        if vz < radius:                  # behind the eye :1256-1257
            mk[obj] = 0x8001
            dt[obj] = 0
            continue
        if vz * 256 < dist * 0x94:       # outside the view cone
            mk[obj] = 0x8001             # :1260-1262 verbatim
            dt[obj] = 0
            continue
        rad = ob.radius
        if dist <= rad:                  # :1264-1266
            dist = rad + 1
        mk[obj] = _CX + FX * vx // vz    # screenX, :1270-1273; the
        dt[obj] = dist                   # cone gate left vz >= radius
    for i in range(len(_sil)):
        _sil[i] = None                   # the silhouette record is
                                         # rebuilt every drawn picture
    order = _ORDER
    del order[:]                         # the depth sort list
    for obj in range(W.NOBJ):
        d = dt[obj]
        if d != 0:                       # 0 == culled / NULL
            order.append((d, obj))
    order.sort(reverse=True)             # draw_sorted_objects_to_buffer
                                         # walks farthest first (:2033)
    for d, obj in order:
        _draw_object(fb, o[obj])
    return True


def _Draw3Space():
    """Draw_3Space_Frame (main.c:2010-2037), verbatim order. The damage
    palette fade (:2012) is dead in the title - no damage, no palette
    flash. The frame-skip gate at :2013-2016: nFrameSkip is 1
    (init.c:202), so the counter reads 0 after the decrement and every
    call draws. nRenderedSpaceFrame++ (:2017) counts drawn frames only -
    the hazard manage cadence's % 20 gate reads it. The transform /
    stars / exhaust / child reposition / sort and the buffer draw
    (:2018-2033) are _draw_pipeline; the head-up display (:2034-2035)
    exists only in the cockpit view mode 0, never here. The SDL
    snapshot / BeginSpaceFrame calls are that build's plumbing."""
    global rendered_space, skip_counter
    skip_counter -= 1                 # :2013
    if skip_counter > 0:              # :2014-2015
        return False
    skip_counter = 1                  # :2016, = nFrameSkip (init.c:202)
    rendered_space += 1               # :2017
    _draw_pipeline()                  # :2018-2033 (forward ref)
    return True                       # :2036


def _RenderView():
    """RenderSpaceViewFrame (main.c:2101-2133), verbatim in structure.
    A frame skipped by the draw gate returns without touching the screen
    (:2103-2104). check_message (:2105) is the message queue - the intro
    has none; UpdateArcadeScoreDisplay (:2106) and the trainsim score
    panel (:2111-2130) belong to the arcade build, gated on
    nTrainSimActive which is never set here. dump_buffer_to_screen
    (:2108) copies the space buffer to the screen view - on the port's
    single buffer the phase loop's display.update is the DIBslam of the
    original loop, and the copy is the no-op. The final ClearViewport
    (:2131) is redundant for the port: _draw_pipeline repaints the whole
    background every frame. Returns whether the frame drew."""
    if not _Draw3Space():
        return False                  # :2103-2104
    return True                       # :2132


def _escaped():
    """CheckEscaped (disk.c:442-464), ported. The original returns the
    queued event's value + 1 for ANY queued key-down, button-down or
    legacy-activate event - any key or button ends the cinematic, not
    only Escape (:449-457) - and flushes every event (:461-462). On
    Thumby the buttons stand in for the keyboard: any button held is
    the level state the bEscapePressedFlag carries (:22 in mathfp.c),
    set until cleared, so once it fires the later checks keep seeing it
    exactly as the original's do; ui.wait_release before the menu is the
    flush."""
    return (buttonA.pressed() or buttonB.pressed() or buttonU.pressed()
            or buttonD.pressed() or buttonMENU.pressed())

# --- geometry helpers (geom.c / eventmgr.c / logic.c / cockpt.c / ship.c) --
# Every helper below was transcribed from a fresh read of the original in
# this build session; the citations are the exact source lines.

def _tdiv(a, b):
    """C integer division: truncates toward zero. Python's // floors,
    which differs for negative operands (same reasoning as flight.py:71)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _saturate(v):
    """FixedToShortSaturating (geom.c:213-220), verbatim."""
    if v < -0x7fff00:
        return -0x7fff
    if v > 0x7fff00:
        return 0x7fff
    return v >> 8


# shrink (eventmgr.c:1366-1385): value = *component / 2, a C division that
# truncates toward zero; the 32-bit unsigned fraction tests reproduce the
# original's (unsigned) casts on a Python int.
def _shrink(c):
    v = _tdiv(c[0], 2)                 # value = *component / 2
    c[0] = v
    u = v & 0xFFFFFFFF                 # the original's (unsigned) fraction
    ip = u >> 16                       # the original's (unsigned) >> 16
    sip = ip - 0x10000 if ip & 0x8000 else ip
    if sip == 0:
        return (u & 0xFFFF) > 0x0f00
    if sip == -1:
        return (u & 0xFFFF) < 0xf100
    if sip != 0:                       # eventmgr.c:1381-1382
        ip = 1
    return ip


def _shrink_vector(d):
    """shrink_vector (eventmgr.c:1353-1363): halve every component until
    none of them shrinks any more. The return value is unused by
    point_at, so the port returns nothing. C hands the components to
    shrink as int*; the port's stand-in is the one-element list
    _shrink expects, so the components are boxed here and written back
    into d when the loop settles."""
    c = [[d[0]], [d[1]], [d[2]]]
    while _shrink(c[0]) | _shrink(c[1]) | _shrink(c[2]):
        pass
    d[0] = c[0][0]
    d[1] = c[1][0]
    d[2] = c[2][0]


def _point_at(o, tx, ty, tz):
    """point_at (geom.c:168-179): the delta to the target point, shrunk,
    written into the forward row, then fix_objects_ijk - M.fix."""
    d = [o.x - tx, o.y - ty, o.z - tz]     # ComputeVectorDelta
    _shrink_vector(d)                      # geom.c:172
    m = o.m
    m[6] = d[0]                            # aShipFwdVec[obj] = direction
    m[7] = d[1]
    m[8] = d[2]
    M.fix(m)                               # fix_objects_ijk (geom.c:178)


def _rel_ijk(spot, x, y, z, m, forward):
    """position_relative_ijk (geom.c:203-210) with right and up zero and
    the whole distance along the forward row: position_relative
    (geom.c:188-200) normalizes the row (the port's rows are already
    unit, length 16384), scales it by distance << 8 and adds - for a
    unit row that is exactly (m[i] * (forward << 8)) >> 14. The result is
    written into the caller's spot list."""
    spot[0] = x
    spot[1] = y
    spot[2] = z
    for i in range(3):
        spot[i] += (m[6 + i] * (forward << 8)) >> 14


def _distance(x1, y1, z1, x2, y2, z2):
    """distance_between_points (geom.c:675-684): the delta, its
    magnitude and the short saturation. Vector_magnitude (mathfp.c:132)
    returns sqrt of the squared 24.8 components as a truncated integer,
    which is what M.mag computes; _saturate reproduces the fixed clamp."""
    n = M.mag(x2 - x1, y2 - y1, z2 - z1)
    return _saturate(n)


def _is_within(x1, y1, z1, x2, y2, z2, rng):
    """IsPointWithinRange (geom.c:949-955) is the IsVectorWithinRange of
    eventmgr.c:1343-1350: abs(range << 8) >= Vector_magnitude(delta)."""
    return abs(rng << 8) >= M.mag(x2 - x1, y2 - y1, z2 - z1)


def _real_velocity(o):
    """real_velocity (ship.c:462-466): FixedToShortSaturating of
    Vector_magnitude(&vel[obj])."""
    return _saturate(M.mag(o.vx, o.vy, o.vz))


def _kilrathi_near(obj, rng):
    """kilrathi_near (cockpt.c:621-634): a Kilrathi ship of class at
    least SHIP within the range of the point, scanning ships 0..9."""
    for ship in range(W.NSHIP):
        t = w.o[ship]
        if (t.cls >= W.C_SHIP and t.side == W.SIDE_KILRATHI
                and _is_within(t.x, t.y, t.z, obj.x, obj.y, obj.z, rng)):
            return 1
    return 0


def _signed_random(r):
    """signed_random (logic.c:164-167): RandomBelowOrEqual(r * 2) - r;
    RandomBelowOrEqual is rndle (mathfp.c:59-64, world.py:98)."""
    return W.rndle(r * 2) - r


def _find_ratio(a0, a1, v, b0, b1):
    """find_ratio (logic.c:1390-1401), verbatim: the clamped input is
    interpolated between the two anchor pairs with C's truncating
    division."""
    if v < a0:
        v = a0
    elif v > a1:
        v = a1
    return _tdiv((b1 - b0) * (v - a0), a1 - a0) + b0


def _rotate_about_i(m, deg):
    """rotate_about_i (geom.c:540-557) on the j / k pair of rows:
    j' = j * c - k * s, k' = j_old * s + k * c. wcmath._rot (a' = a * c
    - b * s, b' = a * s + b * c, read above) applied to the up / forward
    rows is the identical rotation, so this is M.pitch. The port keeps
    frames at 14-bit unit length where the original kept them 24.8 with
    0x4000 as unit and 8-bit trigonometry; M._rot's >> 14 shift matches
    MultiplyFixed's >> 8 at those scales term by term."""
    M.pitch(m, deg)


def _rotate_about_j(m, deg):
    """rotate_about_j (geom.c:560-577) on the i / k pair: i' = k * s +
    i * c, k' = k * c - i_old * s. With a = forward and b = right this
    gives a' = f * c - r * s and b' = f * s + r * c - wcmath.M.yaw
    (_rot(m, F, R)) again. See _rotate_about_i for the scale comment."""
    M.yaw(m, deg)


def _find_vacant():
    """find_vacant_3d_object (geom.c:1028-1040): scan the moving-object
    slots for a NULL class, mark it, return it. Deviation: the original
    scanned 10..60; the port's pool ends at NOBJ = 44."""
    i = W.NSHIP
    while i < W.NOBJ:
        if w.o[i].cls == W.C_NULL:
            _mk[i] = 0x8001                # geom.c:1031
            return i
        i += 1
    return -1


def _fire_fixed(w, o):
    """fire_fixed_projectile_weapon (ship.c:2155-2168): for every weapon
    slot of an enabled, PROJECTILE-class weapon call fire_weapon(obj,
    slot); the first failure returns -1 and stops. The port's weapon
    slots are the [type, hardpoint, disabled] lists wcdata.Types.weapons
    returns (wcdata.py:96-105); the class comes from the same object
    table; fire_weapon's None is ship.c's -1."""
    T = w.T.f
    for slot, wp in enumerate(o.weapons):   # ship.c's *slot walk, :2158
        wt = wp[0]
        if T[D.T_CLASS][wt] == W.C_PROJECTILE and not wp[2]:
            if w.fire_weapon(o, slot) is None:
                return -1
    return 0


# ============================================================
# The renderer pass, the title world and the entry point.
#
# flight.py's drawing port runs in the title's space: the viewport is the
# whole 128 x 112 device screen (the original's 320 x 200), the eye is the
# scripted camera and bk is 0 - one turn per picture, so the world state
# drawn is the state the turn just made (flight.py's between-turns step
# back has no counterpart in a scripted intro).
# ============================================================

# flight.py:49-53: the focal lengths and the greys of distant point pixels
FX = 64                  # focal length in pixels, horizontal
FY = 77                  # vertical (the original's 1:1.2 pixels)
WHITE = 0xFFFF
GREY = 0x8410

_CX = 64                 # the title view's centre column ((0 + 128) >> 1)
_P = [0] * 12            # one blit parameter list (wcgfx.blit_rs)
_sil = [None] * 64       # the full blits of the last drawn picture,
                         # replayed as silhouettes after the subtitle
_SIL_PAL = bytearray(512)    # all-zero palette: a drawn pixel reads black
_ORDER = []              # draw_sorted_objects_to_buffer's depth list
_sets = {}               # flight.py's self.sets: name -> SpriteSet / 0
_ship_names = {}         # flight.py's self.ship_names: typ -> set name
_dirv = None             # the 62 canonical direction frames (init.c)
_CANNS = {}              # world slot -> the object's _Canned interpreter
_CACHE = None            # the flight frame cache the menu hands down
_T = None                # the Types table the menu hands down
_AI = None               # the pilot tables read at start-up, which
                         # the title world rides (docs/12 12.2)
_LOGO_SET = None         # pTitleShape: packet 9 frame 0 (title.c:185-186)
_GEO = None              # ti0geo.wc: the logo's geometry words per frame
sk = None                # the star / dust field, made by _init_view
w = None                 # the title's world, made by _title_world
e = None                 # the scripted eye, made by _init_view

_BOLT_SET = {24: 'fx06.wcs', 25: 'fx08.wcs', 26: 'fx07.wcs',
             27: 'fx06.wcs'}     # flight.py:62-63, numeric weapon types
_EXPL_SET = ('fx01.wcs', 'fx02.wcs', 'fx03.wcs', 'fx09.wcs')


def _cvpy():
    """nCurrentViewCenterPosY in the title's view: the middle row of the
    112-row device screen. Device 56 maps to the original's view centre
    100 exactly (56 * 25 / 14 == 100)."""
    return 56


def _xform_bounds(ss, frame, scale, x, y):
    """GetTransformedShapeBounds (gr.c:1311-1402), run in the original's
    pixel space: the device anchors are mapped back into the 320 x 200
    space the arithmetic belongs to (x * 5 / 2, y * 25 / 14) and the edges
    are mapped back out. The angle is 0, so the cosine is the scale itself
    (trig[0][0] * scale >> 8) and the sine is 0 raised to 1 by gr.c's own
    guard; the low byte test of :1368 / :1372 ((char)v != 0) is the
    v & 0xFF below. Deviations: the inside flag of :1389-1398 is not
    ported - title.c:86-112 draws the three logo frames at the bounds'
    left edge, the view centre and bounds' right edge whichever way the
    test falls - and the top / bottom edges are dropped for the same
    reason. The frame bounds test of :1350 guards a geometry table
    shorter than the frame index."""
    if frame * 8 + 8 > len(_GEO):
        return (x, x)
    right, left, top, bottom = unpack_from('<4h', _GEO, frame * 8)
    fr = left                          # gr.c:1353-1354 swap the extents
    fl = right
    ft = top
    fbt = bottom
    cosine = scale
    sine = 1
    if cosine == 0:                    # gr.c:1361-1364
        cosine += 1
    if sine == 0:
        sine += 1
    xo = x * 5 // 2
    yo = y * 25 // 14
    extentX = fl + fr                  # :1365
    extentY = fbt + ft                 # :1366
    v = sine * extentX + cosine * extentY     # :1367
    if v & 0xFF:                       # :1368-1369
        v += 0x100
    th = v >> 8                        # :1370, arithmetic (flooring)
    v = sine * extentY + cosine * extentX     # :1371
    if v & 0xFF:                       # :1372-1373
        v += 0x100
    tw = v >> 8                        # :1374
    if cosine == 0:                    # :1375-1378, dead here but
        cosine = 1                     # kept verbatim
    if sine == 0:
        sine = 1
    leftEdge = ((sine * ft) >> 8) + xo - ((cosine * fr) >> 8)   # :1379
    extentY = (sine * extentY) >> 8    # :1383-1384
    extentY += 1                       # :1385
    left = leftEdge - extentY          # :1386-1387
    right = left + tw                  # :1388
    return (_tdiv(left * 2, 5), _tdiv(right * 2, 5))   # back to device


def _draw_scaled(fb, ss, frame, scale, x, y):
    """DrawSpriteScaled (gr.c:766) as DrawTitleLogo calls it (title.c:95-
    112): the frame lands with its hot spot on the device anchor (x, y)
    and scales with the 8.8 zoom value - a source step of one source pixel
    per scale/256 screen pixels. The angle is 0 and the flip 0, so the
    inverse matrix is the identity scaled by the step; the size cap is
    flight.py's :333-335. The blit's 16.16 scale is the 8.8 value << 8."""
    slot = _CACHE.get(ss, frame)
    if slot < 0:
        return
    cache = _CACHE
    res = cache.res[slot]
    s16 = scale << 8
    cap = (32 * 64 << 16) // res
    if s16 > cap:
        s16 = cap
    cw = cache.w[slot]
    ch = cache.h[slot]
    hx = cache.hx[slot]
    hy = cache.hy[slot]
    rad = ((M.mag(max(hx, cw - hx), max(hy, ch - hy), 0) * s16) >> 16) + 2
    x0 = max(0, x - rad)
    x1 = min(128, x + rad + 1)
    y0 = max(0, y - rad)
    y1 = min(112, y + rad + 1)
    if x0 >= x1 or y0 >= y1:
        return
    inv = (1 << 24) // (s16 >> 8)      # flight.py:356
    p = _P
    p[0] = x; p[1] = y
    p[2] = (hx << 16) + 0x8000; p[3] = (hy << 16) + 0x8000
    p[4] = inv; p[5] = 0; p[6] = 0; p[7] = inv
    p[8] = x0; p[9] = y0; p[10] = x1; p[11] = y1
    G.blit_rs(fb, ui.pal, cache.buf[slot], cw, ch, p)


def _ship_set_name(typ):
    """flight.py:176-181."""
    n = _ship_names.get(typ)
    if n is None:
        n = 'sh%02d.wcs' % typ
        _ship_names[typ] = n
    return n


def _sset(name):
    """flight.py:183-191, plain: the first load of a name reads its
    table from the heap. The sets dict and everything in it are given
    back when the title module is popped."""
    s = _sets.get(name)
    if s is None:
        if D.exists(name):
            s = D.SpriteSet(name)
        else:
            s = 0
        _sets[name] = s
    return s


def _right_shape(ob, dx, dy, dz, em, table):
    """flight.py:194-230 verbatim: get_right_shape -> (frame, flip,
    clockwise angle)."""
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
    eux, euy, euz = M.to_frame(ob.m, em[3], em[4], em[5])
    dv = _dirv
    b = idx * 6
    px = eux * dv[b] + euy * dv[b + 1] + euz * dv[b + 2]
    py = eux * dv[b + 3] + euy * dv[b + 4] + euz * dv[b + 5]
    ang = M.angle_cw(px >> 8, py >> 8)
    T = _T
    frame = T.dir_frame[idx + table * 62]
    if frame == 0:
        ang -= 90
    elif frame == 36 and table != 1:
        ang += 90
    return frame, T.dir_flip[idx + table * 62], ang % 360


def _draw_object(fb, ob):
    """flight.py:262-375 in the title's space. bk is 0, so the eye is the
    camera and the backward step vanishes (dx / dy / dz are ob - e
    directly); the viewport is the whole screen. With the marker pass
    already having decided which objects reach the picture, flight's own
    gates survive as redundant safety, exactly as they do in flight. A
    full blit in phase A records its parameters for the silhouette
    replay (intro_drawbackgroundships, eventmgr.c:1089)."""
    ob.vis = False
    em = e.m
    dx = (ob.x - e.x) >> 8
    dy = (ob.y - e.y) >> 8
    dz = (ob.z - e.z) >> 8
    if dx > 40000 or dx < -40000 or dz > 40000 or dz < -40000:
        return
    vx, vy, vz = M.to_frame(em, dx, dy, dz)
    if vz < 60:
        return
    dist = M.mag(dx, dy, dz)
    if vz * 256 < dist * 0x94 and ob.radius * 3 < dist:
        return
    sx = _CX + FX * vx // vz
    sy = _cvpy() - FY * vy // vz
    ob.sx = sx
    ob.sy = sy
    ob.dist = dist
    c = ob.cls
    typ = ob.typ
    frame = 0
    flip = 0
    ang = 0
    if c >= W.C_SHIP:
        name = _ship_set_name(typ)
        frame, flip, ang = _right_shape(
            ob, dx, dy, dz, em, 2 if typ == 21 else 0)
    elif c == W.C_MISSILE:
        name = 'ms.wcs'
        frame, flip, ang = _right_shape(ob, dx, dy, dz, em, 1)
    elif c == W.C_PROJECTILE:
        name = _BOLT_SET.get(typ, 'fx06.wcs')
    elif c == W.C_EXPLOSION:
        name = _EXPL_SET[min(3, typ - W.OT_EXPLOSION0)]
        frame = ob.counter >> 1
    elif c == W.C_ASTEROID:
        name = 'fx16.wcs' if typ & 1 == 0 else 'fx17.wcs'
        frame = ((w.tick >> 1) + ob.counter) % 13
    elif c == W.C_MINE:
        name = 'fx15.wcs'
        frame = (w.tick >> 2) % 3
    else:
        return
    mg = 100 + FX * ob.radius // vz
    if sx < 0 - mg or sx > 128 + mg or sy < 0 - mg or sy > 112 + mg:
        return
    ob.vis = 0 <= sx < 128 and 0 <= sy < 112
    dd = dist - ob.radius
    if dd < 1:
        dd = 1
    sset = _sset(name)
    slot = -1
    if sset:
        slot = _CACHE.get(sset, frame)
    if slot < 0:
        if ob.vis:
            display.setPixel(sx, sy, GREY)
        return
    cache = _CACHE
    res = cache.res[slot]
    s16 = ((ob.scale * 40 << 8) // (dd * res)) << 8
    cap = (32 * 64 << 16) // res
    if s16 > cap:
        s16 = cap
    cw = cache.w[slot]
    ch = cache.h[slot]
    hx = cache.hx[slot]
    hy = cache.hy[slot]
    if (max(cw, ch) * s16) >> 16 < 2 or s16 < 2048:
        if ob.vis:
            col = WHITE if c == W.C_PROJECTILE or c == W.C_EXPLOSION \
                else GREY
            display.setPixel(sx, sy, col)
        return
    ex = max(hx, cw - hx)
    ey = max(hy, ch - hy)
    rad = ((M.mag(ex, ey, 0) * s16) >> 16) + 2
    x0 = max(0, sx - rad)
    x1 = min(128, sx + rad + 1)
    y0 = max(0, sy - rad)
    y1 = min(112, sy + rad + 1)
    if x0 >= x1 or y0 >= y1:
        return
    inv = (1 << 24) // (s16 >> 8)
    cs = M.icos(ang)
    sn = M.isin(ang)
    a = ((inv >> 6) * cs) >> 8
    b = ((inv >> 6) * sn) >> 8
    if flip & 1:
        ua = -a; ub = -b
    else:
        ua = a; ub = b
    if flip & 2:
        va = b; vb = -a
    else:
        va = -b; vb = a
    p = _P
    p[0] = sx; p[1] = sy
    p[2] = (hx << 16) + 0x8000; p[3] = (hy << 16) + 0x8000
    p[4] = ua; p[5] = ub; p[6] = va; p[7] = vb
    p[8] = x0; p[9] = y0; p[10] = x1; p[11] = y1
    G.blit_rs(fb, ui.pal, cache.buf[slot], cw, ch, p)
    ob.rad = rad
    if stage == 'A':
        # the solid replay's parameters: the same frame, the same place,
        # the same matrix - only the palette changes (eventmgr.c:1104
        # draws the shape in one solid colour; on the port's zeroed
        # palette every drawn pixel reads black, the original's black)
        _sil[ob.i] = (sset, frame, sx, sy, p[2], p[3], ua, ub, va, vb,
                      x0, y0, x1, y1)


# --- the title mission and the canned brains ------------------------------

class _TitleMission:
    """game.c's title data in world.py's mission shape (game.c:199-290):
    no player, no wing, no objectives. Every nav point sits at the origin
    with radius 50000 and four {0, 0} trigger words stored, not -1 - so
    the port's trigger loop writes nav_type[0] = 0, harmlessly, as the
    original's own trigger walk does."""

    NONE_REC = (-1, 0, -1, -1, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, -1, 0,
                0, 0, 0, -1, -1, 0)     # type < 0: init_ship refuses

    def __init__(self):
        self.player_ship = -1
        self.entry_nav = -1
        self.home_ship = -1
        self.initial = ()
        self.objectives = []             # track_objectives walks nothing
        self.ship_state = [0] * 46       # aMissionShips' states
        self.ship_nav = {}
        self.nav_type = {n: 0 for n in range(20)}
        for n in (16, 17, 18, 19):
            self.nav_type[n] = 1         # game.c:201, type 1

    def ship(self, ms):
        return RECORDS.get(ms, self.NONE_REC)

    def nav_pos(self, nav):
        return (0, 0, 0)                 # game.c:204, aPosition

    def nav_radius(self, nav):
        return 50000                     # game.c:202

    def nav_ships(self, nav):
        return NAV_SHIPS.get(nav, ())    # -1 terminated lists

    def nav_triggers(self, nav):
        # game.c:207-210: eight trigger words, all {0, 0} pairs
        return (0, 0, 0, 0, 0, 0, 0, 0)


class _Camp:
    """campaign.State's bare minimum for world.py: the death table
    is_alive reads. Title pilots are all 0, so nothing reads it."""

    def __init__(self):
        self.death = [0] * 8


class _TitleBrain:
    """world.py's brain slot: a ship's think() is its canned sequence's
    update_canned_sequence (mono.c:286), which is all the intro pilots
    ever do."""

    def __init__(self, w):
        self.w = w

    def think(self, ob):
        c = _CANNS.get(ob.i)
        if c is not None:
            c.update(self.w, ob, e)


class _TitleWorld(W.World):
    """The world of the intro. hazard_turn is silenced: world.py recycles
    rocks around its player (world.py:1508), but the intro's rocks are the
    winmain.c chain's - _make_hazard / _manage_hazard - and leaving both
    alive would spawn each rock twice (documented deviation)."""

    def hazard_turn(self):
        pass


def _title_world():
    """The port's init_3Space_objects(0) (title.c:162): a world whose
    pilots run canned sequences. Deviation from title.c:178-180: the
    original clears a live world's ship states between title cycles; the
    port builds a new world, which achieves the same. The _mk / _dt marker
    lists survive the rebuild like the original's screenX and distance
    arrays survive the reset. flight.py:101-117's direction frames
    (initialize_direction_view_frames, init.c) are built once here."""
    global w, _T, _CACHE, _dirv
    if _dirv is None:
        d = array('h', [0] * (62 * 6))
        tmp = [0] * 9
        for idx in range(62):
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
                d[idx * 6 + k] = min(32767, tmp[k])
        _dirv = d
    _mem('preworld')
    # The world rides the pilot tables read at start-up: parsing a
    # second copy of ai.wc here was some of the room the floor
    # build's title lost. Without one - the PC harness, say - the
    # fresh parse stands instead.
    w = _TitleWorld(
        _T, _AI if _AI is not None else D.Ai(),
        _TitleMission(), _Camp())
    w.brain = _TitleBrain(w)
    _CACHE.reset()


def _set_up_action_sphere(nav):
    """set_up_action_sphere (mission.c:560-624) with the title's mission
    data, plus the spawn point init_intelligence_data's canned case adds
    (mission.c:1004-1015): every intro ship gets its interpreter and one
    advance right away - mono.c's command counter starts at 0 and would
    count 0 forever otherwise (advance_canned_sequence, :1014). The
    screenX gate of :595-596 is the port's _mk list: the original's
    -0x7fff marker is 0x8001 in 16-bit, so a ship the last drawn picture
    saw goes down in flight on the sphere entry - title.c:248's on-screen
    fleet - and an unseen ship is only removed. The wave gate of
    :578-579 reads the next nav point's type; every title point is type 1,
    so the wave is -1 just as world.py:584 gives it past nav 15."""
    mis = w.mis
    o = w.o
    w.nav = nav                          # :576
    w.wave = 2 if nav + 1 < 16 and mis.nav_type[nav + 1] == 2 else -1
    for i in range(1, W.NSHIP):          # :582-600
        ob = o[i]
        if ob.cls != W.C_NULL and ob.nav != -1:
            if ob.cls >= W.C_SHIP and ob.mtype == W.MT_ROUT:
                mis.ship_state[ob.mship] = 3     # :586-590
            if _mk[i] != 0x8001:
                w.explode(-1, i)                 # :595-596
            else:
                w.remove(ob)                     # :598
    for i in range(W.NSHIP, W.NOBJ):
        if o[i].cls in (W.C_ASTEROID, W.C_MINE):
            w.remove(o[i])
    _remove_all_hazards()                # :601
    w.hazards = []                       # :602's count, as a cleared list
    for ms in mis.nav_ships(nav):        # :605-608
        if ms != -1:
            ob = w.init_ship(ms, nav)
            if ob is not None:
                seq = SEQS.get(ms)
                if seq is not None:      # init_intelligence_data, :1004
                    cns = _Canned(seq)   # apCannedSequenceList[obj], :1011
                    _CANNS[ob.i] = cns
                    cns.advance(w, ob, e)        # advance, mission.c:1014
    trig = mis.nav_triggers(nav)         # :613-620
    for k in range(0, 8, 2):
        if trig[k] != -1 and 0 <= trig[k + 1] < 16:
            mis.nav_type[trig[k + 1]] = trig[k] & 0xFF
    w.landing_ok = False
    for i in range(1, W.NSHIP):          # leaders that followed wingmen
        ob = o[i]
        if ob.cls >= W.C_SHIP and ob.leader < 0:
            ob.leader = w.find_ship(mis.ship(ob.mship)[19])
    # mirror the spawned fields onto the winmain chain's list; the hazard
    # record's centre is in world units, the fields want 24.8 (the
    # _is_within comparison left shifts its radius and reads 24.8 deltas)
    for h in w.hazards:
        _add_hazard_field(h[4], (h[0] << 8, h[1] << 8, h[2] << 8), h[3])


def _init_view():
    """initialize_scripted_view (view.c:198-206) for the camera script of
    game.c:110-113: the eye is built and the script parsed - its cmd2 and
    cmd3 store the eye's view 15 and force the collision radius to 10
    (new_view, spc.c:497-501) - and the star / dust field of sky.py is
    attached to the full screen view, flight.py:121-123. The hazard chain
    reads p.view of the player mirror (winmain.c:212 / :356): p is the
    world's slot 0, driven by _match_ship_to_eye, so the eye's view is
    copied onto it here - the original's player object carries its view
    the whole flight."""
    global e, sk
    e = _Eye()
    _parse_view_script(e)
    sk = sky.Sky(e, FX, FY, (0, 0, 128, 112, _CX, _cvpy()))
    w.o[0].view = e.view


def _load_intro_font():
    """pIntroFont = FetchDiskPacketRetrying(9, 1) (title.c:164-165): the
    picture font and its width table."""
    return (_ttl_set('ti1.wcs'), _ttl_read('ti1wd.wc'))


def _load_logo():
    """pTitleShape = FetchDiskPacketRetrying(9, 0) (title.c:185-186) with
    its geometry words, the converter's ti0geo.wc copy of the stored frame
    extents."""
    global _LOGO_SET, _GEO
    _LOGO_SET = _ttl_set('ti0.wcs')
    _GEO = _ttl_read('ti0geo.wc')


def _intro_drawbackgroundships(fb):
    """intro_drawbackgroundships (eventmgr.c:1089-1112): every object with
    a shape is drawn again as one solid colour sprite at the place and
    scale it was just drawn, over the subtitle, so the intro fleet reads
    as black silhouettes while the stars keep their colour. The port
    replays the last picture's full blits through the all-zero palette -
    index 0 stays transparent, drawn pixels read black - and leaves the
    point pixel objects alone, as the original's solid draw of a pixel
    would be invisible anyway."""
    cache = _CACHE
    for rec in _sil:
        if rec is None:
            continue
        slot = cache.get(rec[0], rec[1])   # the LRU keeps the same slot
        if slot < 0:
            continue
        G.blit_rs(fb, _SIL_PAL, cache.buf[slot], cache.w[slot],
                  cache.h[slot], rec[2:])


def title(has_save, T, cache, txt, ai=None):
    """Title_Sequence (title.c:135) for MainGame. Returns the menu's
    selection (0 start, 1 continue) or -1 if B / MENU quit, and None when
    the title art is missing so MainGame can show its static picture
    instead. The asset names are the converter's outputs: ti0 the logo,
    ti0geo its bounds, ti1 the font, ti1wd its widths, ti4 the menu."""
    global _T, _CACHE, _AI, hold, _TXT
    if not (D.exists('ti0.wcs') and D.exists('ti0geo.wc') and
            D.exists('ti1.wcs') and D.exists('ti1wd.wc') and
            D.exists('ti4.wcs')):
        return None
    _T = T
    _CACHE = cache
    # the pilot tables MainGame read at start-up; without one the
    # world builds them again in _title_world (docs/12 12.2)
    _AI = ai
    # The canvas arrives with MainGame, its boot allocation. The lazy
    # path only matters when titleseq runs without one (the PC harness
    # never does); a heap too fragmented for a single 14 KB block
    # skips the text then instead of raising.
    _TXT = txt
    if _TXT is None:
        try:
            _TXT = bytearray(128 * 112)
        except MemoryError:
            _TXT = False
    hold = True                        # the harness holds the pilot out
                                       # while the cinematic pumps
                                       # display.update, which runs an
                                       # engine tick (color.py:205-209);
                                       # _menu returns it to False when
                                       # the menu needs the pilot.
    # The engine tick is the push rate here: every wait loop calls
    # display.update, and each call spins to the next tick and blits
    # the buffer again (color.py:204-211). The panel scans that buffer
    # by DMA while the blit rewrites it, and the race between the two
    # is the flicker the device reported on the title. The cinematic
    # paints one picture per game turn (S.STEP_MS, 10 a second), so
    # the tick is set to the turn's own rate for the sequence: a still
    # picture is pushed once, not twice extra per turn as at the 20 Hz
    # it came in with, and the period is a whole number of ms as
    # flight.py:44-47 requires. The menu keeps its 20 Hz - its button
    # loop would read a press up to 100 ms late at 10.
    display.setFPS(10)
    fb = display.buffer
    _cinematic(fb)                       # False when the player skips;
    display.setFPS(20)
    # the menu is reached either way, title.c:301-319
    return _menu(_ttl_set('ti4.wcs'), has_save)
