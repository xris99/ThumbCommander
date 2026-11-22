#!/usr/bin/env python3
"""
Convert an original Wing Commander 1 (DOS) installation into the asset
pack of games/wingcommander.

The game ships without any Origin data: you point this tool at your own
copy (the folder that holds WC.EXE and GAMEDAT, e.g. from the GOG
release) and it writes everything the ThumbyColor build loads into
games/wingcommander/assets/:

  pal.wc             game palette as 256 RGB565 words
  types.wc           ship / weapon statistics and direction tables
  ai.wc              pilot AI, formation and campaign tables
  sh<NN>.wcs         one ship: its 37 views as 8-bit sprites
  ms.wcs             missile views
  fx<NN>.wcs         explosions, bolts, debris, asteroids, mines
  hud.wcs            crosshairs and target brackets
  ck<N>.wc           cockpit overlays (front view, 128x96)
  font<N>.wc         the original bitmap fonts, 1 bit per pixel
  mod<C>.wc          missions of campaign C (nav points, ships, ...)
  camp<C>.wc         campaign tree and scoring of campaign C
  brf<C>.wc          briefing / debriefing / bar scripts and text
  comm.wc            in-flight radio messages
  *_128_NN.COL.bin   full pictures in the engine's RGB565 format
  head<NN>.wc        one talking-head face: base, ten mouths, ten eyes
  bdrop.wc           conversation backdrops keyed by scene and character
  ovl.wcs            the conversation overlay frames
  meanwhile_128_62.COL.bin the cutscene caption word
  mid<NN>.wc         one cutscene: frames, recompiled scripts, records
  scr<NN>.wcs        SCRAMBLE.VGA sections for the hard-coded launch scenes
  cksc<N>.wcs        cockpit scramble shapes for player ship N (PCSHIP.V0N)
  ckint/ckbg/ckslide<N>.wcs  cockpit interior, backdrop and eject slide
  pil<NN>.wcs        the pilot's death face and the ejection seat
  sfx_*.ima          cockpit sound effects (synthesised, not Origin data)

Campaign 0 is Wing Commander, 1 and 2 are the Secret Missions (only
converted when their files are present).

The original pictures are 320x200 with non-square pixels (a 4:3 screen).
They are resampled to a square-pixel 128x96 picture area; sprites are
kept 1.25x finer than that so they stay crisp when the flight view
zooms in. Every picture and every mission, campaign and conversation
record comes from the files in GAMEDAT. Two things do not: the ship
statistics and AI tables in tool/wc1/tables.py, which the game keeps
inside WC.EXE (they were read out of the wc1-re source), and the five
sound effects, which are synthesised because the PC original has no
sampled sound.

Usage:
    python3 tool/wc1_convert.py /path/to/WING
    python3 tool/wc1_convert.py /path/to/WING --out some/dir --preview
    python3 tool/wc1_convert.py /path/to/WING --dump 1 0   # print a mission

Needs numpy and Pillow (Pillow only for --preview).
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np                                      # noqa: E402

from wc1 import (gfx, shape, tables, refscene,
                 mission as wcmission)                             # noqa: E402
from wc1.packet import PacketFile, PacketError          # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO_ROOT, 'games', 'wingcommander', 'assets')

# Stored sprite resolution relative to the 128x96 screen, x64.
SHIP_RES = 80           # 1.25x - fighters and capital ships
# A ship frame must fit the game's largest frame buffer (wcdata.POOLS):
# capital ships that would be bigger are stored coarser.
MAX_SHIP_PIXELS = 3600
MAX_FX_PIXELS = 1400    # per frame; larger effect frames are stored coarser

# ship type -> data file (INSTALL.DAT logical file = type + 23)
SHIP_FILES = {
    0: 'SHIPTYPE.V00', 1: 'SHIPTYPE.V01', 2: 'SHIPTYPE.V02',
    3: 'SHIPTYPE.V03', 4: 'SHIP.V04', 5: 'SHIP.V05', 6: 'SHIP.V06',
    7: 'SHIP.V07', 8: 'SHIP.V08', 9: 'SHIPTYPE.V09', 10: 'SHIPTYPE.V10',
    11: 'SHIPTYPE.V11', 12: 'SHIPTYPE.V12', 13: 'SHIPTYPE.V13',
    14: 'SHIPTYPE.V14', 15: 'SHIP.V15', 16: 'SHIP.V16', 17: 'SHIP.V17',
    18: 'SHIP.V18', 19: 'SHIP.V19', 20: 'SHIP.V20', 21: 'SHIP.V21',
}
MISSILE_FILE = 'SHIPTYPE.V29'

# OBJECTS.VGA section -> what it is (wc1-re src/logic.c resource lists)
FX_SECTIONS = {
    0: 'thrusters', 1: 'explosion0', 2: 'explosion1', 3: 'explosion2',
    4: 'debris', 5: 'hull debris', 6: 'laser bolt', 7: 'mass driver bolt',
    8: 'neutron bolt', 9: 'laser spark', 10: 'blue spark', 11: 'red spark',
    12: 'spark trail', 13: 'rock chunk', 14: 'jump flash', 15: 'mine',
    16: 'asteroid a', 17: 'asteroid b',
}

# Cockpit layout per player ship (wc1-re src/data.c stCockpitLayout and
# packet 6 of each PCSHIP file): radar centre and half size, left and
# right display rectangles - all in 320x200 coordinates.
COCKPIT_SCANNER = [(159, 126, 14, 13), (103, 132, 14, 13),
                   (160, 39, 14, 13), (159, 129, 14, 13)]
COCKPIT_LEFT_VDU = [(10, 133, 82, 198), (0, 99, 73, 165),
                    (6, 1, 78, 66), (11, 111, 84, 176)]
COCKPIT_RIGHT_VDU = [(236, 133, 309, 198), (246, 97, 319, 165),
                     (241, 1, 313, 66), (235, 111, 308, 176)]

MISSION_COUNT = 64
NAV_BYTES = 16 * 77
OBJECTIVE_BYTES = 16 * 64
SHIP_BYTES = 32 * 42
MISSION_AUX = 40
MISSION_STRIDE = 24 + NAV_BYTES + OBJECTIVE_BYTES + SHIP_BYTES + MISSION_AUX

# Talking heads and cutscenes. The conversation window is 320x129 in the
# original (the talking-head picture, wc1-re src/screens.c) and 128x62 on
# the device; cutscene object positions are kept in 8.7 fixed point (one
# unit per device pixel) so that x = 320 still fits an i16 - the 8.8 first
# planned in docs/06 would overflow it.
HEAD_MAGIC = b'WCH1'
BACKDROP_MAGIC = b'WBD1'
SCENE_MAGIC = b'WCG1'
PIC_W, PIC_H = 128, 62

# scene type -> conversation backdrop shape (wc1-re src/cmpgn.c:215-257,
# the three shapes LoadFace picks per conversation, plus the two rooms
# the hard-coded scenes add: the Colonel's office (Office, cmpgn.c:565)
# and the medal room (AwardCampaignMedal, screens.c:301-302). Scene
# type 3, the funeral, has no backdrop: CloseTalk clears the picture
# and draws the constellation instead (cmpgn.c:440-442).
BACKDROP_SHAPES = [
    (0, 'BRIEFING.VGA', 0),   # the briefing room
    (1, 'BRIEFING.VGA', 6),   # the debriefing room
    (2, 'RECROOM.VGA', 1),    # the rec room / the bar
    (4, 'BRIEFING.VGA', 7),   # the Colonel's office
    (5, 'BRIEFING.VGA', 10),  # the medal room
]

# (type, character, frame) for every character the original gives a
# backdrop; the bdrop.wc entry key is type * 16 + character. The frame
# numbers are the nConversationBackdropFrame picks of LoadFace
# (cmpgn.c:215-257), the same for every room; the office and the medal
# room cover every character the ceremony packets can name.
BACKDROP_KEYS = [
    (0, 0, 4), (0, 1, 5), (0, 2, 0), (0, 3, 1), (0, 4, 2),
    (0, 8, 1), (0, 9, 2),
    (1, 10, 0), (1, 11, 1), (1, 12, 0), (1, 13, 1),
    (2, 2, 0), (2, 3, 1), (2, 4, 2),
    (4, 0, 4), (4, 1, 5), (4, 2, 0), (4, 3, 1), (4, 4, 2),
    (4, 8, 1), (4, 9, 2),
    (4, 10, 0), (4, 11, 1), (4, 12, 0), (4, 13, 1),
    (5, 0, 4), (5, 1, 5), (5, 2, 0), (5, 3, 1), (5, 4, 2),
    (5, 8, 1), (5, 9, 2),
    (5, 10, 0), (5, 11, 1), (5, 12, 0), (5, 13, 1),
]

# Hard-coded cutscene sprites (docs/06 6.2). Archive -> section, taken
# from the FetchDiskPacketRetrying calls of the hard-coded sequences in
# wc1-re src/cutscene.c and src/launch.c. The files use the same .wcs
# layout as the flight sprites (tool/wc1/gfx.py write_sprite_set).
SCRAMBLE_SECTIONS = {
    0: 'hangar walk',        # cutscene.c:300-301
    1: 'deck background',    # cutscene.c:466-473
    2: 'scramble canopy',    # cutscene.c:648-649
    3: 'ship body',          # cutscene.c:650-651
    4: 'deck crew',          # cutscene.c:652
    5: 'landing scroll',     # cutscene.c:850-851
    6: 'landing canopy',     # cutscene.c:853-854
    7: 'launch door',        # launch.c:118-119
    8: "Tiger's Claw",       # launch.c:192-193
    9: 'damage decal',       # cutscene.c:848-849
}

# PCSHIP.V0N section -> cockpit piece used by the hard-coded scenes
CK_CUTSCENE_SECTIONS = {
    8: 'cksc',       # scramble cockpit shapes, cutscene.c:643-644
    0: 'ckint',      # cockpit interior, eject.c:117-118
    3: 'ckbg',       # cockpit space backdrop, screens.c:1711-1712
    5: 'ckslide',    # ejection cockpit slide, eject.c:119-120
}

# PILOTANM.VGA sections used by death_sequence / ejection_sequence
# (screens.c:1710, eject.c:50). Section 2 is the ejected pilot of the
# 3-D chase (eject.c:97-99, :169).
PILOTANM_SECTIONS = {0: 'death face', 1: 'ejection seat',
                     2: 'ejected pilot'}

# BRIEFING.VGA sections drawn by the room scenes the conversation
# director dispatches (docs/05 5.2, docs/06 6.2). Every fetch cited is
# FetchDiskPacketRetrying(4, section, 0) on logical file 4.
BRIEFING_SECTIONS = {
    0: 'briefing room',      # screens.c:193-194 backdrop halves
    1: 'briefing animation', # screens.c:195-196 pilots walking in
    2: 'podium',             # screens.c:1484-1485, 776-777 colonel
    3: 'briefing closeup',   # screens.c:197-198 seated colonel
    4: 'briefing bodies',    # screens.c:199-200, 1523-1528
    5: 'briefing portraits', # screens.c:201-202, 1514-1522
    6: 'debriefing room',    # cmpgn.c:527-528 backdrop pieces
    7: 'office',             # cmpgn.c:564-565 the Colonel's office
    8: 'medal room',         # screens.c:224-228, 300-301 medals
    9: 'funeral',            # cutscene.c:1163-1165 casket and guards
    10: 'medal backdrop',    # screens.c:301-302 the room behind
}


class Converter:
    def __init__(self, src, out, preview=False, verbose=True):
        gamedat = os.path.join(src, 'GAMEDAT')
        if not os.path.isdir(gamedat):
            gamedat = src
        if not os.path.isfile(self._find(gamedat, 'GAME.PAL') or ''):
            raise SystemExit('error: %s does not look like a Wing '
                             'Commander GAMEDAT directory (GAME.PAL is '
                             'missing)' % gamedat)
        self.gamedat = gamedat
        self.out = out
        self.preview = preview
        self.verbose = verbose
        self.total = 0
        os.makedirs(out, exist_ok=True)
        self.palette = gfx.Palette(
            shape.read_palette(self._find(gamedat, 'GAME.PAL')))
        self._packets = {}

    # --- helpers -------------------------------------------------------
    @staticmethod
    def _find(directory, name):
        """Case-insensitive file lookup (DOS names, Unix file systems)."""
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
        low = name.lower()
        try:
            for entry in os.listdir(directory):
                if entry.lower() == low:
                    return os.path.join(directory, entry)
        except OSError:
            pass
        return None

    def has(self, name):
        return self._find(self.gamedat, name) is not None

    def packet(self, name):
        if name not in self._packets:
            path = self._find(self.gamedat, name)
            if path is None:
                raise PacketError('%s is missing from %s'
                                  % (name, self.gamedat))
            self._packets[name] = PacketFile(path)
        return self._packets[name]

    def log(self, text):
        if self.verbose:
            print(text)

    def path(self, name):
        return os.path.join(self.out, name)

    def write(self, name, data):
        with open(self.path(name), 'wb') as f:
            f.write(data)
        self.total += len(data)
        return len(data)

    def save_preview(self, name, frames):
        if not self.preview:
            return
        from PIL import Image
        frames = [f for f in frames if f is not None]
        if not frames:
            return
        cw = max(f[0].shape[1] for f in frames) + 1
        ch = max(f[0].shape[0] for f in frames) + 1
        cols = min(len(frames), 10)
        rows = (len(frames) + cols - 1) // cols
        img = np.zeros((rows * ch, cols * cw, 3), dtype=np.uint8)
        img[...] = (48, 0, 48)
        for i, (pix, _hx, _hy) in enumerate(frames):
            y = (i // cols) * ch
            x = (i % cols) * cw
            h, w = pix.shape
            rgb = self.palette.rgb[pix].astype(np.uint8)
            mask = pix != 0
            img[y:y + h, x:x + w][mask] = rgb[mask]
        pdir = os.path.join(self.out, '_preview')
        os.makedirs(pdir, exist_ok=True)
        Image.fromarray(img).resize((img.shape[1] * 3, img.shape[0] * 3),
                                    Image.NEAREST).save(
            os.path.join(pdir, name + '.png'))

    def scaled_set(self, frames, res):
        sx = gfx.SCREEN_SX * res / 64
        sy = gfx.SCREEN_SY * res / 64
        return [gfx.scale_frame(f, self.palette, sx, sy) for f in frames]

    # --- conversions ---------------------------------------------------
    def convert_palette(self):
        self.write('pal.wc', self.palette.as_rgb565_bytes())

    def convert_types(self):
        """types.wc: struct-of-arrays so the device can slurp each field
        into an array('i') without parsing.

            u8 type count, u8 field count, u8 max weapons, u8 name size
            fields[field count][type count]  int32
            weapons[type count][1 + max weapons * 3]  bytes
            names[type count][name size]
            i16 child offsets[56][3]
            i8  direction frame[186], direction flip[186]
            animations: u16 offset[type count] into the u16 stream that
                        follows (0xFFFF = none), u16 stream length, data
        """
        types = tables.TYPES
        n = len(types)
        fields = []
        for t in types:
            (_id, _name, cls, radius, mass, scale, anim_delay, lifetime,
             damage, expl, max_vel, cruise, accel, pitch, yaw, roll, ab,
             shield, armor, _weapons, _anim) = t
            fields.append([cls, radius, mass, scale, anim_delay, lifetime,
                           damage, expl, max_vel, cruise, accel, pitch, yaw,
                           roll, ab, shield[0], shield[1], armor[0],
                           armor[1], armor[2], armor[3]])
        n_fields = len(fields[0])
        max_weapons = 10
        name_size = 14
        out = bytearray(struct.pack('<BBBB', n, n_fields, max_weapons,
                                    name_size))
        for fi in range(n_fields):
            out += struct.pack('<%di' % n, *[fields[t][fi] for t in range(n)])
        for t in types:
            weapons = t[19]
            rec = bytearray(1 + max_weapons * 3)
            rec[0] = len(weapons)
            for i, (wtype, hardpoint, disabled) in enumerate(weapons):
                rec[1 + i * 3] = wtype
                rec[2 + i * 3] = hardpoint
                rec[3 + i * 3] = disabled & 0xFF
            out += rec
        for t in types:
            out += t[1].encode('latin1')[:name_size - 1].ljust(name_size,
                                                                b'\0')
        for c in tables.CHILD_OFFSETS:
            out += struct.pack('<3h', *c)
        out += struct.pack('<186b', *tables.DIR_FRAME)
        out += struct.pack('<186b', *tables.DIR_FLIP)
        stream = []
        offsets = []
        for t in types:
            anim = t[20]
            if anim:
                offsets.append(len(stream))
                stream += [a & 0xFFFF for a in anim]
            else:
                offsets.append(0xFFFF)
        out += struct.pack('<%dH' % n, *offsets)
        out += struct.pack('<H', len(stream))
        out += struct.pack('<%dH' % len(stream), *stream)
        self.write('types.wc', bytes(out))

    def convert_ai(self):
        """ai.wc: the tables the game keeps inside WC.EXE besides the
        object types (see tool/wc1/tables.py for where each comes from).

            4s   'WCA1'
            5 x  (u8 n, n x u8)        defence manoeuvres per pilot level
            i8   rated[13][9][3][3]    named pilots: threshold, a, b
            i8   kilrathi[5][9][3][3]
            i8   aggression[24], recovery[20]
            u8   turn interval[18]
            i16  formation[5][8][3]
            u8   gun refire delay[4]
            u8   conversation colours[12]
            9 x  (14s name, 14s callsign, u8 rank, u8 missions, u8 kills)
            5 x  10s rank name, 5 x 24s medal name
            u8   player damage systems[5][10]
        """
        t = tables
        out = bytearray(b'WCA1')
        for lst in t.DEFENSE_MANEUVERS:
            out += bytes([len(lst)] + lst)
        out += struct.pack('<%db' % len(t.RATED_MANEUVERS),
                           *t.RATED_MANEUVERS)
        out += struct.pack('<%db' % len(t.KILRATHI_MANEUVERS),
                           *t.KILRATHI_MANEUVERS)
        out += struct.pack('<24b', *t.PILOT_AGGRESSION)
        out += struct.pack('<20b', *t.PILOT_RECOVERY)
        out += bytes(t.PILOT_TURN_INTERVAL)
        out += struct.pack('<120h', *t.FORMATION_POSITIONS)
        out += bytes(t.GUN_REFIRE_DELAY)
        out += bytes(t.CONVERSATION_COLOURS)
        for name, callsign, _portrait, rank, missions, kills, _p in t.PILOTS:
            out += name.encode('latin1').ljust(14, b'\0')
            out += callsign.encode('latin1').ljust(14, b'\0')
            out += bytes([rank, missions, kills])
        for name in t.RANK_NAMES:
            out += name.encode('latin1').ljust(10, b'\0')
        for name in t.MEDAL_NAMES:
            out += name.encode('latin1').ljust(24, b'\0')
        out += bytes(t.PLAYER_DAMAGE_SYSTEMS)
        self.write('ai.wc', bytes(out))

    def convert_ships(self):
        for ship_type, filename in sorted(SHIP_FILES.items()):
            if not self.has(filename):
                self.log('  ship %2d: %s not present, skipped'
                         % (ship_type, filename))
                continue
            pk = self.packet(filename)
            if filename.startswith('SHIPTYPE'):
                frames = shape.decode_all(pk.section(0))
            else:
                # capital ships: one view per section
                frames = []
                for i in range(37):
                    data = pk.section(i) if i < len(pk) else b''
                    frames.append(shape.decode_frame(data, 0)
                                  if len(data) >= 8 else None)
            frames = (frames + [None] * 37)[:37]
            for res in range(SHIP_RES, 31, -2):
                scaled = self.scaled_set(frames, res)
                biggest = max((f[0].size for f in scaled if f), default=0)
                if biggest <= MAX_SHIP_PIXELS:
                    break
            name = 'sh%02d' % ship_type
            size = gfx.write_sprite_set(self.path(name + '.wcs'), scaled,
                                        res)
            self.total += size
            self.save_preview(name, scaled)
            self.log('  ship %2d %-13s %2d views res %2d %7d bytes'
                     % (ship_type, tables.TYPES[ship_type][1],
                        sum(f is not None for f in scaled), res, size))

    def convert_missiles(self):
        frames = shape.decode_all(self.packet(MISSILE_FILE).section(0))
        scaled = self.scaled_set(frames, SHIP_RES)
        self.total += gfx.write_sprite_set(self.path('ms.wcs'), scaled,
                                           SHIP_RES)
        self.save_preview('ms', scaled)

    def convert_effects(self):
        pk = self.packet('OBJECTS.VGA')
        for section, label in sorted(FX_SECTIONS.items()):
            frames = shape.decode_all(pk.section(section))
            biggest = max((f.width * f.height for f in frames if f),
                          default=1)
            res = SHIP_RES
            for res in (80, 64, 48, 40, 32, 24, 16):
                px = biggest * (gfx.SCREEN_SX * res / 64) * \
                    (gfx.SCREEN_SY * res / 64)
                if px <= MAX_FX_PIXELS:
                    break
            scaled = self.scaled_set(frames, res)
            name = 'fx%02d' % section
            size = gfx.write_sprite_set(self.path(name + '.wcs'), scaled,
                                        res)
            self.total += size
            self.save_preview(name, scaled)
            self.log('  fx %2d %-16s %2d frames res %2d %6d bytes'
                     % (section, label, len(frames), res, size))

    def convert_hud(self):
        # COCKPIT.VGA section 0: gun cross, lock ring, ...; kept at
        # screen scale and drawn unscaled.
        frames = shape.decode_all(self.packet('COCKPIT.VGA').section(0))
        scaled = self.scaled_set(frames, 64)
        self.total += gfx.write_sprite_set(self.path('hud.wcs'), scaled, 64)
        self.save_preview('hud', scaled)

    def convert_cockpits(self):
        """ck<N>.wc: the front cockpit of player ship N.

            4s  'WCK1'
            u8  view x, y, w, h        space window inside the picture
            u8  radar cx, cy, rx, ry
            u8  left display x0, y0, x1, y1
            u8  right display x0, y0, x1, y1
            128x96 bytes, 8-bit palette indices, 0 = see-through
        """
        sx, sy = gfx.SCREEN_SX, gfx.SCREEN_SY
        for ship in range(4):
            name = 'PCSHIP.V0%d' % ship
            if not self.has(name):
                continue
            pk = self.packet(name)
            frame = shape.decode_frame(pk.section(0), 0)
            canvas = np.zeros((200, 320, 4), dtype=np.float32)
            rgba = gfx.frame_to_rgba(frame, self.palette)
            canvas[:frame.height, :frame.width] = rgba[:200, :320]
            small = gfx.quantize(gfx.resample(canvas, 128, 96),
                                 self.palette, threshold=0.5)
            geo = pk.section(6)
            first = struct.unpack_from('<h', geo, 2)[0]
            vw, vh, vx, vy = struct.unpack_from('<4h', geo, first)
            head = bytearray(b'WCK1')
            head += bytes([int(vx * sx), int(vy * sy),
                           min(128, int(round(vw * sx))),
                           int(round(vh * sy))])
            cx, cy, rx, ry = COCKPIT_SCANNER[ship]
            head += bytes([int(round(cx * sx)), int(round(cy * sy)),
                           max(3, int(rx * sx)), max(3, int(ry * sy))])
            for rect in (COCKPIT_LEFT_VDU[ship], COCKPIT_RIGHT_VDU[ship]):
                head += bytes([int(rect[0] * sx), int(rect[1] * sy),
                               int(rect[2] * sx), int(rect[3] * sy)])
            self.write('ck%d.wc' % ship, bytes(head) + small.tobytes())
            if self.preview:
                self.save_preview('ck%d' % ship, [(small, 0, 0)])
            self.log('  cockpit %d: view %dx%d at %d,%d'
                     % (ship, head[6], head[7], head[4], head[5]))

    def convert_fonts(self):
        """font<N>.wc: u8 height, u8 bytes per row, u8 widths[256], then
        256 glyphs of height * bytes-per-row bytes, MSB = left pixel."""
        pk = self.packet('FONTS.FNT')
        for index in range(len(pk)):
            data = pk.section(index)
            height = struct.unpack_from('<H', data, 0)[0]
            ink = data[2]
            widths = data[4:4 + 256]
            bpr = (max(widths) + 7) // 8
            out = bytearray([height, bpr]) + bytes(widths)
            for ch in range(256):
                w = widths[ch]
                off = (data[0x204 + ch] << 8) | data[0x104 + ch]
                for row in range(height):
                    bits = 0
                    for col in range(w):
                        p = off + row * w + col
                        if p < len(data) and data[p] == ink:
                            bits |= 1 << (bpr * 8 - 1 - col)
                    out += bits.to_bytes(bpr, 'big')
            self.write('font%d.wc' % index, bytes(out))
            self.log('  font %d: height %d, %d bytes' % (index, height,
                                                         len(out)))

    def convert_campaign(self, campaign):
        """mod<C>.wc / camp<C>.wc / brf<C>.wc - the mission, campaign and
        conversation records exactly as the game reads them, unpacked
        from their archives and laid out for seek-and-read access."""
        suffix = '.%03d' % campaign
        if not self.has('MODULE' + suffix):
            return False
        module = self.packet('MODULE' + suffix)
        header, nav, obj, ships, aux, series_aux = (
            module.section(i) for i in range(6))
        out = bytearray(b'WCM1' + struct.pack('<HH', MISSION_COUNT,
                                              MISSION_STRIDE))
        for m in range(MISSION_COUNT):
            rec = (header[m * 24:(m + 1) * 24] +
                   nav[m * NAV_BYTES:(m + 1) * NAV_BYTES] +
                   obj[m * OBJECTIVE_BYTES:(m + 1) * OBJECTIVE_BYTES] +
                   ships[m * SHIP_BYTES:(m + 1) * SHIP_BYTES] +
                   aux[m * MISSION_AUX:(m + 1) * MISSION_AUX])
            out += rec.ljust(MISSION_STRIDE, b'\0')
        out += series_aux
        self.write('mod%d.wc' % campaign, bytes(out))

        camp = self.packet('CAMP' + suffix)
        sections = [camp.section(i) for i in range(len(camp))]
        blob = bytearray(b'WCC1' + struct.pack('<B', len(sections)))
        for s in sections:
            blob += struct.pack('<H', len(s))
        for s in sections:
            blob += s
        self.write('camp%d.wc' % campaign, bytes(blob))

        brief = self.packet('BRIEFING' + suffix)
        n = len(brief)
        index = bytearray()
        body = bytearray()
        base = 8 + n * 8
        for i in range(n):
            data = brief.section(i)
            index += struct.pack('<II', base + len(body) if data else 0,
                                 len(data))
            body += data
        self.write('brf%d.wc' % campaign,
                   b'WCB1' + struct.pack('<I', n) + bytes(index) +
                   bytes(body))
        self.log('  campaign %d: %d briefing packets' % (campaign, n))
        return True

    def convert_comm(self):
        for src, dst in (('COMMUNIC.DAT', 'comm.wc'),
                         ('COMMSM2.DAT', 'comm2.wc')):
            path = self._find(self.gamedat, src)
            if path:
                with open(path, 'rb') as f:
                    self.write(dst, f.read())

    def convert_pictures(self):
        """Full pictures in the engine's own .COL.bin format. `rows` is
        how much of the 320x200 original is kept (from the top)."""
        jobs = [
            # (output, file, section, frame, source rows)
            ('title_128_96', 'TITLE.VGA', 5, 0, 200),
            ('recroom_128_96', 'RECROOM.VGA', 0, 0, 200),
            ('bar_128_61', 'RECROOM.VGA', 0, 0, 128),
            ('brief_128_61', 'BRIEFING.VGA', 0, 0, 128),
            ('debrief_128_61', 'BRIEFING.VGA', 6, 0, 128),
        ]
        for out_name, filename, section, frame_index, rows in jobs:
            if not self.has(filename):
                continue
            pk = self.packet(filename)
            if section >= len(pk):
                continue
            frame = shape.decode_frame(pk.section(section), frame_index)
            if frame is None:
                continue
            rgb = gfx.picture(frame, self.palette, out_w=128,
                              out_h=int(round(rows * gfx.SCREEN_SY)),
                              src_h=rows)
            path = self.path(out_name + '.COL.bin')
            gfx.write_col_bin(path, rgb)
            self.total += os.path.getsize(path)
        old = self.path('title.COL.bin')
        if os.path.exists(old):
            os.remove(old)

    # --- talking heads and cutscenes (docs/05, docs/06) ---------------

    def _paste(self, canvas, img, px, py):
        """Paste scaled indexed pixels onto an indexed canvas with the
        image's top-left at (px, py) - possibly negative, clipped to the
        canvas. Index 0 keeps whatever is underneath, exactly like the
        original sprite blitter."""
        ch, cw = canvas.shape
        ih, iw = img.shape
        # canvas row y shows source row y - py, so valid rows are
        # py <= y < ih + py (and likewise for columns)
        ys, ye = max(0, py), min(ch, ih + py)
        xs, xe = max(0, px), min(cw, iw + px)
        if ye <= ys or xe <= xs:
            return
        src = img[ys - py:ye - py, xs - px:xe - px]
        old = canvas[ys:ye, xs:xe]
        canvas[ys:ye, xs:xe] = np.where(src == 0, old, src)

    def _bake_stars(self, canvas, stars, rng):
        """The bar backdrop is transparent in its upper half: the
        starfield behind the window. Bake a fixed sprinkle of star
        sprites (PLANETS.VGA section 0) onto those pixels so the device
        sees the same sky; rows 0..36 map to original rows 0..76."""
        overlay = np.zeros(canvas.shape, dtype=np.uint8)
        for _ in range(24):
            fr = stars[rng.randint(0, len(stars))] if stars else None
            if fr is None:
                continue
            img, hx, hy = fr
            self._paste(overlay, img, rng.randint(2, 125) - hx,
                        rng.randint(2, 37) - hy)
        return np.where(canvas == 0, overlay, canvas)

    def _backdrop_canvas(self, frame):
        """One conversation backdrop frame -> 128x62 indexed pixels."""
        canvas = np.zeros((129, 320, 4), dtype=np.float32)
        rgba = gfx.frame_to_rgba(frame, self.palette)
        h, w = rgba.shape[:2]
        canvas[:min(h, 129), :min(w, 320)] = rgba[:129, :320]
        return gfx.quantize(gfx.resample(canvas, PIC_W, PIC_H),
                            self.palette, threshold=0.5)

    def convert_backdrops(self):
        """bdrop.wc: the conversation backdrops. The scene type picks the
        room, the character picks the frame (wc1-re src/cmpgn.c:215-257).

            4s  'WBD1'
            u8  entry count
            per entry: u8 key, u8 flags          key = type*16 + character
                                                  flags bit0: stars baked
            bodies in table order: 128x62 indexed pixels, index 0 keeps
            the previous picture
        """
        shapes = {}
        for kind, filename, section in BACKDROP_SHAPES:
            shapes[kind] = shape.decode_all(
                self.packet(filename).section(section))
        stars = []
        if self.has('PLANETS.VGA'):
            star_frames = shape.decode_all(
                self.packet('PLANETS.VGA').section(0))
            stars = self.scaled_set(star_frames[32:38], 64)
        rng = np.random.RandomState(1990)
        table = bytearray()
        bodies = []
        for kind, char, index in sorted(BACKDROP_KEYS):
            frames = shapes[kind]
            frame = frames[index] if index < len(frames) else None
            if frame is None:
                self.log('  backdrop type %d char %d: frame %d missing'
                         % (kind, char, index))
                continue
            img = self._backdrop_canvas(frame)
            flags = 0
            if kind == 2:
                img = self._bake_stars(img, stars, rng)
                flags = 1
            table += struct.pack('<BB', kind * 16 + char, flags)
            bodies.append(img)
        out = bytearray(BACKDROP_MAGIC)
        out.append(len(bodies))
        out += table
        for img in bodies:
            out += img.tobytes()
        size = self.write('bdrop.wc', bytes(out))
        self.log('  backdrops: %d frames, %d bytes' % (len(bodies), size))
        self.save_preview('bdrop', [(b, 0, 0) for b in bodies])

    def convert_heads(self):
        """head<NN>.wc: one talking-head face. Face f < 11 is TALKING.VGA
        section f; faces 11 and 12 (Doomsday, Jazz) are TALKING1.VGA
        sections 0 and 1 (wc1-re src/cmpgn.c LoadFace). A face section
        holds 0 = the 320x129 head, 1..10 = mouths drawn at
        mouthX/mouthY when mouthFrame == i, 11..20 = eyes at
        faceX/faceY when faceFrame == i. Each patch stores the head
        composited with one frame, so the device pastes it over the
        base picture and gets the original's full-draw result.

            4s  'WCH1'
            u8  reserved, u8 reserved, u8 w, u8 h        (128, 62)
            u8  mouth x0, y0, w, h
            u8  eye x0, y0, w, h
            base: w*h indexed pixels
            ten mouth patches of mouth w * h bytes
            ten eye patches of eye w * h bytes
        """
        sx, sy = gfx.SCREEN_SX, gfx.SCREEN_SY
        pk = self.packet('TALKING.VGA')
        faces = [(f, pk.section(f)) for f in range(11)]
        if self.has('TALKING1.VGA'):
            pk2 = self.packet('TALKING1.VGA')
            faces += [(11, pk2.section(0)), (12, pk2.section(1))]
        for face, data in faces:
            frames = shape.decode_all(data) if data else []
            if not frames or frames[0] is None:
                self.log('  head %d: no face frame, skipped' % face)
                continue
            if face < 11:
                fx, fy, mx, my = tables.TALKING_HEAD_ORIGINS[face]
            else:
                fx, fy, mx, my = tables.SM2_HEAD_ORIGINS[face]

            base = np.zeros((PIC_H, PIC_W), dtype=np.uint8)
            scaled = gfx.scale_frame(frames[0], self.palette, sx, sy)
            if scaled is None:
                self.log('  head %d: head frame empty, skipped' % face)
                continue
            self._paste(base, scaled[0], -scaled[1], -scaled[2])

            def patches(items, ox, oy):
                spots = []
                for fr in items:
                    sc = gfx.scale_frame(fr, self.palette, sx, sy)
                    if sc is None:
                        spots.append(None)
                        continue
                    img, hx, hy = sc
                    px = int(round(ox * sx)) - hx
                    py = int(round(oy * sy)) - hy
                    ys, ye = max(0, py), min(PIC_H, img.shape[0] + py)
                    xs, xe = max(0, px), min(PIC_W, img.shape[1] + px)
                    if ye <= ys or xe <= xs:
                        spots.append(None)      # wholly off the canvas
                        continue
                    spots.append((img, px, py, xs, xe, ys, ye))
                live = [s for s in spots if s]
                if not live:
                    return (0, 0, 0, 0), [np.zeros((0, 0), np.uint8)
                                          for _ in items]
                x0 = min(s[3] for s in live)
                x1 = max(s[4] for s in live)
                y0 = min(s[5] for s in live)
                y1 = max(s[6] for s in live)
                tiles = []
                for s in spots:
                    if s is None:
                        tiles.append(np.zeros((y1 - y0, x1 - x0),
                                              dtype=np.uint8))
                        continue
                    img, px, py = s[0], s[1], s[2]
                    tile = base.copy()
                    self._paste(tile, img, px, py)
                    tiles.append(tile[y0:y1, x0:x1])
                return (int(x0), int(y0), int(x1 - x0), int(y1 - y0)), tiles

            def pad(tiles):
                """TALKING1.VGA sections hold only 20 frames, so the
                last eye patch of faces 11/12 has no source; the format
                always stores ten of each and the device draws nothing
                for a zero patch."""
                if len(tiles) < 10:
                    shape = tiles[-1].shape if tiles else (0, 0)
                    tiles = tiles + [np.zeros(shape, dtype=np.uint8)
                                     for _ in range(10 - len(tiles))]
                return tiles

            m_rect, m_tiles = patches(frames[1:11], mx, my)
            e_rect, e_tiles = patches(frames[11:21], fx, fy)
            m_tiles = pad(m_tiles)
            e_tiles = pad(e_tiles)

            out = bytearray(HEAD_MAGIC)
            out += bytes([0, 0, PIC_W, PIC_H])
            out += bytes(m_rect)
            out += bytes(e_rect)
            out += base.tobytes()
            for tile in m_tiles:
                out += tile.tobytes()
            for tile in e_tiles:
                out += tile.tobytes()
            size = self.write('head%02d.wc' % face, bytes(out))
            self.log('  head %2d: mouth %s eye %s, %d bytes'
                     % (face, m_rect, e_rect, size))
            if self.preview:
                states = [base]
                for i in range(10):
                    comp = base.copy()
                    if e_tiles[i].size:
                        self._paste(comp, e_tiles[i], e_rect[0],
                                    e_rect[1])
                    if m_tiles[i].size:
                        self._paste(comp, m_tiles[i], m_rect[0],
                                    m_rect[1])
                    states.append(comp)
                self.save_preview('head%02d' % face,
                                  [(s, 0, 0) for s in states])

    def convert_overlay(self):
        """ovl.wcs: the conversation overlay frames (TALKING.VGA section
        11), drawn over the whole picture when the scene sets the flag."""
        pk = self.packet('TALKING.VGA')
        if len(pk) <= 11:
            self.log('  overlay: TALKING.VGA has no section 11, skipped')
            return
        scaled = self.scaled_set(shape.decode_all(pk.section(11)), 64)
        size = gfx.write_sprite_set(self.path('ovl.wcs'), scaled, 64)
        self.total += size
        self.save_preview('ovl', scaled)

    def convert_intro_word(self):
        """meanwhile_128_62.COL.bin: "Meanwhile..." set in the intro font
        (TITLE.VGA section 1; glyph index ord(c) - 65 for upper and
        lower case alike, '.' is index 58, advance width + 2), centred
        as the original centres a subtitle line. The cutscene shows it
        in the conversation window before the animation starts."""
        pk = self.packet('TITLE.VGA')
        glyphs = shape.decode_all(pk.section(1)) if len(pk) > 1 else []

        def glyph_index(ch):
            return 58 if ch == '.' else ord(ch) - 65

        def glyph(ch):
            i = glyph_index(ch)
            return glyphs[i] if i < len(glyphs) else None

        word = 'Meanwhile...'
        widths = [g.width if g is not None else 8 for g in
                  (glyph(ch) for ch in word)]
        x = (320 - sum(w + 2 for w in widths)) // 2
        canvas = np.zeros((129, 320, 4), dtype=np.float32)
        for ch, w in zip(word, widths):
            fr = glyph(ch)
            if fr is None:
                x += w + 2
                continue
            rgba = gfx.frame_to_rgba(fr, self.palette)
            px = x - fr.left
            py = 56 - fr.top
            rh, rw = rgba.shape[:2]
            ys, ye = max(0, py), min(129, rh + py)
            xs, xe = max(0, px), min(320, rw + px)
            if ye > ys and xe > xs:
                canvas[ys:ye, xs:xe] = rgba[ys - py:ye - py,
                                            xs - px:xe - px]
            x += w + 2
        small = gfx.resample(canvas, PIC_W, PIC_H)
        rgb = np.clip(small[..., :3], 0, 255)      # over black already
        path = self.path('meanwhile_128_62.COL.bin')
        gfx.write_col_bin(path, rgb)
        size = os.path.getsize(path)
        self.total += size
        self.log('  meanwhile word: %d bytes' % size)
        self.save_preview('meanwhile',
                          [(gfx.quantize(small, self.palette, threshold=0.5),
                            0, 0)])

    def _compile_script(self, script, layer, start):
        """Re-emit one object's bytecode stream as device instructions,
        4-byte '<BBh' records. The original commands survive verbatim -
        X/Y values stay in the original pixel space, so the device
        integrates positions, deltas and goals exactly like the
        original does (logic.c:2431-2450) and only the draw site scales
        to device pixels. The 'D' / 'E' groups become runs of 'D' (draw)
        instructions closed by 'N' / 'E': the group's first DRAW takes
        the place the 'D' opcode had, so re-entering the repeat cursor
        re-runs exactly the original group. A trailing 'K' stands for
        the terminating NUL byte - the cursor parks on it and re-reads
        it every turn, just like the original parks on the zero byte.

        Opcode operands: 'A'/'L'/'Q' carry a property byte and an i16
        value; 'B' carries its label number; 'G'/'J' the label to find;
        'R' the object set and index to copy; 'W' the global wait in
        frames. Anything else (X/P/S) does not occur in the cutscene
        data and is refused.
        """
        out = []
        pending = []
        labels = []
        pos = 0
        end = len(script)
        while pos < end and script[pos] != 0:
            op = script[pos]
            pos += 1
            if op in (0x41, 0x4C, 0x51):                   # A L Q
                prop = script[pos]; pos += 1
                value = struct.unpack_from('<h', script, pos)[0]
                pos += 2
                # X/Y values pass through raw: the device integrates
                # positions, deltas and goals in the original pixel
                # space exactly like the original (logic.c:2431-2450)
                out.append((chr(op), prop, value))
            elif op == 0x42:                                # B label
                value = struct.unpack_from('<h', script, pos)[0]
                pos += 2
                labels.append((value, start + len(out)))
                out.append(('B', 0, value))
            elif op == 0x44:                                # D group
                slot = start + len(out)
                frame = script[pos]; pos += 1
                i = 0
                while frame != 0xFF:
                    out.append(('D', frame & 0xFF,
                                i * 128 if layer == 0 else 0))
                    i += 1
                    frame = script[pos]; pos += 1
                out.append(('N', 0, slot))
            elif op == 0x45:                                # E group
                slot = start + len(out)
                frame = script[pos]; pos += 1
                i = 0
                while frame != 0xFF:
                    out.append(('D', frame & 0xFF, i * 128))
                    i += 1
                    frame = script[pos]; pos += 1
                out.append(('E', 0, slot))
            elif op in (0x47, 0x4A):                        # G / J
                value = struct.unpack_from('<h', script, pos)[0]
                pos += 2
                pending.append((value, start + len(out)))
                out.append((chr(op), 0, 0))
            elif op == 0x52:                                # R copy
                o_set = script[pos]; pos += 1
                o_index = script[pos]; pos += 1
                out.append(('R', o_set, o_index))
            elif op == 0x57:                                # W wait
                value = struct.unpack_from('<h', script, pos)[0]
                pos += 2
                out.append(('W', 0, value))
            else:
                raise ValueError('no device instruction for opcode %r'
                                 % chr(op))
        # The original FindSceneAnimationCommand scans from the script
        # start for the first 'B' whose value matches; labels were
        # emitted in that same order here, so the first hit is the same
        # label, and the jump lands on the command after its operand.
        for value, where in pending:
            hit = next((i for num, i in labels if num == value), None)
            if hit is None:
                raise ValueError('label %d not found' % value)
            op, _b1, _h = out[where - start]
            out[where - start] = (op, 0, hit + 1)
        out.append(('K', 0, 0))
        return out

    def _midgame_variant(self, name, pk, variant, pri_used):
        """Run one MIDGAME variant through the reference interpreter to
        learn which shapes it draws, then compile every object's script
        for the device. Empty variants (no defs at all) come out with
        all counts zero - the device ends those instantly."""
        sx, sy = gfx.SCREEN_SX, gfx.SCREEN_SY
        defs = pk.section(variant + 1)
        shape_data = pk.section(variant + 3)
        pkt = pk.section(variant + 5)
        per = count = nanim = 0
        objects = []
        start_state = []
        if defs:
            per, count, objects = refscene.read_disk_objects(defs)
            nanim = count // per if per else 0
            # the reference interpreter mutates these dicts in place
            # while it runs, so keep each object's disk staging state
            # (layer, frame, x, y, scale, rotation) for the device
            # records - the device replays the same bytecode from the
            # same start and
            # must agree with the reference at step zero (logic.c:2128
            # loads these fields once per PlaySceneAnimation call)
            start_state = [(o['layer'], o['frame'], o['x'], o['y'],
                            o['scale'], o['rotation']) for o in objects]
        drawn_sec = set()
        for a in range(nanim):
            anim = refscene.RefAnimation(defs, objects, a)
            steps = 0
            while not anim.finished:
                if steps >= 4096:
                    raise ValueError('%s variant %d animation %d does '
                                     'not finish' % (name, variant, a))
                # RefAnimation.step records nothing on its own - the
                # frames the original draws arrive through the draw
                # callback only (logic.c:2359,2377 draw sites)
                got = []
                anim.step(lambda layer, frame, x, y: got.append(
                    (layer, frame, x, y)))
                for layer, frame, _x, _y in got:
                    if layer == 0:
                        pri_used.add(frame & 0xFF)
                    elif layer == 1:
                        drawn_sec.add(frame & 0xFF)
                steps += 1
        recs = bytearray()
        instrs = bytearray()
        for i, obj in enumerate(objects):
            start = len(instrs) // 4
            # objects share bytecode streams: the script runs from
            # scriptOffset through the shared tail and ends at the
            # first NUL found at a command position - a NUL inside an
            # operand (label value 0!) is data, not a terminator, so
            # the tail is passed whole and _compile_script stops at
            # the terminating byte itself (logic.c:2291 loop test)
            script = defs[obj['scriptOffset']:]
            for op, b1, h in self._compile_script(script, obj['layer'],
                                                  start):
                instrs += struct.pack('<BBh', ord(op), b1 & 0xFF, h)
            # the record holds the disk staging position, not where the
            # reference left the object (start_state above): the device
            # replays the script from the start and must agree with the
            # reference at step zero. x and y are i32 original pixels:
            # the original runtime holds them as 32-bit ints and the
            # deltas accumulate unclamped (logic.c:2431-2450), so the
            # running position can leave the i16 range; the device
            # carries them the same way and scales only at draw time
            layer, frame, x, y, scale, rot = start_state[i]
            # rotation is stored because the draw site passes it on
            # (logic.c:2382: DrawSpriteScaled gets the rotation), and
            # four objects of MIDGAME.V02 hold 30 degrees. Flip needs
            # no field of its own: the frame byte doubles as the flip
            # bits (gr.c:541-551) and the shipped data only ever
            # reaches 0 and 16 at a draw call.
            recs += struct.pack('<BBiiHhh', layer, frame & 0xFF,
                                x, y, scale & 0xFFFF, start, rot)
        sec_frames = shape.decode_all(shape_data) if shape_data else []
        nsec = max(drawn_sec) + 1 if drawn_sec else 0
        sec_tbl = bytearray()
        sec_pix = bytearray()
        for idx in range(nsec):
            entry = (0, 0, 0, 0, 0)
            if idx in drawn_sec and idx < len(sec_frames):
                sc = gfx.scale_frame(sec_frames[idx], self.palette, sx, sy)
                if sc is not None:
                    img, hx, hy = sc
                    entry = (len(sec_pix), img.shape[1], img.shape[0],
                             max(-128, min(127, hx)),
                             max(-128, min(127, hy)))
                    sec_pix += img.tobytes()
            sec_tbl += struct.pack('<IBBbb', *entry)
        return dict(per=per, nanim=nanim, nobjs=count,
                    ninstrs=len(instrs) // 4, nsec=nsec,
                    pktlen=len(pkt), recs=bytes(recs),
                    instrs=bytes(instrs), sec_tbl=bytes(sec_tbl),
                    sec_pix=bytes(sec_pix), pkt=pkt)

    def _pri_blob(self, frames, used, sx, sy):
        """Scale the shared primary shapes the animations actually
        draw, once for the union over both variants."""
        n = max(used) + 1 if used else 0
        tbl = bytearray()
        blob = bytearray()
        for idx in range(n):
            entry = (0, 0, 0, 0, 0)
            if idx in used and idx < len(frames) and frames[idx]:
                sc = gfx.scale_frame(frames[idx], self.palette, sx, sy)
                if sc is not None:
                    img, hx, hy = sc
                    entry = (len(blob), img.shape[1], img.shape[0],
                             max(-128, min(127, hx)),
                             max(-128, min(127, hy)))
                    blob += img.tobytes()
            tbl += struct.pack('<IBBbb', *entry)
        return tbl, blob, n

    def convert_midgame(self):
        """mid<NN>.wc: one cutscene and its two outcome variants (the
        reference interpreter tool/wc1/refscene.py decides which shape
        frames an animation really draws; only those are scaled into the
        file; the bytecode streams are re-emitted for the device).

            4s   'WCG1'
            u8   cutscene number, u8 variant count (always 2)
            u16  primary frame count, u32 primary pixel blob offset
            per primary frame: u32 offset from the primary pixel blob,
                               u8 w, u8 h, i8 hot_x, i8 hot_y
            per variant: 6 x u16 objects per animation, animations,
                         object count, instruction count, shape frame
                         count, scene packet length; then 5 x u32
                         offsets of the object, instruction, shape
                         table, shape pixel and scene packet blocks
            blocks in variant order: objects, instructions, shape
            table, shape pixels, scene packet; then the primary pixel
            blob. Shape table pixel offsets are relative to the blob
            of their own variant; object records are 16 bytes
            '<BBiiHhh': layer, flip frame, x and y in the original
            pixel space (i32 - the original runtime holds x/y as
            32-bit ints and carries staging positions like -1280 and
            +1170 unclamped, and the device stores them the same way,
            scaling to device pixels only at the draw site), scale,
            index of the object's first instruction, rotation in
            degrees (the draw site
            passes it to DrawSpriteScaled, logic.c:2382).
        """
        sx, sy = gfx.SCREEN_SX, gfx.SCREEN_SY
        for scene in range(9):
            name = 'MIDGAME.V%02d' % scene
            if not self.has(name):
                self.log('  scene %d: %s not installed' % (scene, name))
                continue
            pk = self.packet(name)
            pri_used = set()
            variants = [self._midgame_variant(name, pk, v, pri_used)
                        for v in (0, 1)]
            pri_frames = shape.decode_all(pk.section(0)) \
                if pk.section(0) else []
            pri_tbl, pri_pix, npri = self._pri_blob(pri_frames, pri_used,
                                                    sx, sy)
            fixed = 12 + npri * 8 + len(variants) * 32
            out = bytearray(SCENE_MAGIC)
            out += bytes([scene, len(variants)])
            out += struct.pack('<H', npri)
            pos = fixed
            index = bytearray()
            for v in variants:
                v['obj_off'] = pos
                v['ins_off'] = pos + len(v['recs'])
                v['sectbl_off'] = v['ins_off'] + len(v['instrs'])
                v['secpix_off'] = v['sectbl_off'] + len(v['sec_tbl'])
                v['pkt_off'] = v['secpix_off'] + len(v['sec_pix'])
                pos = v['pkt_off'] + v['pktlen']
                index += struct.pack('<6H', v['per'], v['nanim'],
                                     v['nobjs'], v['ninstrs'], v['nsec'],
                                     v['pktlen'])
                index += struct.pack('<5I', v['obj_off'], v['ins_off'],
                                     v['sectbl_off'], v['secpix_off'],
                                     v['pkt_off'])
            out += struct.pack('<I', pos)           # pri_pix_off
            out += pri_tbl
            out += index
            for v in variants:
                out += v['recs'] + v['instrs'] + v['sec_tbl'] + \
                    v['sec_pix'] + v['pkt']
            out += pri_pix
            size = self.write('mid%02d.wc' % scene, bytes(out))
            self.log('  scene %d: pri %d sec %d/%d instr %d/%d pkt '
                     '%d/%d %d bytes'
                     % (scene, npri, variants[0]['nsec'],
                        variants[1]['nsec'], variants[0]['ninstrs'],
                        variants[1]['ninstrs'], variants[0]['pktlen'],
                        variants[1]['pktlen'], size))

    def convert_scramble(self):
        """scr<NN>.wcs: the SCRAMBLE.VGA sections the hard-coded launch
        and landing scenes draw (docs/06 6.2), at screen scale in the
        same .wcs layout as the flight sprites."""
        if not self.has('SCRAMBLE.VGA'):
            self.log('  scramble: SCRAMBLE.VGA not installed')
            return
        pk = self.packet('SCRAMBLE.VGA')
        for sec, label in sorted(SCRAMBLE_SECTIONS.items()):
            if len(pk) <= sec:
                self.log('  scramble %d (%s): no such section'
                         % (sec, label))
                continue
            scaled = self.scaled_set(shape.decode_all(pk.section(sec)), 64)
            name = 'scr%02d' % sec
            size = gfx.write_sprite_set(self.path(name + '.wcs'),
                                        scaled, 64)
            self.total += size
            self.save_preview(name, scaled)
            self.log('  scr %d %-17s %2d frames res 64 %6d bytes'
                     % (sec, label, len(scaled), size))

    def convert_ck_scenes(self):
        """cksc<N> ckint<N> ckbg<N> ckslide<N>.wcs: the cockpit pieces
        the scramble, door, death and ejection scenes draw for player
        ship N, from PCSHIP.V0N (docs/06 6.2)."""
        for ship in range(4):
            name = 'PCSHIP.V0%d' % ship
            if not self.has(name):
                self.log('  ck scenes %d: %s not installed' % (ship, name))
                continue
            pk = self.packet(name)
            for sec, stem in sorted(CK_CUTSCENE_SECTIONS.items()):
                if len(pk) <= sec:
                    self.log('  ck %s%d: no section %d' % (stem, ship, sec))
                    continue
                scaled = self.scaled_set(
                    shape.decode_all(pk.section(sec)), 64)
                fname = '%s%d' % (stem, ship)
                size = gfx.write_sprite_set(self.path(fname + '.wcs'),
                                            scaled, 64)
                self.total += size
                self.save_preview(fname, scaled)
                self.log('  ck %s%d sec %d %2d frames %6d bytes'
                         % (stem, ship, sec, len(scaled), size))

    def convert_pilotanm(self):
        """pil<NN>.wcs: PILOTANM.VGA - the pilot's death face (section
        0, screens.c:1710), the ejection seat (section 1, eject.c:50)
        and the ejected pilot the chase projects (section 2,
        eject.c:97-99), at screen scale."""
        if not self.has('PILOTANM.VGA'):
            self.log('  pilotanm: PILOTANM.VGA not installed')
            return
        pk = self.packet('PILOTANM.VGA')
        for sec, label in sorted(PILOTANM_SECTIONS.items()):
            if len(pk) <= sec:
                self.log('  pilotanm %d (%s): no such section'
                         % (sec, label))
                continue
            scaled = self.scaled_set(shape.decode_all(pk.section(sec)), 64)
            name = 'pil%02d' % sec
            size = gfx.write_sprite_set(self.path(name + '.wcs'),
                                        scaled, 64)
            self.total += size
            self.save_preview(name, scaled)
            self.log('  pil %d %-15s %2d frames res 64 %6d bytes'
                     % (sec, label, len(scaled), size))

    def convert_sounds(self):
        """sfx_*.ima: the original has no sampled effects on a PC (its
        sound is AdLib / Roland music data), so the handful of cockpit
        sounds is synthesised here and encoded for the engine's
        IMA-ADPCM player (15625 Hz, see tool/wav_to_ima_converter.py)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'wav_to_ima_converter',
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'wav_to_ima_converter.py'))
        ima = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ima)
        rate = 15625
        rng = np.random.RandomState(1990)

        def env(n, attack, decay):
            t = np.arange(n) / rate
            return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t * decay)

        def sweep(n, f0, f1):
            f = np.linspace(f0, f1, n)
            return np.sin(2 * np.pi * np.cumsum(f) / rate)

        def noise(n, smooth):
            x = rng.uniform(-1, 1, n)
            k = np.ones(smooth) / smooth
            return np.convolve(x, k, mode='same') * np.sqrt(smooth)

        n = int(rate * 0.16)
        laser = (sweep(n, 1900, 420) * 0.7 +
                 np.sign(sweep(n, 950, 210)) * 0.2) * env(n, 0.002, 14)
        n = int(rate * 0.7)
        missile = (noise(n, 6) * 0.8 + sweep(n, 180, 90) * 0.3) * \
            env(n, 0.03, 3.5)
        n = int(rate * 0.22)
        hit = (noise(n, 3) * 0.9 + sweep(n, 240, 60) * 0.5) * \
            env(n, 0.001, 16)
        n = int(rate * 1.1)
        boom = (noise(n, 14) * 1.0 + sweep(n, 110, 35) * 0.6) * \
            env(n, 0.004, 3.2)
        n = int(rate * 0.35)
        pop = (noise(n, 8) * 0.9 + sweep(n, 200, 70) * 0.4) * \
            env(n, 0.002, 9)
        for name, wave in (('sfx_laser', laser), ('sfx_missile', missile),
                           ('sfx_hit', hit), ('sfx_boom', boom),
                           ('sfx_pop', pop)):
            pcm = np.clip(wave / max(1e-6, np.abs(wave).max()) * 26000,
                          -32768, 32767).astype(np.int16)
            enc = ima.IMAEncoder()
            data = bytearray()
            for i in range(0, len(pcm), 2):
                c1 = enc.encode_sample(int(pcm[i]))
                c2 = enc.encode_sample(int(pcm[i + 1])) \
                    if i + 1 < len(pcm) else 0
                data.append((c1 << 4) | c2)
            path = self.path(name + '.ima')
            ima.write_ima_file(path, data, rate, len(pcm), 'high_first')
            self.total += os.path.getsize(path)

    def run(self, campaigns=(0, 1, 2)):
        self.log('Converting %s -> %s' % (self.gamedat, self.out))
        self.convert_palette()
        self.convert_types()
        self.convert_ai()
        self.log('ships:')
        self.convert_ships()
        self.convert_missiles()
        self.log('effects:')
        self.convert_effects()
        self.convert_hud()
        self.log('cockpits:')
        self.convert_cockpits()
        self.log('fonts:')
        self.convert_fonts()
        self.log('campaigns:')
        for c in campaigns:
            if not self.convert_campaign(c):
                self.log('  campaign %d: not installed' % c)
        self.convert_comm()
        self.convert_pictures()
        self.log('heads:')
        self.convert_heads()
        self.convert_backdrops()
        self.convert_overlay()
        self.convert_intro_word()
        self.log('scenes:')
        self.convert_midgame()
        self.log('scramble:')
        self.convert_scramble()
        self.convert_ck_scenes()
        self.convert_pilotanm()
        self.convert_sounds()
        self.log('done: %d files, %.1f MB'
                 % (len([f for f in os.listdir(self.out)
                         if not f.startswith('_')]), self.total / 1e6))


