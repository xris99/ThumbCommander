"""
ThumbyColor native display and sprite emulation for PC
Uses pygame for rendering
"""

import pygame
import os
from .framebuf import FrameBuffer, RGB565


class ColorDisplay:
    """
    ThumbyColor display emulation using pygame
    Implements the same API as the ThumbyColor display
    """

    def __init__(self, width=128, height=128, scale=4):
        """
        Initialize pygame display

        Args:
            width: Display width in pixels (default 128)
            height: Display height in pixels (default 128)
            scale: Scale factor for the window (default 4 for 512x512 window)
        """
        pygame.init()
        self.width = width
        self.height = height
        self.scale = scale

        # Create window
        self.screen = pygame.display.set_mode((width * scale, height * scale))
        pygame.display.set_caption("ThumbCommander - ThumbyColor Edition (PC)")

        # Create internal framebuffer (RGB565 format)
        self.buffer = bytearray(width * height * 2)  # 2 bytes per pixel for RGB565
        self.internal_fb = FrameBuffer(self.buffer, width, height, RGB565)

        # Font settings
        self.font_file = None
        self.font_width = 8
        self.font_height = 8
        self.font_space = 0
        self.font = None
        self.font_data = None

        # FPS control
        self.clock = pygame.time.Clock()
        self.fps = 60

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
        self.ENEMY_PURPLE = 0x8010

        # Grayscale enabled flag
        self.grayscale_enabled = False

    def enableGrayscale(self):
        """Enable grayscale mode (for compatibility)"""
        self.grayscale_enabled = True

    def setFPS(self, fps):
        """Set target FPS"""
        self.fps = fps

    def setFont(self, font_file, width, height, space):
        """Set font parameters"""
        self.font_file = font_file
        self.font_width = width
        self.font_height = height
        self.font_space = space

        # Try to load font if it exists
        try:
            if font_file and os.path.exists(font_file):
                with open(font_file, 'rb') as f:
                    self.font_data = f.read()
        except:
            pass

        # Fall back to pygame font
        try:
            self.font = pygame.font.Font(None, height * 2)
        except:
            self.font = None

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
        self.internal_fb.rect(x, y, w, h, color, fill=True)

    def drawText(self, text, x, y, color):
        """Draw text at (x, y)"""
        if self.font:
            # Use pygame font for better rendering on PC
            for i, char in enumerate(str(text)):
                char_x = x + i * (self.font_width + self.font_space)
                # Draw simple character representation
                for cy in range(self.font_height):
                    for cx in range(self.font_width):
                        # Simple pattern - this would be replaced with actual font data
                        if (ord(char) * cx + cy) % 7 < 4:
                            self.internal_fb.pixel(char_x + cx, y + cy, color)
        else:
            # Fallback text rendering
            for i, char in enumerate(str(text)):
                char_x = x + i * 6
                self.internal_fb.rect(char_x, y, 5, 8, color)

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

    def draw_sprite_from_file(self, filename, x, y, frame=0):
        """Draw sprite directly from color file"""
        try:
            if os.path.exists(filename):
                # Load and draw the color bitmap
                with open(filename, 'rb') as f:
                    data = f.read()
                    # Parse filename to get dimensions
                    # Format: name_width_height.COL.bin
                    basename = os.path.basename(filename)
                    parts = basename.replace('.COL.bin', '').split('_')

                    # Try to extract width and height from filename
                    sprite_width = self.width
                    sprite_height = self.height

                    if len(parts) >= 3:
                        try:
                            sprite_width = int(parts[-2])
                            sprite_height = int(parts[-1])
                        except ValueError:
                            pass

                    # Draw sprite data (RGB565 format: 2 bytes per pixel)
                    bytes_per_pixel = 2
                    bytes_per_frame = sprite_width * sprite_height * bytes_per_pixel

                    # Calculate frame offset
                    frame_offset = frame * bytes_per_frame

                    if frame_offset + bytes_per_frame <= len(data):
                        for py in range(sprite_height):
                            for px in range(sprite_width):
                                idx = frame_offset + (py * sprite_width + px) * bytes_per_pixel
                                if idx + 1 < len(data):
                                    # Read RGB565 color (little endian)
                                    color = data[idx] | (data[idx + 1] << 8)
                                    # Draw to screen
                                    screen_x = x + px
                                    screen_y = y + py
                                    if 0 <= screen_x < self.width and 0 <= screen_y < self.height:
                                        self.internal_fb.pixel(screen_x, screen_y, color)
        except Exception as e:
            print(f"Error loading sprite from {filename}: {e}")

    def draw_fullwidth_sprite(self, filename, y=0):
        """Draw full-width sprite from file"""
        self.draw_sprite_from_file(filename, 0, y)

    def rgb565_to_rgb888(self, color565):
        """Convert RGB565 to RGB888 for pygame"""
        r = ((color565 >> 11) & 0x1F) * 255 // 31
        g = ((color565 >> 5) & 0x3F) * 255 // 63
        b = (color565 & 0x1F) * 255 // 31
        return (r, g, b)

    def update(self):
        """Update display - blit framebuffer to screen"""
        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                import sys
                sys.exit()

        # Convert framebuffer to pygame surface
        for y in range(self.height):
            for x in range(self.width):
                color565 = self.internal_fb.pixel(x, y)
                if color565 is not None:
                    rgb = self.rgb565_to_rgb888(color565)
                    # Draw scaled pixel
                    pygame.draw.rect(
                        self.screen,
                        rgb,
                        (x * self.scale, y * self.scale, self.scale, self.scale)
                    )

        pygame.display.flip()
        self.clock.tick(self.fps)


