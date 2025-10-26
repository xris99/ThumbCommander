"""
framebuf.py - PC implementation of MicroPython's framebuf module
Provides FrameBuffer class compatible with MicroPython API
"""

# Format constants
MONO_VLSB = 0
MONO_HLSB = 3
MONO_HMSB = 4
RGB565 = 1
GS2_HMSB = 5
GS4_HMSB = 2
GS8 = 6


class FrameBuffer:
    """PC implementation of MicroPython FrameBuffer"""

    def __init__(self, buffer, width, height, format, stride=None):
        self.buffer = buffer
        self.width = width
        self.height = height
        self.format = format
        self.stride = stride if stride is not None else width

    def fill(self, color):
        """Fill entire framebuffer with color"""
        if self.format == RGB565:
            # RGB565: 2 bytes per pixel
            for i in range(0, len(self.buffer), 2):
                self.buffer[i] = color & 0xFF
                self.buffer[i + 1] = (color >> 8) & 0xFF
        elif self.format == GS8:
            # GS8: 1 byte per pixel (grayscale)
            for i in range(len(self.buffer)):
                self.buffer[i] = color & 0xFF
        else:
            # Other formats - basic fill
            for i in range(len(self.buffer)):
                self.buffer[i] = 0 if color == 0 else 0xFF

    def pixel(self, x, y, color=None):
        """Get or set pixel at (x, y)"""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        if self.format == RGB565:
            idx = (y * self.stride + x) * 2
            if color is None:
                # Get pixel
                if idx + 1 < len(self.buffer):
                    return self.buffer[idx] | (self.buffer[idx + 1] << 8)
                return 0
            else:
                # Set pixel
                if idx + 1 < len(self.buffer):
                    self.buffer[idx] = color & 0xFF
                    self.buffer[idx + 1] = (color >> 8) & 0xFF
        elif self.format == GS8:
            idx = y * self.stride + x
            if color is None:
                # Get pixel
                if idx < len(self.buffer):
                    return self.buffer[idx]
                return 0
            else:
                # Set pixel
                if idx < len(self.buffer):
                    self.buffer[idx] = color & 0xFF

    def hline(self, x, y, w, color):
        """Draw horizontal line"""
        for i in range(w):
            self.pixel(x + i, y, color)

    def vline(self, x, y, h, color):
        """Draw vertical line"""
        for i in range(h):
            self.pixel(x, y + i, color)

    def line(self, x0, y0, x1, y1, color):
        """Draw line using Bresenham's algorithm"""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def rect(self, x, y, w, h, color, fill=False):
        """Draw rectangle"""
        if fill:
            for dy in range(h):
                self.hline(x, y + dy, w, color)
        else:
            self.hline(x, y, w, color)
            self.hline(x, y + h - 1, w, color)
            self.vline(x, y, h, color)
            self.vline(x + w - 1, y, h, color)

    def text(self, s, x, y, color):
        """Draw text (basic implementation - just placeholder)"""
        # This is a stub - actual text rendering happens in ColorDisplay.drawText()
        pass

    def blit(self, source_fb, x, y, key=-1, palette=None):
        """Blit (copy) another framebuffer to this one"""
        if palette:
            # Palette mode: source is indexed (GS8), palette maps to RGB565
            # Highly optimized version - pre-build palette lookup and minimize bounds checks

            # Pre-build RGB565 color lookup from palette
            palette_colors = []
            for i in range(256):
                pal_idx = i * 2
                if pal_idx + 1 < len(palette.buffer):
                    color = palette.buffer[pal_idx] | (palette.buffer[pal_idx + 1] << 8)
                    palette_colors.append((color & 0xFF, (color >> 8) & 0xFF))
                else:
                    palette_colors.append((0, 0))

            # Calculate clipping bounds once
            src_y_start = max(0, -y)
            src_y_end = min(source_fb.height, self.height - y)
            src_x_start = max(0, -x)
            src_x_end = min(source_fb.width, self.width - x)

            # Fast blit with minimal bounds checking
            for sy in range(src_y_start, src_y_end):
                dy = y + sy
                src_row_offset = sy * source_fb.stride
                dst_row_offset = dy * self.stride

                for sx in range(src_x_start, src_x_end):
                    dx = x + sx

                    # Get palette index from source
                    src_idx = src_row_offset + sx
                    if src_idx < len(source_fb.buffer):
                        palette_idx = source_fb.buffer[src_idx]
                        color_lo, color_hi = palette_colors[palette_idx]

                        # Check color key
                        if key == -1 or (color_lo | (color_hi << 8)) != key:
                            # Write to destination
                            dst_idx = (dst_row_offset + dx) * 2
                            if dst_idx + 1 < len(self.buffer):
                                self.buffer[dst_idx] = color_lo
                                self.buffer[dst_idx + 1] = color_hi
        else:
            # Direct blit - optimized for RGB565
            if self.format == RGB565 and source_fb.format == RGB565:
                for sy in range(source_fb.height):
                    dy = y + sy
                    if dy < 0 or dy >= self.height:
                        continue
                    for sx in range(source_fb.width):
                        dx = x + sx
                        if dx < 0 or dx >= self.width:
                            continue

                        src_idx = (sy * source_fb.stride + sx) * 2
                        if src_idx + 1 < len(source_fb.buffer):
                            color = source_fb.buffer[src_idx] | (source_fb.buffer[src_idx + 1] << 8)

                            if key == -1 or color != key:
                                dst_idx = (dy * self.stride + dx) * 2
                                if dst_idx + 1 < len(self.buffer):
                                    self.buffer[dst_idx] = source_fb.buffer[src_idx]
                                    self.buffer[dst_idx + 1] = source_fb.buffer[src_idx + 1]
            else:
                # Fallback to pixel-by-pixel
                for sy in range(source_fb.height):
                    for sx in range(source_fb.width):
                        color = source_fb.pixel(sx, sy)
                        if color is not None and (key == -1 or color != key):
                            self.pixel(x + sx, y + sy, color)

    def scroll(self, dx, dy):
        """Scroll framebuffer"""
        # Create temporary buffer
        temp = bytearray(len(self.buffer))
        for i in range(len(self.buffer)):
            temp[i] = self.buffer[i]

        # Clear buffer
        self.fill(0)

        # Copy shifted data
        for y in range(self.height):
            for x in range(self.width):
                old_x = x - dx
                old_y = y - dy
                if 0 <= old_x < self.width and 0 <= old_y < self.height:
                    if self.format == RGB565:
                        old_idx = (old_y * self.stride + old_x) * 2
                        new_idx = (y * self.stride + x) * 2
                        if old_idx + 1 < len(temp) and new_idx + 1 < len(self.buffer):
                            self.buffer[new_idx] = temp[old_idx]
                            self.buffer[new_idx + 1] = temp[old_idx + 1]
                    elif self.format == GS8:
                        old_idx = old_y * self.stride + old_x
                        new_idx = y * self.stride + x
                        if old_idx < len(temp) and new_idx < len(self.buffer):
                            self.buffer[new_idx] = temp[old_idx]
