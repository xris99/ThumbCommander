"""
pygame_platform.py - Pygame wrapper that mimics ThumbyColor API using FrameBuffer
This allows running ThumbCommander on PC for testing without modifying game code
"""
import pygame
import os
import struct

# Try to import numpy for fast array operations
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Initialize pygame
pygame.init()

# Emulate ThumbyColor display (128x128, RGB565)
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 128
SCALE_FACTOR = 4  # Display at 4x size for visibility

# FrameBuffer format constants
RGB565 = 1
GS8 = 2

# Pre-compute RGB565 to RGB888 lookup table for speed
RGB565_TO_RGB888 = []
for i in range(65536):
    r = ((i >> 11) & 0x1F) * 255 // 31
    g = ((i >> 5) & 0x3F) * 255 // 63
    b = (i & 0x1F) * 255 // 31
    RGB565_TO_RGB888.append((r << 16) | (g << 8) | b)


class PygameFrameBuffer:
    """
    Mimics micropython's framebuf.FrameBuffer using pygame
    Implements the same API as the real FrameBuffer class
    """

    def __init__(self, buffer, width, height, format):
        self.buffer = buffer
        self.width = width
        self.height = height
        self.format = format

        # Create pygame surface based on format
        if format == RGB565:
            # RGB565: 2 bytes per pixel
            self.pygame_surface = pygame.Surface((width, height))
        elif format == GS8:
            # GS8: 1 byte per pixel (grayscale/indexed)
            self.pygame_surface = pygame.Surface((width, height))
        else:
            self.pygame_surface = pygame.Surface((width, height))

    def rgb565_to_rgb888(self, rgb565):
        """Convert RGB565 to RGB888 tuple"""
        r = ((rgb565 >> 11) & 0x1F) * 255 // 31
        g = ((rgb565 >> 5) & 0x3F) * 255 // 63
        b = (rgb565 & 0x1F) * 255 // 31
        return (r, g, b)

    def rgb888_to_rgb565(self, r, g, b):
        """Convert RGB888 to RGB565"""
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    def fill(self, color):
        """Fill the framebuffer with a color"""
        if self.format == RGB565:
            rgb = self.rgb565_to_rgb888(color)
            self.pygame_surface.fill(rgb)
            # Update buffer
            for y in range(self.height):
                for x in range(self.width):
                    pixel_index = (y * self.width + x) * 2
                    if pixel_index + 1 < len(self.buffer):
                        self.buffer[pixel_index] = color & 0xFF
                        self.buffer[pixel_index + 1] = (color >> 8) & 0xFF
        elif self.format == GS8:
            gray = color & 0xFF
            rgb = (gray, gray, gray)
            self.pygame_surface.fill(rgb)
            # Update buffer
            for i in range(min(len(self.buffer), self.width * self.height)):
                self.buffer[i] = gray

    def rect(self, x, y, w, h, c, fill=False):
        """Draw a rectangle (micropython FrameBuffer API)

        Args:
            x, y: Top-left corner
            w, h: Width and height
            c: Color
            fill: If True, draw filled rectangle
        """
        if fill:
            # Draw filled rectangle
            for dy in range(h):
                for dx in range(w):
                    px = x + dx
                    py = y + dy
                    if 0 <= px < self.width and 0 <= py < self.height:
                        self.pixel(px, py, c)
        else:
            # Draw rectangle outline
            # Top and bottom
            for dx in range(w):
                if 0 <= x + dx < self.width:
                    if 0 <= y < self.height:
                        self.pixel(x + dx, y, c)
                    if 0 <= y + h - 1 < self.height:
                        self.pixel(x + dx, y + h - 1, c)
            # Left and right
            for dy in range(h):
                if 0 <= y + dy < self.height:
                    if 0 <= x < self.width:
                        self.pixel(x, y + dy, c)
                    if 0 <= x + w - 1 < self.width:
                        self.pixel(x + w - 1, y + dy, c)

    def hline(self, x, y, w, c):
        """Draw a horizontal line (micropython FrameBuffer API)"""
        for dx in range(w):
            px = x + dx
            if 0 <= px < self.width and 0 <= y < self.height:
                self.pixel(px, y, c)

    def vline(self, x, y, h, c):
        """Draw a vertical line (micropython FrameBuffer API)"""
        for dy in range(h):
            py = y + dy
            if 0 <= x < self.width and 0 <= py < self.height:
                self.pixel(x, py, c)

    def line(self, x1, y1, x2, y2, c):
        """Draw a line (micropython FrameBuffer API)"""
        # Bresenham's line algorithm
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy

        while True:
            if 0 <= x1 < self.width and 0 <= y1 < self.height:
                self.pixel(x1, y1, c)
            if x1 == x2 and y1 == y2:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x1 += sx
            if e2 < dx:
                err += dx
                y1 += sy

    def text(self, s, x, y, c):
        """Draw text (basic implementation for micropython FrameBuffer API)"""
        # This is a minimal implementation - micropython has bitmap fonts
        # For now, just record that text should be drawn
        # The actual rendering would need bitmap font data
        pass

    def pixel(self, x, y, color=None):
        """Get or set a pixel"""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return

        if color is None:
            # Get pixel
            if self.format == RGB565:
                pixel_index = (y * self.width + x) * 2
                if pixel_index + 1 < len(self.buffer):
                    return self.buffer[pixel_index] | (self.buffer[pixel_index + 1] << 8)
            elif self.format == GS8:
                pixel_index = y * self.width + x
                if pixel_index < len(self.buffer):
                    return self.buffer[pixel_index]
            return 0
        else:
            # Set pixel
            if self.format == RGB565:
                rgb = self.rgb565_to_rgb888(color)
                self.pygame_surface.set_at((x, y), rgb)
                pixel_index = (y * self.width + x) * 2
                if pixel_index + 1 < len(self.buffer):
                    self.buffer[pixel_index] = color & 0xFF
                    self.buffer[pixel_index + 1] = (color >> 8) & 0xFF
            elif self.format == GS8:
                gray = color & 0xFF
                rgb = (gray, gray, gray)
                self.pygame_surface.set_at((x, y), rgb)
                pixel_index = y * self.width + x
                if pixel_index < len(self.buffer):
                    self.buffer[pixel_index] = gray

    def blit(self, source_fb, x, y, key=-1, palette=None):
        """
        Blit another framebuffer onto this one

        Args:
            source_fb: Source PygameFrameBuffer to copy from
            x, y: Position to blit to
            key: Transparent color key (default -1 = no transparency)
            palette: Optional palette framebuffer for indexed color mode
        """
        if palette is not None:
            # Palette-based blitting (for 8-bit indexed mode) - OPTIMIZED
            # Source is GS8 (indexed), palette is RGB565
            # Direct buffer access for speed - NO PYGAME SURFACE UPDATE
            for sy in range(source_fb.height):
                dest_y = y + sy
                if dest_y < 0 or dest_y >= self.height:
                    continue

                for sx in range(source_fb.width):
                    dest_x = x + sx
                    if dest_x < 0 or dest_x >= self.width:
                        continue

                    # Get palette index from source buffer directly
                    src_idx = sy * source_fb.width + sx
                    if src_idx >= len(source_fb.buffer):
                        continue

                    index = source_fb.buffer[src_idx]

                    # Skip if matches key
                    if key != -1 and index == key:
                        continue

                    # Look up color in palette buffer directly
                    if index < palette.width:
                        pal_idx = index * 2  # RGB565 = 2 bytes
                        if pal_idx + 1 < len(palette.buffer):
                            color = palette.buffer[pal_idx] | (palette.buffer[pal_idx + 1] << 8)

                            # Write to destination buffer directly
                            dest_idx = (dest_y * self.width + dest_x) * 2
                            if dest_idx + 1 < len(self.buffer):
                                self.buffer[dest_idx] = color & 0xFF
                                self.buffer[dest_idx + 1] = (color >> 8) & 0xFF
            # Note: pygame surface update happens in display.update()
        else:
            # Direct blitting - OPTIMIZED
            if source_fb.format == self.format == RGB565:
                # Fast path for RGB565 to RGB565 - NO PYGAME SURFACE UPDATE
                for sy in range(source_fb.height):
                    dest_y = y + sy
                    if dest_y < 0 or dest_y >= self.height:
                        continue

                    for sx in range(source_fb.width):
                        dest_x = x + sx
                        if dest_x < 0 or dest_x >= self.width:
                            continue

                        # Direct buffer copy
                        src_idx = (sy * source_fb.width + sx) * 2
                        if src_idx + 1 >= len(source_fb.buffer):
                            continue

                        color = source_fb.buffer[src_idx] | (source_fb.buffer[src_idx + 1] << 8)

                        # Skip if matches key
                        if key != -1 and color == key:
                            continue

                        dest_idx = (dest_y * self.width + dest_x) * 2
                        if dest_idx + 1 < len(self.buffer):
                            self.buffer[dest_idx] = source_fb.buffer[src_idx]
                            self.buffer[dest_idx + 1] = source_fb.buffer[src_idx + 1]
                # Note: pygame surface update happens in display.update()
            else:
                # Fallback to pixel-by-pixel
                for sy in range(source_fb.height):
                    for sx in range(source_fb.width):
                        dest_x = x + sx
                        dest_y = y + sy

                        if 0 <= dest_x < self.width and 0 <= dest_y < self.height:
                            color = source_fb.pixel(sx, sy)

                            if color is None:
                                continue

                            # Skip if matches key
                            if key != -1 and color == key:
                                continue

                            self.pixel(dest_x, dest_y, color)


