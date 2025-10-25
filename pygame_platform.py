"""
pygame_platform.py - Pygame wrapper that mimics ThumbyColor API
This allows running ThumbCommander on PC for testing without modifying game code
"""
import pygame
import os
from array import array

# Initialize pygame
pygame.init()

# Emulate ThumbyColor display (128x128, RGB565)
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 128
SCALE_FACTOR = 4  # Display at 4x size for visibility

class PygameDisplay:
    """Mimics ThumbyColor ColorDisplay API"""

    # Color constants (RGB565 format converted to RGB888)
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
    YELLOW = 0xffee
    LASER_BLUE = 0x001F
    ENEMY_PURPLE = 0x8010

    def __init__(self):
        self.screen = pygame.display.set_mode(
            (DISPLAY_WIDTH * SCALE_FACTOR, DISPLAY_HEIGHT * SCALE_FACTOR)
        )
        pygame.display.set_caption("ThumbCommander - Pygame Test")
        self.clock = pygame.time.Clock()
        self.target_fps = 60

        # Internal framebuffer (128x128 RGB888)
        self.internal_fb = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        self.internal_fb.fill((0, 0, 0))

        # Font loading
        self.current_font = None
        self.font_width = 3
        self.font_height = 5
        self.font_space = 1

        # Load fonts
        try:
            self.font_3x5 = pygame.font.Font(None, 10)  # Small font
            self.font_5x7 = pygame.font.Font(None, 14)  # Medium font
            self.font_8x8 = pygame.font.Font(None, 16)  # Larger font
            self.current_font = self.font_3x5
        except:
            self.current_font = pygame.font.Font(None, 10)

        # Sprite cache
        self.sprite_cache = {}

    def rgb565_to_rgb888(self, rgb565):
        """Convert RGB565 to RGB888 tuple"""
        r = ((rgb565 >> 11) & 0x1F) * 255 // 31
        g = ((rgb565 >> 5) & 0x3F) * 255 // 63
        b = (rgb565 & 0x1F) * 255 // 31
        return (r, g, b)

    def setFPS(self, fps):
        """Set target frame rate"""
        self.target_fps = fps

    def fill(self, color):
        """Fill screen with color"""
        rgb = self.rgb565_to_rgb888(color)
        self.internal_fb.fill(rgb)

    def setPixel(self, x, y, color):
        """Draw a single pixel"""
        if 0 <= x < DISPLAY_WIDTH and 0 <= y < DISPLAY_HEIGHT:
            rgb = self.rgb565_to_rgb888(color)
            self.internal_fb.set_at((int(x), int(y)), rgb)

    def drawLine(self, x0, y0, x1, y1, color):
        """Draw a line"""
        rgb = self.rgb565_to_rgb888(color)
        pygame.draw.line(self.internal_fb, rgb, (int(x0), int(y0)), (int(x1), int(y1)))

    def drawRectangle(self, x, y, width, height, color):
        """Draw rectangle outline"""
        rgb = self.rgb565_to_rgb888(color)
        pygame.draw.rect(self.internal_fb, rgb, (int(x), int(y), int(width), int(height)), 1)

    def drawFilledRectangle(self, x, y, width, height, color):
        """Draw filled rectangle"""
        rgb = self.rgb565_to_rgb888(color)
        pygame.draw.rect(self.internal_fb, rgb, (int(x), int(y), int(width), int(height)))

    def setFont(self, font_file, width, height, space):
        """Set current font"""
        self.font_width = width
        self.font_height = height
        self.font_space = space

        # Map to pygame fonts
        if "3x5" in font_file:
            self.current_font = self.font_3x5
        elif "5x7" in font_file:
            self.current_font = self.font_5x7
        elif "8x8" in font_file or "6x10" in font_file:
            self.current_font = self.font_8x8

    def drawText(self, text, x, y, color):
        """Draw text"""
        rgb = self.rgb565_to_rgb888(color)
        text_surface = self.current_font.render(str(text), True, rgb)
        self.internal_fb.blit(text_surface, (int(x), int(y)))

    def drawSprite(self, sprite):
        """Draw a sprite"""
        if hasattr(sprite, 'draw'):
            sprite.draw(self)

    def drawSpriteWithScale(self, sprite):
        """Draw a scaled sprite"""
        if hasattr(sprite, 'draw_scaled'):
            sprite.draw_scaled(self)
        else:
            self.drawSprite(sprite)

    def draw_sprite_from_file(self, filename, x, y, frame):
        """Draw sprite directly from file (stub for now)"""
        # For testing, just draw a placeholder
        rgb = self.rgb565_to_rgb888(self.LIGHTGRAY)
        pygame.draw.rect(self.internal_fb, rgb, (int(x), int(y), 20, 20), 1)

    def draw_fullwidth_sprite(self, filename, y=0, frame=0):
        """Draw full-width sprite (stub)"""
        pass

    def update(self):
        """Update the display"""
        # Scale up the internal framebuffer to the screen
        scaled = pygame.transform.scale(
            self.internal_fb,
            (DISPLAY_WIDTH * SCALE_FACTOR, DISPLAY_HEIGHT * SCALE_FACTOR)
        )
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()
        self.clock.tick(self.target_fps)

        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                import sys
                sys.exit()

    def enableGrayscale(self):
        """Stub for compatibility"""
        pass


