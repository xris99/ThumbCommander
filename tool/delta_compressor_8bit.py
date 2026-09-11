# delta_frame_compressor.py
import struct
import argparse
from PIL import Image
from pathlib import Path

class DeltaFrameCompressor:
    """Delta frame compression with 8-bit palette for ThumbyColor cutscenes"""
    
    def __init__(self, scale_factor=1):
        self.scale_factor = scale_factor
        self.TRANSPARENT = 0x0000  # Black = transparent/unchanged
        self.CHANGE_MARKER = 0xF81F  # Magenta = "pixel changed" marker
        self.color_remap = {}  # Color remapping for quantization
    
    def rgb_to_rgb565(self, r, g, b):
        """Convert RGB888 to RGB565"""
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    
    def compress_cutscene_delta(self, input_pattern, output_filename, sprite_name):
        """
        Create delta-compressed cutscene with 8-bit palette from JPEG frames
        
        Args:
            input_pattern: Pattern like "scene*.jpg"
            output_filename: Output like "scene_delta.COL.bin"  
            sprite_name: Scene identifier
        """
        # Find all matching files
        jpeg_files = sorted(Path('.').glob(input_pattern))
        if not jpeg_files:
            print(f"No files found matching {input_pattern}")
            return
        
        frames = []
        previous_pixels = None
        frame_width = None
        frame_height = None
        all_colors = set()  # Track all unique colors across frames
        
        print("Processing delta frames and building palette...")
        
        # First pass: collect all unique colors and frame data
        all_frame_pixels = []
        for i, jpeg_file in enumerate(jpeg_files):
            # Load and process image
            img = Image.open(jpeg_file).convert('RGB')
            
            if self.scale_factor != 1:
                new_width = img.width * self.scale_factor
                new_height = img.height * self.scale_factor
                img = img.resize((new_width, new_height), Image.NEAREST)
            
            if frame_width is None:
                frame_width = img.width
                frame_height = img.height
            elif frame_width != img.width or frame_height != img.height:
                print(f"Warning: {jpeg_file} size mismatch, skipping")
                continue
            
            # Convert to RGB565 pixels and collect colors
            current_pixels = []
            for y in range(img.height):
                for x in range(img.width):
                    r, g, b = img.getpixel((x, y))
                    rgb565 = self.rgb_to_rgb565(r, g, b)
                    current_pixels.append(rgb565)
                    all_colors.add(rgb565)
            
            all_frame_pixels.append(current_pixels)
        
        # Build optimized palette (max 256 colors)
        palette = self._build_palette(all_colors)
        
        # Build color to index mapping
        color_to_index = {}
        for idx, color in enumerate(palette):
            color_to_index[color] = idx
        
        print(f"Palette size: {len(palette)} colors")
        
        # Second pass: compress frames using palette indices
        for i, current_pixels in enumerate(all_frame_pixels):
            # Convert pixels to palette indices
            indexed_pixels = []
            for pixel in current_pixels:
                # Check if we have a remapping for this color
                if pixel in self.color_remap:
                    palette_color = self.color_remap[pixel]
                    indexed_pixels.append(color_to_index[palette_color])
                else:
                    # Color should be directly in palette
                    indexed_pixels.append(color_to_index[pixel])
            
            if i == 0:
                # First frame: store full frame with smart compression
                delta_data = self._create_full_frame_indexed(indexed_pixels)
                frame_type = delta_data[:4]
                if frame_type == b'FULL':
                    print(f"Frame {i}: RLE full frame ({len(delta_data)} bytes)")
                elif frame_type == b'URAW':
                    print(f"Frame {i}: Raw full frame ({len(delta_data)} bytes)")
            else:
                # Subsequent frames: try delta
                previous_indexed = []
                for pixel in previous_pixels:
                    # Check if we have a remapping for this color
                    if pixel in self.color_remap:
                        palette_color = self.color_remap[pixel]
                        previous_indexed.append(color_to_index[palette_color])
                    else:
                        # Color should be directly in palette
                        previous_indexed.append(color_to_index[pixel])
                
                changed_count = sum(1 for prev, curr in zip(previous_indexed, indexed_pixels) if prev != curr)
                change_percent = (changed_count / len(indexed_pixels)) * 100
                
                delta_data = self._create_delta_frame_indexed(previous_indexed, indexed_pixels)
                
                frame_type = delta_data[:4]
                if frame_type == b'FULL':
                    print(f"Frame {i}: RLE full frame ({len(delta_data)} bytes, {change_percent:.1f}% changed)")
                elif frame_type == b'URAW':
                    print(f"Frame {i}: Raw full frame ({len(delta_data)} bytes, {change_percent:.1f}% changed)")
                elif frame_type == b'DLTA':
                    print(f"Frame {i}: Delta frame ({len(delta_data)} bytes, {change_percent:.1f}% changed)")
                elif frame_type == b'SAME':
                    print(f"Frame {i}: Same frame ({len(delta_data)} bytes, {change_percent:.1f}% changed)")
            
            frames.append(delta_data)
            previous_pixels = current_pixels[:]  # Keep original pixels for next comparison
        
        # Save delta-compressed file with palette
        self._save_delta_cutscene_indexed(output_filename, frames, frame_width, frame_height, palette)
        
        # Generate player code
        self._generate_delta_player(output_filename.replace('.COL.bin', '_delta_player.py'),
                                  output_filename, frame_width, frame_height, len(frames))
    
    def _build_palette(self, colors):
        """Build optimized palette from color set using simple quantization"""
        unique_colors = list(colors)
        
        if len(unique_colors) <= 256:
            self.color_remap = {}  # No remapping needed
            return unique_colors
        
        print(f"Warning: {len(unique_colors)} colors found, reducing to 256")
        
        # Progressive bit-shift quantization
        for shift in range(1, 5):  # Try shifts from 1 to 4
            quantized_to_original = {}
            
            for color in unique_colors:
                # Extract RGB565 components
                r = (color >> 11) & 0x1F  # 5 bits
                g = (color >> 5) & 0x3F   # 6 bits  
                b = color & 0x1F          # 5 bits
                
                # Quantize by shifting
                r_q = (r >> shift) << shift
                g_q = (g >> shift) << shift
                b_q = (b >> shift) << shift
                
                # Reconstruct quantized color
                quantized = (r_q << 11) | (g_q << 5) | b_q
                
                if quantized not in quantized_to_original:
                    quantized_to_original[quantized] = []
                quantized_to_original[quantized].append(color)
            
            if len(quantized_to_original) <= 256:
                # Success! Build palette and remap table
                palette = list(quantized_to_original.keys())
                
                # Build complete remapping for ALL original colors
                self.color_remap = {}
                for quantized, originals in quantized_to_original.items():
                    for original in originals:
                        self.color_remap[original] = quantized
                
                print(f"Quantized to {len(palette)} palette entries with {shift}-bit reduction")
                return palette
        
        # If we still have too many colors after max quantization, just take first 256
        # This is a fallback that shouldn't normally happen
        print("Warning: Maximum quantization still exceeds 256 colors, truncating")
        palette = list(quantized_to_original.keys())[:256]
        
        # For unmapped colors, find closest match
        self.color_remap = {}
        for color in unique_colors:
            if color not in self.color_remap:
                # Find closest color in palette
                closest = min(palette, key=lambda p: self._color_distance(color, p))
                self.color_remap[color] = closest
        
        return palette
    
    def _color_distance(self, c1, c2):
        """Calculate distance between two RGB565 colors"""
        r1 = (c1 >> 11) & 0x1F
        g1 = (c1 >> 5) & 0x3F
        b1 = c1 & 0x1F
        
        r2 = (c2 >> 11) & 0x1F
        g2 = (c2 >> 5) & 0x3F
        b2 = c2 & 0x1F
        
        return abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
    
    def _create_full_frame_indexed(self, indexed_pixels):
        """Create full frame data with 8-bit indices"""
        # Try RLE compression first
        rle_compressed = self._rle_compress_indexed(indexed_pixels)
        
        # Calculate uncompressed size
        uncompressed_size = len(indexed_pixels)  # 8-bit indices
        
        # Use RLE only if it's actually smaller
        if len(rle_compressed) < uncompressed_size:
            return b'FULL' + struct.pack('<I', len(rle_compressed)) + rle_compressed
        else:
            # RLE makes it bigger - store uncompressed
            uncompressed = bytearray(indexed_pixels)
            return b'URAW' + struct.pack('<I', len(uncompressed)) + uncompressed
    
    def _rle_compress_indexed(self, indexed_pixels):
        """RLE compress 8-bit indexed pixels"""
        compressed = bytearray()
        i = 0
        
        while i < len(indexed_pixels):
            current_index = indexed_pixels[i]
            run_length = 1
            
            # Count consecutive pixels (max 255)
            while (i + run_length < len(indexed_pixels) and 
                   indexed_pixels[i + run_length] == current_index and 
                   run_length < 255):
                run_length += 1
            
            # Store index + count
            compressed.extend(struct.pack('<BB', current_index, run_length - 1))
            i += run_length
        
        return compressed
    
    def _create_delta_frame_indexed(self, previous_indexed, current_indexed):
        """Create delta frame with only changed pixels using 8-bit indices"""
        delta_changes = []  # List of (index, new_pixel_index) tuples
        
        # Find all changed pixels
        for i, (prev, curr) in enumerate(zip(previous_indexed, current_indexed)):
            if prev != curr:
                delta_changes.append((i, curr))
        
        # If no changes, return SAME frame
        if not delta_changes:
            return b'SAME' + struct.pack('<I', 0)
        
        # Calculate compression efficiency
        change_percentage = len(delta_changes) / len(current_indexed)
        
        # Use delta only if it's more efficient (threshold: 30% changed pixels)
        if change_percentage > 0.30:
            # Too many changes - store as full frame with RLE
            return self._create_full_frame_indexed(current_indexed)
        
        # Delta is efficient - store changes individually
        compressed = bytearray()
        compressed.extend(struct.pack('<I', len(delta_changes)))  # Number of changes
        
        # Store each change as: index (4 bytes) + pixel index (1 byte)
        for idx, pixel_idx in delta_changes:
            compressed.extend(struct.pack('<IB', idx, pixel_idx))
        
        return b'DLTA' + struct.pack('<I', len(compressed)) + compressed
    
    def _save_delta_cutscene_indexed(self, filename, frames, width, height, palette):
        """Save delta-compressed cutscene file with 8-bit palette"""
        with open(filename, 'wb') as f:
            # Header with new magic for 8-bit version
            f.write(b'TDL8')  # ThumbyDeLta8bit magic
            f.write(struct.pack('<HHH', width, height, len(frames)))
            
            # Write palette (256 RGB565 colors)
            palette_data = bytearray()
            for i in range(256):
                if i < len(palette):
                    palette_data.extend(struct.pack('<H', palette[i]))
                else:
                    palette_data.extend(struct.pack('<H', 0))  # Pad with black
            f.write(palette_data)
            
            # Calculate frame offsets
            header_size = 4 + 6 + 512  # magic + header + palette
            offset_table_size = len(frames) * 4
            current_offset = header_size + offset_table_size
            
            frame_offsets = []
            for frame in frames:
                frame_offsets.append(current_offset)
                current_offset += len(frame)
            
            # Write offset table
            for offset in frame_offsets:
                f.write(struct.pack('<I', offset))
            
            # Write frame data
            total_uncompressed_16bit = width * height * len(frames) * 2
            total_compressed = sum(len(frame) for frame in frames) + header_size + offset_table_size
            
            for frame in frames:
                f.write(frame)
        
        print(f"Saved {filename}")
        print(f"8-bit compression: {total_compressed}/{total_uncompressed_16bit} bytes ({total_compressed/total_uncompressed_16bit*100:.1f}%)")
    
    def _generate_delta_player(self, filename, sprite_file, width, height, frame_count):
        """Generate MicroPython delta frame player with 8-bit palette support"""
        player_code = f'''# {filename}
# Delta frame player for ThumbyColor cutscenes with 8-bit palette
import struct
import framebuf
from gc import collect

class DeltaFramePlayer:
    """Memory-efficient delta frame cutscene player with 8-bit palette"""
    
    def __init__(self, filename, display):
        self.filename = filename
        self.display = display
        self.width = {width}
        self.height = {height}
        self.frame_count = {frame_count}
        self.frame_offsets = []
        self.palette = []
        
        # Persistent frame buffers
        self.index_buffer = bytearray(self.width * self.height)  # 8-bit indices
        self.frame_buffer = bytearray(self.width * self.height * 2)  # 16-bit RGB565
        self.framebuf_obj = framebuf.FrameBuffer(self.frame_buffer, 
                                               self.width, self.height, 
                                               framebuf.RGB565)
        
        self._load_header()
    
    def _load_header(self):
        """Load file header, palette, and frame offsets"""
        with open(self.filename, 'rb') as f:
            magic = f.read(4)
            if magic not in (b'TDLT', b'TDL8'):
                raise ValueError(f"Invalid delta file: {{magic}}")
            
            self.is_8bit = (magic == b'TDL8')
            
            if self.is_8bit:
                # Load palette for 8-bit version
                f.seek(10)  # Skip header
                for _ in range(256):
                    color = struct.unpack('<H', f.read(2))[0]
                    self.palette.append(color)
            
            # Frame offsets
            offset_pos = 10 + (512 if self.is_8bit else 0)
            f.seek(offset_pos)
            for _ in range(self.frame_count):
                offset = struct.unpack('<I', f.read(4))[0]
                self.frame_offsets.append(offset)
    
    def play_cutscene(self, x=0, y=0, fps=20, frame_callback=None):
        """Play the delta-compressed cutscene"""
        self.display.setFPS(fps)
        
        with open(self.filename, 'rb') as f:
            for frame_idx in range(self.frame_count):
                self.display.fill(0)
                
                # Apply frame delta to buffers
                self._apply_frame_delta(f, frame_idx)
                
                # Blit frame buffer to display
                self.display.internal_fb.blit(self.framebuf_obj, x, y)
                
                if frame_callback:
                    frame_callback(frame_idx)
                
                self.display.update()
                collect()
    
    def _apply_frame_delta(self, file_handle, frame_idx):
        """Apply delta changes to persistent buffers"""
        file_handle.seek(self.frame_offsets[frame_idx])
        
        # Read frame type
        frame_type = file_handle.read(4)
        data_size = struct.unpack('<I', file_handle.read(4))[0]
        frame_data = file_handle.read(data_size)
        
        if self.is_8bit:
            # Process 8-bit indexed frame
            if frame_type == b'FULL':
                self._decompress_full_frame_8bit(frame_data)
            elif frame_type == b'URAW':
                self._load_raw_frame_8bit(frame_data)
            elif frame_type == b'DLTA':
                self._apply_delta_changes_8bit(frame_data)
            elif frame_type == b'SAME':
                pass  # No changes
            
            # Convert index buffer to RGB565 frame buffer
            self._convert_indexed_to_rgb565()
        else:
            # Original 16-bit processing
            if frame_type == b'FULL':
                self._decompress_full_frame(frame_data)
            elif frame_type == b'URAW':
                self._load_raw_frame(frame_data)
            elif frame_type == b'DLTA':
                self._apply_delta_changes(frame_data)
            elif frame_type == b'SAME':
                pass
    
    def _decompress_full_frame_8bit(self, data):
        """Decompress full RLE 8-bit indexed frame"""
        i = 0
        pos = 0
        
        while i + 2 <= len(data) and pos < len(self.index_buffer):
            index = data[i]
            count = data[i + 1] + 1
            
            for _ in range(count):
                if pos < len(self.index_buffer):
                    self.index_buffer[pos] = index
                    pos += 1
                else:
                    break
            
            i += 2
    
    def _load_raw_frame_8bit(self, raw_data):
        """Load uncompressed 8-bit indexed frame"""
        copy_size = min(len(self.index_buffer), len(raw_data))
        for i in range(copy_size):
            self.index_buffer[i] = raw_data[i]
    
    def _apply_delta_changes_8bit(self, data):
        """Apply delta changes for 8-bit indexed frame"""
        offset = 0
        change_count = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        
        for _ in range(change_count):
            if offset + 5 <= len(data):
                pixel_idx = struct.unpack('<I', data[offset:offset+4])[0]
                new_index = data[offset+4]
                offset += 5
                
                if pixel_idx < len(self.index_buffer):
                    self.index_buffer[pixel_idx] = new_index
            else:
                break
    
    def _convert_indexed_to_rgb565(self):
        """Convert 8-bit index buffer to 16-bit RGB565 frame buffer"""
        for i in range(len(self.index_buffer)):
            index = self.index_buffer[i]
            color = self.palette[index]
            
            buf_idx = i * 2
            if buf_idx + 1 < len(self.frame_buffer):
                self.frame_buffer[buf_idx] = color & 0xFF
                self.frame_buffer[buf_idx + 1] = (color >> 8) & 0xFF
    
    # Original 16-bit methods remain unchanged...
    def _decompress_full_frame(self, data):
        """Original 16-bit RLE decompression"""
        pixels = self._rle_decompress(data)
        for i, pixel in enumerate(pixels):
            if i * 2 + 1 < len(self.frame_buffer):
                self.frame_buffer[i * 2] = pixel & 0xFF
                self.frame_buffer[i * 2 + 1] = (pixel >> 8) & 0xFF
    
    def _load_raw_frame(self, raw_data):
        """Original 16-bit raw frame loading"""
        copy_size = min(len(self.frame_buffer), len(raw_data))
        for i in range(copy_size):
            self.frame_buffer[i] = raw_data[i]
    
    def _apply_delta_changes(self, data):
        """Original 16-bit delta changes"""
        offset = 0
        change_count = struct.unpack('<I', data[offset:offset+4])[0]
        offset += 4
        
        for _ in range(change_count):
            if offset + 6 <= len(data):
                pixel_idx = struct.unpack('<I', data[offset:offset+4])[0]
                new_pixel = struct.unpack('<H', data[offset+4:offset+6])[0]
                offset += 6
                
                buf_idx = pixel_idx * 2
                if buf_idx + 1 < len(self.frame_buffer):
                    self.frame_buffer[buf_idx] = new_pixel & 0xFF
                    self.frame_buffer[buf_idx + 1] = (new_pixel >> 8) & 0xFF
            else:
                break
    
    def _rle_decompress(self, data):
        """Original 16-bit RLE decompression"""
        pixels = []
        i = 0
        
        while i + 3 <= len(data):
            pixel = struct.unpack('<H', data[i:i+2])[0]
            count = data[i + 2] + 1
            pixels.extend([pixel] * count)
            i += 3
        
        return pixels

# Usage:
# player = DeltaFramePlayer('{sprite_file}', display)
# player.play_cutscene(x=10, y=10, fps=24)
'''
        
        with open(filename, 'w') as f:
            f.write(player_code)
        
        print(f"Generated delta player: {filename}")

def main():
    parser = argparse.ArgumentParser(description='Create delta-compressed cutscenes with 8-bit palette')
    parser.add_argument('input_pattern', help='Input pattern (e.g., "scene*.jpg")')
    parser.add_argument('output_file', help='Output file (e.g., "scene_delta.COL.bin")')
    parser.add_argument('--sprite-name', default='cutscene', help='Scene identifier')
    parser.add_argument('--scale', type=int, default=1, help='Scale factor')
    
    args = parser.parse_args()
    
    compressor = DeltaFrameCompressor(scale_factor=args.scale)
    compressor.compress_cutscene_delta(args.input_pattern, args.output_file, args.sprite_name)

if __name__ == "__main__":
    main()