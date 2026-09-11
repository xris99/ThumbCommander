# grayscale_video_generator.py
# Converts JPEG frames to Thumby grayscale format (BIT + SHD files)
# Compatible with play_cutscene_animation() from platform_loader.py

import struct
import argparse
from PIL import Image
from pathlib import Path


class GrayscaleVideoGenerator:
    """
    Converts JPEG frames to Thumby's 4-color grayscale format.
    
    Output format:
    - Two files: {name}_{width}_{height}.BIT.bin and {name}_{width}_{height}.SHD.bin
    - Full frames only (no delta compression)
    - Column-major format: each byte contains 8 vertical pixels
    
    Color mapping (matches grayscale.py):
    - BLACK = 0:     BIT=0, SHD=0
    - WHITE = 1:     BIT=1, SHD=0  
    - DARKGRAY = 2:  BIT=0, SHD=1
    - LIGHTGRAY = 3: BIT=1, SHD=1
    """
    
    # Grayscale color indices
    BLACK = 0
    WHITE = 1
    DARKGRAY = 2
    LIGHTGRAY = 3
    
    def __init__(self, target_width=72, target_height=40, dither=False):
        """
        Initialize the generator.
        
        Args:
            target_width: Output width (default 72 for Thumby)
            target_height: Output height (default 40 for Thumby)
            dither: Enable Floyd-Steinberg dithering for better gradients
        """
        self.target_width = target_width
        self.target_height = target_height
        self.dither = dither
        
        # Grayscale thresholds for 4 levels (0-255 -> 0-3)
        # Evenly spaced: 0-63=BLACK, 64-127=DARKGRAY, 128-191=LIGHTGRAY, 192-255=WHITE
        self.thresholds = [64, 128, 192]
    
    def _grayscale_to_4level(self, gray_value):
        """Convert 0-255 grayscale to 4-level index (0-3)."""
        if gray_value < self.thresholds[0]:
            return self.BLACK      # 0
        elif gray_value < self.thresholds[1]:
            return self.DARKGRAY   # 2
        elif gray_value < self.thresholds[2]:
            return self.LIGHTGRAY  # 3
        else:
            return self.WHITE      # 1
    
    def _apply_dithering(self, img):
        """Apply Floyd-Steinberg dithering to grayscale image."""
        # Convert to float for error diffusion
        pixels = list(img.getdata())
        width, height = img.size
        
        # Create mutable float array
        float_pixels = [[float(pixels[y * width + x]) for x in range(width)] for y in range(height)]
        
        # Floyd-Steinberg error diffusion
        for y in range(height):
            for x in range(width):
                old_pixel = float_pixels[y][x]
                
                # Quantize to nearest of 4 levels
                if old_pixel < 64:
                    new_pixel = 0      # BLACK
                elif old_pixel < 128:
                    new_pixel = 85     # DARKGRAY (255/3)
                elif old_pixel < 192:
                    new_pixel = 170    # LIGHTGRAY (255*2/3)
                else:
                    new_pixel = 255    # WHITE
                
                float_pixels[y][x] = new_pixel
                error = old_pixel - new_pixel
                
                # Distribute error to neighbors
                if x + 1 < width:
                    float_pixels[y][x + 1] += error * 7 / 16
                if y + 1 < height:
                    if x > 0:
                        float_pixels[y + 1][x - 1] += error * 3 / 16
                    float_pixels[y + 1][x] += error * 5 / 16
                    if x + 1 < width:
                        float_pixels[y + 1][x + 1] += error * 1 / 16
        
        # Convert back to image
        result = Image.new('L', (width, height))
        for y in range(height):
            for x in range(width):
                result.putpixel((x, y), int(max(0, min(255, float_pixels[y][x]))))
        
        return result
    
    def _convert_frame_to_bitplanes(self, img):
        """
        Convert a grayscale image to BIT and SHD bitplanes.
        
        Format: Column-major, each byte contains 8 vertical pixels.
        Byte layout for column x:
            byte 0: pixels y=0-7 (bit 0 = y=0, bit 7 = y=7)
            byte 1: pixels y=8-15
            etc.
        
        Returns:
            (bit_data, shd_data): Tuple of bytearrays
        """
        width, height = img.size
        
        # Calculate buffer size: width * ceil(height / 8)
        pages = (height + 7) // 8
        buffer_size = width * pages
        
        bit_data = bytearray(buffer_size)
        shd_data = bytearray(buffer_size)
        
        for x in range(width):
            for y in range(height):
                # Get grayscale value and convert to 4-level
                gray = img.getpixel((x, y))
                color = self._grayscale_to_4level(gray)
                
                # Calculate byte position and bit position
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * width + x
                
                # Set bits based on color
                # Color bit 0 -> BIT file
                # Color bit 1 -> SHD file
                if color & 1:
                    bit_data[byte_idx] |= (1 << bit_pos)
                if color & 2:
                    shd_data[byte_idx] |= (1 << bit_pos)
        
        return bit_data, shd_data
    
    def generate_video(self, input_pattern, output_basename):
        """
        Convert JPEG frames to Thumby grayscale video format.
        
        Args:
            input_pattern: Glob pattern for input files (e.g., "frame*.jpg")
            output_basename: Base name for output (e.g., "cutscene")
                            Will create: cutscene_{width}_{height}.BIT.bin
                                        cutscene_{width}_{height}.SHD.bin
        """
        # Find all matching files
        jpeg_files = sorted(Path('.').glob(input_pattern))
        if not jpeg_files:
            print(f"No files found matching {input_pattern}")
            return None
        
        print(f"Found {len(jpeg_files)} frames")
        
        all_bit_data = bytearray()
        all_shd_data = bytearray()
        frame_width = None
        frame_height = None
        
        for i, jpeg_file in enumerate(jpeg_files):
            # Load image
            img = Image.open(jpeg_file)
            
            # Convert to grayscale
            img = img.convert('L')
            
            # Resize to target dimensions
            if img.width != self.target_width or img.height != self.target_height:
                img = img.resize((self.target_width, self.target_height), Image.LANCZOS)
            
            # Store dimensions from first frame
            if frame_width is None:
                frame_width = img.width
                frame_height = img.height
                pages = (frame_height + 7) // 8
                buffer_size = frame_width * pages
                print(f"Frame size: {frame_width}x{frame_height}")
                print(f"Buffer size per frame: {buffer_size} bytes")
            
            # Apply dithering if enabled
            if self.dither:
                img = self._apply_dithering(img)
            
            # Convert to bitplanes
            bit_data, shd_data = self._convert_frame_to_bitplanes(img)
            
            all_bit_data.extend(bit_data)
            all_shd_data.extend(shd_data)
            
            if (i + 1) % 10 == 0 or i == len(jpeg_files) - 1:
                print(f"Processed frame {i + 1}/{len(jpeg_files)}")
        
        # Generate output filenames with dimensions (required by play_cutscene_animation)
        bit_filename = f"{output_basename}_{frame_width}_{frame_height}.BIT.bin"
        shd_filename = f"{output_basename}_{frame_width}_{frame_height}.SHD.bin"
        
        # Write BIT file
        with open(bit_filename, 'wb') as f:
            f.write(all_bit_data)
        
        # Write SHD file
        with open(shd_filename, 'wb') as f:
            f.write(all_shd_data)
        
        print(f"\nGenerated files:")
        print(f"  {bit_filename} ({len(all_bit_data)} bytes)")
        print(f"  {shd_filename} ({len(all_shd_data)} bytes)")
        print(f"  Total frames: {len(jpeg_files)}")
        print(f"  Bytes per frame: {buffer_size}")
        
        return bit_filename, shd_filename


