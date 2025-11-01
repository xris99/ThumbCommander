"""
MicroPython framebuf module emulation for PC
Implements FrameBuffer class with RGB565 support
"""

# Framebuffer formats
MONO_VLSB = 0
MONO_HLSB = 3
MONO_HMSB = 4
RGB565 = 1
GS2_HMSB = 5
GS4_HMSB = 2
GS8 = 6


class FrameBuffer:
    """
    MicroPython-compatible FrameBuffer class
    Supports RGB565 format for ThumbyColor compatibility
    """

    def __init__(self, buffer, width, height, format=RGB565, stride=None):
        """
        Initialize framebuffer

        Args:
            buffer: bytearray to store pixel data
            width: width in pixels
            height: height in pixels
            format: pixel format (RGB565 for ThumbyColor)
            stride: bytes per line (optional)
        """
        self.buffer = buffer
        self.width = width
        self.height = height
        self.format = format

        if stride is None:
            if format == RGB565:
                stride = width * 2  # 2 bytes per pixel
            elif format in (MONO_VLSB, MONO_HLSB, MONO_HMSB):
                stride = (width + 7) // 8
            elif format == GS2_HMSB:
                stride = (width + 3) // 4
            elif format == GS4_HMSB:
                stride = (width + 1) // 2
            elif format == GS8:
                stride = width

        self.stride = stride

    def fill(self, color):
        """Fill entire framebuffer with color"""
        if self.format == RGB565:
            # RGB565: 2 bytes per pixel
            for i in range(0, len(self.buffer), 2):
                self.buffer[i] = color & 0xFF
                self.buffer[i + 1] = (color >> 8) & 0xFF
        else:
            # For other formats, fill with color value
            for i in range(len(self.buffer)):
                self.buffer[i] = color

    def pixel(self, x, y, color=None):
        """Get or set pixel at (x, y)"""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return

        if self.format == RGB565:
            idx = (y * self.width + x) * 2
            if color is None:
                # Get pixel
                return self.buffer[idx] | (self.buffer[idx + 1] << 8)
            else:
                # Set pixel
                self.buffer[idx] = color & 0xFF
                self.buffer[idx + 1] = (color >> 8) & 0xFF
        elif self.format in (MONO_VLSB, MONO_HLSB, MONO_HMSB):
            # Monochrome formats
            if self.format == MONO_VLSB:
                idx = x + (y // 8) * self.stride
                bit = y & 7
            elif self.format == MONO_HLSB:
                idx = (x // 8) + y * self.stride
                bit = x & 7
            else:  # MONO_HMSB
                idx = (x // 8) + y * self.stride
                bit = 7 - (x & 7)

            if color is None:
                return (self.buffer[idx] >> bit) & 1
            elif color:
                self.buffer[idx] |= 1 << bit
            else:
                self.buffer[idx] &= ~(1 << bit)

    def hline(self, x, y, w, color):
        """Draw horizontal line"""
        for i in range(w):
            self.pixel(x + i, y, color)

    def vline(self, x, y, h, color):
        """Draw vertical line"""
        for i in range(h):
            self.pixel(x, y + i, color)

    def line(self, x1, y1, x2, y2, color):
        """Draw line using Bresenham's algorithm"""
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        while True:
            self.pixel(x1, y1, color)
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy

    def rect(self, x, y, w, h, color, fill=False):
        """Draw rectangle"""
        if fill:
            for i in range(h):
                self.hline(x, y + i, w, color)
        else:
            self.hline(x, y, w, color)
            self.hline(x, y + h - 1, w, color)
            self.vline(x, y, h, color)
            self.vline(x + w - 1, y, h, color)

    def fill_rect(self, x, y, w, h, color):
        """Draw filled rectangle"""
        self.rect(x, y, w, h, color, fill=True)

    def blit(self, source_fb, x, y, key=-1, palette=None):
        """
        Blit another framebuffer onto this one

        Args:
            source_fb: Source FrameBuffer
            x, y: Position to blit to
            key: Transparent color key (optional)
            palette: Color palette for format conversion (optional)
        """
        for sy in range(source_fb.height):
            for sx in range(source_fb.width):
                color = source_fb.pixel(sx, sy)
                if color != key:
                    self.pixel(x + sx, y + sy, color)

    def scroll(self, dx, dy):
        """Scroll the framebuffer by dx, dy pixels"""
        # Create a temporary copy
        temp = bytearray(self.buffer)
        temp_fb = FrameBuffer(temp, self.width, self.height, self.format, self.stride)

        # Clear current buffer
        self.fill(0)

        # Blit with offset
        for y in range(self.height):
            for x in range(self.width):
                sx = x - dx
                sy = y - dy
                if 0 <= sx < self.width and 0 <= sy < self.height:
                    color = temp_fb.pixel(sx, sy)
                    self.pixel(x, y, color)

    def text(self, string, x, y, color):
        """Draw text (basic implementation)"""
        # Basic 8x8 character drawing
        for i, char in enumerate(string):
            char_x = x + i * 8
            # This is a simplified version - real implementation would need a font
            self.rect(char_x, y, 8, 8, color)
