# Color (RGB565) display driver for ThumbyColor and the PC emulation.
from array import array
from gc import collect , mem_free
from struct import unpack
from ..platform.constants import get_constants
from engine_draw import back_fb
from  engine import time_to_next_tick, tick, fps_limit
import framebuf
from machine import Timer, Pin
from ..util.fpmath import fpmul, fpdiv

timer = Timer()

PC = get_constants(True)  # Force ThumbyColor constants

buzzer = Pin(5, Pin.OUT)
def _rumble(duration:int):
    global timer
    buzzer.value(1)
    timer.init(mode=Timer.ONE_SHOT, period=duration, callback=_norumble)

def _norumble(thisTimer):
  buzzer.value(0)
  thisTimer.deinit()

class ColorDisplay:
    """Native resolution ThumbyColor display using internal buffer"""

    def __init__(self, font=None, fps=0):
        # Get the engine's framebuffer
        self.engine_fb = back_fb()

        # Create our own internal buffer for viper operations
        self.buffer = bytearray(PC.WIDTH * PC.HEIGHT * 2)  #2 bytes per pixel for RGB565

        # Create a framebuffer object from our buffer for blitting
        self.internal_fb = framebuf.FrameBuffer(self.buffer, PC.WIDTH, PC.HEIGHT, framebuf.RGB565)

        # Pre-allocate lookup tables for scaled sprites (max 128 pixels)
        self._x_table = array('H', [0] * 128)
        self._y_table = array('H', [0] * 128)

        # Reusable row scratch for _stream_sprite_to_fb (allocated on first use)
        self._row_w = 0
        self._row_buffer = None
        self._row_fb = None

        # The engine is game-agnostic: font and target FPS are supplied by
        # the game (e.g. display.setFont(PC.FONT_FILE, ...) / setFPS(PC.FPS)).
        self.font_bmap = None
        if font is not None:
            self.setFont(*font)
        if fps:
            fps_limit(fps)

    def fill(self, color):
        """Fill screen with color"""
        self.internal_fb.fill(color)
    
    def setPixel(self, x, y, color):
        """Set a single pixel"""
        self.internal_fb.pixel(x, y, color)
    
    def drawFilledRectangle(self, x, y, width, height, color):
        """Draw filled rectangle"""
        self.internal_fb.fill_rect(x, y, width, height, color)
    
    def drawRectangle(self, x, y, width, height, color):
        """Draw rectangle outline"""
        self.internal_fb.rect(x, y, width, height, color)
    
    def drawLine(self, x0, y0, x1, y1, color):
        """Draw line"""
        self.internal_fb.line(x0, y0, x1, y1, color)
    
    def drawText(self, text, x, y, color):
        """Draw text"""
        self.internal_fb.text(text, x, y, color)      
    
    def drawSprite(self, sprite):
        if sprite.key == -1:  # No transparency
            self.internal_fb.blit(sprite.sprite_fb, sprite.x, sprite.y)
        else:
            self.internal_fb.blit(sprite.sprite_fb, sprite.x, sprite.y, sprite.key)
    
    @micropython.native  
    def drawSpriteWithScale(self, sprite):
        """Draw scaled sprite with viper-optimized lookup tables"""
        scale = fpdiv(256<<16, sprite.scale)>>16

        # Fill pre-allocated tables in viper (no Python allocation)
        self._fillLookupTables(self._x_table, self._y_table,  sprite.scaledWidth, sprite.scaledHeight, scale,
                               1 if sprite.mirrorX else 0, 1 if sprite.mirrorY else 0)

        self._blitWithTables(sprite.frame_view, sprite.x, sprite.y,  sprite.scaledWidth, sprite.scaledHeight,
                             sprite.key, self._x_table, self._y_table, sprite.width)

    @micropython.viper
    def _fillLookupTables(self, x_table, y_table, width:int, height:int, scale:int, mirrorX:int, mirrorY:int):
        """Fill lookup tables in viper - no Python allocation"""
        xt = ptr16(x_table)
        yt = ptr16(y_table)

        if mirrorX:
            w1 = width - 1
            x = 0
            while x < width:
                xt[x] = ((w1 - x) * scale) >> 8
                x += 1
        else:
            x = 0
            while x < width:
                xt[x] = (x * scale) >> 8
                x += 1

        if mirrorY:
            h1 = height - 1
            y = 0
            while y < height:
                yt[y] = ((h1 - y) * scale) >> 8
                y += 1
        else:
            y = 0
            while y < height:
                yt[y] = (y * scale) >> 8
                y += 1

    @micropython.viper
    def _blitWithTables(self, src_data, x:int, y:int, width:int, height:int, key:int,
                        x_table, y_table, realWidth:int):
        """Optimized blit using pre-computed lookup tables"""
        if x + width < 0 or x >= 128 or y + height < 0 or y >= 128:
            return

        fb = ptr16(self.buffer)
        src = ptr16(src_data)
        xt = ptr16(x_table)
        yt = ptr16(y_table)

        xStart = int(x)
        yStart = int(y)

        # Clipping
        yFirst = 0
        if yStart < 0:
            yFirst = -yStart
        blitHeight = height
        if yStart + height > 128:
            blitHeight = 128 - yStart

        xFirst = 0
        if xStart < 0:
            xFirst = -xStart
        blitWidth = width
        if xStart + width > 128:
            blitWidth = 128 - xStart

        # Main blit loop with table lookups (no per-pixel arithmetic)
        dy = yFirst
        while dy < blitHeight:
            src_row = yt[dy] * realWidth
            dst_row = (yStart + dy) * 128 + xStart
            dx = xFirst
            while dx < blitWidth:
                pixel = src[src_row + xt[dx]]
                if pixel != key:
                    fb[dst_row + dx] = pixel
                dx += 1
            dy += 1

    @micropython.native  
    def draw_sprite_from_file(self, filename, x=0, y=0, key=-1):
        try:
            with open(filename, 'rb') as f:
                # Read header (4 bytes: width + height as uint16)
                header = f.read(4)
                width, height = unpack('<HH', header)
                f.read(4)  # Skip frame count and flags
                self._stream_sprite_to_fb(f, x, y, width, height, key)
                return True
        except Exception as e:
            print(f"Error drawing sprite from file {filename}: {e}")
            return False

    @micropython.native
    def _stream_sprite_to_fb(self, file_handle, x, y, width, height, key):
        if self._row_w != width:
            self._row_w = width
            self._row_buffer = bytearray(width * 2)
            self._row_fb = framebuf.FrameBuffer(self._row_buffer, width, 1, framebuf.RGB565)
        row_buffer = self._row_buffer
        row_fb = self._row_fb
        internal_fb = self.internal_fb
        for row in range(height):
            file_handle.readinto(row_buffer)
            internal_fb.blit(row_fb, x, y + row, key)

    def draw_open_sprite(self, file_handle, x, y, width, height, key):
        """Draw a single-frame .COL sprite from an already-open handle
        (pixel data at offset 8) via the normal key-based row stream."""
        file_handle.seek(8)
        self._stream_sprite_to_fb(file_handle, x, y, width, height, key)

    @micropython.native
    def update(self):
        """Update display by blitting internal buffer to engine framebuffer"""
        while (time_to_next_tick() > 0):
            pass
        tick()
        # Blit our internal buffer to the engine's framebuffer
        self.engine_fb.blit(self.internal_fb, 0, 0) 
        
    def blit_framebuffer(self, fb, x, y, key=-1, palette=None):
        """Public blit of an arbitrary framebuffer (used by the cutscene
        player). palette: optional 256-color RGB565 palette to map an
        8-bit indexed source through."""
        if palette is not None:
            self.internal_fb.blit(fb, x, y, key, palette)
        else:
            self.internal_fb.blit(fb, x, y, key)

    def show(self):
        """Alias for update()"""
        self.update()

    def enableGrayscale(self):
        """Compatibility method"""
        pass
    
    def setFPS(self, fps):
        """Set frame rate"""
        fps_limit(fps)
    
    def setFont(self, fontFile, width, height, space):
        """Text is rendered using the fb text() method. This is just for Thumby compatibility; the font is not used for rendering in ThumbyColor."""
        self.font_bmap = None
            
