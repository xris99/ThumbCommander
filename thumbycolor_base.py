"""
Base ColorDisplay class that mimics the ThumbyColor hardware API
This represents what the hardware provides through engine_io
"""

from framebuf import FrameBuffer, RGB565


class ColorDisplay:
    """
    Base ColorDisplay class matching ThumbyColor hardware API
    On real hardware, this comes from engine_io built-in module
    """

    def __init__(self):
        self.width = 128
        self.height = 128

        # Internal framebuffer - key attribute that game expects
        self.buffer = bytearray(self.width * self.height * 2)
        self.internal_fb = FrameBuffer(self.buffer, self.width, self.height, RGB565)

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
        self.LASER_COLOR = 0x297F
        self.ENEMY_PURPLE = 0x8010
        self.HIT_COLOR = 0xF800

        # Font settings
        self.font_file = None
        self.font_width = 8
        self.font_height = 8
        self.font_space = 0

        # FPS control
        self.fps = 60
        self.grayscale_enabled = False

    def enableGrayscale(self):
        """Enable grayscale mode"""
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

    # Drawing methods - delegate to internal_fb
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
        self.internal_fb.fill_rect(x, y, w, h, color)

    def drawText(self, text, x, y, color):
        """Draw text using internal_fb's embedded 8x8 font"""
        self.internal_fb.text(str(text), x, y, color)

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

    def draw_fullwidth_sprite(self, filename, x=0, y=0):
        """Draw full-width sprite from .COL.bin file"""
        # This would be implemented in hardware
        # PC implementation will override this
        pass

    def update(self):
        """Update display - on hardware this pushes to screen"""
        # Hardware implementation would update the physical display
        # PC implementation will override this
        pass


class ColorSprite:
    """Base ColorSprite class matching ThumbyColor hardware API"""

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY
        self.currentFrame = 0
        self.frameCount = 1
        self.scale = 65536  # Fixed point 1.0
        self.scaledWidth = width
        self.scaledHeight = height
        self.frame_data = None

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
        """Set life count"""
        self.lifes = lifes

    def getLifes(self):
        """Get life count"""
        return getattr(self, 'lifes', 0)

    def render(self, display):
        """Render sprite - to be implemented by subclass"""
        pass

    def render_scaled(self, display):
        """Render scaled sprite - to be implemented by subclass"""
        pass


def _rumble(duration):
    """Rumble function - does nothing in base"""
    pass
