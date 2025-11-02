# thumbycolor_native.py 
from array import array
import struct
from platform_constants import get_constants
from engine_draw import back_fb
from  engine import time_to_next_tick, tick, fps_limit
import framebuf
import _thread
from machine import Timer, Pin

timer = Timer()

PC = get_constants(True)  # Force ThumbyColor constants

@micropython.viper
def fpdiv(a:int, b:int) -> int:
    return ((a << 6) // (b >> 6)) << 4

@micropython.viper
def fpmul(a:int, b:int) -> int:
    return (a >> 6) * (b >> 6) >> 4

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
    
    # Color definitions
    BLACK = 0x0000
    WHITE = 0xFFFF
    DARKGRAY = 0x4208
    LIGHTGRAY = 0xBDF7
    
    # Game-specific colors
    SPACE_BLACK = 0x0000
    STAR_WHITE = 0xFFFF
    LASER_RED = 0xF800
    LASER_GREEN = 0x07E0
    LASER_BLUE = 0x001F
    SHIELD_CYAN = 0x07FF
    EXPLOSION_ORANGE = 0xFD20
    ENEMY_PURPLE = 0x8010
    ASTEROID_BROWN = 0x8410
    HUD_BLUE = 0x001F
    
    def __init__(self):
        self.width = PC.WIDTH
        self.height = PC.HEIGHT
        
        # Get the engine's framebuffer
        self.engine_fb = back_fb()
        
        # Create our own internal buffer for viper operations
        self.buffer_size = self.width * self.height * 2  # 2 bytes per pixel for RGB565
        self.buffer = bytearray(self.buffer_size)
        
        # Create a framebuffer object from our buffer for blitting
        self.internal_fb = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565)
        
        # Font setup
        self.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT, PC.FONT_SPACE)
        
        fps_limit(PC.FPS)
    
    def fill(self, color):
        """Fill screen with color"""
        self.internal_fb.fill(color)
    
    def setPixel(self, x, y, color):
        """Set a single pixel"""
        if 0 <= x < self.width and 0 <= y < self.height:
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
      
    def drawSpriteWithScale(self, sprite):
        """Draw scaled sprite"""
        # Scaled or mirrored - use our viper blit
        self.blitScaled(sprite.frame_view, sprite.x, sprite.y, 
                         sprite.scaledWidth, sprite.scaledHeight, sprite.key,
                         1 if sprite.mirrorX else 0, 1 if sprite.mirrorY else 0, 
                         fpdiv(256<<16, sprite.scale)>>16, sprite.width, sprite.height)


    @micropython.viper
    def blitScaled(self, src_data, x:int, y:int, width:int, height:int, key:int, 
                   mirrorX:int, mirrorY:int, scale:int, realWidth:int, realHeight:int):
        """Efficient scaled blit using viper for sprites"""
        if x + width < 0 or x >= 128:
            return
        if y + height < 0 or y >= 128:
            return
        
        fb = ptr16(self.buffer)
        src = ptr16(src_data)
        
        xStart = int(x)
        yStart = int(y)
        
        # Clipping
        yFirst = 0 - yStart
        blitHeight = height
        if yFirst < 0:
            yFirst = 0
        if yStart + height > 128:
            blitHeight = 128 - yStart
        
        xFirst = 0 - xStart
        blitWidth = width
        if xFirst < 0:
            xFirst = 0
        if xStart + width > 128:
            blitWidth = 128 - xStart
        
        y = yFirst
        while y < blitHeight:
            x = xFirst
            src_y = (((height - 1 - y if mirrorY == 1 else y) * scale) >> 8)
            
            # Bounds check for source y
            #if src_y >= realHeight:
            #    y += 1
            #    continue
            
            # Calculate source row offset once per row
            src_row_offset = src_y * realWidth
            
            # Calculate destination row offset once per row
            dst_row_offset = (yStart + y) * 128 + xStart
            
            while x < blitWidth:
                # Calculate source x coordinate
                src_x = (((width - 1 - x if mirrorX == 1 else x) * scale) >> 8)
                
                # Bounds check for source x
                if src_x < realWidth:
                    # Get pixel from source
                    pixel = src[src_row_offset + src_x]
                    
                    # Check transparency (key color)
                    if pixel != key:
                        # Write to framebuffer
                        fb[dst_row_offset + x] = pixel
                
                x += 1
            y += 1

    def draw_sprite_from_file(self, filename, x=0, y=0, key=-1):
        try:
            with open(filename, 'rb') as f:
                # Read header
                header = f.read(8)
                width, height, frame_count, flags = struct.unpack('<HHHH', header)
                self._stream_sprite_to_fb(f, x, y, width, height, key)
                return True
        except Exception as e:
            print(f"Error drawing sprite from file {filename}: {e}")
            return False
        finally:
            if (f): f.close()
    
    @micropython.viper
    def _stream_sprite_to_fb(self, file_handle, x:int, y:int, width:int, height:int, key:int):
        fb = ptr16(self.buffer)
        screen_width = int(self.width)
        screen_height = int(self.height)
        
        # Calculate clipping bounds
        start_x = int(x)
        start_y = int(y)
        end_x = start_x + int(width)
        end_y = start_y + int(height)
        
        # Clip to screen bounds
        skip_left = 0
        skip_top = 0
        
        if start_x < 0:
            skip_left = -start_x
            start_x = 0
        if start_y < 0:
            skip_top = -start_y
            start_y = 0
        if end_x > screen_width:
            end_x = screen_width
        if end_y > screen_height:
            end_y = screen_height
        
        draw_width = end_x - start_x
        draw_height = end_y - start_y
        
        if draw_width <= 0 or draw_height <= 0:
            return
        
        # Create a row buffer (in Python, before viper section)
        bytes_per_row = int(width) * 2
        row_buffer = bytearray(bytes_per_row)
        
        # Skip rows that are above the screen
        if skip_top > 0:
            file_handle.seek(8 + skip_top * bytes_per_row)
        
        # Read and draw each visible row
        for row in range(int(draw_height)):
            # Read one row of pixels
            file_handle.readinto(row_buffer)
            
            # Process this row
            row_ptr = ptr16(row_buffer)
            dest_y = start_y + row
            dest_offset = dest_y * screen_width + start_x
            
            for col in range(int(draw_width)):
                src_col = skip_left + col
                pixel = row_ptr[src_col]
                
                # Check transparency
                if int(key) == -1 or pixel != int(key):
                    fb[dest_offset + col] = pixel

    def draw_fullwidth_sprite(self, filename, y=0, key=-1):
        """ Draw a full-width sprite with optional transparency support."""
        try:
            with open(filename, 'rb') as f:
                # Read header
                header = f.read(8)
                width, height, frame_count, flags = struct.unpack('<HHHH', header)
                # Verify sprite is full width
                if width != 128:
                    print(f"Error: Sprite width {width} != 128")
                    return False
                # Calculate how many rows to draw
                rows_to_draw = min(height, 128 - y)
                if rows_to_draw <= 0:
                    return False  
                if key == -1:
                    # No transparency - use direct streaming (fastest)
                    fb_offset = y * 256
                    fb_view = memoryview(self.buffer)[fb_offset:fb_offset + (rows_to_draw * 256)]
                    f.readinto(fb_view)
                else:
                    # With transparency - process in chunks
                    self._draw_fullwidth_sprite_with_key(f, y, width, rows_to_draw, key)  
                return True            
        except Exception as e:
            print(f"Error drawing fullwidth sprite: {e}")
            return False
        finally:
            if (f):
                f.close()
            else:
                print("Error closeing file handle")
              
    def _draw_fullwidth_sprite_with_key(self, file_handle, y, width, height, key):
        """ Draw sprite with transparency using row-by-row processing."""
        # Process multiple rows at once for efficiency
        ROWS_PER_CHUNK = const(4)  # Process 4 rows at a time (1KB chunks for 128px width)
        
        row_bytes = width * 2  # 2 bytes per pixel for RGB565
        chunk_bytes = row_bytes * ROWS_PER_CHUNK
        chunk_buffer = bytearray(chunk_bytes)
        
        rows_processed = 0
        
        while rows_processed < height:
            # Calculate rows to read in this chunk
            rows_to_read = min(ROWS_PER_CHUNK, height - rows_processed)
            actual_bytes = rows_to_read * row_bytes
            
            # Read chunk into buffer
            chunk_view = memoryview(chunk_buffer)[:actual_bytes]
            file_handle.readinto(chunk_view)
            
            # Create temporary framebuffer for this chunk
            chunk_fb = framebuf.FrameBuffer(chunk_view, width, rows_to_read, framebuf.RGB565)
            
            # Blit with transparency to main buffer
            self.internal_fb.blit(chunk_fb, 0, y + rows_processed, key)
            rows_processed += rows_to_read
        del chunk_buffer
      
    def update(self):
        """Update display by blitting internal buffer to engine framebuffer"""
        while (time_to_next_tick() > 0):
          pass
        # Blit our internal buffer to the engine's framebuffer
        self.engine_fb.blit(self.internal_fb, 0, 0) 
        tick()
    
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
        """Load font file"""
        try:
            import os
            self.font_width = width
            self.font_height = height
            self.font_space = space
            
            # Read font file
            size = os.stat(fontFile)[6]
            self.font_bmap = bytearray(size)
            with open(fontFile, 'rb') as f:
                f.readinto(self.font_bmap)
                f.close()
            self.font_glyphcnt = size // width
        except:
            # Fallback if font not found
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
        self.scale = PC.SPRITE_SCALE  # Fixed point 16.16
        self.scaledWidth = fpmul(width<<16, self.scale)>>16
        self.scaledHeight = fpmul(height<<16, self.scale)>>16
        
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
        self.width, self.height, self.frameCount, flags = struct.unpack('<HHHH', header)
        
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
    
    def setScale(self, scale):
        """Set sprite scale in fixed point"""
        self.scale = fpmul(scale, PC.SPRITE_SCALE)
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

