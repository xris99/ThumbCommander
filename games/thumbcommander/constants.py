# ThumbCommander - game-specific constants.
#
# This module extends the engine's shared `PC` object (the
# PlatformConstants singleton, created for the detected target by
# thumby_engine.platform) in place with everything this game needs:
# sprite positions, HUD layout, game-field size, fonts and game colors.
# The engine itself only knows the screen size and the platform palette;
# everything below is ThumbCommander business.
#
# Must be imported AFTER thumby_engine.platform (MainGame.py guarantees
# order). Because it mutates the same object the engine bound, every
# module holding the PC object sees the game fields too.

from thumby_engine.platform import IS_THUMBY_COLOR, PC

try:
    from micropython import const
except ImportError:
    const = lambda x: x


# --- Game constants (extend the shared PC object in place) ---------------------
if not IS_THUMBY_COLOR:
    # Original Thumby (72x40, 1-bit 4-level dither, no audio)
    # Ship positioning
    PC.SHIP_X = const(4)
    PC.SHIP_Y = const(23)

    # HUD positioning
    PC.HUD_X = const(27)
    PC.HUD_Y = const(8)
    PC.HUD_SCALE = const(12000)
    PC.RADAR_X = const(57)
    PC.RADAR_Y = const(0)
    PC.COUNTER_X = const(30)
    PC.COUNTER_Y = const(8)
    PC.COCKPIT_HEIGHT = const(18)

    # Game area
    PC.SPACE_WIDTH = const(2047)
    PC.SPACE_HEIGHT = const(1400)
    PC.Z_DISTANCE = const(30)
    PC.SPACE_STARS = const(200)

    # UI
    PC.FONT_FILE = "assets/font3x5.bin"
    PC.FONT_WIDTH = const(3)
    PC.FONT_HEIGHT = const(5)
    PC.FONT_SPACE = const(1)
    PC.SETTING_ITEMS = const(4)
    PC.TEXTBOX_WIDTH = PC.WIDTH
    PC.TEXTBOX_HEIGHT = PC.HEIGHT

    # Performance
    PC.FPS = const(40)
    PC.STAR_COUNT = const(20)

    # Colors (1-bit 4-level palette values)
    PC.STARCOLORS = [PC.WHITE, PC.DARKGRAY, PC.LIGHTGRAY]
    PC.SELECT = PC.WHITE
    PC.UNSELECT = PC.LIGHTGRAY
    PC.LASER_COLOR = PC.WHITE
    PC.HIT_COLOR = PC.WHITE
    PC.HUD_COLOR = PC.WHITE
    PC.HUD_SELECT = PC.WHITE
    PC.HUD_UNSELECT = PC.LIGHTGRAY
else:
    # ThumbyColor / PC (128x128, RGB565, audio)
    # Ship positioning
    PC.SHIP_X = const(5)
    PC.SHIP_Y = const(75)

    # HUD positioning
    PC.HUD_X = const(4)
    PC.HUD_Y = const(30)
    PC.HUD_SCALE = const(24500)
    PC.RADAR_X = const(88)
    PC.RADAR_Y = const(28)
    PC.COUNTER_X = const(52)
    PC.COUNTER_Y = const(21)
    PC.COCKPIT_HEIGHT = const(53)

    # Game area adjustments
    PC.Z_DISTANCE = const(50)     # Deeper perspective
    PC.SPACE_WIDTH = const(2559)
    PC.SPACE_HEIGHT = const(2559)
    PC.SPACE_STARS = const(350)

    # UI dimensions
    PC.FONT_FILE = "assets/font6x10.bin"
    PC.FONT_WIDTH = const(8)
    PC.FONT_HEIGHT = const(8)
    PC.FONT_SPACE = const(0)
    PC.TEXTBOX_WIDTH = const(100)
    PC.TEXTBOX_HEIGHT = const(100)
    PC.SETTING_ITEMS = const(8)

    # Performance
    PC.FPS = const(40)
    PC.STAR_COUNT = const(30)

    # Colors (RGB565 values from the platform palette)
    PC.STARCOLORS = [PC.WHITE, PC.LIGHTGRAY, PC.WHITE, PC.LIGHTGRAY,
                     PC.YELLOW, PC.BLUE, PC.BLUELIGHTLIGHT,
                     PC.BLUEDARK, PC.BLUEDARKDARK]
    PC.SELECT = const(61002)
    PC.UNSELECT = const(60801)
    PC.LASER_COLOR = PC.ORANGE
    PC.HIT_COLOR = PC.RED
    PC.HUD_COLOR = PC.RED
    PC.HUD_SELECT = const(63488)
    PC.HUD_UNSELECT = const(65504)
