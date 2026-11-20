# talk.py - the conversation director (briefings, debriefings, the bar).
#
# The scripts are the original BRIEFING.00x scene streams, played by a
# port of SceneDirector / ParseTests (wc1-re src/screens.c, GPL-3.0):
# 13-byte records with a camera shot, a text colour, a speaker and an
# optional list of branch tests against the campaign state. The talking
# heads are not drawn - each line is shown in the speaker's colour with
# the speaker's name - but every branch the original takes is taken.

from struct import unpack_from
from thumby_engine.platform import (display, buttonA, buttonB, buttonMENU)
import ui
import wcdata as D

# camera shot 20 + n shows face n
FACES = (b'Col. Halcyon', None, None, None, None, None, None, None, None,
         None, b'Shotglass')


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
    def run(self, title, packet, which, series_name=b''):
        """Play scene `which` (0 briefing, 1 debriefing, 2..4 bar) of a
        briefing packet. Returns False if the player skipped it."""
        if len(packet) < 40:
            return True
        self.series_name = series_name
        head = unpack_from('<10I', packet, 0)
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
            shot, col, talker, dur, tests, toff, _m, _f = unpack_from(
                '<bbbhhhhh', packet, o)
            if shot == -2:
                break
            if tests:
                j = self.branch(D.cstr(packet, tbase + tests) + b'\0')
                if j != -1 and j != rec:
                    rec = j
                    continue
            kind = shot & 0x3F if shot >= 0 else -1
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
            if 0 <= col < 12:
                colour = ui.pal565(self.ai.colours[col])
            raw = D.cstr(packet, tbase + toff)
            if raw:
                if not self.say(title, speaker, self.expand(raw), colour,
                                kind == 4):
                    return False
            rec += 1
        return True

    def say(self, title, speaker, line, colour, show_map):
        fb = display.buffer
        lines = []
        for part in line.split(b'\n'):
            lines.extend(ui.text.wrap(part, 122))
        display.fill(0)
        ui.frame_title(title)
        y = 15
        if show_map and self.map_draw is not None:
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
