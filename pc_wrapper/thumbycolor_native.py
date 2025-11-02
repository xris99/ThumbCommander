"""
PC wrapper for ThumbyColor display
Provides ColorDisplay and ColorSprite classes compatible with hardware API
On real hardware, these come from the built-in thumbycolor_native module
"""

import os
import sys
import struct

# Import framebuf from pc_wrapper
try:
    from pc_wrapper import framebuf
except:
    import framebuf

from platform_constants import get_constants
PC = get_constants(True)

# Lazy import pygame
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
    ThumbyColor display for PC - matches hardware API
    On hardware this would use engine_fb, on PC we use pygame
    """

    # Color constants (RGB565)
    BLACK = 0x0000
    WHITE = 0xFFFF
    DARKGRAY = 0x4208
    LIGHTGRAY = 0xBDF7
    LASER_RED = 0xF800
    LASER_GREEN = 0x07E0
    LASER_BLUE = 0x001F
    LASER_COLOR = 0x001F
    SHIELD_CYAN = 0x07FF
    EXPLOSION_ORANGE = 0xFD20
    ORANGE = 0xFD20
    ENEMY_PURPLE = 0x8010
    PURPLE = 0x8010
    ASTEROID_BROWN = 0x8410
    HUD_BLUE = 0x001F
    RED = 0xF800
    GREEN = 0x07E0
    BLUE = 0x001F
    CYAN = 0x07FF
    YELLOW = 0xFFEE
    HIT_COLOR = 0xF800

    def __init__(self, width=128, height=128, scale=4):
        self.width = width
        self.height = height
        self.scale = scale

        # Create internal buffer (RGB565)
        self.buffer_size = width * height * 2
        self.buffer = bytearray(self.buffer_size)
        self.internal_fb = framebuf.FrameBuffer(self.buffer, width, height, framebuf.RGB565)

        # Font setup
        self.font_width = 8
        self.font_height = 8
        self.font_space = 0
        self.font_bmap = None
        self.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT, PC.FONT_SPACE)

        # FPS
        self.fps = PC.FPS

        # Initialize pygame
        self.screen = None
        self.clock = None
        if _ensure_pygame():
            self.screen = pygame.display.set_mode((width * scale, height * scale))
            pygame.display.set_caption("ThumbCommander - ThumbyColor Edition (PC)")
            self.clock = pygame.time.Clock()

    def fill(self, color):
        """Fill screen with color"""
        self.internal_fb.fill(color)

    def setPixel(self, x, y, color):
        """Set a single pixel"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.internal_fb.pixel(x, y, color)

    def getPixel(self, x, y):
        """Get pixel color"""
        return self.internal_fb.pixel(x, y)

    def drawFilledRectangle(self, x, y, width, height, color):
        """Draw filled rectangle"""
        self.internal_fb.fill_rect(x, y, width, height, color)

    def drawRectangle(self, x, y, width, height, color):
        """Draw rectangle outline"""
        self.internal_fb.rect(x, y, width, height, color)

    def drawLine(self, x0, y0, x1, y1, color):
        """Draw line"""
        self.internal_fb.line(x0, y0, x1, y1, color)

    def drawText(self, text, x, y, color):
        """Draw text"""
        self.internal_fb.text(str(text), x, y, color)

    def drawSprite(self, sprite):
        """Draw sprite - uses sprite's render method"""
        if sprite.key == -1:
            self.internal_fb.blit(sprite.sprite_fb, sprite.x, sprite.y)
        else:
            self.internal_fb.blit(sprite.sprite_fb, sprite.x, sprite.y, sprite.key)

    def drawSpriteWithScale(self, sprite):
        """Draw scaled sprite"""
        # Use simple pixel-by-pixel rendering for scaled sprites
        if sprite.scaledWidth <= 0 or sprite.scaledHeight <= 0:
            return

        for screen_y in range(sprite.scaledHeight):
            for screen_x in range(sprite.scaledWidth):
                # Map back to source pixel
                src_x = (screen_x * sprite.width) // sprite.scaledWidth
                src_y = (screen_y * sprite.height) // sprite.scaledHeight

                # Apply mirroring
                if sprite.mirrorX:
                    src_x = sprite.width - 1 - src_x
                if sprite.mirrorY:
                    src_y = sprite.height - 1 - src_y

                # Get pixel from sprite
                pixel = sprite.sprite_fb.pixel(src_x, src_y)
                if pixel is not None and pixel != sprite.key:
                    final_x = sprite.x + screen_x
                    final_y = sprite.y + screen_y
                    if 0 <= final_x < self.width and 0 <= final_y < self.height:
                        self.internal_fb.pixel(final_x, final_y, pixel)

    def draw_fullwidth_sprite(self, filename, y=0, key=-1):
        """Draw a full-width sprite from .COL.bin file"""
        try:
            with open(filename, 'rb') as f:
                # Read header
                header = f.read(8)
                width, height, frame_count, flags = struct.unpack('<HHHH', header)

                # Calculate rows to draw
                rows_to_draw = min(height, 128 - y)
                if rows_to_draw <= 0:
                    return False

                # Load sprite data
                sprite_data = bytearray(width * rows_to_draw * 2)
                f.readinto(sprite_data)

                # Create framebuffer and blit
                sprite_fb = framebuf.FrameBuffer(sprite_data, width, rows_to_draw, framebuf.RGB565)
                self.internal_fb.blit(sprite_fb, 0, y, key)
                return True
        except Exception as e:
            print(f"Error drawing fullwidth sprite: {e}")
            return False

    def update(self):
        """Update display - blit to pygame"""
        if self.screen is None:
            return

        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # Blit internal_fb to pygame surface
        for y in range(self.height):
            for x in range(self.width):
                color565 = self.internal_fb.pixel(x, y)
                if color565 is not None:
                    # Convert RGB565 to RGB888
                    r = ((color565 >> 11) & 0x1F) * 255 // 31
                    g = ((color565 >> 5) & 0x3F) * 255 // 63
                    b = (color565 & 0x1F) * 255 // 31

                    # Draw scaled pixel
                    pygame.draw.rect(
                        self.screen,
                        (r, g, b),
                        (x * self.scale, y * self.scale, self.scale, self.scale)
                    )

        pygame.display.flip()
        if self.clock:
            self.clock.tick(self.fps)

    def show(self):
        """Alias for update()"""
        self.update()

    def enableGrayscale(self):
        """Compatibility method"""
        pass

    def setFPS(self, fps):
        """Set frame rate"""
        self.fps = fps

    def setFont(self, fontFile, width, height, space):
        """Load font file"""
        try:
            self.font_width = width
            self.font_height = height
            self.font_space = space

            if os.path.exists(fontFile):
                size = os.path.getsize(fontFile)
                self.font_bmap = bytearray(size)
                with open(fontFile, 'rb') as f:
                    f.readinto(self.font_bmap)
                self.font_glyphcnt = size // width
            else:
                self.font_bmap = None
        except:
            self.font_bmap = None