class ColorSprite:
    """
    ThumbyColor sprite emulation
    """

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        """
        Initialize sprite

        Args:
            width: Sprite width
            height: Sprite height
            bitmap_data: Either a filename (str) or tuple of (bitmap, shadow)
            x, y: Position
            key: Transparent color key
            mirrorX, mirrorY: Mirroring flags
        """
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
            # Load from color file
            self.load_from_file(bitmap_data)
        elif isinstance(bitmap_data, tuple):
            # Load from bitmap/shadow pair (grayscale compatibility)
            self.bitmap = bitmap_data
            self.bitmapByteCount = (width * height + 7) // 8

    def load_from_file(self, filename):
        """Load sprite from color file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    self.frame_data = f.read()

                # Try to get dimensions from filename
                # Format: name_width_height.COL.bin
                basename = os.path.basename(filename)
                parts = basename.replace('.COL.bin', '').split('_')

                if len(parts) >= 3:
                    try:
                        self.width = int(parts[-2])
                        self.height = int(parts[-1])
                    except ValueError:
                        pass

                # Calculate frame count from file size
                bytes_per_frame = self.width * self.height * 2  # RGB565
                if len(self.frame_data) >= bytes_per_frame:
                    self.frameCount = len(self.frame_data) // bytes_per_frame

                # Initialize scaled dimensions
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
        """Render sprite to display"""
        if self.frame_data:
            # Render from frame data
            bytes_per_frame = self.width * self.height * 2
            frame_offset = self.currentFrame * bytes_per_frame

            for py in range(self.height):
                for px in range(self.width):
                    idx = frame_offset + (py * self.width + px) * 2
                    if idx + 1 < len(self.frame_data):
                        color = self.frame_data[idx] | (self.frame_data[idx + 1] << 8)
                        # Skip transparent pixels
                        if color != self.key:
                            screen_x = self.x + px
                            screen_y = self.y + py
                            if hasattr(display, 'internal_fb'):
                                display.internal_fb.pixel(screen_x, screen_y, color)
        else:
            # Fallback - draw rectangle
            if hasattr(display, 'drawRectangle'):
                display.drawRectangle(self.x, self.y, self.width, self.height, display.WHITE)

    def render_scaled(self, display):
        """Render scaled sprite"""
        if self.frame_data and self.scaledWidth > 0 and self.scaledHeight > 0:
            # Render with scaling
            bytes_per_frame = self.width * self.height * 2
            frame_offset = self.currentFrame * bytes_per_frame

            # Simple nearest-neighbor scaling
            for screen_y in range(self.scaledHeight):
                for screen_x in range(self.scaledWidth):
                    # Map back to source pixel
                    src_x = (screen_x * self.width) // self.scaledWidth
                    src_y = (screen_y * self.height) // self.scaledHeight

                    # Apply mirroring if needed
                    if self.mirrorX:
                        src_x = self.width - 1 - src_x
                    if self.mirrorY:
                        src_y = self.height - 1 - src_y

                    idx = frame_offset + (src_y * self.width + src_x) * 2
                    if idx + 1 < len(self.frame_data):
                        color = self.frame_data[idx] | (self.frame_data[idx + 1] << 8)
                        # Skip transparent pixels
                        if color != self.key:
                            final_x = self.x + screen_x
                            final_y = self.y + screen_y
                            if hasattr(display, 'internal_fb'):
                                display.internal_fb.pixel(final_x, final_y, color)
        else:
            # Fallback
            self.render(display)


def _rumble(duration):
    """Rumble stub - does nothing on PC"""
    pass
