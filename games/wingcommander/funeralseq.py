# funeralseq.py - the funeral (docs/06 6.2): the honour guard at the
# casket, the commands, the three volleys and the long descent into
# the grave, played when the player dies (gameflow.c:407) or when a
# wingman did not come back (:469).
#
# Verbatim ports of (wc1-re, GPL-3.0):
#   funeral_sequence    src/cutscene.c:1103  (0x408C50)
#   funeral_player      src/cutscene.c:998   (0x4089A0)
#   funeral_wingman     src/cutscene.c:1069  (0x4089E0)
#   InitializeConstellationField src/view.c:279
#   DrawConstellationField       src/view.c:330
# on the sprite sets tool/wc1_convert.py writes from BRIEFING.VGA
# section 9 (fun.wcs) and PLANETS.VGA section 0 (con.wcs).
#
# The scene draws into the conversation picture, device rows 16..77
# (scramble.py's mapping: original pixel (x, y) -> _cx / _cy). The
# conversation is talk.py with scene type 3; its shot 17 records
# animate this scene through shot17 below, exactly as the original's
# SceneDirector dispatches previousShot 17 to funeral_wingman
# (screens.c:1443-1445). Positions, velocities and sizes stay in
# original-pixel units and are mapped only at the draw site.
#
# Not ported, on purpose:
#  - the music (track 0x20, :1106-1108) and the sound effects 0x24
#    "Atten-SHUN!", 0x1f loading, 0x1e the first volley, 0x1d the
#    shots: the PC original has no sampled effects to convert;
#  - the descent's music gate (:1368-1377): without music the
#    playback mode is always 0, so the original's own fallback - the
#    break at frame > 160 (:1364-1366) - is what runs;
#  - pIntroFont (TITLE.VGA section 1, fetched at :1125): the port has
#    no font sprites, so "THE END" uses the text font at row 43,
#    centred, where print_subtitle places one line at y=56 (mono.c:219-222).
#
# The star field's picks are os.urandom draws, not the original's
# rand(): the field never repeats between viewings, as in the DOS game.

import scramble as S
import talk
from time import ticks_ms, ticks_diff
from thumby_engine.platform import display
import ui
import wcdata as D
import wcgfx as G

TXT_Y = 79                     # the conversation text's first row

# asFuneralSceneBySeries[13] - cutscene.c:162-164: which eulogy a
# player funeral reads, times two.
SCENE_BY_SERIES = (0, 1, 1, 1, 1, 1, 2, 3, 2, 3, 3, 2, 3)
# aFuneralParticleOrigins[7] - cutscene.c:157-160
PARTICLE_ORIGINS = ((234, 83), (248, 85), (260, 80), (273, 78),
                    (286, 75), (299, 76), (310, 74))
# asConstellationFrame[16] and asConstellationVelocity[16] - view.c:17-22
CON_FRAME = (0, 16, 16, 0, 4, 4, 20, 20, 24, 8, 8, 24, 28, 12, 12, 28)
CON_VELOCITY = (8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1, 1)
# cBlueColour = 0x25 - init.c:14, the phase texts' colour
NOOP = lambda i: None


def _rand(n):
    """RandomInRange(0, n), inclusive (view.c:303-307, :312-324)."""
    return S._rnd(16) % (n + 1)


