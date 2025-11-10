# platform_constants.py - Platform-specific constants
import os

try:
    from micropython import const
except ImportError:
    # Fallback for systems without micropython
    def const(x):
        return x

class PlatformConstants:
    """All platform-specific constants in one place"""

    def __init__(self, is_thumby_color):
        # Detect if running on PC
        is_running_on_pc = os.environ.get('RUNNING_ON_PC') == '1'

        if is_thumby_color:
            # ThumbyColor constants (128x128)
            # On PC, use current directory; on hardware, use /Games/ThumbCommander/
            self.GAME_PATH = "" if is_running_on_pc else "/Games/ThumbCommander/"
            self.WIDTH = const(128)
            self.HEIGHT = const(128)
            self.CENTER_X = const(64)
            self.CENTER_Y = const(64)
            self.SCREEN_SCALE = const(2)
          
            # Ship positioning
            self.SHIP_X = const(5)
            self.SHIP_Y = const(75)
            
            # HUD positioning
            self.HUD_X = const(4)
            self.HUD_Y = const(30)
            self.HUD_SCALE = const(14000)
            self.RADAR_X = const(88)
            self.RADAR_Y = const(28)
            self.COUNTER_X = const(52)
            self.COUNTER_Y = const(21)
            
            # Game area adjustments
            self.Z_DISTANCE = const(50)     # Deeper perspective
            self.SPACE_WIDTH = const(2559)
            self.SPACE_HEIGHT = const(2559)
            self.SPACE_STARS = const(350)
            self.SPACE_ASTROIDS = const(1730)
            self.SPACE_ENEMIES = const(1000)
            
            # UI dimensions - UPDATED to actual framebuffer font size
            self.FONT_WIDTH = const(8)      # Changed from 6 to 8
            self.FONT_HEIGHT = const(8)     # Changed from 10 to 8
            self.FONT_SPACE = const(0)      # Changed from 2 to 0 for framebuffer
            self.FONT_FILE = "/lib/font6x10.bin"  # Not used but kept for compatibility
            self.TEXTBOX_WIDTH = const(100)
            self.TEXTBOX_HEIGHT = const(100)
            self.SETTING_ITEMS = const(8)
            
            # Sprite scaling
            self.SPRITE_SCALE = const(113377)
            self.COCKPIT_WIDTH = const(118)
            self.COCKPIT_HEIGHT = const(53)
            
            # Performance
            self.FPS = const(60)
            self.STAR_COUNT = const(30)

            #colors
            self.BLACK = const(0x0000)
            self.WHITE = const(0xFFFF)
            self.DARKGRAY = const(0x4208)
            self.LIGHTGRAY = const(0xBDF7)
            self.RED = const(0xF800)
            self.GREEN = const(0x07E0)
            self.BLUELIGHTLIGHT = const(0x633f)
            self.BLUELIGHT = const(0x297f)
            self.BLUE = const(0x001F)
            self.BLUEDARK = const(0x0016)
            self.BLUEDARKDARK = const(0x0010)
            self.CYAN = const(0x07FF)
            self.ORANGE = const(0xFD20)
            self.PURPLE = const(0x8010)
            self.BROWN = const(0x8410)
            self.YELLOW = const(0xffee)
            self.STARCOLORS = [self.WHITE, self.LIGHTGRAY, self.WHITE, self.LIGHTGRAY, self.YELLOW, self.BLUE, self.BLUELIGHTLIGHT, self.BLUEDARK, self.BLUEDARKDARK]
            self.SELECT = const(61002)
            self.UNSELECT = const(60801)
            self.LASER_COLOR = self.ORANGE
            self.HIT_COLOR = self.RED
            self.HUD_COLOR = self.RED
            self.HUD_SELECT = const(63488)
            self.HUD_UNSELECT = const(65504)
            
        else:
            # Original Thumby constants (72x40)
            # On PC, use current directory; on hardware, use /Games/ThumbCommander/
            self.GAME_PATH = "" if is_running_on_pc else "/Games/ThumbCommander/"
            self.WIDTH = const(72)
            self.HEIGHT = const(40)
            self.CENTER_X = const(36)
            self.CENTER_Y = const(20)
            self.SCREEN_SCALE = const(1)
            
            # Ship positioning
            self.SHIP_X = const(4)
            self.SHIP_Y = const(23)
            
            # HUD positioning
            self.HUD_X = const(27)
            self.HUD_Y = const(8)
            self.HUD_SCALE = const(12000)
            self.RADAR_X = const(57)
            self.RADAR_Y = const(0)
            self.COUNTER_X = const(30)
            self.COUNTER_Y = const(8)
            
            # Game area
            self.SPACE_WIDTH = const(2047)
            self.SPACE_HEIGHT = const(1400)
            self.Z_DISTANCE = const(30)
            self.SPACE_STARS = const(200)
            self.SPACE_ASTROIDS = const(1000)
            self.SPACE_ENEMIES = const(1000)
          
            # UI dimensions
            self.FONT_WIDTH = const(3)
            self.FONT_HEIGHT = const(5)
            self.FONT_SPACE = const(1)
            self.FONT_FILE = "/lib/font3x5.bin"
            self.SETTING_ITEMS = const(5)
            self.TEXTBOX_WIDTH = self.WIDTH
            self.TEXTBOX_HEIGHT = self.HEIGHT
            
            # Sprite scaling
            self.SPRITE_SCALE = const(1)
            self.COCKPIT_WIDTH = const(66)
            self.COCKPIT_HEIGHT = const(18)
            
            # Performance
            self.FPS = const(40)
            self.STAR_COUNT = const(20)

            #colors
            self.BLACK = const(0)
            self.WHITE = const(1)
            self.DARKGRAY = const(2)
            self.LIGHTGRAY = const(3)
            self.STARCOLORS = [self.WHITE, self.DARKGRAY, self.LIGHTGRAY]
            self.SELECT = self.WHITE
            self.UNSELECT = self.LIGHTGRAY
            self.LASER_COLOR = self.WHITE
            self.HIT_COLOR = self.WHITE
            self.HUD_COLOR = self.WHITE
            self.HUD_SELECT = self.WHITE
            self.HUD_UNSELECT = self.LIGHTGRAY

# Create singleton instance
_instance = None

def get_constants(is_thumby_color):
    global _instance
    if _instance is None:
        _instance = PlatformConstants(is_thumby_color)
    return _instance