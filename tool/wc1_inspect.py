#!/usr/bin/env python3
"""
Look inside an original Wing Commander 1 (DOS) installation.

This is the research companion of tool/wc1_convert.py: it prints the
structures that games/wingcommander does not use yet (talking heads,
cutscene scripts, radio messages, music, timbres) so that every statement
in games/wingcommander/docs can be checked against your own copy of the
game. It only reads; with --png / --export it writes into a folder you
name (keep that folder out of the repository - it holds Origin data).

    python3 tool/wc1_inspect.py WING files
    python3 tool/wc1_inspect.py WING sections TALKING.VGA
    python3 tool/wc1_inspect.py WING shape TALKING.VGA 0 --png out/
    python3 tool/wc1_inspect.py WING talk 0 1 0            # campaign series mission
    python3 tool/wc1_inspect.py WING talk 0 1 0 --scene 2  # first bar scene
    python3 tool/wc1_inspect.py WING midgame 0 0           # scene, variant
    python3 tool/wc1_inspect.py WING comm
    python3 tool/wc1_inspect.py WING music
    python3 tool/wc1_inspect.py WING music --track 1 --events
    python3 tool/wc1_inspect.py WING music --export out/
    python3 tool/wc1_inspect.py WING songs                 # durations, loops, exits
    python3 tool/wc1_inspect.py WING timbres

WING is the folder that holds GAMEDAT (or GAMEDAT itself).
"""

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wc1 import shape                                   # noqa: E402
from wc1.packet import PacketFile, PacketError          # noqa: E402

SCENE_NAMES = ['briefing', 'debriefing', 'bar 1', 'bar 2', 'bar 3']
PERSONALITIES = ['Spirit', 'Hunter', 'Bossman', 'Iceman', 'Angel',
                 'Paladin', 'Maniac', 'Knight', 'Kilrathi ace 1',
                 'Kilrathi ace 2', 'Kilrathi ace 3', 'Kilrathi ace 4',
                 'generic Confed', 'generic Kilrathi']
COMM_LINES = ['acknowledge', 'refuse', 'enemy sighted', 'attacking',
              'needs help', 'kill', 'praise', 'dying', 'retreat / clear',
              'leaving / denied', 'friendly fire']


class Data:
    def __init__(self, root):
        cand = [root, os.path.join(root, 'GAMEDAT'),
                os.path.join(root, 'gamedat')]
        self.dir = next((c for c in cand if os.path.isfile(
            self._find_in(c, 'INSTALL.DAT') or '')), None)
        if self.dir is None:
            sys.exit('no INSTALL.DAT under %s' % root)

    @staticmethod
    def _find_in(folder, name):
        if not os.path.isdir(folder):
            return None
        for entry in os.listdir(folder):
            if entry.upper() == name.upper():
                return os.path.join(folder, entry)
        return None

    def path(self, name):
        p = self._find_in(self.dir, name)
        if p is None:
            sys.exit('%s not found in %s' % (name, self.dir))
        return p

    def raw(self, name):
        with open(self.path(name), 'rb') as f:
            return f.read()

    def packet(self, name):
        return PacketFile(self.path(name))


def cstr(data, off):
    return data[off:].split(b'\0', 1)[0].decode('latin1')


