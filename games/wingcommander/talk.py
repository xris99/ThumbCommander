# talk.py - the conversation director (briefings, debriefings, the bar).
#
# The scripts are the original BRIEFING.00x scene streams, played by a
# port of SceneDirector / ParseTests (wc1-re src/screens.c, GPL-3.0):
# 13-byte records with a camera shot, a text colour, a speaker and an
# optional list of branch tests against the campaign state. Records that
# select a face (shot 20 + n) draw the talking head from head<NN>.wc and
# play its mouth and eye animation (wc1-re src/cmpgn.c
# ParseMouthAnimation, ParseFaceAnimation, LoadFace, LongTalk, CloseTalk);
# every branch the original takes is still taken.

from struct import unpack_from, pack
from time import ticks_ms, ticks_diff, ticks_add
from gc import collect
from thumby_engine.platform import (display, buttonA, buttonB, buttonMENU)
import ui
import wcdata as D
import wcgfx

# camera shot 20 + n shows face n
FACES = (b'Col. Halcyon', None, None, None, None, None, None, None, None,
         None, b'Shotglass')

# asMouthFramesByPhoneme (wc1-re src/cmpgn.c:12-15): letter to mouth frame
PHONEME = bytes((0, 5, 4, 4, 1, 8, 4, 7, 0, 4, 4, 7, 5,
                 4, 2, 5, 6, 4, 4, 4, 3, 4, 6, 4, 4, 4))

# one pass of LongTalk's loop is one displayed frame; the original ran
# a pass per displayed frame and the reference port throttled those
# frames to 16 per second, 62 ms (docs/04 1.4). The pass keeps that
# throttle - the turn's 100 ms animated every head 1.6 times slower
# than the original (device report).
STEP_MS = 62

# both command lists end with one -1 (wc1-re src/cmpgn.c:60, 97)
END = pack('<h', -1)


def parse_mouth(raw):
    """ParseMouthAnimation verbatim (wc1-re src/cmpgn.c:65-98): one
    (frame, ticks) pair per spoken character, '$' selects the resting
    mouth, every other character is skipped, decimal digits after a
    character give the hold time in ticks (default 1). Ticks exceed 255
    ('$100' is common), so pairs are stored as 16 bits, 4 bytes each,
    with the -1 sentinel behind them."""
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n and raw[i] != 0:
        ch = raw[i]
        i += 1
        if ch == 0x24:                     # '$'
            frame = 9
        elif 0x61 <= ch <= 0x7A:           # 'a'..'z'
            frame = PHONEME[ch - 0x61]
        else:
            continue                       # cmpgn.c:79
        ticks = 1
        digits = bytearray()
        while i < n and raw[i] <= 0x39:    # cmpgn.c:83-93: the digit run
            c = raw[i]
            if c < 0x30:
                break
            if len(digits) < 4:            # duration[5] (cmpgn.c:68)
                                           # holds 4 digits and the NUL;
                                           # a fifth digit would run off
                                           # the original's stack buffer
                digits.append(c)
            i += 1
            # cmpgn.c:91: atoi over the whole buffer built so far, not a
            # running accumulation: '$100' is 100 ticks, not 1100
            ticks = int(digits) if digits else 1
        out += pack('<hh', frame, ticks)
    out += END
    return out