class _Funeral:
    def __init__(self, ai, st, player):
        self.ai = ai
        self.st = st
        self.player = player
        self.blue = ui.pal565(0x25)
        self.ok = False
        self.esc = False
        self.fun = S._set('fun.wcs')
        self.con = S._set('con.wcs')
        if self.fun is None or self.con is None:
            return
        # cutscene.c:1111: the funeral packet is BRIEFING.000 section 0
        # whatever campaign was flown; on the device brf0.wc keeps all
        # its sections. 14 ints head it (:1116-1132).
        self.packet = D.briefing_packet(0, 0, 0)
        if len(self.packet) < 56:
            return
        if player:
            # :1119-1124: series 0 and 14 read the opening eulogy,
            # every other series a pair from the table, doubled
            if st.series == 0 or st.series == 14:
                sp = 0
            else:
                sp = SCENE_BY_SERIES[st.series - 1] * 2
            self.which = (sp + 2) // 2       # ints sp+2 / sp+3
            self.follow = 0                  # ints 0 / 1
        else:
            self.which = 6                   # ints 12 / 13
            self.follow = 5                  # ints 10 / 11
        # the opening state, cutscene.c:1134-1141
        self.casket_x = 180
        self.casket_y = 70
        self.fg_x = 30
        self.fg_y = 0
        self.main_dist = 112
        self.particle_dist = 16
        self.guard_frame = 2
        self.rifle_frame = 4
        self.base_x = 0
        self.base_y = 0
        self.pvx = [0] * 7
        self.pvy = [0] * 7
        self.show_end = 0
        # InitializeConstellationField(stSceneBuffer, -1, 16)
        # (view.c:279-327): ten stars and sixteen particles over the
        # whole scene buffer, drifting left
        self.stars = []
        for _ in range(10):
            self.stars.append([_rand(319), _rand(127), _rand(5) + 32])
        self.parts = []
        for _ in range(16):
            r = _rand(15)
            self.parts.append([_rand(319), _rand(127),
                               -CON_VELOCITY[r],
                               CON_FRAME[r] + _rand(3)])
        self.ok = True

    # --- the picture (funeral_player, cutscene.c:998-1066) -------------------
    def _composite(self):
        fb = display.buffer
        # DrawConstellationField (view.c:339-348) first, behind the
        # crowd. Its clear colour cPrimaryViewBufferColour (init.c:27)
        # is palette index 191, which the converted menu palette holds
        # as black.
        G.fill_rows(fb, S.PIC_Y0, S.PIC_Y1, 0)
        for x, y, f in self.stars:          # :340-348, stars stand still
            S._draw(fb, self.con, f, x, y)
        for p in self.parts:                # :349-356
            S._draw(fb, self.con, p[3], p[0], p[1])
        self._advance_parts()               # :357-395
        # :1004: the crowd's scale, 8.8; 256 at nFuneralMainDist 112
        S._draw(fb, self.fun, 0, self.base_x, self.base_y)      # :1005-1006
        S._draws(fb, self.fun, 8, self.casket_x, self.casket_y, 0,
                 0x7000 // self.main_dist, 0)                   # :1007-1009
        S._draw(fb, self.fun, 1, self.base_x, self.base_y)      # :1010-1012
        S._draw(fb, self.fun, self.guard_frame, self.base_x, self.base_y)
        S._draw(fb, self.fun, self.rifle_frame, self.base_x, self.base_y)
        # :1019-1043: the volley particles, 256 at distance 16,
        # falling as they go; a particle that has left the buffer top
        # (y < 0) is spent
        sc = 0x1000 // self.particle_dist
        for i in range(7):
            if self.pvx[i]:
                S._draws(fb, self.fun, 9, self.pvx[i], self.pvy[i],
                         0, sc, 0)
                self.pvx[i] -= 6
                self.pvy[i] -= 6
                if self.pvy[i] < 0:
                    self.pvx[i] = 0
        # :1044-1051: the foreground trees, the right one 180 over
        S._draw(fb, self.fun, 7, self.fg_x, self.fg_y)
        S._draw(fb, self.fun, 6, self.fg_x + 180, self.fg_y)
        # :1053-1061: the end card while the casket is lowered
        if self.show_end:
            ui.text.centre(fb, b'THE END', S._cy(56), ui.WHITE)

    def _advance_parts(self):
        """view.c:357-378: move after drawing, cycle the frame inside
        its group of four, and a particle that ran off the left edge
        starts again just inside the right edge."""
        for p in self.parts:
            p[0] += p[2]
            p[3] = (p[3] & 0xfc) + (p[3] + 1) % 4
            if p[0] < 0:
                r = _rand(15)
                sp = CON_VELOCITY[r]
                p[0] = 319 - _rand(sp)
                p[1] = _rand(127)
                p[2] = -sp
                p[3] = CON_FRAME[r] + _rand(3)

    def _casket(self, i=None):
        """cutscene.c:1273-1285, verbatim - the even test runs after
        the decrement, and once the casket is left of centre the trees
        and the whole crowd slide right, so the group walks off. The
        index is ignored; S._steps hands it to every step function."""
        self.casket_x -= 1
        if self.casket_x % 2 == 0:
            self.casket_y -= 1
        self.main_dist += 1
        if self.casket_x < 160:
            self.fg_x += 2
            self.base_x += 1

    # --- texts ---------------------------------------------------------------
    def _text(self, line):
        """ClearViewport(&stCurrentConvTextViewport, cBlackColour) and
        the centred command line (the blue phase texts, cutscene.c:1198-
        1259; cBlueColour init.c:14)."""
        fb = display.buffer
        G.fill_rows(fb, TXT_Y, 112, 0)
        y = TXT_Y
        for ln in ui.text.wrap(line, 122):
            ui.text.centre(fb, ln, y, self.blue)
            y += 9

    # --- loops ---------------------------------------------------------------
    def _phase(self, n, step=NOOP):
        """One rendered picture every STEP_MS, n of them (the original's
        nFrameSkip is 1, init.c:202, so every pass draws and moves).
        True returns on a key, as every loop here checks
        bEscapePressedFlag."""
        esc = S._steps(n, self._composite, step)
        if esc:
            self.esc = True
        return esc

    def _count(self, n):
        """The 'Prepare arms!' countdown (cutscene.c:1229-1234): the
        only loop in the sequence with no escape check - the port keeps
        that, so a key held through it only ends the phases after."""
        t0 = ticks_ms()
        for i in range(n):
            self._composite()
            display.update()
            while ticks_diff(ticks_ms(), t0) < (i + 1) * S.STEP_MS:
                display.update()

    def shot17(self, line, colour, dur):
        """funeral_wingman (cutscene.c:1070-1096): the eulogy text under
        the scene while the scene runs for duration ticks; talk.py calls
        this for shot 17 records (screens.c:1443-1445). True returns
        when a key ended it - the original sets bEscapePressedFlag,
        which stops the whole funeral."""
        fb = display.buffer
        G.fill_rows(fb, TXT_Y, 112, 0)      # :1079 ClearViewport
        y = TXT_Y
        for ln in ui.text.wrap(line, 122):  # :1081-1091 the formatted text
            ui.text.centre(fb, ln, y, colour)
            y += 9
        ms = dur * 1000 // 60               # the port's tick convention
        t0 = ticks_ms()
        i = 0
        while True:
            self._composite()               # :1093 funeral_player
            display.update()
            while ticks_diff(ticks_ms(), t0) < (i + 1) * S.STEP_MS:
                display.update()
            i += 1
            if ticks_diff(ticks_ms(), t0) >= ms:
                break                       # :1095 the timer elapsed
            if S._key():                    # :1094 CheckEscaped
                ui.wait_release()
                self.esc = True
                return True
        ui.wait_release()
        return False

    # --- the conversation (SceneDirector type 3, screens.c:1235) --------------
    def _talk(self, which):
        t = talk.Talk(self.ai, self.st)
        t.funeral = self
        # the funeral packets have a 14-int header, and scene type 3:
        # no backdrop (cmpgn.c:440-442 clears the picture to the
        # primary colour, black in the menu palette) and the special
        # shapes fun.wcs frames 10 and 11 behind characters 5 and 6
        # (cmpgn.c:462-473). A B/M skip reads as a return of False;
        # a key on a shot-17 eulogy sets t.escaped, which is the
        # original's bEscapePressedFlag and stops the whole funeral
        ok = t.run(b'', self.packet, which, nhead=14, kind=3,
                   special=self.fun)
        return ok and not t.escaped

    def run(self):
        """funeral_sequence without the music: the eulogy, the commands,
        the volleys and the descent (cutscene.c:1103-1396). True returns
        when a key ended the sequence."""
        if not self.ok:
            return False
        fb = display.buffer
        if not self._talk(self.which):      # :1172
            self.esc = True
        # :1174: every phase after the eulogy runs behind the escape
        # guard, for a wingman's funeral as well as the player's - the
        # honour guard is played either way, only "THE END" is reserved
        # for the player (:1356-1358)
        if not self.esc:
            # :1175-1177 clear the scene and the text area: the
            # conversation's eulogy line is gone before the watch
            G.fill_rows(fb, S.PIC_Y0, S.PIC_Y1, 0)   # :1175
            G.fill_rows(fb, TXT_Y, 112, 0)           # :1176-1177
            if not self._phase(10):                  # :1179-1184 watching
                self._text(b'Company...')            # :1187-1196
                if not self._phase(15):              # :1191-1196
                    self._text(b'Atten-SHUN!')       # :1203 (sfx 0x24)
                    if not self._phase(10):          # :1205-1212
                        self.guard_frame = 3         # :1215
                        if not self._phase(10):      # :1218-1223
                            G.fill_rows(fb, TXT_Y, 112, 0)   # :1226-1228
                            self._text(b'Prepare arms!')     # :1230-1232
                            self._count(10)                  # :1233-1236
                            self.rifle_frame = 5             # :1239
                            if not self._phase(10):          # :1241-1248 (sfx 0x1f)
                                if not self._talk(self.follow):   # :1251-1252
                                    self.esc = True
                                else:
                                    G.fill_rows(fb, S.PIC_Y0,
                                                S.PIC_Y1, 0)   # :1253-1254
                                    self._volleys()
                                    if not self.esc:
                                        self._descent()        # :1340
        # :1385-1386: fade to black, then the screen is cleared
        for _ in range(10):
            G.dim_rows(fb, 0, 128)
            display.update()
        G.fill_rows(fb, 0, 128, 0)
        return self.esc

    def _volleys(self):
        """cutscene.c:1257-1333: three volleys. Each shows "Fire!",
        draws the casket ten frames of motion from the second volley
        on, then a fresh spray of seven particles for 24 frames."""
        fb = display.buffer
        for volley in range(3):             # :1257 nVolleyCount 0..2
            self._text(b'Fire!')            # :1259 (sfx 0x1e on :1259's
                                            # second volley, nVolleyCount==1)
            if volley:
                esc = self._phase(10, self._casket)   # :1270-1288, motion
                                                      # gated at :1273
            else:
                esc = self._phase(10)                 # :1270-1288, first
                                                      # volley: no motion
            if esc:
                return
            G.fill_rows(fb, TXT_Y, 112, 0)            # :1290-1292
            self.particle_dist = 16                   # :1296
            for i in range(7):                        # :1297-1310
                self.pvx[i] = PARTICLE_ORIGINS[i][0] + self.base_x
                self.pvy[i] = PARTICLE_ORIGINS[i][1] + self.base_y

            def volley_step(i, volley=volley):        # :1315-1333
                # the casket walks during the spray from the second
                # volley on (:1318-1330), the particle distance on
                # every pass (:1331)
                if volley > 0:
                    self._casket()
                self.particle_dist += 1
            if self._phase(24, volley_step):          # :1315 (sfx 0x1d)
                return

    def _descent(self):
        """cutscene.c:1340-1368: the long walk down, frame by frame.
        The music gate is not ported, so the playback-mode-0 fallback
        at :1360-1364 decides: the loop stops once frame passes 160."""
        fb = display.buffer
        t0 = ticks_ms()
        frame = 0
        while True:
            self._composite()               # :1346
            display.update()
            self.casket_x -= 1              # :1347-1350
            if self.casket_x % 2 == 0:
                self.casket_y -= 1
            frame += 1                      # :1351
            self.main_dist += 1             # :1352-1355: the motion here
            self.base_x += 1                # runs on every pass, not
            self.fg_x += 2                  # only left of 160
            self.particle_dist += 1
            if frame == 110 and self.player:    # :1356-1358: the card,
                self.show_end = 1               # players only
            if frame > 160:                 # :1360-1364: no music, so
                break                       # this break is what runs
            while ticks_diff(ticks_ms(), t0) < frame * S.STEP_MS:
                if S._key():
                    self.esc = True
                    return
                display.update()


def funeral(kind, ai, st):
    """funeral_sequence: kind 1 when the player died (gameflow.c:407),
    kind 0 when a wingman did not return (:469). Without the sprite
    sets the scene is skipped, as in every other hard scene."""
    seq = _Funeral(ai, st, kind == 1)
    if not seq.ok:
        return False
    esc = seq.run()
    S.cleanup()                             # let go of fun.wcs / con.wcs
    return esc


def cleanup():
    """Let go of the cached sets between campaigns."""
    S.cleanup()
