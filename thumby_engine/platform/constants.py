# platform constants - display-level values for the active hardware.
#
# One shared object for the whole program: get_constants() returns a
# singleton (first call wins). The platform module creates it for the
# detected target; a display driver fetches the same instance, and a
# game extends it in place with its own fields (see
# games/<name>/constants.py).
try:
    from micropython import const
except ImportError:
    const = lambda x: x


class PlatformConstants:
    """Display-level constants for the active platform."""
    def __init__(self, is_thumby_color):
        if not is_thumby_color:
            # Original Thumby: 72x40, 1-bit 4-level dither
            self.WIDTH = const(72)
            self.HEIGHT = const(40)
            self.CENTER_X = const(36)
            self.CENTER_Y = const(20)
            self.SCREEN_SCALE = const(1)

            # 1-bit palette (bit0 = light, bit1 = shading -> 4 levels)
            self.BLACK = const(0)
            self.WHITE = const(1)
            self.DARKGRAY = const(2)
            self.LIGHTGRAY = const(3)
        else:
            # ThumbyColor (and its PC emulation): 128x128 RGB565
            self.WIDTH = const(128)
            self.HEIGHT = const(128)
            self.CENTER_X = const(64)
            self.CENTER_Y = const(64)
            self.SCREEN_SCALE = const(2)

            # RGB565 palette
            self.BLACK = const(0x0000)
            self.WHITE = const(0xFFFF)
            self.DARKGRAY = const(0x4208)
            self.LIGHTGRAY = const(0xBDF7)
            self.RED = const(0xF800)
            self.GREEN = const(0x07E0)
            self.BLUELIGHTLIGHT = const(0x633F)
            self.BLUE = const(0x001F)
            self.BLUEDARK = const(0x0016)
            self.BLUEDARKDARK = const(0x0010)
            self.ORANGE = const(0xFD20)
            self.YELLOW = const(0xFFEE)


_instance = None


def get_constants(is_thumby_color):
    global _instance
    if _instance is None:
        _instance = PlatformConstants(is_thumby_color)
    return _instance