def parse_face(raw):
    """ParseFaceAnimation verbatim (wc1-re src/cmpgn.c:27-62): commands
    '<frame><ticks>,'. Hex 'A'..'F' are frames 10..15 (frame 10 means
    "no eye overlay", LongTalk maps it to -1); 'R' is the marker command
    written as (-2, sequenceIndex) without advancing that count, so a
    leading 'R' is the command index 0 - the first real command."""
    out = bytearray()
    seq = 0
    i = 0
    n = len(raw)
    while i < n and raw[i] != 0:
        frame = raw[i]
        i += 1
        if frame == 0x52:                  # 'R', cmpgn.c:37-40
            out += pack('<hh', -2, seq)
            continue
        if 0x41 <= frame <= 0x46:          # cmpgn.c:42-43
            frame = frame - 0x41 + 10
        else:
            frame = frame - 0x30           # '0'..'9'
        chars = bytearray()
        while i < n and raw[i] != 0x2C:    # cmpgn.c:49-52: to the ','
            if len(chars) < 7:             # duration[8] (cmpgn.c:29)
                                           # holds 7 bytes plus the NUL;
                                           # longer runs would run off the
                                           # original's stack buffer
                chars.append(raw[i])
            i += 1
        i += 1                             # consume the ','
        ticks = 0
        for c in chars:                    # cmpgn.c:54: atoi takes the
            if 0x30 <= c <= 0x39:          # leading digit run and stops
                ticks = ticks * 10 + c - 0x30   # at the first other byte
            else:
                break
        out += pack('<hh', frame, ticks)
        seq += 1                           # cmpgn.c:56
    out += END
    return out