# ---------------------------------------------------------------- files
def cmd_files(d, args):
    """INSTALL.DAT: 16-byte records name[13], disk, type, id + 1."""
    raw = d.raw('INSTALL.DAT')
    print('logical  disk type  name')
    for i in range(len(raw) // 16):
        rec = raw[i * 16:(i + 1) * 16]
        name = rec[:13].split(b'\0', 1)[0].decode('latin1')
        if name:
            print('  %3d     %3d  %3d  %s' % (rec[15] - 1, rec[13], rec[14],
                                             name))


# ------------------------------------------------------------- sections
def cmd_sections(d, args):
    p = d.packet(args.file)
    print('%s: %d sections, %d bytes' % (p.name, len(p), p.size))
    for i in range(len(p)):
        comp, start, end = p.section_range(i)
        try:
            data = p.section(i)
        except PacketError as e:
            print('  %2d  %s' % (i, e))
            continue
        note = 'empty'
        if data:
            note = 'raw data'
            if shape.looks_like_shape(data):
                frames = [f for f in shape.decode_all(data) if f]
                if frames:
                    note = '%d frames, largest %dx%d' % (
                        shape.frame_count(data),
                        max(f.width for f in frames),
                        max(f.height for f in frames))
        print('  %2d  %7d bytes%s  %s' % (i, len(data),
                                         ' (LZW)' if comp == 1 else '',
                                         note))


# ---------------------------------------------------------------- shape
def cmd_shape(d, args):
    data = d.packet(args.file).section(args.section)
    n = shape.frame_count(data)
    frames = shape.decode_all(data)
    print('%s section %d: %d frames' % (args.file, args.section, n))
    print('frame   size      hot spot (left, top)')
    for i, f in enumerate(frames):
        if f is None:
            print('  %3d   -' % i)
        else:
            print('  %3d   %3dx%-3d   %d, %d' % (i, f.width, f.height,
                                                f.left, f.top))
    if not args.png:
        return
    from PIL import Image
    pal = shape.read_palette(d.path('GAME.PAL'))
    os.makedirs(args.png, exist_ok=True)
    stem = '%s_%02d' % (args.file.replace('.', '_'), args.section)
    for i, f in enumerate(frames):
        if f is None:
            continue
        img = Image.new('RGBA', (f.width, f.height), (0, 0, 0, 0))
        px = img.load()
        for y, row in enumerate(f.pixels):
            for x, c in enumerate(row):
                if c != shape.TRANSPARENT:
                    px[x, y] = pal[c] + (255,)
        img.save(os.path.join(args.png, '%s_%02d.png' % (stem, i)))
    print('frames written to %s (Origin data - do not commit)' % args.png)


# ----------------------------------------------------------------- talk
def scene_records(packet, scene, tbase):
    pos = scene
    while pos + 13 <= len(packet):
        rec = struct.unpack_from('<bbbhhhhh', packet, pos)
        if rec[0] == -2:
            break
        yield rec
        pos += 13


def describe_shot(shot):
    if shot < 0:
        return 'shot %d' % shot
    kind = shot & 0x3F
    extra = ' +overlay' if shot & 0x40 else ''
    names = {0: 'establishing', 1: 'briefing long', 2: 'podium',
             3: 'dismissed', 4: 'nav map', 5: 'back to long',
             6: 'medal long', 7: 'medal establishing', 8: 'pin medal',
             9: 'funeral long', 10: 'debrief establishing',
             11: 'debrief long', 16: 'medal chest', 17: 'funeral wingman'}
    if 20 <= kind <= 32:
        return 'face %d%s' % (kind - 20, extra)
    if 50 <= kind <= 59:
        return 'animation %d%s' % (kind - 50, extra)
    if 12 <= kind <= 15:
        return 'funeral %d%s' % (kind, extra)
    return names.get(kind, 'shot %d' % kind) + extra


def print_scene(packet, scene, tbase):
    for i, (shot, colour, talker, dur, tests, text, mouth, face) in \
            enumerate(scene_records(packet, scene, tbase)):
        print('%3d  %-18s colour %2d talker %3d wait %4d' % (
            i, describe_shot(shot), colour, talker, dur))
        if tests:
            raw = packet[tbase + tests:].split(b'\0', 1)[0]
            if raw:
                print('       tests %s' % ' '.join('%d' % b for b in raw))
        print('       text  %r' % cstr(packet, tbase + text))
        if mouth and cstr(packet, tbase + mouth):
            print('       mouth %r' % cstr(packet, tbase + mouth))
        if face and cstr(packet, tbase + face):
            print('       face  %r' % cstr(packet, tbase + face))


def cmd_talk(d, args):
    brief = d.packet('BRIEFING.%03d' % args.campaign)
    index = args.mission + args.series * 4
    if index >= len(brief):
        sys.exit('no packet %d (file has %d)' % (index, len(brief)))
    packet = brief.section(index)
    if len(packet) < 40:
        sys.exit('packet %d is empty' % index)
    head = struct.unpack_from('<10I', packet, 0)
    scenes = range(5) if args.scene is None else [args.scene]
    for which in scenes:
        scene, tbase = head[which * 2], head[which * 2 + 1]
        if scene == 0 or scene >= len(packet):
            continue
        print('--- %s (scene %d): records at %d, text at %d' % (
            SCENE_NAMES[which], which, scene, tbase))
        print_scene(packet, scene, tbase)


# -------------------------------------------------------------- midgame
def disassemble(defs, off):
    """One object's script of a MIDGAME animation (see docs/05)."""
    out = []
    c = off
    while c < len(defs) and defs[c] != 0:
        op = chr(defs[c])
        c += 1
        if op in 'ALQ':
            out.append('%s%s%d' % (op, chr(defs[c]),
                                   struct.unpack_from('<h', defs, c + 1)[0]))
            c += 3
        elif op in 'BGJW':
            out.append('%s%d' % (op, struct.unpack_from('<h', defs, c)[0]))
            c += 2
        elif op in 'DE':
            frames = []
            while defs[c] != 0xFF:
                frames.append(defs[c])
                c += 1
            c += 1
            out.append('%s%s' % (op, frames))
        elif op == 'R':
            out.append('R%d,%d' % (defs[c], defs[c + 1]))
            c += 2
        elif op == 'X':
            out.append('X%s' % (struct.unpack_from('<5h', defs, c),))
            c += 10
        elif op == 'P':
            out.append('P')
        else:
            out.append('?0x%02x' % ord(op))
            break
    return ' '.join(out)


def cmd_midgame(d, args):
    p = d.packet('MIDGAME.V%02d' % args.scene)
    v = args.variant
    defs = p.section(v + 1)
    if len(defs) < 4:
        sys.exit('scene %d has no variant %d' % (args.scene, v))
    per = struct.unpack_from('<h', defs, 0)[0]
    first = struct.unpack_from('<h', defs, 4)[0]
    count = (first - 2) // 0x36
    print('%s variant %d: %d objects, %d per animation -> %d animations'
          % (p.name, v, count, per, count // max(per, 1)))
    for i in range(count):
        o = 2 + i * 0x36
        layer, script = struct.unpack_from('<hh', defs, o)
        x, y, rot, scale, frame = struct.unpack_from('<5h', defs, o + 0x18)
        if i % per == 0:
            print('animation %d' % (i // per))
        print('  obj %d layer %d  x %4d y %4d rot %3d scale %4d frame %2d'
              % (i % per, layer, x, y, rot, scale, frame))
        print('        %s' % disassemble(defs, script))
    packet = p.section(v + 5)
    if len(packet) >= 8:
        scene, tbase = struct.unpack_from('<II', packet, 0)
        print('--- scene packet: records at %d, text at %d' % (scene, tbase))
        print_scene(packet, scene, tbase)


# ----------------------------------------------------------------- comm
def cmd_comm(d, args):
    raw = d.raw('COMMSM2.DAT' if args.sm2 else 'COMMUNIC.DAT')
    people = len(raw) // (11 * 80)
    print('%d bytes = %d personalities x 11 lines x 80 bytes' % (
        len(raw), people))
    for p in range(people):
        name = PERSONALITIES[p] if p < len(PERSONALITIES) else '?'
        print('personality %d (%s)' % (p, name))
        for line in range(11):
            text = cstr(raw, (p * 11 + line) * 80)
            if text:
                print('  %2d %-17s %r' % (line, COMM_LINES[line], text))


# ---------------------------------------------------------------- music
def read_varlen(data, pos):
    value = 0
    while True:
        b = data[pos]
        pos += 1
        value = (value << 7) | (b & 0x7F)
        if not b & 0x80:
            return value, pos


def midi_tracks(mid):
    if mid[:4] != b'MThd':
        return None, 0, []
    hlen, fmt, ntrk, division = struct.unpack_from('>IHHH', mid, 4)
    pos = 8 + hlen
    tracks = []
    for _ in range(ntrk):
        if mid[pos:pos + 4] != b'MTrk':
            break
        size = struct.unpack_from('>I', mid, pos + 4)[0]
        tracks.append(mid[pos + 8:pos + 8 + size])
        pos += 8 + size
    return fmt, division, tracks


def track_events(trk):
    """Yield (tick, offset, kind, data): kind is a status byte, 'meta'
    (data = (type, bytes)) or 'fe' (data = (type, bytes, data offset)).
    Follows OriginFxReadTrackEvent in wc1-re src/sdl/originfx.cpp: running
    status survives meta, sysex and 0xFE events; an 0xFE event is
    FE <type> <length> <data...> with a plain length byte."""
    pos = 0
    tick = 0
    status = 0
    while pos < len(trk):
        delta, pos = read_varlen(trk, pos)
        tick += delta
        at = pos
        b = trk[pos]
        if b == 0xFF:
            kind = trk[pos + 1]
            length, pos = read_varlen(trk, pos + 2)
            yield tick, at, 'meta', (kind, trk[pos:pos + length])
            pos += length
        elif b == 0xFE:                     # Origin control event
            kind, length = trk[pos + 1], trk[pos + 2]
            pos += 3
            yield tick, at, 'fe', (kind, trk[pos:pos + length], pos)
            pos += length
        elif b in (0xF0, 0xF7):
            length, pos = read_varlen(trk, pos + 1)
            pos += length
        else:
            if b & 0x80:
                status = b
                pos += 1
            n = 1 if (status & 0xE0) == 0xC0 else 2
            yield tick, at, status, trk[pos:pos + n]
            pos += n


FE_NAMES = {0: 'loop', 1: 'end if leaving', 2: 'jump if leaving',
            3: 'marker', 4: 'jump if branch !=', 5: 'jump if branch =='}


def cmd_music(d, args):
    p = d.packet('MUSIC.MID')
    if args.export:
        os.makedirs(args.export, exist_ok=True)
    tracks = range(len(p)) if args.track is None else [args.track]
    for t in tracks:
        mid = p.section(t)
        fmt, division, trks = midi_tracks(mid)
        if fmt is None:
            print('track %2d: %d bytes, not a MIDI file' % (t, len(mid)))
            continue
        ticks = 0
        notes = 0
        fe = {}
        channels = set()
        programs = set()
        tempo = []
        for trk in trks:
            for tick, at, kind, data in track_events(trk):
                ticks = max(ticks, tick)
                if kind == 'fe':
                    fe[data[0]] = fe.get(data[0], 0) + 1
                elif kind == 'meta':
                    if data[0] == 0x51:
                        tempo.append(int.from_bytes(data[1], 'big'))
                elif (kind & 0xF0) == 0x90 and data[1]:
                    notes += 1
                    channels.add(kind & 15)
                elif (kind & 0xF0) == 0xC0:
                    programs.add(data[0])
        print('track %2d: %5d bytes, %2d MTrk, division %d, %6d ticks, '
              '%5d notes, channels %s' % (
                  t, len(mid), len(trks), division, ticks, notes,
                  ','.join(str(c) for c in sorted(channels))))
        print('          tempo %s  programs %s' % (
            ','.join(str(x) for x in tempo[:4]) or 'default',
            ','.join(str(x) for x in sorted(programs))))
        print('          control events: %s' % (
            ', '.join('%s x%d' % (FE_NAMES.get(k, 'type %d' % k), v)
                      for k, v in sorted(fe.items())) or 'none'))
        if args.events:
            for n, trk in enumerate(trks):
                for tick, at, kind, data in track_events(trk):
                    if kind == 'fe':
                        typ, body, dpos = data
                        note = FE_NAMES.get(typ, 'type %d' % typ)
                        if typ != 3 and len(body) >= 2:
                            off = struct.unpack_from('<h', body, 0)[0]
                            note += ' -> byte %d' % (dpos - off)
                            if len(body) >= 3:
                                note += ', branch %d' % body[2]
                        elif typ == 3 and body:
                            note += ' %d' % body[0]
                        print('    MTrk %2d tick %6d byte %5d  FE %-18s %s'
                              % (n, tick, at, body.hex(), note))
                    elif kind == 'meta' and data[0] in (0x51, 0x2F):
                        print('    MTrk %2d tick %6d byte %5d  meta %02x %s'
                              % (n, tick, at, data[0], data[1].hex()))
        if args.export:
            with open(os.path.join(args.export, 'track%02d.mid' % t),
                      'wb') as f:
                f.write(mid)
    if args.export:
        print('tracks written to %s (Origin data - do not commit; the '
              '0xFE events are not standard MIDI)' % args.export)


def delta_ticks(trk):
    """Map the byte offset of every delta time to its tick. A control
    event jumps to such an offset: the sequencer plays an event and then
    reads the delta that follows it."""
    out = {}
    pos = 0
    tick = 0
    status = 0
    while pos < len(trk):
        out[pos] = tick
        delta, pos = read_varlen(trk, pos)
        tick += delta
        b = trk[pos]
        if b == 0xFF:
            length, pos = read_varlen(trk, pos + 2)
            pos += length
        elif b == 0xFE:
            pos += 3 + trk[pos + 2]
        elif b in (0xF0, 0xF7):
            length, pos = read_varlen(trk, pos + 1)
            pos += length
        else:
            if b & 0x80:
                status = b
                pos += 1
            pos += 1 if (status & 0xE0) == 0xC0 else 2
    out[pos] = tick
    return out


def cmd_songs(d, args):
    """Per song: linear playing time, most notes held at once, and the
    loop / exit structure with jump targets as ticks. `same` tells
    whether every MTrk that has jumps has the same ones (then the song
    can be flattened into one event stream)."""
    p = d.packet('MUSIC.MID')
    total = 0
    print('song   secs  held  same  structure (ticks)')
    for t in range(len(p)):
        fmt, division, trks = midi_tracks(p.section(t))
        if fmt is None:
            continue
        tempos = []
        notes = []
        jumps = []
        for trk in trks:
            where = delta_ticks(trk)
            mine = []
            for tick, at, kind, data in track_events(trk):
                if kind == 'meta':
                    if data[0] == 0x51:
                        tempos.append((tick, int.from_bytes(data[1], 'big')))
                elif kind == 'fe':
                    typ, body, dpos = data
                    if typ in (0, 2, 4, 5) and len(body) >= 2:
                        off = struct.unpack_from('<h', body, 0)[0]
                        mine.append((tick, typ, where.get(dpos - off, -1),
                                     body[2] if len(body) >= 3 else -1))
                    elif typ == 1:
                        mine.append((tick, typ, -1, -1))
                else:
                    notes.append((tick, kind, data[0],
                                  data[1] if len(data) > 1 else 0))
            if mine:
                jumps.append(tuple(mine))
        end = max([n[0] for n in notes] + [0])
        us = 0
        last = 0
        tempo = 500000
        for tick, value in sorted(tempos):
            if tick > end:
                break
            us += (tick - last) * tempo // division
            last, tempo = tick, value
        us += (end - last) * tempo // division
        total += us
        held = set()
        most = 0
        notes.sort(key=lambda n: (n[0], (n[1] & 0xF0) == 0x90 and n[3] > 0))
        for tick, status, key, velocity in notes:
            if (status & 0xF0) == 0x90 and velocity:
                held.add((status & 15, key))
            elif (status & 0xF0) in (0x80, 0x90):
                held.discard((status & 15, key))
            most = max(most, len(held))
        full = [j for j in jumps if len(j) == max(len(x) for x in jumps)]
        same = all(j == full[0] for j in full) if full else True
        groups = {}
        for tick, typ, target, branch in (full[0] if full else ()):
            groups.setdefault((typ, target, branch), []).append(tick)
        parts = []
        for (typ, target, branch), ticks in groups.items():
            at = str(ticks[0]) if len(ticks) == 1 else '%dx %d..%d' % (
                len(ticks), ticks[0], ticks[-1])
            text = '%s at %s' % (FE_NAMES[typ], at)
            if branch >= 0:
                text += ' %d' % branch
            if target >= 0:
                text += ' -> %d' % target
            parts.append(text)
        print(' %2d  %6.1f   %2d   %-4s  %s' % (
            t, us / 1e6, most, 'yes' if same else 'NO',
            '; '.join(parts) or 'plays once'))
    print('all songs played once through: %.0f s' % (total / 1e6))


def cmd_timbres(d, args):
    p = d.packet('WINGLDR.TIM')
    for s, name in enumerate(('MT-32', 'AdLib', 'PC speaker')):
        print('section %d (%s): %d bytes' % (s, name, len(p.section(s))))
    bank = p.section(1)
    n = bank[0]
    print('AdLib bank: %d timbres of 48 bytes' % n)
    print(' #  prog  mod 20 40 60 80 E0  car 20 40 60 80 E0  C0 rhy '
          'vel bend vib(rate,depth) detune layer keytrk')
    for i in range(n):
        t = bank[1 + i * 48:1 + (i + 1) * 48]
        detune = struct.unpack_from('<h', t, 36)[0]
        print('%2d  %3d   %s   %s  %02x  %2d  %d/%d %3d   %3d,%-3d     '
              '%5d   %d    %4d' % (
                  i, t[47], ' '.join('%02x' % b for b in t[0:5]),
                  ' '.join('%02x' % b for b in t[5:10]), t[10], t[11],
                  t[12], t[13], t[14], t[16], t[17], detune, t[38],
                  struct.unpack_from('<b', t, 39)[0]))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('root', help='folder that holds GAMEDAT')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('files')
    s = sub.add_parser('sections')
    s.add_argument('file')
    s = sub.add_parser('shape')
    s.add_argument('file')
    s.add_argument('section', type=int)
    s.add_argument('--png', metavar='DIR')
    s = sub.add_parser('talk')
    s.add_argument('campaign', type=int)
    s.add_argument('series', type=int)
    s.add_argument('mission', type=int)
    s.add_argument('--scene', type=int)
    s = sub.add_parser('midgame')
    s.add_argument('scene', type=int)
    s.add_argument('variant', type=int)
    s = sub.add_parser('comm')
    s.add_argument('--sm2', action='store_true')
    s = sub.add_parser('music')
    s.add_argument('--track', type=int)
    s.add_argument('--events', action='store_true')
    s.add_argument('--export', metavar='DIR')
    sub.add_parser('songs')
    sub.add_parser('timbres')
    args = ap.parse_args()
    d = Data(args.root)
    try:
        globals()['cmd_' + args.cmd](d, args)
    except BrokenPipeError:         # output piped into head, less, ...
        sys.stderr.close()


if __name__ == '__main__':
    main()
