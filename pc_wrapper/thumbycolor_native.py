"""
PC wrapper for ThumbyColor display - extends base ColorDisplay
Only overrides what's needed for pygame rendering
"""

import os
import sys

# Import base class
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from thumbycolor_base import ColorDisplay as BaseColorDisplay, ColorSprite as BaseColorSprite, _rumble as base_rumble
from framebuf import FrameBuffer, RGB565

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


class ColorDisplay(BaseColorDisplay):
    """
    PC ColorDisplay - extends base ColorDisplay with pygame rendering
    Only overrides __init__, update(), and draw_fullwidth_sprite()
    """

    def __init__(self, width=128, height=128, scale=4):
        # Call parent __init__ to setup internal_fb and all base attributes
        super().__init__()

        # Add PC-specific attributes
        self.scale = scale
        self.screen = None
        self.clock = None

        # Initialize pygame if available
        if _ensure_pygame():
            self.screen = pygame.display.set_mode((width * scale, height * scale))
            pygame.display.set_caption("ThumbCommander - ThumbyColor Edition (PC)")
            self.clock = pygame.time.Clock()

    def draw_fullwidth_sprite(self, filename, x=0, y=0):
        """Draw full-width sprite from .COL.bin file - PC implementation"""
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

    def update(self):
        """Update display - PC implementation blits to pygame surface"""
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


class ColorSprite(BaseColorSprite):
    """
    PC ColorSprite - extends base ColorSprite with file loading
    """

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        super().__init__(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)

        # Load bitmap data
        if isinstance(bitmap_data, str):
            self.load_from_file(bitmap_data)
        elif isinstance(bitmap_data, tuple):
            # Grayscale compatibility
            self.bitmap = bitmap_data
            self.bitmapByteCount = (width * height + 7) // 8

    def load_from_file(self, filename):
        """Load sprite from .COL.bin file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    self.frame_data = f.read()

                # Parse dimensions from filename
                basename = os.path.basename(filename)
                parts = basename.replace('.COL.bin', '').split('_')

                if len(parts) >= 3:
                    try:
                        self.width = int(parts[-2])
                        self.height = int(parts[-1])
                    except ValueError:
                        pass

                # Calculate frame count
                bytes_per_frame = self.width * self.height * 2
                if len(self.frame_data) >= bytes_per_frame:
                    self.frameCount = len(self.frame_data) // bytes_per_frame

                self.scaledWidth = self.width
                self.scaledHeight = self.height
        except Exception as e:
            print(f"Error loading sprite from {filename}: {e}")

    def render(self, display):
        """Render sprite to display using blit"""
        if not self.frame_data:
            return

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


# Export _rumble from base
_rumble = base_rumble