class Talk:
    def __init__(self, tables, state, outcome=None, world=None,
                 map_draw=None, picture=None):
        self.ai = tables
        self.st = state
        self.out = outcome
        self.world = world
        self.map_draw = map_draw
        self.picture = picture
        self.medal = outcome.medal if outcome else -1
        if outcome:
            self.cur = outcome.flown_mission + outcome.flown_series * 4
        else:
            self.cur = state.mission + state.series * 4
        # director state, mirrors the original's globals; run() resets
        # it when a packet starts
        self.kind = 0                  # nTalkSceneType (screens.c:1249)
        self.character = -1            # screens.c:149
        self.prev_shot = -2            # screens.c:1246 previousShot
        self.prev_colour = -2          # screens.c:1247 previousColour
        self.overlay = 0               # bConversationOverlay
        self.head = None               # pTalkHeadShape
        self.head_face = -1            # nTalkingHeadFace
        self.ovl = None                # pConvOverlayShapePtr, on demand
        self.bdrop = None              # pCurrentConversationBackdrop
        self.bd_view = None
        self.bd_idx = -2               # the backdrop frame shown now
        self.funeral = None            # the running funeralseq, when set
        self.special = None            # pCurrentConversationSpecialShape
        self.sp_view = None
        self.escaped = False           # bEscapePressedFlag as run() ends

    # --- $ codes (AddPCName) -----------------------------------------------
    def expand(self, raw):
        st = self.st
        out = bytearray()
        i = 0
        n = len(raw)
        while i < n:
            c = raw[i]
            i += 1
            if c != 0x24 or i >= n:        # '$'
                out.append(c)
                continue
            k = raw[i]
            i += 1
            if k == 0x43:                  # C callsign
                out.extend(st.callsign.encode())
            elif k == 0x4E or k == 0x50:   # N, P name
                out.extend(st.name.encode())
            elif k == 0x4B:                # K kills this mission
                out.extend(str(self.out.kills if self.out else 0).encode())
            elif k == 0x4C:                # L wingman kills
                out.extend(str(self.out.wing_kills if self.out
                               else 0).encode())
            elif k == 0x44 or k == 0x45:   # D, E date
                out.extend(('%04d.%03d' % (st.year, st.day)).encode())
            elif k == 0x54:                # T time
                out.extend(('%02d:00' % (6 + st.missions % 12)).encode())
            elif k == 0x52:                # R rank
                r = self.ai.ranks[min(4, st.rank)]
                if i < n and raw[i] == 0x2E and r[-1:] == b'.':
                    r = r[:-1]
                out.extend(r)
            elif k == 0x41:                # A medal
                out.extend(self.ai.medals[max(0, min(4, self.medal))])
            elif k == 0x53:                # S system name
                out.extend(self.series_name)
            elif k == 0x57:                # W<n> wingman name
                if i < n:
                    p = raw[i] - 0x30
                    i += 1
                    if 0 <= p < 8:
                        out.extend(self.ai.pilots[p][0])
            else:
                out.append(k)
        return bytes(out)

    # --- branch tests (ParseTests) -------------------------------------------
    def wing_status(self, p):
        if p < 0 or p >= 8 or self.st.death[p] == 0:
            return 3
        if self.cur == self.st.death[p]:
            return 1
        return 2

    def achieved(self, i):
        o = self.out.objectives if self.out else []
        return 0 <= i < len(o) and o[i][3] & 2

    def sighted(self, i):
        o = self.out.objectives if self.out else []
        return 0 <= i < len(o) and o[i][3] & 4

    def branch(self, tests):
        """Returns the record index to jump to, or -1."""
        st = self.st
        out = self.out
        pos = 0
        n = len(tests)

        def value():
            nonlocal pos
            v = 0
            neg = False
            while pos < n and tests[pos] != 0x2C and tests[pos] != 0x29:
                ch = tests[pos]
                if ch == 0x2D:
                    neg = True
                elif 0x30 <= ch <= 0x39:
                    v = v * 10 + ch - 0x30
                pos += 1
            pos += 1
            return -v if neg else v

        kills = out.kills if out else 0
        wkills = out.wing_kills if out else 0
        ejected = out.ejected if out else False
        while pos < n and tests[pos] != 0:
            code = tests[pos]
            pos += 1
            a = value()
            two = code in (2, 3, 4, 5, 11, 12, 27, 28, 29, 30, 31, 32, 33, 34)
            b = value() if two else a
            hit = False
            if code == 1:
                hit = True
            elif code == 2:
                hit = st.mission_score < a
            elif code == 3:
                hit = a <= st.mission_score
            elif code == 4:
                hit = self.wing_status(a) != 3
            elif code == 5:
                hit = self.wing_status(a) == 3
            elif code == 6:
                hit = kills == 0
            elif code == 7:
                hit = kills != 0
            elif code == 8:
                hit = wkills == 0
            elif code == 9:
                hit = wkills != 0
            elif code == 10:
                hit = not (out and out.office)
            elif code == 11:
                hit = not self.achieved(a)
            elif code == 12:
                hit = bool(self.achieved(a))
            elif code == 13:
                hit = self.medal == 4
            elif code == 14:
                hit = self.medal < 3
            elif code == 15:
                hit = self.medal == 3
            elif code == 16:
                hit = not (out and out.promoted)
            elif code == 17:
                hit = not ejected
            elif code == 18:
                hit = ejected and st.ejects == 1
            elif code == 19:
                hit = not (out and out.ship_changed)
            elif code == 20:
                hit = st.ship != 0
            elif code == 21:
                hit = st.ship != 2
            elif code == 22:
                hit = st.ship != 3
            elif code == 23:
                hit = st.ship != 1
            elif code == 24:
                hit = st.ship != 1 and out is not None and \
                    st.ship < out.prev_ship
            elif code == 25:
                hit = st.ship == 1 or out is None or st.ship >= out.prev_ship
            elif code == 26:
                hit = ejected and st.ejects > 1
            elif code == 27:
                hit = bool(self.sighted(a))
            elif code == 28:
                hit = not self.sighted(a)
            elif code == 29:
                hit = self.wing_status(a) == 2
            elif code == 30:
                hit = self.wing_status(a) == 1
            elif code in (31, 32, 33, 34):
                # Kilrathi ace status: aces are not tracked between
                # missions here, they count as still at large
                hit = code in (31, 33)
            elif code == 35:
                hit = out is not None and out.score == out.full_score
            elif code == 36:
                hit = out is None or out.score < out.full_score
            elif code == 37:
                hit = out is None or not any(o[3] & 2 for o in out.objectives)
            elif code == 38:
                hit = out is not None and any(o[3] & 2
                                              for o in out.objectives)
            if hit:
                return b
        return -1

    # --- director --------------------------------------------------------------
    def run(self, title, packet, which, series_name=b'', nhead=10,
            kind=None, special=None):
        """Play scene `which` (0 briefing, 1 debriefing, 2..4 bar) of a
        briefing packet. Returns False if the player skipped it; a key
        that ended a funeral eulogy line (shot 17) sets self.escaped
        instead, as the original's bEscapePressedFlag ends the whole
        sequence. funeralseq passes nhead=14 (the funeral packets'
        header), kind=3 (the funeral conversation, screens.c:1235) and
        the funeral sprite set as `special`."""
        if len(packet) < nhead * 4:
            return True
        self.series_name = series_name
        # the scene type decides the backdrop: 0 briefing, 1 debriefing,
        # 2..4 are the bar's tables (docs/05 5.1); the funeral sets it
        # to 3 (SceneDirector(3, ...) cutscene.c:1172)
        self.kind = kind if kind is not None else (which if which <= 2
                                                   else 2)
        self.character = -1            # screens.c:149
        self.prev_shot = -2            # screens.c:1246
        self.prev_colour = -2          # screens.c:1247
        self.overlay = 0
        self.head = None
        self.head_face = -1
        self.ovl = None
        self.bd_idx = -2
        self.escaped = False
        self.special = special
        self.sp_view = bytearray(special.largest) if special else None
        head = unpack_from('<%dI' % nhead, packet, 0)
        scene = head[which * 2]
        tbase = head[which * 2 + 1]
        if scene == 0 or scene >= len(packet):
            return True
        rec = 0
        guard = 0
        speaker = None
        colour = ui.WHITE
        while guard < 400:
            guard += 1
            o = scene + rec * 13
            if o + 13 > len(packet):
                break
            shot, col, talker, dur, tests, toff, moff, foff = unpack_from(
                '<bbbhhhhh', packet, o)
            if shot == -2:
                break
            if tests:
                j = self.branch(D.cstr(packet, tbase + tests) + b'\0')
                if j != -1 and j != rec:
                    rec = j
                    continue
            kind = shot
            if shot != -1:             # screens.c:1257-1264: shot -1
                if shot & 0x40:        # keeps the picture and the overlay
                    self.overlay = 1
                    kind = shot & 0x3F
                else:
                    self.overlay = 0
            if talker != -2:           # screens.c:1273-1274
                self.character = talker
            # prepare the picture, screens.c:1276-1357 verbatim
            if kind in (0, 3, 5, 6, 7, 8, 9, 10, 11, 16, 17):
                self.prev_shot = kind  # screens.c:1288
                self.head_face = -1    # screens.c:1289
            elif kind == 1:
                if self.prev_shot != 1:        # screens.c:1291-1297
                    self.prev_shot = 1
                    self.head_face = -1
            elif kind == 2:
                if self.prev_shot != 2:        # screens.c:1298-1304
                    self.prev_shot = 2
                    self.head_face = -1
            elif kind == 4:                    # screens.c:1305-1309
                self.prev_shot = 4             # cCurrentObjective =
                self.head_face = -1            # abs(character): the port's
                                               # map shows the whole plan
            elif kind in (12, 13, 14, 15):     # screens.c:1310-1323
                if self.prev_shot != kind:     # the funeral star field is
                    self.head_face = -1        # baked into the backdrop,
                    self.prev_shot = kind      # nothing else to init
            elif 20 <= kind <= 32:             # screens.c:1324-1343
                if self.prev_shot != kind:
                    self.load_face(kind - 20)
                    self.prev_shot = kind
            elif 50 <= kind <= 59:             # screens.c:1344-1356
                self.prev_shot = 50            # scripted animations live
                self.head_face = -1            # in chapter 6, not here
            # the speaker's name above the text (the port's addition;
            # shot 20 + n is character n)
            if 20 <= kind <= 32:
                face = kind - 20
                if face == 9:
                    speaker = self.st.callsign.encode()
                elif 1 <= face <= 8:
                    speaker = self.ai.pilots[face - 1][1]
                elif face < len(FACES):
                    speaker = FACES[face]
                else:
                    speaker = None
            elif kind != -1:
                speaker = None
            # colour: only changed records change it (screens.c:1358-
            # 1373). asConversationTextColours is in ai.wc; Secret
            # Missions 2's entries 12 and 13 map to palette 9 and 13.
            if 0 <= col < 14 and col != self.prev_colour and col != -1:
                self.prev_colour = col
                if col < 12:
                    c = self.ai.colours[col]
                elif col == 12:
                    c = 9
                else:
                    c = 13
                colour = ui.pal565(c)
            raw = D.cstr(packet, tbase + toff)
            if raw:
                if self.funeral is not None and self.prev_shot == 17:
                    # screens.c:1443-1445: previousShot 17 dispatches
                    # the eulogy to funeral_wingman (cutscene.c:1069),
                    # which runs the honour-guard scene under the text
                    # instead of talking; a key there is the original's
                    # Escape - it ends the SceneDirector loop (:1461)
                    # and the whole funeral (:1174)
                    if self.funeral.shot17(self.expand(raw), colour, dur):
                        self.escaped = True
                        break
                else:
                    # the mouth and face lists are only read by LongTalk
                    # (screens.c:1375-1384 and the default case at
                    # 1449-1454); the record's offsets are relative to
                    # the text base, an empty string leaves the
                    # single-sentinel list
                    mcmd = fcmd = None
                    if self.head is not None and 20 <= self.prev_shot <= 32:
                        mcmd = END
                        fcmd = END
                        mo = tbase + moff
                        fo = tbase + foff
                        if 0 <= mo < len(packet) and packet[mo] != 0:
                            mcmd = parse_mouth(D.cstr(packet, mo))
                        if 0 <= fo < len(packet) and packet[fo] != 0:
                            fcmd = parse_face(D.cstr(packet, fo))
                    if not self.say(title, speaker, self.expand(raw),
                                    colour, kind == 4,
                                    max(0, dur * 1000 // 60),
                                    mcmd, fcmd):
                        return False
            rec += 1
        return True

    # --- the talking head ----------------------------------------------------

    def escape_button(self):
        """Any button reads as the original's Esc key (CheckEscaped)."""
        if buttonA.justPressed():
            return 'A'
        if buttonB.justPressed():
            return 'B'
        if buttonMENU.justPressed():
            return 'M'
        return None

    def lazy_bdrop(self):
        """Open bdrop.wc the first time a head is shown; a missing file
        leaves the backdrop black and must not break the game."""
        if self.bdrop is None:
            try:
                self.bdrop = D.Backdrops()
                self.bd_view = bytearray(D.Backdrops.SIZE)
            except OSError:
                self.bdrop = False

    def load_face(self, face):
        """LoadFace (wc1-re src/cmpgn.c:209-300). The star field of
        characters 2 and 8 is baked into their backdrop frames in
        bdrop.wc, the SM2 faces 11 and 12 are not ported, and the head
        is reloaded only when the face changes (cmpgn.c:258-274)."""
        if face == self.head_face and self.head is not None:
            return
        self.head = None                 # FreePacketAndClear, cmpgn.c:259
        collect()                        # MicroPython has no reference
                                         # counting: the dropped face's
                                         # 13 to 18 KB block stays
                                         # heap-held until this sweep,
                                         # and the new face asks one
                                         # block of its file's size -
                                         # so only one head is ever
                                         # live, and the hole the old
                                         # face leaves is re-made
                                         # before the ask. Device log
                                         # 2026-11-27: the third face
                                         # failed with 66,336 free in
                                         # no one piece. docs/12.
        self.head_face = face
        if not D.exists('head%02d.wc' % face):
            return                       # text-only fallback, docs/05 5.7.5
        try:
            self.head = D.Head(face)
        except (OSError, MemoryError):
            return                       # no picture: the text shows
        # LoadFace ends with CloseTalk(head, -1, -1) (cmpgn.c:298): the
        # neutral face shows at once, even if this record has no text
        self.lazy_bdrop()
        self.close_talk(-1, -1)

    def close_talk(self, mouth_frame, face_frame):
        """CloseTalk verbatim (wc1-re src/cmpgn.c:421-461): every call
        composes the whole conversation picture into rows 16..77. LongTalk
        calls it once per displayed frame (cmpgn.c:404-409), so the port
        redraws everything per step instead of only the rectangles that
        changed. The text below row 77 is not touched here."""
        fb = display.buffer
        # 1. star field (cmpgn.c:424-425): characters 2 and 8 bake their
        #    window stars into the backdrop frame (docs/05 5.6), so the
        #    constellation is never animated separately
        # 2. backdrop (cmpgn.c:426-445): the character's frame of this
        #    scene's backdrops, black when LoadFace finds none. Scene
        #    type 3 - the funeral - is the one case that never shows a
        #    backdrop: it clears to cPrimaryViewBufferColour (:440-442),
        #    palette 191, which the converted menu palette holds as
        #    black, so the fill below is already what the original does.
        idx = self.bdrop.index(self.kind, self.character) \
            if (self.bdrop and self.kind != 3) else -1
        if idx != self.bd_idx:
            self.bd_idx = idx
            if idx >= 0:
                self.bdrop.read(idx, self.bd_view)
        if idx < 0:
            wcgfx.fill_rows(fb, 16, 78, 0)   # ClearViewport(black)
        else:
            wcgfx.blit_indexed(fb, ui.pal, self.bd_view,
                               0, 16, 128, 62, 16, 78)
        # 3. the head, frame 0 at (0, 0) (cmpgn.c:447)
        wcgfx.blit_indexed(fb, ui.pal, self.head.base, 0, 16,
                           self.head.w, self.head.h, 16, 78)
        # 4. eyes: frame faceFrame + 11 at the face origin (cmpgn.c:448-
        #    452). TALKING.VGA only has eye shapes 11..20, so patches
        #    0..9 exist; hex frames 'B'..'F' (11..15) asked the original
        #    for shapes it never had (docs/05 5.3) and draw nothing.
        if 0 <= face_frame <= 9:
            x, y, w, h = self.head.eye_rect
            wcgfx.blit_indexed(fb, ui.pal, self.head.eye[face_frame],
                               x, 16 + y, w, h, 16, 78)
        # 5. mouth: frame mouthFrame + 1 at the mouth origin
        #    (cmpgn.c:453-457)
        if 0 <= mouth_frame <= 9:
            x, y, w, h = self.head.mouth_rect
            wcgfx.blit_indexed(fb, ui.pal, self.head.mouth[mouth_frame],
                               x, 16 + y, w, h, 16, 78)
        # 6. overlay (shot flag 0x40): TALKING.VGA section 11, frame
        #    min(nTalkingHeadFace, 1), at (0, 0) (cmpgn.c:458-461).
        #    ovl.wcs holds that section at screen resolution, unscaled.
        if self.overlay and self.head_face >= 0:
            if self.ovl is None:
                try:
                    self.ovl = D.SpriteSet('ovl.wcs')
                    self.ovl_view = bytearray(self.ovl.largest)
                except OSError:
                    self.ovl = False
            if self.ovl:
                frame = self.head_face if self.head_face < 1 else 1
                off = unpack_from('<I', self.ovl.table, frame * 8)[0]
                if off:
                    self.ovl.read(off, self.ovl_view)
                    wcgfx.blit_indexed(fb, ui.pal, self.ovl_view, 0, 16,
                                       self.ovl.table[frame * 8 + 4],
                                       self.ovl.table[frame * 8 + 5],
                                       16, 78)
        # 7. conversation characters 5 and 6 add a special shape
        #    (cmpgn.c:462-473): the funeral packet, BRIEFING.VGA
        #    section 9 that funeral_sequence fetches at cutscene.c:1166
        #    - fun.wcs frames 10 and 11, drawn at (0, 0) of the scene
        #    viewport, the hot spot landing at the viewport's corner.
        #    This closes docs/05 5.8: character 5 shows frame 10 only
        #    (:463-467), character 6 both frames (:468-473).
        if self.special is not None and self.sp_view is not None:
            if self.character == 5:
                frames = (10,)
            elif self.character == 6:
                frames = (10, 11)
            else:
                frames = ()
            for frame in frames:
                off, w, h, hx, hy = unpack_from('<IBBbb',
                                                self.special.table,
                                                frame * 8)
                if off and w and h:
                    self.special.read(off, memoryview(self.sp_view)[:w * h])
                    wcgfx.blit_indexed(fb, ui.pal, self.sp_view,
                                       -hx, 16 - hy, w, h, 16, 78)

    def scene_advance(self, fb, dur_ms):
        """WaitForSceneAdvance(duration, 0) verbatim (wc1-re
        src/disk.c:509-548): hold the picture until the duration has
        passed or a button goes down; a press waits for the release
        before returning."""
        deadline = ticks_add(ticks_ms(), dur_ms)
        while True:
            display.update()
            if ticks_diff(ticks_ms(), deadline) >= 0:
                return 'done', None
            btn = self.escape_button()
            if btn is not None:
                ui.wait_release()        # the do/while release, :541-543
                return 'key', btn

    def long_talk(self, fb, mcmd, fcmd, dur_ms):
        """LongTalk (wc1-re src/cmpgn.c:303-418) without the voice
        branches of the SDL port - no voices are ported, so the mouth
        always follows its script (cmpgn.c:314-323 are skipped). Two
        cursors step over the (frame, ticks) pairs, one pass per displayed
        frame; outside flight that is the throttle's 62 ms pass (STEP_MS).
        Returns
        ('done', None) when the line ended on its own and ('key', button)
        when the player ended it.

        The original's oddities are copied, not fixed (docs/05 5.5): a
        cursor advances before it reads, so the first command of each
        list is skipped unless a marker pulls the cursor back; and the
        wait started by the mouth's end can cut the line short while the
        eyes are still animating (cmpgn.c:412-413)."""
        mc = 0
        fc = 0
        mcd = 0                          # cmpgn.c:333-334
        fcd = 0
        mfr = 0
        ffr = 0
        waiting = 0                      # cmpgn.c:325
        deadline = 0
        last = ticks_ms()
        acc = 0
        while True:
            now = ticks_ms()
            acc += ticks_diff(now, last)
            last = now
            steps = acc // STEP_MS
            acc -= steps * STEP_MS
            for _ in range(steps):
                mv = unpack_from('<h', mcmd, mc)[0]
                fv = unpack_from('<h', fcmd, fc)[0]
                if mv == -1 and fv == -1:        # cmpgn.c:341-355
                    if waiting == 0:
                        self.close_talk(-1, -1)  # cmpgn.c:347
                        return self.scene_advance(fb, dur_ms)
                    return 'done', None          # cmpgn.c:353-354:
                                                 # the unconditional return
                trig = mcd == 0                  # cmpgn.c:367: the --
                mcd -= 1                         # happens inside the test
                if trig:
                    if mv != -1:                 # cmpgn.c:368-369:
                        mc += 4                  # advance before reading
                    mv = unpack_from('<h', mcmd, mc)[0]
                    if mv == -2:                 # cmpgn.c:371: rewind
                        mc = 0
                        mv = unpack_from('<h', mcmd, mc)[0]
                    if mv == -1:
                        mfr = -1                 # cmpgn.c:377-383: only
                        if waiting == 0:         # the mouth starts the
                            waiting = 1          # after-line wait
                            deadline = ticks_add(now, dur_ms)
                    else:                        # cmpgn.c:373-375
                        mfr = mv
                        mcd = unpack_from('<h', mcmd, mc + 2)[0] * 2
                trig = fcd == 0                  # cmpgn.c:386
                fcd -= 1
                if trig:
                    if fv != -1:
                        fc += 4
                    fv = unpack_from('<h', fcmd, fc)[0]
                    if fv == -2:
                        fc = 0
                        fv = unpack_from('<h', fcmd, fc)[0]
                    if fv == -1:
                        ffr = -1                 # cmpgn.c:398-400: no wait
                    else:                        # cmpgn.c:392-397
                        if fv == 10:
                            ffr = -1             # 'A': the head's own eyes
                        else:
                            ffr = fv
                        fcd = unpack_from('<h', fcmd, fc + 2)[0] * 2
                # nFrameSkipCounter is 1 at cmpgn.c:339 and nFrameSkip is
                # 1 (init.c:202), so the original redraws every pass; when
                # the catch-up ran several passes, only the last picture
                # can still be shown to the player
                self.close_talk(mfr, ffr)
            display.update()
            btn = self.escape_button()           # cmpgn.c:410
            if btn is not None:
                # cmpgn.c:415-416: break, then wait for the release
                ui.wait_release()
                return 'key', btn
            if waiting and ticks_diff(now, deadline) >= 0:
                return 'done', None

    def say(self, title, speaker, line, colour, show_map,
            dur_ms=0, mcmd=None, fcmd=None):
        """Show one line. While a face shot is active the head is on
        screen, so rows 16..77 hold the conversation picture (docs/05 5.3)
        and long_talk plays the mouth and eye lists below it; otherwise
        the room, the map or a plain page is shown as before. Returns
        False when the player skips the conversation."""
        fb = display.buffer
        lines = []
        for part in line.split(b'\n'):
            lines.extend(ui.text.wrap(part, 122))
        display.fill(0)
        ui.frame_title(title)
        y = 15
        head_pic = (self.head is not None and 20 <= self.prev_shot <= 32)
        if head_pic:
            # the neutral face: what LoadFace drew when the head was
            # loaded (cmpgn.c:298); it also clears the previous line's
            # text from the picture rows
            self.lazy_bdrop()
            self.close_talk(-1, -1)
            y = 79
        elif show_map and self.map_draw is not None:
            self.map_draw(13, 55)
            y = 71
        elif self.picture:
            h = ui.backdrop(self.picture, 12)
            if h:
                y = 14 + h
        if speaker:
            ui.small.draw(fb, speaker, 3, y, 0xBDF7)
            y += 8
        room = (120 - y) // 9
        for ln in lines[:room]:
            ui.text.draw(fb, ln, 3, y, colour)
            y += 9
        ui.small.draw(fb, b'A', 121, 121, ui.GREY)
        ui.wait_release()
        if head_pic and mcmd is not None:
            state, btn = self.long_talk(fb, mcmd, fcmd, dur_ms)
            if btn in ('B', 'M'):
                return False             # skip the whole conversation
            # 'key' with A and 'done' both mean the line is over
        else:
            while True:
                display.update()
                if buttonA.justPressed():
                    if len(lines) > room:
                        # a long line: show the rest on a second page
                        del lines[:room]
                        return self.say(title, speaker, b' '.join(lines),
                                        colour, show_map)
                    return True
                if buttonB.justPressed() or buttonMENU.justPressed():
                    return False
        # the animation ended but a long line still has text below the
        # fold: show the rest on a static second page (the original shows
        # the whole line at once and has no pages)
        if len(lines) > room:
            del lines[:room]
            return self.say(title, speaker, b' '.join(lines),
                            colour, show_map)
        return True