class ColorSprite:
    """ThumbyColor sprite - compatible with hardware API"""

    def __init__(self, width, height, bitmapData, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY
        self.width = width
        self.height = height

        # Scaling properties
        self.scale = PC.SPRITE_SCALE
        self.scaledWidth = (width * self.scale) >> 16
        self.scaledHeight = (height * self.scale) >> 16

        self.file_handle = None
        self.frame_data = None
        self.sprite_fb = None
        self.frameCount = 1
        self.currentFrame = 0

        # Load sprite data
        if isinstance(bitmapData, str) and bitmapData.endswith('.COL.bin'):
            self._load_color_sprite(bitmapData)
        elif isinstance(bitmapData, bytearray):
            self.pixels_per_frame = width * height
            self.bytes_per_frame = self.pixels_per_frame * 2
            self.frame_data = bytearray(self.bytes_per_frame)
            for i in range(min(len(bitmapData), self.bytes_per_frame)):
                self.frame_data[i] = bitmapData[i]
            self.frameCount = len(bitmapData) // self.bytes_per_frame
            self.sprite_fb = framebuf.FrameBuffer(self.frame_data, width, height, framebuf.RGB565)

    def _load_color_sprite(self, filename):
        """Load sprite from .COL.bin file"""
        try:
            with open(filename, 'rb') as f:
                # Read header
                header = f.read(8)
                self.width, self.height, self.frameCount, flags = struct.unpack('<HHHH', header)

                # Setup dimensions
                self.scaledWidth = (self.width * self.scale) >> 16
                self.scaledHeight = (self.height * self.scale) >> 16

                # Calculate frame properties
                self.pixels_per_frame = self.width * self.height
                self.bytes_per_frame = self.pixels_per_frame * 2

                # Pre-allocate frame buffer
                self.frame_data = bytearray(self.bytes_per_frame)

                # Load first frame
                f.readinto(self.frame_data)

                # Create framebuffer for this sprite
                self.sprite_fb = framebuf.FrameBuffer(self.frame_data, self.width, self.height, framebuf.RGB565)

                # Keep file open for frame switching
                self.file_handle = open(filename, 'rb')
                self.file_handle.seek(8)  # Skip header
        except Exception as e:
            print(f"Error loading sprite from {filename}: {e}")

    def setFrame(self, frame):
        """Set animation frame"""
        if frame == self.currentFrame or not self.file_handle:
            return

        self.currentFrame = frame % self.frameCount

        # Seek to frame position
        frame_offset = 8 + self.currentFrame * self.bytes_per_frame
        self.file_handle.seek(frame_offset)

        # Read frame data
        self.file_handle.readinto(self.frame_data)

    def setScale(self, scale):
        """Set sprite scale in fixed point"""
        # scale is in fixed point format
        self.scale = (scale * PC.SPRITE_SCALE) >> 16
        self.scaledWidth = (self.width * self.scale) >> 16
        self.scaledHeight = (self.height * self.scale) >> 16

    def setLifes(self, lifes):
        """Store life count"""
        self.lifes = lifes

    def getLifes(self):
        """Get life count"""
        return getattr(self, 'lifes', 0)

    def __del__(self):
        """Clean up file handle"""
        if self.file_handle:
            try:
                self.file_handle.close()
            except:
                pass


def _rumble(duration):
    """Rumble stub - no-op on PC"""
    pass