class ColorSprite:
    """Native resolution sprite for ThumbyColor with efficient scaling"""
    
    def __init__(self, width, height, bitmapData, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY
        
        # Scaling properties
        self.scale = 1<<16
        self.scaledWidth = width
        self.scaledHeight = height
        
        # File handle for efficient frame switching
        self.file_handle = None
        self.frame_data = None
        
        # Detect if this is a color sprite
        if isinstance(bitmapData, str) and bitmapData.endswith('.COL.bin'):
            self._load_color_sprite(bitmapData)
        elif isinstance(bitmapData, bytearray):
            self.width = width
            self.height = height
            self.pixels_per_frame = self.width * self.height
            self.bytes_per_frame = self.pixels_per_frame * 2  # 2 bytes per RGB565 pixel
            self.frame_data = memoryview(bitmapData)[0:self.bytes_per_frame]
            self.frameCount = len(bitmapData) // self.bytes_per_frame
            self.frame_view = memoryview(self.frame_data)
            self.sprite_fb = framebuf.FrameBuffer(self.frame_data, self.width, self.height, framebuf.RGB565)
        else:
            print(f"Could not load color sprite; not a color file {bitmapData}")
    
    def _load_color_sprite(self, filename):
        """Load native color sprite and keep file open"""
        self.file_handle = open(filename, 'rb')
        
        # Read header
        header = self.file_handle.read(8)
        self.width, self.height, self.frameCount, flags = unpack('<HHHH', header)
        
        # Setup dimensions
        self.scaledWidth = fpmul(self.width<<16, self.scale)>>16
        self.scaledHeight = fpmul(self.height<<16, self.scale)>>16
        
        # Calculate frame properties
        self.pixels_per_frame = self.width * self.height
        self.bytes_per_frame = self.pixels_per_frame * 2  # 2 bytes per RGB565 pixel
        self.currentFrame = 0
        
        # Pre-allocate frame buffer
        self.frame_data = bytearray(self.bytes_per_frame)
        
        # Load first frame
        self.file_handle.readinto(self.frame_data)
        
        # Create memoryview for efficient access
        self.frame_view = memoryview(self.frame_data)
        
        # Create framebuffer for this sprite (for non-scaled blitting)
        self.sprite_fb = framebuf.FrameBuffer(self.frame_data, self.width, self.height, framebuf.RGB565)
    
    @micropython.native  
    def setFrame(self, frame):
        """Set animation frame efficiently using seek"""
        if frame == self.currentFrame:
            return
            
        self.currentFrame = frame % self.frameCount
        
        if self.file_handle:
            # Seek to frame position
            frame_offset = 8 + self.currentFrame * self.bytes_per_frame
            self.file_handle.seek(frame_offset)
            
            # Read frame data directly into buffer
            self.file_handle.readinto(self.frame_data)
    
    @micropython.native  
    def setScale(self, scale):
        """Set sprite scale in fixed point"""
        self.scale = scale
        self.scaledWidth = fpmul(self.width<<16, self.scale)>>16
        self.scaledHeight = fpmul(self.height<<16, self.scale)>>16
    
    def __del__(self):
        """Clean up file handle when sprite is destroyed"""
        if self.file_handle:
            self.file_handle.close()
    
    def setLifes(self, lifes):
        """Store life count for HUD display"""
        self.lifes = lifes
    
    def getLifes(self):
        """Get life count"""
        return getattr(self, 'lifes', 0)

# Set global Sprite class
Sprite = ColorSprite

def create_sprite(width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False, cWidth=0, cHeight=0):
    """ThumbyColor version that prioritizes color sprites with memory management.

    `bitmap_data` is either the path of a .COL.bin file, or a (BIT, SHD)
    tuple of the 1-bit source sprite. In the tuple case the matching color
    sprite is derived: <prefix>_<cWidth>_<cHeight>.COL.bin, looked up in the
    same directory as the 1-bit sources. This lets a game call
    create_sprite() identically on both platforms.
    """
    # Force GC before creating new sprites
    collect()
    color_file = ""
    if isinstance(bitmap_data, tuple) and isinstance(bitmap_data[0], str):
        base_file = bitmap_data[0]
        # Calculate output dimensions
        output_width = width if cWidth == 0 else cWidth
        output_height = height if cHeight == 0 else cHeight
        # Sprite names are '<prefix>_<w>_<h>.<ext>'; derive from the
        # basename so underscores in parent directories can't break
        # the lookup.
        name = base_file.rsplit('/', 1)[-1]
        prefix = name.split("_")[0]
        directory = base_file[:len(base_file) - len(name)]
        color_file = directory + prefix + f'_{output_width}_{output_height}.COL.bin'
    elif isinstance(bitmap_data, str):
        # Try color version first
        color_file = bitmap_data
    else:
        # Fall back to standard sprite
        return Sprite(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)
        
    print(f"Loading sprite: {color_file}")
    sprite = Sprite(0, 0, color_file, x, y, key, mirrorX, mirrorY)
    print(f"Free memory after loading Sprite: {mem_free()}")
    return sprite