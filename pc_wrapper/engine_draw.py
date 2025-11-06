"""
Engine draw module for PC
Provides back_fb object that the hardware thumbycolor_native uses to render
"""

import sys

# Lazy import pygame
pygame = None
_pygame_initialized = False
_back_fb_instance = None


def _ensure_pygame():
    """Ensure pygame is imported and initialized"""
    global pygame, _pygame_initialized
    if pygame is None:
        try:
            import pygame as pg
            import os
            # IMPORTANT: Initialize mixer BEFORE pygame.init() to set audio parameters
            # Using 8000 Hz to match sound effects speed (FXEngine at 8000 Hz is correct)
            # Cutscene audio (15625 Hz) will be resampled down to play slower
            # Reinitializing pygame.mixer breaks Channel playback on macOS!
            # Try real audio hardware first, fall back to dummy if that fails
            pg.mixer.pre_init(frequency=8000, size=-16, channels=1, buffer=512)
            try:
                pg.init()
                print("[Audio] Pygame initialized at 8000 Hz with real audio hardware", flush=True)
            except Exception as e:
                # Real audio failed, try dummy mode
                print(f"[Audio] Real audio hardware failed ({e}), falling back to dummy mode", flush=True)
                os.environ['SDL_AUDIODRIVER'] = 'dummy'
                pg.mixer.quit()  # Clean up failed attempt
                pg.mixer.pre_init(frequency=8000, size=-16, channels=1, buffer=512)
                pg.init()
                print("[Audio] Pygame initialized at 8000 Hz with dummy audio driver", flush=True)
            pygame = pg
            _pygame_initialized = True
        except ImportError as e:
            print(f"[Audio] Failed to import pygame: {e}", flush=True)
            _pygame_initialized = False
    return _pygame_initialized


class BackFrameBuffer:
    """
    Represents the engine's back framebuffer
    On hardware, this is the engine's internal buffer that gets blitted to screen
    On PC, we render it to pygame surface
    """

    def __init__(self, width=128, height=128, scale=4):
        self.width = width
        self.height = height
        self.scale = scale
        self.screen = None
        self.clock = None

        # Initialize pygame
        if _ensure_pygame():
            self.screen = pygame.display.set_mode((width * scale, height * scale))
            pygame.display.set_caption("ThumbCommander - ThumbyColor Edition (PC)")
            self.clock = pygame.time.Clock()

    def blit(self, source_fb, x, y, key=-1, palette=None):
        """
        Blit a framebuffer to the pygame screen
        This is called by the hardware thumbycolor_native.py in update()

        Args:
            source_fb: FrameBuffer object to blit from
            x, y: Position (should be 0, 0 for full screen)
            key: Transparency color key (unused for full screen blit)
            palette: Color palette (unused)
        """
        if self.screen is None:
            return

        # Handle pygame events (window close, etc.)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        # Blit framebuffer to pygame surface
        # source_fb should have a buffer attribute with RGB565 data
        if hasattr(source_fb, 'buffer') and hasattr(source_fb, 'width') and hasattr(source_fb, 'height'):
            for py in range(min(source_fb.height, self.height)):
                for px in range(min(source_fb.width, self.width)):
                    # Read pixel from framebuffer
                    pixel = source_fb.pixel(px, py)
                    if pixel is not None:
                        # Convert RGB565 to RGB888
                        r = ((pixel >> 11) & 0x1F) * 255 // 31
                        g = ((pixel >> 5) & 0x3F) * 255 // 63
                        b = (pixel & 0x1F) * 255 // 31

                        # Draw scaled pixel
                        screen_x = (x + px) * self.scale
                        screen_y = (y + py) * self.scale
                        pygame.draw.rect(
                            self.screen,
                            (r, g, b),
                            (screen_x, screen_y, self.scale, self.scale)
                        )

        pygame.display.flip()

    def set_fps(self, fps):
        """Set target FPS for pygame clock"""
        # This will be used by the clock in tick()
        pass


def back_fb():
    """
    Return the back framebuffer instance
    This is called by hardware thumbycolor_native.py to get the engine's framebuffer
    """
    global _back_fb_instance
    if _back_fb_instance is None:
        _back_fb_instance = BackFrameBuffer()
    return _back_fb_instance
