# sprite_converter.py - Updated to handle embedded bytearrays
import os
import struct
from array import array

class SpriteConverter:
    """Convert grayscale sprites to color format with headers"""
    
    # Color palettes for different sprite types
    SHIP_PALETTE = [
        0x0000,  # Black
        0x8C51,  # Metal gray
        0xC618,  # Light metal
        0xFFFF   # White highlights
    ]
    
    ENEMY_PALETTE = [
        0x0000,  # Black
        0x8010,  # Purple
        0xC01F,  # Light purple
        0xF81F   # Bright purple
    ]
    
    ASTEROID_PALETTE = [
        0x0000,  # Black
        0x8410,  # Brown
        0xC618,  # Light brown
        0xEF5D   # Sandy
    ]
    
    EXPLOSION_PALETTE = [
        0x0000,  # Black
        0xF800,  # Red
        0xFD20,  # Orange
        0xFFE0   # Yellow
    ]
    
    UI_PALETTE = [
        0x0000,  # Black
        0x07FF,  # Cyan (for UI elements)
        0x001F,  # Blue
        0xFFFF   # White
    ]
    
    SHIELD_PALETTE = [
        0x0000,  # Transparent/Black
        0x07FF,  # Cyan shield color
        0x0FFF,  # Light cyan
        0x1FFF   # Very light cyan
    ]
    
    def __init__(self, game_path=".", scale_factor=1.73):
        self.game_path = game_path
        self.scale_factor = scale_factor
        self.converted_files = []
        
    def convert_sprite(self, bit_file, shd_file=None, output_file=None):
        """Convert a grayscale sprite to color format with header"""
        
        # Determine sprite type from filename
        sprite_type = self._detect_sprite_type(bit_file)
        palette = self._get_palette(sprite_type)
        
        # Read sprite data
        bit_data = self._read_file(bit_file)
        shd_data = self._read_file(shd_file) if shd_file else None
        
        if not bit_data:
            print(f"Error: Could not read {bit_file}")
            return None
        
        # Get sprite dimensions from filename
        width, height = self._parse_dimensions(bit_file)
        
        # Calculate frame count
        bytes_per_frame = width * ((height + 7) // 8)
        frame_count = len(bit_data) // bytes_per_frame
        
        print(f"Converting {bit_file}:")
        print(f"  Original size: {width}x{height}")
        print(f"  Frames: {frame_count}")
        
        # Calculate output dimensions
        output_width = int(width * self.scale_factor)
        output_height = int(height * self.scale_factor)
        
        print(f"  Output size: {output_width}x{output_height}")
        
        # Convert each frame
        color_data = array('H')  # 16-bit color values
        
        for frame in range(frame_count):
            frame_offset = frame * bytes_per_frame
            frame_bit = bit_data[frame_offset:frame_offset + bytes_per_frame]
            frame_shd = shd_data[frame_offset:frame_offset + bytes_per_frame] if shd_data else None
            
            # Convert frame to color
            color_frame = self._convert_frame(frame_bit, frame_shd, width, height, palette)
            color_data.extend(color_frame)
        
        # Generate output filename if not specified
        if not output_file:
            output_file = bit_file.split("_")[0] + f'_{output_width}_{output_height}.COL.bin'
            #output_file = bit_file.replace('.BIT.bin', f'_{output_width}.COL.bin')
        
        # Save color sprite with header
        self._save_color_sprite(output_file, color_data, output_width, output_height, frame_count)
        
        return output_file
    
    def convert_bytearray_sprite(self, bit_data, shd_data, width, height, output_file, sprite_type='ui'):
        """Convert bytearray sprites (embedded in code) to color format"""
        
        palette = self._get_palette(sprite_type)
        
        # Calculate frame count
        bytes_per_frame = width * ((height + 7) // 8)
        frame_count = len(bit_data) // bytes_per_frame
        
        print(f"Converting bytearray sprite to {output_file}:")
        print(f"  Original size: {width}x{height}")
        print(f"  Frames: {frame_count}")
        
        # Calculate output dimensions
        output_width = int(width * self.scale_factor)
        output_height = int(height * self.scale_factor)
        
        print(f"  Output size: {output_width}x{output_height}")
        
        # Convert each frame
        color_data = array('H')
        
        for frame in range(frame_count):
            frame_offset = frame * bytes_per_frame
            frame_bit = bit_data[frame_offset:frame_offset + bytes_per_frame]
            frame_shd = shd_data[frame_offset:frame_offset + bytes_per_frame] if shd_data else None
            
            # Convert frame to color
            color_frame = self._convert_frame(frame_bit, frame_shd, width, height, palette)
            color_data.extend(color_frame)
        
        # Save color sprite with header
        self._save_color_sprite(output_file, color_data, output_width, output_height, frame_count)
        
        return output_file
    
    def _convert_frame(self, bit_data, shd_data, width, height, palette):
        """Convert a single frame to color"""
        color_frame = array('H')
        
        # Scale dimensions
        output_width = int(width * self.scale_factor)
        output_height = int(height * self.scale_factor)
        
        for y in range(output_height):
            for x in range(output_width):
                # Sample from original sprite
                orig_x = int(x // self.scale_factor)
                orig_y = int(y // self.scale_factor)
                
                # Get bit values
                byte_index = (orig_y // 8) * width + orig_x
                bit_index = orig_y & 7
                
                bit_val = (bit_data[byte_index] >> bit_index) & 1 if byte_index < len(bit_data) else 0
                shd_val = (shd_data[byte_index] >> bit_index) & 1 if shd_data and byte_index < len(shd_data) else 0
                
                # Combine to get color index
                color_index = bit_val | (shd_val << 1)
                
                # Add some dithering for better visuals when scaling
                if self.scale_factor > 1 and color_index > 0 and color_index < 3:
                    # Add slight variation based on position
                    if (x + y) % 3 == 0:
                        color_index = min(3, color_index + 1)
                
                # Get color from palette
                color = palette[color_index]
                color_frame.append(color)
        
        return color_frame
    
    def _detect_sprite_type(self, filename):
        """Detect sprite type from filename"""
        filename_lower = filename.lower()
        if 'enemy' in filename_lower:
            return 'enemy'
        elif 'astroid' in filename_lower or 'asteroid' in filename_lower:
            return 'asteroid'
        elif 'explode' in filename_lower:
            return 'explosion'
        elif 'cockpit' in filename_lower or 'target' in filename_lower or 'radar' in filename_lower:
            return 'ui'
        elif 'shield' in filename_lower:
            return 'shield'
        else:
            return 'ship'
    
    def _get_palette(self, sprite_type):
        """Get color palette for sprite type"""
        palettes = {
            'enemy': self.ENEMY_PALETTE,
            'asteroid': self.ASTEROID_PALETTE,
            'explosion': self.EXPLOSION_PALETTE,
            'ship': self.SHIP_PALETTE,
            'ui': self.UI_PALETTE,
            'shield': self.SHIELD_PALETTE
        }
        return palettes.get(sprite_type, self.SHIP_PALETTE)
    
    def _parse_dimensions(self, filename):
        """Parse sprite dimensions from filename"""
        # Format: name_WIDTH_HIGHT.BIT.bin
        parts = filename.split('.')
        if len(parts) > 1:
            size_part = parts[0].split('_')[1]
            try:
                width = int(size_part)
            except:
                width = 32  # Default
            
            size_part = parts[0].split('_')[2]
            try:
                height = int(size_part)
            except:
                height = 32  # Default
        else:
            width = height = 32  # Default
        
        return int(width), int(height)
    
    def _read_file(self, filename):
        """Read binary file"""
        if not filename:
            return None
        
        full_path = os.path.join(self.game_path, filename)
        try:
            with open(full_path, 'rb') as f:
                return bytearray(f.read())
        except:
            return None
    
    def _save_color_sprite(self, filename, color_data, width, height, frame_count):
        """Save color sprite data with header"""
        full_path = os.path.join(self.game_path, filename)
        
        # Create header: width, height, frame_count, flags
        header = struct.pack('<HHHH', width, height, frame_count, 0)
        
        try:
            with open(full_path, 'wb') as f:
                # Write header
                f.write(header)
                
                # Write color data
                color_data.tofile(f)
            
            # Validate file size
            expected_size = 8 + (width * height * frame_count * 2)  # Header + pixel data
            actual_size = os.path.getsize(full_path)
            
            print(f"Saved: {filename}")
            print(f"  File size: {actual_size} bytes")
            
            if expected_size != actual_size:
                print(f"  WARNING: Size mismatch! Expected {expected_size} bytes")
            else:
                print(f"  ✓ File size correct")
                
        except Exception as e:
            print(f"Error saving {filename}: {e}")
    
    def convert_embedded_sprites(self):
        """Convert embedded bytearray sprites from ThumbCommander.py"""
        
        # Define embedded sprites with their data
        # These need to be copied from ThumbCommander.py
        cockpit = bytearray([255,252,255,253,253,255,251,251,251,247,247,239,239,239,223,31,159,31,31,31,35,29,61,29,63,31,63,157,61,29,35,31,31,31,31,31,63,63,31,31,63,31,31,63,31,63,31,31,31,159,223,223,223,239,239,239,247,247,251,251,251,253,253,255,252,255,
                   255,255,255,255,255,255,255,127,127,63,63,63,159,15,11,6,0,0,0,0,0,0,0,0,0,0,0,86,0,0,0,0,0,0,0,0,0,0,0,0,8,20,8,0,0,0,0,0,0,0,2,11,15,159,31,63,63,127,127,255,255,255,255,255,255,255,
                   3,3,3,1,1,0,0,0,0,0,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,1,1,3,3,3])
        cockpitSHD = bytearray([1,3,3,2,2,6,4,4,12,12,24,24,16,48,48,96,160,96,160,224,124,98,226,226,226,226,226,226,226,98,124,96,96,96,96,96,96,224,224,224,224,224,224,224,224,224,224,160,96,224,96,96,48,48,16,24,24,12,12,4,6,6,2,3,3,1,
                   0,0,0,0,0,0,128,128,192,192,224,96,144,112,220,247,188,223,239,255,127,119,127,127,119,127,127,119,127,128,128,128,128,128,128,128,128,127,127,66,74,87,74,66,127,127,225,225,255,253,247,220,112,144,96,224,192,192,128,128,0,0,0,0,0,0,
                   0,2,2,2,3,3,3,3,3,1,0,2,1,3,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,3,3,3,3,3,3,3,3,0,0,0,0,0,0,0,0,0,3,0,0,0,0,0,3,1,2,0,1,3,3,3,3,3,3,2,2,0])
        
        target = bytearray([65,34,0,0,0,34,65])
        targetSHD = bytearray([0,0,0,0,0,0,0])
        
        targetactive = bytearray([127,99,65,65,65,99,127])
        targetactiveSHD = bytearray([62,65,65,65,65,65,62])
        
        radar = bytearray([192,152,132,130,130,128,129,255,129,128,130,130,132,152,192,
                   1,4,16,32,32,0,64,127,64,0,32,32,16,12,1])
        radarSHD = bytearray([192,152,132,130,130,128,129,255,129,128,130,130,132,152,192,
                   1,4,16,32,32,0,64,127,64,0,32,32,16,12,1])
        
        shield = bytearray([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,192,224,224,32,48,112,112,24,8,8,24,56,24,24,24,24,24,24,24,56,120,112,240,240,224,224,224,192,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,128,192,224,240,88,4,2,3,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,8,13,15,31,31,126,222,252,248,240,224,192,128,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,192,240,60,7,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,7,15,95,255,255,255,252,240,192,0,0,0,0,0,
                   0,0,0,240,255,63,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,15,255,255,255,255,255,240,0,0,0,
                   0,0,0,255,243,17,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,255,255,255,255,255,255,0,0,0,
                   0,0,0,3,24,200,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,224,252,255,255,255,255,63,3,0,0,0,
                   0,0,0,0,0,0,3,14,14,94,232,32,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,32,96,224,224,250,255,127,31,15,3,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,0,0,1,2,6,15,30,24,32,96,96,224,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,128,128,192,224,208,240,224,224,224,112,112,56,62,30,15,7,3,1,0,0,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,3,3,3,6,4,4,4,6,6,6,6,6,7,7,7,7,7,3,3,3,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        shieldSHD = bytearray([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,192,224,224,32,48,112,112,24,8,8,24,56,8,24,16,24,24,24,24,48,112,96,240,240,192,192,192,128,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,0,192,224,240,88,4,2,3,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,8,13,15,31,31,110,204,128,0,0,0,0,128,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,192,224,60,7,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,7,14,94,255,254,247,32,0,0,0,0,0,0,0,
                   0,0,0,240,255,63,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,15,255,252,0,0,1,0,0,0,0,
                   0,0,0,191,243,17,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,253,196,0,0,0,0,0,0,0,
                   0,0,0,3,24,200,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,224,252,255,79,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,3,14,14,94,232,32,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,32,96,224,224,58,31,29,23,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,0,0,1,2,6,15,30,24,32,96,96,224,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,128,128,192,224,208,240,224,224,224,112,112,56,46,14,15,7,3,1,0,0,0,0,0,0,0,0,0,0,0,
                   0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,3,3,3,6,4,4,4,6,6,6,6,6,7,7,7,3,1,1,3,2,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
        
        # Convert embedded sprites
        embedded_sprites = [
            (cockpit, cockpitSHD, 66, 18, 'cockpit_114_31.COL.bin', 'ui'),
            (target, targetSHD, 7, 7, 'target_12_12.COL.bin', 'ui'),
            (targetactive, targetactiveSHD, 7, 7, 'targetactive_12_12.COL.bin', 'ui'),
            (radar, radarSHD, 15, 15, 'radar_25_25.COL.bin', 'ui'),  # 15x2=30 for scale 2
            (shield, shieldSHD, 70, 70, 'shield_121_121.COL.bin', 'shield'),
        ]
        
        print("\n=== Converting Embedded Sprites ===\n")
        
        for bit_data, shd_data, width, height, output_file, sprite_type in embedded_sprites:
            try:
                self.convert_bytearray_sprite(bit_data, shd_data, width, height, output_file, sprite_type)
                self.converted_files.append(output_file)
                print()
            except Exception as e:
                print(f"Error converting {output_file}: {e}\n")
    
    def batch_convert(self):
        """Convert all sprites in the game directory"""
        sprites_to_convert = [
            ('enemy1_70_59.BIT.bin', 'enemy1_70_59.SHD.bin'),
            ('astroid1_56_47.BIT.bin', 'astroid1_56_47.SHD.bin'),
            ('astroid2_56_47.BIT.bin', 'astroid2_56_47.SHD.bin'),
            ('explode_56_54.BIT.bin', 'explode_56_54.SHD.bin'),
            ('intro_74_30.BIT.bin', 'intro_74_30.SHD.bin'),
            ('start1_74_30.BIT.bin', 'start1_74_30.SHD.bin'),
            ('start2_74_30.BIT.bin', 'start2_74_30.SHD.bin'),
            ('medie_74_40.BIT.bin', 'medie_74_40.SHD.bin'),
            ('home_74_30.BIT.bin', 'home_74_30.SHD.bin'),
            ('menu_71_40.BIT.bin', 'menu_71_40.SHD.bin'),
        ]
        
        print("=== Batch Sprite Conversion ===\n")
        
        converted_count = 0
        for bit_file, shd_file in sprites_to_convert:
            try:
                result = self.convert_sprite(bit_file, shd_file)
                if result:
                    converted_count += 1
                    self.converted_files.append(result)
                print()  # Empty line between conversions
            except Exception as e:
                print(f"Error converting {bit_file}: {e}\n")
        
        # Also convert embedded sprites
        self.convert_embedded_sprites()
        
        print(f"=== Conversion Complete ===")
        print(f"Successfully converted {converted_count} file-based sprites")
        print(f"Plus embedded UI sprites")
    
    def validate_sprite(self, filename):
        """Validate a converted sprite file"""
        full_path = os.path.join(self.game_path, filename)
        
        try:
            with open(full_path, 'rb') as f:
                # Read header
                header_data = f.read(8)
                if len(header_data) < 8:
                    print(f"Error: {filename} - File too small")
                    return False
                
                width, height, frames, flags = struct.unpack('<HHHH', header_data)
                
                # Calculate expected file size
                pixel_data_size = width * height * frames * 2
                expected_size = 8 + pixel_data_size
                actual_size = os.path.getsize(full_path)
                
                print(f"Validating {filename}:")
                print(f"  Dimensions: {width}x{height}")
                print(f"  Frames: {frames}")
                print(f"  Expected size: {expected_size} bytes")
                print(f"  Actual size: {actual_size} bytes")
                print(f"  Valid: {'YES' if expected_size == actual_size else 'NO'}")
                
                return expected_size == actual_size
                
        except Exception as e:
            print(f"Error validating {filename}: {e}")
            return False

# Run converter if executed directly
if __name__ == "__main__":
    converter = SpriteConverter()
    converter.batch_convert()
    
    # Optionally validate all converted files
    print("\n=== Validating Converted Files ===\n")
    
    
    print("Sprites:")
    for filename in converter.converted_files:
        if os.path.exists(os.path.join(converter.game_path, filename)):
            converter.validate_sprite(filename)
            print()