class PygameSprite:
    """Mimics ThumbyColor ColorSprite API"""

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY
        self.currentFrame = 0
        self.frameCount = 13  # Default for enemy sprites
        self.scaledWidth = width
        self.scaledHeight = height
        self.scale_factor = 1.0

        # Create a placeholder surface
        self.surface = pygame.Surface((width, height))
        self.surface.fill((100, 100, 100))  # Gray placeholder

        # For bitmap data, create simple colored surface
        if isinstance(bitmap_data, str):
            # File-based sprite - use color based on filename
            if "enemy" in bitmap_data:
                self.surface.fill((200, 100, 100))  # Red for enemies
            elif "astroid" in bitmap_data:
                self.surface.fill((150, 150, 100))  # Brown for asteroids
            elif "shield" in bitmap_data:
                self.surface.fill((100, 100, 200))  # Blue for shields

    def setFrame(self, frame):
        """Set current frame"""
        self.currentFrame = frame

    def setScale(self, scale):
        """Set sprite scale"""
        if isinstance(scale, int):
            # Fixed-point scale (65536 = 1.0)
            self.scale_factor = scale / 65536.0
        else:
            self.scale_factor = scale
        self.scaledWidth = int(self.width * self.scale_factor)
        self.scaledHeight = int(self.height * self.scale_factor)

    def draw(self, display):
        """Draw sprite at x, y"""
        if hasattr(display, 'internal_fb'):
            display.internal_fb.blit(self.surface, (int(self.x), int(self.y)))

    def draw_scaled(self, display):
        """Draw scaled sprite"""
        if self.scaledWidth > 0 and self.scaledHeight > 0:
            scaled = pygame.transform.scale(self.surface, (self.scaledWidth, self.scaledHeight))
            if hasattr(display, 'internal_fb'):
                display.internal_fb.blit(scaled, (int(self.x), int(self.y)))

    def setLifes(self, lifes):
        """Store life count for HUD"""
        self._lifes = lifes

    def getLifes(self):
        """Get life count"""
        return getattr(self, '_lifes', 0)


class ButtonClass:
    """Mimics thumbyButton.ButtonClass with pygame keyboard"""

    def __init__(self, key_mapping):
        self.key_mapping = key_mapping
        self._pressed = False
        self._just_pressed = False
        self._prev_state = False

    def update(self):
        """Update button state from pygame keyboard"""
        keys = pygame.key.get_pressed()
        current_state = keys[self.key_mapping]

        self._just_pressed = current_state and not self._prev_state
        self._pressed = current_state
        self._prev_state = current_state

    def pressed(self):
        """Check if button is currently pressed"""
        return self._pressed

    def justPressed(self):
        """Check if button was just pressed this frame"""
        result = self._just_pressed
        self._just_pressed = False  # Clear after read
        return result


# Button mappings (keyboard keys)
# Note: Uses Y instead of Z for German (QWERTZ) keyboard compatibility
BUTTON_MAPPINGS = {
    'A': pygame.K_y,      # Y key (Fire) - works on both QWERTY and QWERTZ
    'B': pygame.K_x,      # X key
    'UP': pygame.K_UP,
    'DOWN': pygame.K_DOWN,
    'LEFT': pygame.K_LEFT,
    'RIGHT': pygame.K_RIGHT,
    'LB': pygame.K_q,     # Q key (Left bumper - target previous)
    'RB': pygame.K_w,     # W key (Right bumper - target next)
    'MENU': pygame.K_ESCAPE
}

# Create button instances
buttonA = ButtonClass(BUTTON_MAPPINGS['A'])
buttonB = ButtonClass(BUTTON_MAPPINGS['B'])
buttonU = ButtonClass(BUTTON_MAPPINGS['UP'])
buttonD = ButtonClass(BUTTON_MAPPINGS['DOWN'])
buttonL = ButtonClass(BUTTON_MAPPINGS['LEFT'])
buttonR = ButtonClass(BUTTON_MAPPINGS['RIGHT'])
buttonLB = ButtonClass(BUTTON_MAPPINGS['LB'])
buttonRB = ButtonClass(BUTTON_MAPPINGS['RB'])
buttonMENU = ButtonClass(BUTTON_MAPPINGS['MENU'])

# All buttons for bulk update
ALL_BUTTONS = [buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, buttonLB, buttonRB, buttonMENU]


def update_buttons():
    """Update all button states - call once per frame"""
    for btn in ALL_BUTTONS:
        btn.update()


def dpadPressed():
    """Check if any dpad button is pressed"""
    return buttonU.pressed() or buttonD.pressed() or buttonL.pressed() or buttonR.pressed()


def inputJustPressed():
    """Check if any button was just pressed"""
    return (buttonA.justPressed() or buttonB.justPressed() or buttonU.justPressed() or
            buttonD.justPressed() or buttonL.justPressed() or buttonR.justPressed() or
            buttonLB.justPressed() or buttonRB.justPressed() or buttonMENU.justPressed())


# Stubs for other functions
def rumble(duration):
    """Stub for rumble"""
    pass


def play_cutscene_animation(filename, frames, cancel_callback):
    """Stub for cutscene animation"""
    pass


def create_cancel_callback():
    """Stub for cancel callback"""
    return lambda: False


# Audio stubs
def audio_load(filename):
    pass

def audio_play():
    pass

def audio_stop():
    pass

def audio_set_volume(volume):
    pass

def audio_set_loop(loop, start=0, end=0):
    pass

def audio_get_position():
    return 0

def audio_set_end_callback(callback):
    pass

def audio_clear_end_callback():
    pass

def audio_open_id(filename, id):
    pass

def audio_play_id(id):
    pass

def audio_close_ids():
    pass


# Create display instance
display = PygameDisplay()
Sprite = PygameSprite


# Helper function
def create_sprite(width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False, scale=1.0):
    """Create a sprite"""
    return PygameSprite(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)