def main():
    ap = argparse.ArgumentParser(
        description='Convert your Wing Commander 1 (DOS) data for the '
                    'ThumbyColor game.')
    ap.add_argument('source', help='folder with WC.EXE and GAMEDAT '
                                   '(or the GAMEDAT folder itself)')
    ap.add_argument('--out', default=DEFAULT_OUT,
                    help='asset directory to write (default: %(default)s)')
    ap.add_argument('--preview', action='store_true',
                    help='also write PNG contact sheets to <out>/_preview '
                         '(needs Pillow)')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--dump', nargs=2, type=int, metavar=('SERIES',
                                                          'MISSION'),
                    help='print one mission of campaign 0 (series is '
                         '1-based, mission 0-based) and write nothing')
    args = ap.parse_args()
    conv = Converter(args.source, args.out, preview=args.preview,
                     verbose=not args.quiet)
    if args.dump:
        dump_mission(conv, args.dump[0], args.dump[1])
        return
    conv.run()


def dump_mission(conv, series, mission):
    m = wcmission.read_mission(conv.packet('MODULE.000'), series, mission)
    if m is None:
        raise SystemExit('no such mission')
    print('entry nav %d, home ship %d, player ship %d, flight %s'
          % (m['entry_nav'], m['home_ship'], m['player_ship'],
             [s for s in m['initial'] if s != -1]))
    for i, n in enumerate(m['navs']):
        if n['name']:
            print('nav %2d %-14s type %2d at %s radius %d ships %s' % (
                i, n['name'], n['type'], tuple(v >> 8 for v in n['pos']),
                n['radius'], [s for s in n['ships'] if s != -1]))
    for o in m['objectives']:
        print('objective type %d index %2d: %s' % (o['type'], o['index'],
                                                   o['text']))
    for i, s in enumerate(m['ships']):
        if s['type'] != -1:
            name = tables.TYPES[s['type']][1] if s['type'] < 58 else '?'
            print('ship %2d %-13s side %d pilot %2d mission %2d nav %2d '
                  'leader %2d target %2d at %s' % (
                      i, name or 'field', s['side'], s['pilot'],
                      s['mission_type'], s['nav'], s['leader_index'],
                      s['target'], tuple(v >> 8 for v in s['pos'])))


if __name__ == '__main__':
    main()
