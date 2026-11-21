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

from wc1 import gfx, shape, tables, mission as wcmission  # noqa: E402
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
