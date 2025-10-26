"""
color_native.py - Unified ThumbyColor display module for both hardware and PC

On hardware: Re-exports from thumbycolor_native
On PC: Implements ColorDisplay and ColorSprite with pygame backend
"""

# Detect platform
IS_PC = False
try:
    import thumbycolor_native
    # Hardware mode - just re-export everything
    from thumbycolor_native import ColorDisplay, ColorSprite, _rumble
except ImportError:
    # PC mode - implement the API
    IS_PC = True

    import pygame
    pygame.init()

    # Display constants
    DISPLAY_WIDTH = 128
    DISPLAY_HEIGHT = 128
    SCALE_FACTOR = 4

    # Pre-compute RGB565 to RGB888 lookup table for fast conversion
    RGB565_TO_RGB888 = {}
    for rgb565 in range(65536):
        r5 = (rgb565 >> 11) & 0x1F
        g6 = (rgb565 >> 5) & 0x3F
        b5 = rgb565 & 0x1F
        r8 = (r5 << 3) | (r5 >> 2)
        g8 = (g6 << 2) | (g6 >> 4)
        b8 = (b5 << 3) | (b5 >> 2)
        RGB565_TO_RGB888[rgb565] = (r8 << 16) | (g8 << 8) | b8


    class ColorDisplay:
        """PC implementation of ThumbyColor ColorDisplay"""

        # Color constants (RGB565)
        BLACK = 0x0000
        WHITE = 0xFFFF
        DARKGRAY = 0x4208
        LIGHTGRAY = 0xBDF7
        RED = 0xF800
        GREEN = 0x07E0
        BLUELIGHTLIGHT = 0x633f
        BLUELIGHT = 0x297f
        BLUE = 0x001F
        BLUEDARK = 0x0016
        BLUEDARKDARK = 0x0010
        CYAN = 0x07FF
        ORANGE = 0xFD20
        PURPLE = 0x8010
        BROWN = 0x8410
        YELLOW = 0xFFEE
        LASER_COLOR = ORANGE
        LASER_BLUE = 0x001F
        ENEMY_PURPLE = 0x8010
        HIT_COLOR = 0xF800

        def __init__(self):
            # Create pygame window
            self.screen = pygame.display.set_mode((DISPLAY_WIDTH * SCALE_FACTOR, DISPLAY_HEIGHT * SCALE_FACTOR))
            pygame.display.set_caption("ThumbCommander - PC Mode")
            self.clock = pygame.time.Clock()
            self.target_fps = 60

            # Create internal framebuffer (RGB565 format, just like hardware)
            from framebuf import FrameBuffer, RGB565
            self.fb_buffer = bytearray(DISPLAY_WIDTH * DISPLAY_HEIGHT * 2)
            self.internal_fb = FrameBuffer(self.fb_buffer, DISPLAY_WIDTH, DISPLAY_HEIGHT, RGB565)

            # Pygame surface for rendering
            self.pygame_surface = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))

            # Font properties
            self.font_width = 3
            self.font_height = 5
            self.font_space = 1
            self.current_font = pygame.font.Font(None, 10)

            # Text queue (render after buffer sync)
            self.text_queue = []

            # Button registry for automatic updates
            self.buttons = []

        def setFPS(self, fps):
            """Set target FPS"""
            self.target_fps = fps

        def fill(self, color):
            """Fill screen with color"""
            self.internal_fb.fill(color)

        def setPixel(self, x, y, color):
            """Set a single pixel"""
            self.internal_fb.pixel(x, y, color)

        def drawLine(self, x0, y0, x1, y1, color):
            """Draw a line"""
            self.internal_fb.line(x0, y0, x1, y1, color)

        def drawRectangle(self, x, y, width, height, color):
            """Draw rectangle outline"""
            self.internal_fb.rect(x, y, width, height, color, False)

        def drawFilledRectangle(self, x, y, width, height, color):
            """Draw filled rectangle"""
            self.internal_fb.rect(x, y, width, height, color, True)

        def drawSprite(self, sprite):
            """Draw a sprite at its position"""
            if hasattr(sprite, 'draw_to_framebuffer'):
                sprite.draw_to_framebuffer(self.internal_fb)

        def drawSpriteWithScale(self, sprite):
            """Draw a sprite with scaling"""
            self.drawSprite(sprite)

        def draw_sprite_from_file(self, filename, x, y, key=-1):
            """Draw sprite directly from file"""
            temp_sprite = ColorSprite(0, 0, filename, x, y, key)
            self.drawSprite(temp_sprite)

        def draw_fullwidth_sprite(self, filename, y_offset=0, key=-1):
            """Draw fullwidth sprite"""
            self.draw_sprite_from_file(filename, 0, y_offset, key)

        def drawText(self, text, x, y, color):
            """Queue text for rendering"""
            self.text_queue.append((text, x, y, color))

        def setFont(self, font_path, width, height, space):
            """Set font (stubbed - uses pygame font)"""
            self.font_width = width
            self.font_height = height
            self.font_space = space

        def enableGrayscale(self):
            """Stub for grayscale mode"""
            pass

        def disableGrayscale(self):
            """Stub for grayscale mode"""
            pass

        def register_button(self, button):
            """Register a button for automatic updates"""
            if button not in self.buttons:
                self.buttons.append(button)

        def update(self):
            """Update display - sync framebuffer to screen"""
            # Handle pygame events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    import sys
                    sys.exit()

            # Update all registered buttons
            for button in self.buttons:
                button.update()

            # Sync RGB565 buffer to pygame surface
            # Fast conversion using lookup table and fromstring
            rgb_data = bytearray(DISPLAY_WIDTH * DISPLAY_HEIGHT * 3)
            rgb_idx = 0
            fb_idx = 0

            for i in range(DISPLAY_WIDTH * DISPLAY_HEIGHT):
                if fb_idx + 1 < len(self.fb_buffer):
                    rgb565 = self.fb_buffer[fb_idx] | (self.fb_buffer[fb_idx + 1] << 8)
                    rgb888 = RGB565_TO_RGB888[rgb565]
                    rgb_data[rgb_idx] = (rgb888 >> 16) & 0xFF      # R
                    rgb_data[rgb_idx + 1] = (rgb888 >> 8) & 0xFF   # G
                    rgb_data[rgb_idx + 2] = rgb888 & 0xFF          # B
                rgb_idx += 3
                fb_idx += 2

            # Create surface from RGB data
            self.pygame_surface = pygame.image.fromstring(bytes(rgb_data), (DISPLAY_WIDTH, DISPLAY_HEIGHT), 'RGB')

            # Render queued text on top
            for text, x, y, color in self.text_queue:
                try:
                    rgb888 = RGB565_TO_RGB888[color]
                    r = (rgb888 >> 16) & 0xFF
                    g = (rgb888 >> 8) & 0xFF
                    b = rgb888 & 0xFF
                    text_surface = self.current_font.render(str(text), True, (r, g, b))
                    self.pygame_surface.blit(text_surface, (x, y))
                except:
                    pass
            self.text_queue = []

            # Scale and blit to screen
            scaled = pygame.transform.scale(self.pygame_surface,
                                          (DISPLAY_WIDTH * SCALE_FACTOR, DISPLAY_HEIGHT * SCALE_FACTOR))
            self.screen.blit(scaled, (0, 0))
            pygame.display.flip()

            # Control FPS
            self.clock.tick(self.target_fps)


    class ColorSprite:
        """PC implementation of ThumbyColor ColorSprite"""

        def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
            self.x = x
            self.y = y
            self.key = key
            self.mirrorX = mirrorX
            self.mirrorY = mirrorY
            self.current_frame = 0
            self.scale = 65536  # 1.0 in 16.16 fixed point
            self.lifes = 0

            # Load sprite from file
            if isinstance(bitmap_data, str) and bitmap_data.endswith('.COL.bin'):
                self._load_from_file(bitmap_data)
            else:
                # Simple bitmap data
                self.width = width
                self.height = height
                self.frameCount = 1
                from framebuf import FrameBuffer, RGB565
                frame_size = width * height * 2
                self.frame_buffers = [FrameBuffer(bytearray(frame_size), width, height, RGB565)]

        def _load_from_file(self, filename):
            """Load sprite from .COL.bin file"""
            from framebuf import FrameBuffer, RGB565

            with open(filename, 'rb') as f:
                # Read header (6 bytes: width, height, frameCount, each 2 bytes)
                header = f.read(6)
                self.width = header[0] | (header[1] << 8)
                self.height = header[2] | (header[3] << 8)
                self.frameCount = header[4] | (header[5] << 8)

                # Read frame data
                self.frame_buffers = []
                frame_size = self.width * self.height * 2
                for _ in range(self.frameCount):
                    frame_data = bytearray(f.read(frame_size))
                    fb = FrameBuffer(frame_data, self.width, self.height, RGB565)
                    self.frame_buffers.append(fb)

        def setFrame(self, frame):
            """Set current animation frame"""
            if 0 <= frame < self.frameCount:
                self.current_frame = frame

        def setScale(self, scale):
            """Set sprite scale (16.16 fixed point)"""
            self.scale = scale

        def getLifes(self):
            """Get life count"""
            return self.lifes

        def setLifes(self, lifes):
            """Set life count"""
            self.lifes = lifes

        def draw_to_framebuffer(self, target_fb):
            """Draw sprite to target framebuffer"""
            if not self.frame_buffers:
                return

            source_fb = self.frame_buffers[self.current_frame]
            target_fb.blit(source_fb, self.x, self.y, self.key)


    def _rumble(duration):
        """Stub for rumble"""
        pass


    # ButtonClass for PC keyboard input
    class ButtonClass:
        """PC keyboard button implementation matching ThumbyColor ButtonClass API"""

        def __init__(self, key_code):
            """key_code: pygame key constant"""
            self.key_code = key_code
            self.current_state = False
            self.previous_state = False
            self._just_pressed = False

        def update(self):
            """Update button state - must be called each frame"""
            self.previous_state = self.current_state
            keys = pygame.key.get_pressed()
            self.current_state = keys[self.key_code]
            self._just_pressed = self.current_state and not self.previous_state

        def pressed(self):
            """Returns True if button is currently pressed"""
            return self.current_state

        def justPressed(self):
            """Returns True if button was just pressed this frame"""
            return self._just_pressed
