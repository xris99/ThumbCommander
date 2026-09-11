# png_to_rgb565_converter.py
import os
import struct
from PIL import Image
import numpy as np
from pathlib import Path

class PNGToRGB565Converter:
    """Convert PNG sprite sheets to RGB565 format for ThumbyColor"""
    
    def __init__(self, scale_factor=2):
        self.scale_factor = scale_factor
        
    def png_to_rgb565(self, r, g, b):
        """Convert RGB888 to RGB565"""
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    
    def convert_sprite_sheet(self, input_pattern, output_filename, sprite_name):
        """
        Convert PNG files matching pattern to single RGB565 sprite file
        
        Args:
            input_pattern: Pattern like "enemy*.png" 
            output_filename: Output file like "enemy1_128.COL.bin"
            sprite_name: Base name for sprite detection
        """
        # Find all matching PNG files
        png_files = sorted(Path('.').glob(input_pattern))
        if not png_files:
            print(f"No files found matching {input_pattern}")
            return
            
        frames = []
        frame_width = None
        frame_height = None
        
        # Process each frame
        for png_file in png_files:
            # Load PNG
            img = Image.open(png_file).convert('RGBA')
            
            # Scale up by scale factor
            new_width = img.width * self.scale_factor
            new_height = img.height * self.scale_factor
            img = img.resize((new_width, new_height), Image.NEAREST)
            
            if frame_width is None:
                frame_width = new_width
                frame_height = new_height
            elif frame_width != new_width or frame_height != new_height:
                print(f"Warning: Frame {png_file} has different size, skipping")
                continue
            
            # Convert to RGB565
            frame_data = []
            for y in range(new_height):
                for x in range(new_width):
                    r, g, b, a = img.getpixel((x, y))
                    
                    # Handle transparency - use black for transparent pixels
                    if a < 128:
                        rgb565 = 0x0000
                    else:
                        rgb565 = self.png_to_rgb565(r, g, b)
                    
                    frame_data.append(rgb565)
            
            frames.append(frame_data)
            print(f"Processed {png_file}: {new_width}x{new_height}")
        
        # Save as binary file
        self._save_sprite_file(output_filename, frames, frame_width, frame_height)
        
        # Also generate metadata file
        self._save_metadata(output_filename.replace('.COL.bin', '.meta'), 
                          frame_width, frame_height, len(frames), sprite_name)
    
    def _save_sprite_file(self, filename, frames, width, height):
        """Save sprite data in ThumbyColor format"""
        with open(filename, 'wb') as f:
            # Header: width, height, frame_count, flags
            header = struct.pack('<HHHH', width, height, len(frames), 0)
            f.write(header)
            
            # Write frame data
            for frame in frames:
                for pixel in frame:
                    f.write(struct.pack('<H', pixel))
        
        print(f"Saved {filename}: {width}x{height}, {len(frames)} frames")
    
    def _save_metadata(self, filename, width, height, frame_count, sprite_type):
        """Save sprite metadata for runtime optimization"""
        metadata = {
            'width': width,
            'height': height,
            'frames': frame_count,
            'type': sprite_type,
            'scale': self.scale_factor
        }
        
        with open(filename, 'w') as f:
            f.write(str(metadata))
    
    def batch_convert_game_sprites(self):
        """Convert all game sprites from PNG sources"""
        sprite_conversions = [
            # (input_pattern, output_file, sprite_type)
            ('enemy1_*.png', 'enemy1_128.COL.bin', 'enemy'),
            ('asteroid1_*.png', 'astroid1_112.COL.bin', 'asteroid'),
            ('asteroid2_*.png', 'astroid2_112.COL.bin', 'asteroid'),
            ('explode_*.png', 'explode_112.COL.bin', 'explosion'),
            ('ship_*.png', 'ship_128.COL.bin', 'ship'),
            ('intro_*.png', 'intro_148.COL.bin', 'intro'),
            ('menu_*.png', 'menu_142.COL.bin', 'menu'),
        ]
        
        for pattern, output, sprite_type in sprite_conversions:
            try:
                self.convert_sprite_sheet(pattern, output, sprite_type)
            except Exception as e:
                print(f"Error converting {pattern}: {e}")

# Enhanced ColorSprite class to load native color data
class EnhancedColorSprite(ColorSprite):
    """Sprite class that prioritizes native color sprites"""
    
    def __init__(self, width, height, bitmapData, x=0, y=0, key=-1, mirrorX=False, mirrorY=False):
        # Store original dimensions for compatibility
        self.original_width = width
        self.original_height = height
        
        # Check for native color sprite first
        if isinstance(bitmapData, tuple):
            base_file = bitmapData[0]
        else:
            base_file = bitmapData
            
        if isinstance(base_file, str):
            # Try to load native color version
            color_file = base_file.replace('.BIT.bin', '.COL.bin')
            if self._try_load_color_sprite(color_file):
                # Successfully loaded color sprite
                self.has_native_color = True
                self.x = x
                self.y = y
                self.key = key
                self.mirrorX = mirrorX
                self.mirrorY = mirrorY
                return
        
        # Fall back to parent class implementation
        super().__init__(width, height, bitmapData, x, y, key, mirrorX, mirrorY)
        self.has_native_color = False
    
    def _try_load_color_sprite(self, color_file):
        """Try to load native color sprite file"""
        try:
            with open(color_file, 'rb') as f:
                # Read header
                header = f.read(8)
                self.width, self.height, self.frameCount, flags = struct.unpack('<HHHH', header)
                
                # Calculate sizes
                self.pixels_per_frame = self.width * self.height
                self.bytes_per_frame = self.pixels_per_frame * 2  # 2 bytes per RGB565 pixel
                
                # Load first frame
                self.current_frame_data = array.array('H', f.read(self.bytes_per_frame))
                
                # Store file handle for frame switching
                self.color_file = color_file
                self.currentFrame = 0
                
                # Update scaled dimensions
                self.scaledWidth = self.width
                self.scaledHeight = self.height
                
                return True
        except:
            return False
    
    def setFrame(self, frame):
        """Set frame for native color sprite"""
        if self.has_native_color:
            if frame != self.currentFrame:
                self.currentFrame = frame % self.frameCount
                
                # Load frame data
                with open(self.color_file, 'rb') as f:
                    # Skip header and previous frames
                    offset = 8 + (self.currentFrame * self.bytes_per_frame)
                    f.seek(offset)
                    
                    # Read frame data
                    data = f.read(self.bytes_per_frame)
                    self.current_frame_data = array.array('H')
                    self.current_frame_data.frombytes(data)
        else:
            super().setFrame(frame)
    
    def draw_color(self, display):
        """Draw native color sprite"""
        if self.has_native_color:
            self._draw_native_color_sprite(display)
        else:
            super().draw_color(display)
    
    def _draw_native_color_sprite(self, display):
        """Draw native RGB565 sprite data"""
        # No scaling needed - sprite is already at correct resolution
        for y in range(self.height):
            for x in range(self.width):
                if self.x + x >= 0 and self.x + x < display.width and \
                   self.y + y >= 0 and self.y + y < display.height:
                    
                    # Get pixel from frame data
                    pixel_index = y * self.width + x
                    color = self.current_frame_data[pixel_index]
                    
                    # Check transparency (black = transparent)
                    if color != 0x0000 or self.key != 0:
                        display.framebuffer[(self.y + y) * display.width + self.x + x] = color

# Usage example
if __name__ == "__main__":
    converter = PNGToRGB565Converter(scale_factor=2)
    converter.batch_convert_game_sprites()