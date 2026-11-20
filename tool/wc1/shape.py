"""WC1 shape packets -> indexed bitmaps (see wc1-re src/gr.c).

A shape packet is

    u32  packet size (not read by the game)
    u32  frameOffsets[n]   relative to the packet start; the low word of
                           frameOffsets[0] is the end of this table

and every frame is

    i16 right, left, top, bottom    extents around the frame's hot spot
    scanlines:
        u16 code      0 terminates the frame;
                      otherwise count = code >> 1, bit 0 = RLE-packed
        i16 x, y      relative to the hot spot
        pixels        count literal bytes, or (when packed) a sequence of
                      u8 run codes: bit 0 set -> repeat next byte
                      (code >> 1) times, clear -> (code >> 1) literals

Width = left + right + 1, height = top + bottom + 1; the hot spot is at
(left, top) inside the bitmap. Pixels never written stay transparent.
"""

import struct

TRANSPARENT = -1


class Frame:
    __slots__ = ('width', 'height', 'left', 'top', 'pixels')

    def __init__(self, width, height, left, top, pixels):
        self.width = width
        self.height = height
        self.left = left      # hot spot x inside the bitmap
        self.top = top        # hot spot y inside the bitmap
        self.pixels = pixels  # list of rows, each a list of palette
        #                       indices or TRANSPARENT


def frame_count(packet):
    if len(packet) < 8:
        return 0
    return (struct.unpack_from('<H', packet, 4)[0] >> 2) - 1


def decode_frame(packet, index):
    """Decode one frame; returns None for an empty / missing frame."""
    table_end = struct.unpack_from('<H', packet, 4)[0]
    entry = index * 4 + 4
    if index < 0 or entry >= table_end:
        return None
    pos = struct.unpack_from('<i', packet, entry)[0]
    if pos <= 0 or pos + 8 > len(packet):
        return None
    right, left, top, bottom = struct.unpack_from('<4h', packet, pos)
    width = left + right + 1
    height = top + bottom + 1
    if width <= 0 or height <= 0 or width > 2048 or height > 2048:
        return None
    rows = [[TRANSPARENT] * width for _ in range(height)]
    pos += 8
    end = len(packet)
    while pos + 2 <= end:
        code = struct.unpack_from('<H', packet, pos)[0]
        pos += 2
        if code == 0:
            break
        sx, sy = struct.unpack_from('<2h', packet, pos)
        pos += 4
        x = left + sx
        y = top + sy
        count = code >> 1
        row = rows[y] if 0 <= y < height else None
        if code & 1:
            while count > 0:
                run = packet[pos]
                pos += 1
                length = run >> 1
                if run & 1:
                    colour = packet[pos]
                    pos += 1
                    if row is not None:
                        for i in range(length):
                            if 0 <= x + i < width:
                                row[x + i] = colour
                else:
                    if row is not None:
                        for i in range(length):
                            if 0 <= x + i < width:
                                row[x + i] = packet[pos + i]
                    pos += length
                x += length
                count -= length
                if length == 0:
                    break
        else:
            if row is not None:
                for i in range(count):
                    if 0 <= x + i < width:
                        row[x + i] = packet[pos + i]
            pos += count
    return Frame(width, height, left, top, rows)


def decode_all(packet):
    return [decode_frame(packet, i) for i in range(frame_count(packet))]


def looks_like_shape(packet):
    """Cheap plausibility test used when scanning unknown archives."""
    if len(packet) < 16:
        return False
    table_end = struct.unpack_from('<H', packet, 4)[0]
    if table_end < 8 or table_end & 3 or table_end > len(packet):
        return False
    n = (table_end >> 2) - 1
    offsets = struct.unpack_from('<%di' % n, packet, 4)
    if any(o < table_end or o + 8 > len(packet) for o in offsets if o):
        return False
    try:
        frame = decode_frame(packet, 0)
    except (struct.error, IndexError):
        return False
    return frame is not None


def read_palette(path):
    """GAME.PAL: an IFF ILBM stub whose CMAP chunk data starts at 0x30 -
    256 RGB triplets, 8 bits per component (the game reads exactly these
    0x300 bytes, see LoadPaletteTripletsFile in wc1-re src/auto.c)."""
    with open(path, 'rb') as f:
        f.seek(0x30)
        raw = f.read(0x300)
    if len(raw) != 0x300:
        raise ValueError('%s: not a palette file' % path)
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, 0x300, 3)]
