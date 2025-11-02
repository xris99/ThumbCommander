"""
ThumbyColor display and sprite emulation for PC
Minimal wrapper that extends the original ThumbyColor API
"""

import os
try:
    # Try relative import first (when imported as package)
    from .framebuf import FrameBuffer, RGB565
except ImportError:
    # Fall back to absolute import (when imported directly)
    from framebuf import FrameBuffer, RGB565

# Lazy import pygame - only when display is created
pygame = None
_pygame_available = None


def _ensure_pygame():
    """Ensure pygame is imported and initialized"""
    global pygame, _pygame_available
    if _pygame_available is None:
        try:
            import pygame as pg
            pg.init()
            pygame = pg
            _pygame_available = True
        except ImportError:
            _pygame_available = False
    return _pygame_available


class ColorDisplay:
    """
    ThumbyColor display emulation
    Provides internal_fb FrameBuffer for game rendering
    """

    def __init__(self, width=128, height=128, scale=4):
        self.width = width
        self.height = height
        self.scale = scale

        # Create internal framebuffer (RGB565 format) - THIS IS KEY!
        # The game expects display.internal_fb to be a FrameBuffer object
        self.buffer = bytearray(width * height * 2)  # 2 bytes per pixel for RGB565
        self.internal_fb = FrameBuffer(self.buffer, width, height, RGB565)

        # Color constants (RGB565)
        self.BLACK = 0x0000
        self.WHITE = 0xFFFF
        self.DARKGRAY = 0x4208
        self.LIGHTGRAY = 0xBDF7
        self.RED = 0xF800
        self.GREEN = 0x07E0
        self.BLUE = 0x001F
        self.CYAN = 0x07FF
        self.ORANGE = 0xFD20
        self.PURPLE = 0x8010
        self.YELLOW = 0xFFEE
        self.LASER_BLUE = 0x297F
        self.LASER_COLOR = 0x297F
        self.ENEMY_PURPLE = 0x8010
        self.HIT_COLOR = 0xF800

        # Font settings (not used - internal_fb.text() uses embedded font)
        self.font_file = None
        self.font_width = 8
        self.font_height = 8
        self.font_space = 0

        # FPS control
        self.fps = 60
        self.grayscale_enabled = False

        # Initialize pygame if available
        self.screen = None
        self.clock = None
        if _ensure_pygame():
            self.screen = pygame.display.set_mode((width * scale, height * scale))
            pygame.display.set_caption("ThumbCommander - ThumbyColor Edition (PC)")
            self.clock = pygame.time.Clock()

    def enableGrayscale(self):
        """Enable grayscale mode (for compatibility)"""
        self.grayscale_enabled = True

    def setFPS(self, fps):
        """Set target FPS"""
        self.fps = fps

    def setFont(self, font_file, width, height, space):
        """Set font parameters (for compatibility - internal_fb uses embedded font)"""
        self.font_file = font_file
        self.font_width = width
        self.font_height = height
        self.font_space = space

    # Drawing methods - delegate to internal_fb
    def fill(self, color):
        """Fill display with color"""
        self.internal_fb.fill(color)

    def setPixel(self, x, y, color):
        """Set pixel at (x, y) to color"""
        self.internal_fb.pixel(x, y, color)

    def getPixel(self, x, y):
        """Get pixel color at (x, y)"""
        return self.internal_fb.pixel(x, y)

    def drawLine(self, x1, y1, x2, y2, color):
        """Draw line from (x1,y1) to (x2,y2)"""
        self.internal_fb.line(x1, y1, x2, y2, color)

    def drawRectangle(self, x, y, w, h, color):
        """Draw rectangle outline"""
        self.internal_fb.rect(x, y, w, h, color, fill=False)

    def drawFilledRectangle(self, x, y, w, h, color):
        """Draw filled rectangle"""
        self.internal_fb.fill_rect(x, y, w, h, color)

    def drawText(self, text, x, y, color):
        """Draw text using internal_fb's embedded 8x8 font"""
        self.internal_fb.text(str(text), x, y, color)

    def drawSprite(self, sprite):
        """Draw a sprite at its position"""
        if hasattr(sprite, 'render'):
            sprite.render(self)

    def drawSpriteWithScale(self, sprite):
        """Draw a scaled sprite"""
        if hasattr(sprite, 'render_scaled'):
            sprite.render_scaled(self)
        else:
            self.drawSprite(sprite)

    def draw_fullwidth_sprite(self, filename, x=0, y=0):
        """Draw full-width sprite from .COL.bin file"""
        if not isinstance(filename, str):
            return

        if not os.path.exists(filename):
            return

        try:
            with open(filename, 'rb') as f:
                data = f.read()

            # Parse dimensions from filename (format: name_width_height.COL.bin)
            basename = os.path.basename(filename)
            parts = basename.replace('.COL.bin', '').split('_')

            if len(parts) >= 3:
                try:
                    sprite_width = int(parts[-2])
                    sprite_height = int(parts[-1])
                except ValueError:
                    sprite_width = self.width
                    sprite_height = self.height
            else:
                sprite_width = self.width
                sprite_height = self.height

            # Create FrameBuffer and blit
            if len(data) >= sprite_width * sprite_height * 2:
                sprite_buffer = bytearray(sprite_width * sprite_height * 2)
                for i in range(len(sprite_buffer)):
                    sprite_buffer[i] = data[i]

                sprite_fb = FrameBuffer(sprite_buffer, sprite_width, sprite_height, RGB565)
                self.internal_fb.blit(sprite_fb, x, y)
        except Exception as e:
            print(f"Error drawing fullwidth sprite {filename}: {e}")

    def rgb565_to_rgb888(self, color565):
        """Convert RGB565 to RGB888 for pygame"""
        r = ((color565 >> 11) & 0x1F) * 255 // 31
        g = ((color565 >> 5) & 0x3F) * 255 // 63
        b = (color565 & 0x1F) * 255 // 31
        return (r, g, b)

    def update(self):
        """Update display - blit framebuffer to pygame surface and handle events"""
        if self.screen is None:
            return

        # Handle pygame events (including button input)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                import sys
                sys.exit()

        # Blit internal_fb to pygame surface
        for y in range(self.height):
            for x in range(self.width):
                color565 = self.internal_fb.pixel(x, y)
                if color565 is not None:
                    rgb = self.rgb565_to_rgb888(color565)
                    pygame.draw.rect(
                        self.screen,
                        rgb,
                        (x * self.scale, y * self.scale, self.scale, self.scale)
                    )

        pygame.display.flip()
        if self.clock:
            self.clock.tick(self.fps)


