"""
CPython emulation of the ThumbyColor `engine_draw` firmware module.
Provides the back_fb() back framebuffer that the color display
(thumby_engine.display.color) renders into via pygame.

Since the ThumbyColor revision this module also renders the *original
Thumby* screen (72x40, two 1bpp bitplanes -> 4 gray levels) for the
PC Thumby mode (thumby_engine.pc.grayscale_display). Same window
mechanics, smaller panel.
"""

import os
import sys
import threading

# Lazy import pygame
pygame = None
_pygame_initialized = False
_back_fb_instance = None

# Serialize window rendering: the Thumby boot intro drives frames from a
# machine.Timer callback thread while the main thread may draw too.
_render_lock = threading.Lock()

# The four gray levels the original Thumby OLED composes from the
# (bitplane, shading-bitplane) pair. Hardware duty per subframe:
# WHITE 3/3 (all subframes), LIGHTGRAY 2/3 (MID+BRIGHT), DARKGRAY 1/3
# (DIM only), BLACK 0 -> 255/170/85/0. Index = hardware level value
# (bit0 = light, bit1 = shading).
GRAY_BY_LEVEL = [(0, 0, 0), (255, 255, 255), (85, 85, 85), (170, 170, 170)]
_PALETTE_256 = list(GRAY_BY_LEVEL) + [(0, 0, 0)] * 252


def _ensure_pygame():
    """Ensure pygame is imported and initialized"""
    global pygame, _pygame_initialized
    if pygame is None:
        try:
            import pygame as pg
            # IMPORTANT: Initialize mixer at 15625 Hz BEFORE pygame.init()
            # This must match the frequency in thumby_engine.audio.pc
            # pygame.mixer can only be initialized ONCE, so we do it here first
            pg.mixer.pre_init(frequency=15625, size=-16, channels=1, buffer=512)
            try:
                pg.init()
                print("[Display] Pygame initialized (mixer at 15625 Hz for cutscene sync)", flush=True)
            except Exception as e:
                print(f"[Display] Pygame initialization failed: {e}", flush=True)
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

    def __init__(self, width=128, height=128, scale=4, caption=None,
                 grayscale=False):
        self.width = width
        self.height = height
        self.scale = scale
        self.grayscale = grayscale
        self.screen = None
        self.clock = None
        # Fast grayscale path (palettized blit + integer scale). Disabled
        # automatically if the transform ever fails (e.g. exotic SDL build).
        self._use_transform = True

        # Initialize pygame
        if _ensure_pygame():
            self.screen = pygame.display.set_mode((width * scale, height * scale))
            if caption is None:
                caption = "Thumby 72x40 (PC)" if grayscale else "ThumbyColor (PC)"
            pygame.display.set_caption(caption)
            self.clock = pygame.time.Clock()

    def blit(self, source_fb, x, y, key=-1, palette=None):
        """
        Blit a framebuffer to the pygame screen
        This is called by the color display's update()

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

    def blit_grayscale(self, buffer, shading, invert=0):
        """
        Render the original-Thumby screen: two 1bpp column-major page
        bitplanes (light plane + shading plane, 5 pages of 72 bytes for
        40 rows) combined into the 4-level gray image and scaled up.

        Args:
            buffer:  memoryview of the light bitplane (72*5 bytes)
            shading: memoryview of the shading bitplane (72*5 bytes)
            invert:  hardware invert flag (flips the light plane)
        """
        if self.screen is None:
            return

        with _render_lock:
            # Handle pygame events (window close, etc.). os._exit is used
            # instead of sys.exit: this render can be called from the intro
            # Timer thread, and SystemExit there would only kill the thread
            # and leave the game stuck in a busy-wait intro join.
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    os._exit(0)

            W = self.width
            H = self.height
            xor = 0xFF if invert else 0x00

            # Decode bitplanes -> one level byte per pixel (row-major).
            levels = bytearray(W * H)
            if xor:
                for y in range(H):
                    o = (y >> 3) * W
                    bit = 1 << (y & 7)
                    row = y * W
                    for x in range(W):
                        v = ((buffer[o + x] ^ xor) & bit) and 1
                        v |= (shading[o + x] & bit) and 2
                        levels[row + x] = v
            else:
                for y in range(H):
                    o = (y >> 3) * W
                    bit = 1 << (y & 7)
                    row = y * W
                    for x in range(W):
                        v = ((buffer[o + x] & bit) and 1)
                        v |= (shading[o + x] & bit) and 2
                        levels[row + x] = v

            self._present(levels)

    def _present(self, levels):
        """Push a row-major level byte per pixel to the window."""
        if self._use_transform:
            try:
                surf = pygame.image.frombuffer(bytes(levels),
                                               (self.width, self.height), 'P')
                surf.set_palette(_PALETTE_256)
                scaled = pygame.transform.scale(
                    surf, (self.width * self.scale, self.height * self.scale))
                self.screen.blit(scaled, (0, 0))
                pygame.display.flip()
                return
            except Exception:
                self._use_transform = False

        # Robust fallback: one scaled pygame rect per pixel (same pattern
        # the RGB565 blit uses, slower but always available).
        s = self.scale
        W = self.width
        for y in range(self.height):
            row = y * W
            sy = y * s
            for x in range(W):
                pygame.draw.rect(self.screen, GRAY_BY_LEVEL[levels[row + x]],
                                 (x * s, sy, s, s))
        pygame.display.flip()

    def set_fps(self, fps):
        """Set target FPS for pygame clock"""
        # This will be used by the clock in tick()
        pass


def back_fb(width=128, height=128, scale=4, caption=None, grayscale=False):
    """
    Return the back framebuffer instance
    This is called by hardware thumbycolor_native.py to get the engine's framebuffer.
    On the PC emulation it is also called by the grayscale display with its
    panel geometry; the first call wins (one mode per process).
    """
    global _back_fb_instance
    if _back_fb_instance is None:
        _back_fb_instance = BackFrameBuffer(width, height, scale, caption,
                                            grayscale)
    return _back_fb_instance