class GrayscalePreviewGenerator:
    """Generate preview images to verify the conversion."""
    
    # RGB values for preview (approximate OLED appearance)
    COLORS = {
        0: (0, 0, 0),       # BLACK
        1: (255, 255, 255), # WHITE
        2: (85, 85, 85),    # DARKGRAY
        3: (170, 170, 170)  # LIGHTGRAY
    }
    
    @staticmethod
    def generate_preview(bit_file, shd_file, output_file, frame_index=0, scale=4):
        """
        Generate a preview image from BIT/SHD files.
        
        Args:
            bit_file: Path to .BIT.bin file
            shd_file: Path to .SHD.bin file
            output_file: Output PNG file
            frame_index: Which frame to preview (0-based)
            scale: Upscale factor for preview
        """
        # Parse dimensions from filename
        parts = Path(bit_file).stem.split('_')
        width = int(parts[-2])
        height = int(parts[-1].replace('.BIT', ''))
        
        pages = (height + 7) // 8
        buffer_size = width * pages
        
        # Read frame data
        with open(bit_file, 'rb') as f:
            f.seek(frame_index * buffer_size)
            bit_data = f.read(buffer_size)
        
        with open(shd_file, 'rb') as f:
            f.seek(frame_index * buffer_size)
            shd_data = f.read(buffer_size)
        
        # Create preview image
        preview = Image.new('RGB', (width * scale, height * scale))
        
        for x in range(width):
            for y in range(height):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * width + x
                
                # Reconstruct color from bitplanes
                color = 0
                if bit_data[byte_idx] & (1 << bit_pos):
                    color |= 1
                if shd_data[byte_idx] & (1 << bit_pos):
                    color |= 2
                
                rgb = GrayscalePreviewGenerator.COLORS[color]
                
                # Draw scaled pixel
                for dy in range(scale):
                    for dx in range(scale):
                        preview.putpixel((x * scale + dx, y * scale + dy), rgb)
        
        preview.save(output_file)
        print(f"Preview saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert JPEG frames to Thumby grayscale video format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "frame*.jpg" cutscene
      Creates cutscene_72_40.BIT.bin and cutscene_72_40.SHD.bin
  
  %(prog)s "scene*.jpg" myscene --width 74 --height 30 --dither
      Creates myscene_74_30.BIT.bin and myscene_74_30.SHD.bin with dithering
  
  %(prog)s "*.jpg" video --preview 0
      Creates video files and preview of frame 0

Output files are compatible with play_cutscene_animation() from platform_loader.py
        """
    )
    
    parser.add_argument('input_pattern', 
                        help='Input pattern for JPEG files (e.g., "frame*.jpg")')
    parser.add_argument('output_basename',
                        help='Base name for output files (e.g., "cutscene")')
    parser.add_argument('--width', type=int, default=72,
                        help='Target width (default: 72)')
    parser.add_argument('--height', type=int, default=40,
                        help='Target height (default: 40)')
    parser.add_argument('--dither', action='store_true',
                        help='Enable Floyd-Steinberg dithering')
    parser.add_argument('--preview', type=int, metavar='FRAME',
                        help='Generate preview PNG of specified frame')
    parser.add_argument('--preview-scale', type=int, default=4,
                        help='Scale factor for preview (default: 4)')
    
    args = parser.parse_args()
    
    # Create generator and process frames
    generator = GrayscaleVideoGenerator(
        target_width=args.width,
        target_height=args.height,
        dither=args.dither
    )
    
    result = generator.generate_video(args.input_pattern, args.output_basename)
    
    if result and args.preview is not None:
        bit_file, shd_file = result
        preview_file = f"{args.output_basename}_preview_frame{args.preview}.png"
        GrayscalePreviewGenerator.generate_preview(
            bit_file, shd_file, preview_file,
            frame_index=args.preview,
            scale=args.preview_scale
        )


if __name__ == "__main__":
    main()