class ColorSprite:
    """
    ThumbyColor sprite - loads and renders .COL.bin sprite files
    """

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY

        self.currentFrame = 0
        self.frameCount = 1
        self.frame_data = None

        # Scaling
        self.scale = 65536  # Fixed point 1.0
        self.scaledWidth = width
        self.scaledHeight = height

        # Load bitmap data
        if isinstance(bitmap_data, str):
            # Load from .COL.bin file
            self.load_from_file(bitmap_data)
        elif isinstance(bitmap_data, tuple):
            # Grayscale compatibility (not implemented for PC)
            self.bitmap = bitmap_data
            self.bitmapByteCount = (width * height + 7) // 8

    def load_from_file(self, filename):
        """Load sprite from .COL.bin file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    self.frame_data = f.read()

                # Parse dimensions from filename (format: name_width_height.COL.bin)
                basename = os.path.basename(filename)
                parts = basename.replace('.COL.bin', '').split('_')

                if len(parts) >= 3:
                    try:
                        self.width = int(parts[-2])
                        self.height = int(parts[-1])
                    except ValueError:
                        pass

                # Calculate frame count
                bytes_per_frame = self.width * self.height * 2  # RGB565
                if len(self.frame_data) >= bytes_per_frame:
                    self.frameCount = len(self.frame_data) // bytes_per_frame

                self.scaledWidth = self.width
                self.scaledHeight = self.height
        except Exception as e:
            print(f"Error loading sprite from {filename}: {e}")

    def setFrame(self, frame):
        """Set current animation frame"""
        if frame < self.frameCount:
            self.currentFrame = frame

    def setScale(self, scale):
        """Set sprite scale (fixed point)"""
        self.scale = scale
        self.scaledWidth = (self.width * scale) >> 16
        self.scaledHeight = (self.height * scale) >> 16

    def setLifes(self, lifes):
        """Set life count (for HUD)"""
        self.lifes = lifes

    def getLifes(self):
        """Get life count"""
        return getattr(self, 'lifes', 0)

    def render(self, display):
        """Render sprite to display using blit"""
        if not self.frame_data:
            return

        # Create a FrameBuffer for this sprite frame
        bytes_per_frame = self.width * self.height * 2
        frame_offset = self.currentFrame * bytes_per_frame

        if frame_offset + bytes_per_frame > len(self.frame_data):
            return

        # Extract frame data
        frame_buffer = bytearray(bytes_per_frame)
        for i in range(bytes_per_frame):
            frame_buffer[i] = self.frame_data[frame_offset + i]

        # Create FrameBuffer and blit to display
        sprite_fb = FrameBuffer(frame_buffer, self.width, self.height, RGB565)
        display.internal_fb.blit(sprite_fb, self.x, self.y, self.key)

    def render_scaled(self, display):
        """Render scaled sprite"""
        if not self.frame_data or self.scaledWidth <= 0 or self.scaledHeight <= 0:
            self.render(display)
            return

        # For scaled rendering, we need to manually scale pixels
        bytes_per_frame = self.width * self.height * 2
        frame_offset = self.currentFrame * bytes_per_frame

        if frame_offset + bytes_per_frame > len(self.frame_data):
            return

        # Render with scaling (nearest-neighbor)
        for screen_y in range(self.scaledHeight):
            for screen_x in range(self.scaledWidth):
                # Map back to source pixel
                src_x = (screen_x * self.width) // self.scaledWidth
                src_y = (screen_y * self.height) // self.scaledHeight

                # Apply mirroring
                if self.mirrorX:
                    src_x = self.width - 1 - src_x
                if self.mirrorY:
                    src_y = self.height - 1 - src_y

                # Read pixel from frame data
                idx = frame_offset + (src_y * self.width + src_x) * 2
                if idx + 1 < len(self.frame_data):
                    color = self.frame_data[idx] | (self.frame_data[idx + 1] << 8)
                    # Skip transparent pixels
                    if color != self.key:
                        final_x = self.x + screen_x
                        final_y = self.y + screen_y
                        display.internal_fb.pixel(final_x, final_y, color)


def _rumble(duration):
    """Rumble stub - does nothing on PC"""
    pass
