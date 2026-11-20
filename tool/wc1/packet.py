"""Origin packet container and LZW decoder (WC1 DOS data files).

Container layout (little endian), see wc1-re src/sdl/resources.c:

    u32  file size
    u32  entry[n]   low 24 bits = section offset, high 8 bits = compression
                    (entry[0]'s offset is also the size of this directory,
                    so n = offset/4 - 1)

A section with compression == 1 starts with a u32 uncompressed size
followed by an LZW stream (9..12 bit codes, LSB first, 0x100 = clear,
0x101 = stop). Every other compression value means "stored".
"""

import os
import struct

LZW_CLEAR = 0x100
LZW_STOP = 0x101
LZW_FIRST = 0x102
LZW_MAX = 0x1000


class PacketError(Exception):
    pass


def lzw_decode(src, out_size):
    """Decode one Origin LZW stream into exactly out_size bytes."""
    out = bytearray()
    n_bits = len(src) * 8
    pos = 0

    def read(width):
        nonlocal pos
        if pos + width > n_bits:
            raise PacketError('LZW stream truncated')
        byte = pos >> 3
        chunk = int.from_bytes(src[byte:byte + 3], 'little')
        value = (chunk >> (pos & 7)) & ((1 << width) - 1)
        pos += width
        return value

    code = read(9)
    if code == LZW_STOP:
        return bytes(out)
    if code != LZW_CLEAR:
        raise PacketError('LZW stream does not start with a clear code')

    prefix = [0] * LZW_MAX
    value = [0] * LZW_MAX
    while True:
        width = 9
        threshold = 1 << width
        size = LZW_FIRST
        prev = LZW_CLEAR
        while True:
            code = read(width)
            if code == LZW_STOP:
                if len(out) != out_size:
                    raise PacketError(
                        'LZW size mismatch: %d != %d' % (len(out), out_size))
                return bytes(out)
            if code == LZW_CLEAR:
                break
            if code > size:
                raise PacketError('LZW code out of range')
            special = code == size
            cur = prev if special else code
            if cur == LZW_CLEAR:
                raise PacketError('LZW bad first code')
            # unwind the dictionary chain
            stack = []
            while cur >= LZW_FIRST:
                stack.append(value[cur])
                cur = prefix[cur]
            first = cur
            out.append(first)
            out.extend(reversed(stack))
            if prev != LZW_CLEAR:
                if size >= LZW_MAX:
                    raise PacketError('LZW dictionary overflow')
                prefix[size] = prev
                value[size] = first
                size += 1
                if special:
                    out.append(first)
                if size == threshold and width < 12:
                    width += 1
                    threshold <<= 1
            prev = code


class PacketFile:
    """One GAMEDAT archive; sections are decoded on demand and cached."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, 'rb') as f:
            self.data = f.read()
        if len(self.data) < 8:
            raise PacketError('%s: too small for a packet file' % self.name)
        declared = struct.unpack_from('<I', self.data, 0)[0]
        first = struct.unpack_from('<I', self.data, 4)[0]
        dir_size = first & 0xFFFFFF
        if declared > len(self.data) or dir_size < 8 or dir_size & 3:
            raise PacketError('%s: not an Origin packet file' % self.name)
        self.size = declared
        self.count = (dir_size >> 2) - 1
        self.entries = struct.unpack_from('<%dI' % self.count, self.data, 4)
        self._cache = {}

    def __len__(self):
        return self.count

    def section_range(self, index):
        entry = self.entries[index]
        start = entry & 0xFFFFFF
        if index + 1 < self.count:
            end = self.entries[index + 1] & 0xFFFFFF
        else:
            end = self.size
        return entry >> 24, start, end

    def section(self, index):
        """Decoded bytes of one section (b'' for an empty section)."""
        if index in self._cache:
            return self._cache[index]
        if not 0 <= index < self.count:
            raise PacketError('%s: no section %d' % (self.name, index))
        compression, start, end = self.section_range(index)
        if end <= start:
            data = b''
        elif compression == 1:
            out_size = struct.unpack_from('<I', self.data, start)[0]
            data = lzw_decode(self.data[start + 4:end], out_size)
        else:
            data = self.data[start:end]
        self._cache[index] = data
        return data


def is_packet_file(path):
    try:
        PacketFile(path)
        return True
    except (PacketError, OSError, struct.error):
        return False