class PygameDisplay:
    """Mimics ThumbyColor ColorDisplay API using FrameBuffer"""

    # Color constants (RGB565 format)
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

        # Internal framebuffer (128x128 RGB565) - THIS IS THE KEY!
        self.fb_buffer = bytearray(DISPLAY_WIDTH * DISPLAY_HEIGHT * 2)  # RGB565 = 2 bytes/pixel
        self.internal_fb = PygameFrameBuffer(self.fb_buffer, DISPLAY_WIDTH, DISPLAY_HEIGHT, RGB565)

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

        # Button states
        self.buttons = {
            'A': False, 'B': False, 'UP': False, 'DOWN': False,
            'LEFT': False, 'RIGHT': False, 'LB': False, 'RB': False, 'MENU': False
        }

        # Text rendering queue (to render after buffer sync)
        self.text_queue = []

    def rgb565_to_rgb888(self, rgb565):
        """Convert RGB565 to RGB888 tuple"""
        r = ((rgb565 >> 11) & 0x1F) * 255 // 31
        g = ((rgb565 >> 5) & 0x3F) * 255 // 63
        b = (rgb565 & 0x1F) * 255 // 31
        return (r, g, b)

    def setFPS(self, fps):
        """Set target frame rate"""
        self.target_fps = fps

    def enableGrayscale(self):
        """Stub for enabling grayscale mode (not needed for pygame)"""
        pass

    def disableGrayscale(self):
        """Stub for disabling grayscale mode (not needed for pygame)"""
        pass

    def fill(self, color):
        """Fill screen with color"""
        self.internal_fb.fill(color)

    def setPixel(self, x, y, color):
        """Draw a single pixel"""
        self.internal_fb.pixel(int(x), int(y), color)

    def drawLine(self, x0, y0, x1, y1, color):
        """Draw a line"""
        # Simple line drawing using Bresenham's algorithm
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        while True:
            self.internal_fb.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def drawRectangle(self, x, y, width, height, color):
        """Draw rectangle outline"""
        x, y, width, height = int(x), int(y), int(width), int(height)
        # Top
        for i in range(width):
            self.internal_fb.pixel(x + i, y, color)
        # Bottom
        for i in range(width):
            self.internal_fb.pixel(x + i, y + height - 1, color)
        # Left
        for i in range(height):
            self.internal_fb.pixel(x, y + i, color)
        # Right
        for i in range(height):
            self.internal_fb.pixel(x + width - 1, y + i, color)

    def drawFilledRectangle(self, x, y, width, height, color):
        """Draw filled rectangle"""
        x, y, width, height = int(x), int(y), int(width), int(height)
        for dy in range(height):
            for dx in range(width):
                px = x + dx
                py = y + dy
                if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                    self.internal_fb.pixel(px, py, color)

    def drawSprite(self, sprite):
        """Draw a sprite using FrameBuffer.blit()"""
        # Get the current frame's framebuffer
        sprite_fb = sprite.get_current_framebuffer()
        if sprite_fb:
            # Blit sprite framebuffer to display framebuffer
            self.internal_fb.blit(sprite_fb, sprite.x, sprite.y, sprite.key)

    def drawSpriteWithScale(self, sprite):
        """Draw a scaled sprite using FrameBuffer.blit()"""
        # Get the current frame's framebuffer
        sprite_fb = sprite.get_current_framebuffer()
        if sprite_fb:
            # For now, just draw at sprite position (scaling happens via setScale)
            # TODO: Implement proper scaling if needed
            self.internal_fb.blit(sprite_fb, sprite.x, sprite.y, sprite.key)

    def draw_sprite_from_file(self, filename, x, y, key=-1):
        """Draw a sprite directly from a .COL.bin file (ThumbyColor specific)"""
        # Load and draw the sprite
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    # Read header
                    header = f.read(6)
                    if len(header) == 6:
                        width, height, frames = struct.unpack('<HHH', header)

                        # Read first frame
                        frame_size = width * height * 2
                        frame_data = bytearray(f.read(frame_size))

                        if len(frame_data) == frame_size:
                            # Create temporary framebuffer
                            temp_fb = PygameFrameBuffer(frame_data, width, height, RGB565)
                            # Blit to display
                            self.internal_fb.blit(temp_fb, x, y, key)
        except Exception as e:
            print(f"Error drawing sprite from file {filename}: {e}")

    def drawText(self, text, x, y, color):
        """Draw text - queued for rendering after buffer sync"""
        # Add to queue instead of rendering immediately
        # This ensures text is drawn AFTER the buffer sync in update()
        self.text_queue.append((str(text), int(x), int(y), color))

    def setFont(self, font_path, width, height, space):
        """Set current font"""
        self.font_width = width
        self.font_height = height
        self.font_space = space

        # Map font sizes to pygame fonts
        if width <= 3:
            self.current_font = self.font_3x5
        elif width <= 5:
            self.current_font = self.font_5x7
        else:
            self.current_font = self.font_8x8

    def draw_fullwidth_sprite(self, filename, y_offset=0, key=-1):
        """Draw a fullwidth sprite (background image)"""
        # For now, just fill with a dark color to show it's being called
        # The actual sprite loading would happen here on real hardware
        try:
            # Try to load the binary file if it exists
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    data = f.read()
                    # Parse RGB565 data
                    width = DISPLAY_WIDTH
                    height = min(DISPLAY_HEIGHT - y_offset, len(data) // (width * 2))

                    for y in range(height):
                        for x in range(width):
                            offset = (y * width + x) * 2
                            if offset + 1 < len(data):
                                rgb565 = data[offset] | (data[offset + 1] << 8)
                                # Skip if matches key (transparency)
                                if key != -1 and rgb565 == key:
                                    continue
                                self.internal_fb.pixel(x, y + y_offset, rgb565)
            else:
                # File doesn't exist, draw placeholder
                # Draw a gradient background
                for y in range(DISPLAY_HEIGHT - y_offset):
                    blue_val = int(10 + (y / DISPLAY_HEIGHT) * 20)
                    color = (0 << 11) | (blue_val << 5) | 31  # Blue gradient
                    for x in range(DISPLAY_WIDTH):
                        self.internal_fb.pixel(x, y + y_offset, color)
        except Exception as e:
            print(f"Error loading sprite {filename}: {e}")

    def update(self):
        """Update the display and handle events"""
        # Handle pygame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                import sys
                sys.exit()

        # Update button states
        self.update_buttons()

        # Sync RGB565 buffer to pygame surface ONCE per frame
        if HAS_NUMPY:
            # Fast path with numpy
            rgb565_array = np.frombuffer(self.internal_fb.buffer, dtype=np.uint16).reshape((DISPLAY_HEIGHT, DISPLAY_WIDTH))
            r = ((rgb565_array >> 11) & 0x1F) * 255 // 31
            g = ((rgb565_array >> 5) & 0x3F) * 255 // 63
            b = (rgb565_array & 0x1F) * 255 // 31
            rgb_array = np.dstack((r, g, b)).astype(np.uint8)
            pygame.surfarray.blit_array(self.internal_fb.pygame_surface, np.transpose(rgb_array, (1, 0, 2)))
        else:
            # Fallback with PixelArray and lookup table (faster than set_at)
            pxarray = pygame.PixelArray(self.internal_fb.pygame_surface)
            for y in range(DISPLAY_HEIGHT):
                for x in range(DISPLAY_WIDTH):
                    idx = (y * DISPLAY_WIDTH + x) * 2
                    if idx + 1 < len(self.internal_fb.buffer):
                        color = self.internal_fb.buffer[idx] | (self.internal_fb.buffer[idx + 1] << 8)
                        # Use lookup table for speed
                        pxarray[x][y] = RGB565_TO_RGB888[color]
            del pxarray  # Release the lock on the surface

        # Render all queued text AFTER buffer sync
        for text, x, y, color in self.text_queue:
            try:
                rgb = self.rgb565_to_rgb888(color)
                text_surface = self.current_font.render(text, True, rgb)
                self.internal_fb.pygame_surface.blit(text_surface, (x, y))
            except Exception as e:
                pass  # Silently skip failed text rendering
        # Clear the queue
        self.text_queue = []

        # Scale and blit internal framebuffer to screen
        scaled_surface = pygame.transform.scale(
            self.internal_fb.pygame_surface,
            (DISPLAY_WIDTH * SCALE_FACTOR, DISPLAY_HEIGHT * SCALE_FACTOR)
        )
        self.screen.blit(scaled_surface, (0, 0))
        pygame.display.flip()

        # Maintain frame rate
        self.clock.tick(self.target_fps)

    def update_buttons(self):
        """Update button states from keyboard"""
        # Update all button instances
        for button in [buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, buttonLB, buttonRB, buttonMENU]:
            button.update()


# Button mappings (updated for German keyboard)
BUTTON_MAPPINGS = {
    'A': pygame.K_y,      # Y key (works on QWERTZ)
    'B': pygame.K_x,      # X key
    'UP': pygame.K_UP,    # Arrow up
    'DOWN': pygame.K_DOWN,  # Arrow down
    'LEFT': pygame.K_LEFT,  # Arrow left
    'RIGHT': pygame.K_RIGHT, # Arrow right
    'LB': pygame.K_q,     # Q key (German keyboard friendly)
    'RB': pygame.K_w,     # W key (German keyboard friendly)
    'MENU': pygame.K_ESCAPE  # ESC key
}


class PygameButton:
    """Mimics ThumbyButton ButtonClass"""

    def __init__(self, key_code):
        self.key_code = key_code
        self.last_state = False
        self.current_state = False
        self.just_pressed_flag = False

    def update(self):
        """Update button state - called once per frame in display.update()"""
        # Process events first to ensure fresh key state
        pygame.event.pump()  # Process internal pygame events
        keys = pygame.key.get_pressed()
        self.last_state = self.current_state
        self.current_state = keys[self.key_code]
        # Set flag if button just transitioned from not pressed to pressed
        self.just_pressed_flag = self.current_state and not self.last_state

    def pressed(self):
        """Check if button is currently pressed"""
        # Return the cached state from last update()
        # This ensures consistency when checking buttons after inputJustPressed()
        # and works correctly during cutscenes where update() is called regularly
        return self.current_state

    def justPressed(self):
        """Check if button was just pressed (True only on the frame it was pressed)"""
        # Return the flag that was set by update()
        # The flag persists for the entire frame until the next update()
        return self.just_pressed_flag


class PygameSprite:
    """Mimics ThumbyColor ColorSprite - loads and displays .COL.bin files"""

    def __init__(self, width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.key = key
        self.mirrorX = mirrorX
        self.mirrorY = mirrorY

        # Animation properties
        self.current_frame = 0
        self.frameCount = 1
        self.frame_data = None

        # Scaling properties
        self.scale = 1 << 16  # Fixed point 16.16
        self.scaledWidth = width
        self.scaledHeight = height

        # Load sprite data from .COL.bin file
        if isinstance(bitmap_data, str):
            self._load_col_bin(bitmap_data)
        else:
            # Fallback for non-.COL.bin data (shouldn't happen on ThumbyColor)
            print(f"Warning: Non-.COL.bin sprite data type: {type(bitmap_data)}")
            self.frame_buffers = []
            self.frameCount = 1

    def _load_col_bin(self, filename):
        """Load a .COL.bin sprite file"""
        try:
            if os.path.exists(filename):
                with open(filename, 'rb') as f:
                    # Read header: width (uint16), height (uint16), frames (uint16)
                    header = f.read(6)
                    if len(header) == 6:
                        file_width, file_height, frames = struct.unpack('<HHH', header)

                        # Update dimensions from file
                        self.width = file_width
                        self.height = file_height
                        self.frameCount = frames
                        self.scaledWidth = file_width
                        self.scaledHeight = file_height

                        # Read all frame data
                        frame_size = self.width * self.height * 2  # RGB565 = 2 bytes/pixel
                        self.frame_data = []
                        self.frame_buffers = []

                        for frame_idx in range(self.frameCount):
                            frame_bytes = f.read(frame_size)
                            if len(frame_bytes) == frame_size:
                                # Store raw frame data
                                self.frame_data.append(bytearray(frame_bytes))
                                # Create a FrameBuffer for this frame
                                fb = PygameFrameBuffer(self.frame_data[frame_idx], self.width, self.height, RGB565)
                                self.frame_buffers.append(fb)
                            else:
                                print(f"Warning: Frame {frame_idx} incomplete in {filename}")
                                break
                    else:
                        print(f"Warning: Invalid .COL.bin header in {filename}")
                        self.frame_buffers = []
            else:
                print(f"Warning: Sprite file not found: {filename}")
                self.frame_buffers = []
        except Exception as e:
            print(f"Error loading sprite {filename}: {e}")
            self.frame_buffers = []
            self.frameCount = 1

    def setFrame(self, frame):
        """Set the current animation frame"""
        if 0 <= frame < self.frameCount:
            self.current_frame = frame

    def setScale(self, scale):
        """Set the sprite scale (fixed point 16.16 format)"""
        self.scale = scale
        # Convert fixed point to integer dimensions
        self.scaledWidth = (self.width * scale) >> 16
        self.scaledHeight = (self.height * scale) >> 16
        if self.scaledWidth < 1:
            self.scaledWidth = 1
        if self.scaledHeight < 1:
            self.scaledHeight = 1

    def getLifes(self):
        """Return number of lives (for specific sprites that represent life count)"""
        # This is used for some HUD sprites - return current frame as life count
        return self.current_frame

    def get_current_framebuffer(self):
        """Get the FrameBuffer for the current frame"""
        if self.frame_buffers and 0 <= self.current_frame < len(self.frame_buffers):
            return self.frame_buffers[self.current_frame]
        return None


def rumble(duration):
    """Stub for rumble function"""
    pass


# Audio stub functions (all deactivated)
def audio_load(filename):
    """Stub for audio loading"""
    pass

def audio_play():
    """Stub for audio playback"""
    pass

def audio_stop():
    """Stub for audio stop"""
    pass

def audio_set_volume(volume):
    """Stub for setting volume"""
    pass

def audio_set_loop(loop, start=0, end=0):
    """Stub for setting loop"""
    pass

def audio_get_position():
    """Stub for getting playback position"""
    return 0

def audio_set_end_callback(callback):
    """Stub for setting end callback"""
    pass

def audio_clear_end_callback():
    """Stub for clearing end callback"""
    pass

def audio_open_id(filename, id):
    """Stub for opening audio by ID"""
    pass

def audio_play_id(id):
    """Stub for playing audio by ID"""
    pass

def audio_close_ids():
    """Stub for closing all audio IDs"""
    pass


def update_buttons():
    """Update all button states - called by game code"""
    for button in [buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, buttonLB, buttonRB, buttonMENU]:
        button.update()


def get_just_pressed_button():
    """Get which button was just pressed - for settings menu remapping"""
    # Check in order of priority
    if buttonA.just_pressed_flag: return 'A'
    if buttonB.just_pressed_flag: return 'B'
    if buttonU.just_pressed_flag: return 'U'
    if buttonD.just_pressed_flag: return 'D'
    if buttonL.just_pressed_flag: return 'L'
    if buttonR.just_pressed_flag: return 'R'
    if buttonLB.just_pressed_flag: return 'LB'
    if buttonRB.just_pressed_flag: return 'RB'
    if buttonMENU.just_pressed_flag: return 'MENU'
    return ''


# Create global display instance
display = PygameDisplay()

def get_display():
    global display
    if display is None:
        display = PygameDisplay()
    return display


# Aliases for compatibility
Sprite = PygameSprite

# Create button instances
buttonA = PygameButton(BUTTON_MAPPINGS['A'])
buttonB = PygameButton(BUTTON_MAPPINGS['B'])
buttonU = PygameButton(BUTTON_MAPPINGS['UP'])
buttonD = PygameButton(BUTTON_MAPPINGS['DOWN'])
buttonL = PygameButton(BUTTON_MAPPINGS['LEFT'])
buttonR = PygameButton(BUTTON_MAPPINGS['RIGHT'])
buttonLB = PygameButton(BUTTON_MAPPINGS['LB'])
buttonRB = PygameButton(BUTTON_MAPPINGS['RB'])
buttonMENU = PygameButton(BUTTON_MAPPINGS['MENU'])
