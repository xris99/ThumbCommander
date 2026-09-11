# grayscale_sprite_scaler.py
# Scales Thumby grayscale sprite files (BIT + SHD) to a specified percentage

import argparse
from pathlib import Path
from PIL import Image


class GrayscaleSpriteScaler:
    """
    Scales Thumby grayscale sprite files (BIT/SHD format) to a new size.
    
    Format:
    - Column-major: each byte contains 8 vertical pixels
    - Two files: .BIT.bin (bit 0) and .SHD.bin (bit 1)
    - 4 colors: BLACK=0, WHITE=1, DARKGRAY=2, LIGHTGRAY=3
    """
    
    # Color indices
    BLACK = 0
    WHITE = 1
    DARKGRAY = 2
    LIGHTGRAY = 3
    
    def __init__(self):
        pass
    
    def _decode_sprite(self, bit_data, shd_data, width, height):
        """
        Decode BIT/SHD data to a 2D array of color indices.
        
        Returns:
            List of lists: pixels[y][x] = color index (0-3)
        """
        pixels = [[0 for _ in range(width)] for _ in range(height)]
        
        pages = (height + 7) // 8
        
        for x in range(width):
            for y in range(height):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * width + x
                
                if byte_idx < len(bit_data):
                    color = 0
                    if bit_data[byte_idx] & (1 << bit_pos):
                        color |= 1
                    if shd_data[byte_idx] & (1 << bit_pos):
                        color |= 2
                    pixels[y][x] = color
        
        return pixels
    
    def _encode_sprite(self, pixels, width, height):
        """
        Encode 2D pixel array back to BIT/SHD format.
        
        Args:
            pixels: List of lists, pixels[y][x] = color index (0-3)
            width: Output width
            height: Output height
            
        Returns:
            (bit_data, shd_data): Tuple of bytearrays
        """
        pages = (height + 7) // 8
        buffer_size = width * pages
        
        bit_data = bytearray(buffer_size)
        shd_data = bytearray(buffer_size)
        
        for x in range(width):
            for y in range(height):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * width + x
                
                color = pixels[y][x]
                
                if color & 1:
                    bit_data[byte_idx] |= (1 << bit_pos)
                if color & 2:
                    shd_data[byte_idx] |= (1 << bit_pos)
        
        return bit_data, shd_data
    
    def _scale_nearest(self, pixels, src_width, src_height, dst_width, dst_height):
        """Scale using nearest neighbor interpolation."""
        scaled = [[0 for _ in range(dst_width)] for _ in range(dst_height)]
        
        x_ratio = src_width / dst_width
        y_ratio = src_height / dst_height
        
        for y in range(dst_height):
            for x in range(dst_width):
                src_x = int(x * x_ratio)
                src_y = int(y * y_ratio)
                
                # Clamp to valid range
                src_x = min(src_x, src_width - 1)
                src_y = min(src_y, src_height - 1)
                
                scaled[y][x] = pixels[src_y][src_x]
        
        return scaled
    
    def _scale_area_average(self, pixels, src_width, src_height, dst_width, dst_height):
        """
        Scale using area averaging for better quality downscaling.
        Averages all source pixels that contribute to each destination pixel.
        """
        scaled = [[0 for _ in range(dst_width)] for _ in range(dst_height)]
        
        x_ratio = src_width / dst_width
        y_ratio = src_height / dst_height
        
        for y in range(dst_height):
            for x in range(dst_width):
                # Calculate source region that maps to this destination pixel
                src_x_start = x * x_ratio
                src_x_end = (x + 1) * x_ratio
                src_y_start = y * y_ratio
                src_y_end = (y + 1) * y_ratio
                
                # Collect all source pixels in this region
                color_sum = 0
                count = 0
                
                for src_y in range(int(src_y_start), min(int(src_y_end) + 1, src_height)):
                    for src_x in range(int(src_x_start), min(int(src_x_end) + 1, src_width)):
                        color_sum += pixels[src_y][src_x]
                        count += 1
                
                if count > 0:
                    # Average and round to nearest color (0-3)
                    avg = color_sum / count
                    scaled[y][x] = int(round(avg))
                    # Clamp to valid range
                    scaled[y][x] = max(0, min(3, scaled[y][x]))
        
        return scaled
    
    def scale_sprite(self, bit_file, shd_file, src_width, src_height, 
                     scale_percent=None, dst_width=None, dst_height=None,
                     method='area', output_prefix=None):
        """
        Scale a grayscale sprite to a new size.
        
        Args:
            bit_file: Path to .BIT.bin file
            shd_file: Path to .SHD.bin file  
            src_width: Original sprite width
            src_height: Original sprite height
            scale_percent: Scale percentage (e.g., 50 for 50%)
            dst_width: Target width (alternative to scale_percent)
            dst_height: Target height (alternative to scale_percent)
            method: 'nearest' or 'area' (default: area)
            output_prefix: Output filename prefix (default: derived from input)
            
        Returns:
            (output_bit_file, output_shd_file): Tuple of output filenames
        """
        # Calculate destination dimensions
        if scale_percent is not None:
            scale = scale_percent / 100.0
            dst_width = max(1, int(src_width * scale))
            dst_height = max(1, int(src_height * scale))
        elif dst_width is None or dst_height is None:
            raise ValueError("Must specify either scale_percent or both dst_width and dst_height")
        
        # Read source files
        with open(bit_file, 'rb') as f:
            bit_data = f.read()
        with open(shd_file, 'rb') as f:
            shd_data = f.read()
        
        # Calculate expected size and frame count
        src_pages = (src_height + 7) // 8
        src_frame_size = src_width * src_pages
        frame_count = len(bit_data) // src_frame_size
        
        print(f"Source: {src_width}x{src_height}, {frame_count} frame(s)")
        print(f"Target: {dst_width}x{dst_height} ({scale_percent}%)" if scale_percent else 
              f"Target: {dst_width}x{dst_height}")
        print(f"Method: {method}")
        
        # Process each frame
        dst_pages = (dst_height + 7) // 8
        dst_frame_size = dst_width * dst_pages
        
        all_bit_data = bytearray()
        all_shd_data = bytearray()
        
        for frame_idx in range(frame_count):
            # Extract frame data
            offset = frame_idx * src_frame_size
            frame_bit = bit_data[offset:offset + src_frame_size]
            frame_shd = shd_data[offset:offset + src_frame_size]
            
            # Decode to pixels
            pixels = self._decode_sprite(frame_bit, frame_shd, src_width, src_height)
            
            # Scale
            if method == 'nearest':
                scaled = self._scale_nearest(pixels, src_width, src_height, dst_width, dst_height)
            else:  # area
                scaled = self._scale_area_average(pixels, src_width, src_height, dst_width, dst_height)
            
            # Encode back to BIT/SHD format
            new_bit, new_shd = self._encode_sprite(scaled, dst_width, dst_height)
            
            all_bit_data.extend(new_bit)
            all_shd_data.extend(new_shd)
            
            if frame_count > 1 and (frame_idx + 1) % 10 == 0:
                print(f"Processed frame {frame_idx + 1}/{frame_count}")
        
        # Generate output filenames
        if output_prefix is None:
            # Try to extract base name from input
            base = Path(bit_file).stem
            # Remove dimension suffix if present (e.g., "_72_40.BIT")
            parts = base.replace('.BIT', '').replace('.SHD', '').split('_')
            # Check if last two parts are numbers (dimensions)
            try:
                int(parts[-1])
                int(parts[-2])
                output_prefix = '_'.join(parts[:-2])
            except (ValueError, IndexError):
                output_prefix = base.replace('.BIT', '').replace('.SHD', '')
        
        output_bit = f"{output_prefix}_{dst_width}_{dst_height}.BIT.bin"
        output_shd = f"{output_prefix}_{dst_width}_{dst_height}.SHD.bin"
        
        # Write output files
        with open(output_bit, 'wb') as f:
            f.write(all_bit_data)
        with open(output_shd, 'wb') as f:
            f.write(all_shd_data)
        
        print(f"\nGenerated files:")
        print(f"  {output_bit} ({len(all_bit_data)} bytes)")
        print(f"  {output_shd} ({len(all_shd_data)} bytes)")
        print(f"  Frames: {frame_count}")
        print(f"  Bytes per frame: {dst_frame_size}")
        
        return output_bit, output_shd


class GrayscaleSpritePreview:
    """Generate preview images from BIT/SHD sprite files."""
    
    COLORS = {
        0: (0, 0, 0),       # BLACK
        1: (255, 255, 255), # WHITE
        2: (85, 85, 85),    # DARKGRAY
        3: (170, 170, 170)  # LIGHTGRAY
    }
    
    @staticmethod
    def generate_preview(bit_file, shd_file, width, height, output_file, 
                        frame_index=0, scale=1):
        """
        Generate a preview PNG from BIT/SHD files.
        
        Args:
            bit_file: Path to .BIT.bin file
            shd_file: Path to .SHD.bin file
            width: Sprite width
            height: Sprite height
            output_file: Output PNG filename
            frame_index: Which frame to preview (0-based)
            scale: Upscale factor for preview
        """
        pages = (height + 7) // 8
        frame_size = width * pages
        
        with open(bit_file, 'rb') as f:
            f.seek(frame_index * frame_size)
            bit_data = f.read(frame_size)
        
        with open(shd_file, 'rb') as f:
            f.seek(frame_index * frame_size)
            shd_data = f.read(frame_size)
        
        # Create preview image
        preview = Image.new('RGB', (width * scale, height * scale))
        
        for x in range(width):
            for y in range(height):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * width + x
                
                color = 0
                if byte_idx < len(bit_data):
                    if bit_data[byte_idx] & (1 << bit_pos):
                        color |= 1
                    if shd_data[byte_idx] & (1 << bit_pos):
                        color |= 2
                
                rgb = GrayscaleSpritePreview.COLORS[color]
                
                for dy in range(scale):
                    for dx in range(scale):
                        preview.putpixel((x * scale + dx, y * scale + dy), rgb)
        
        preview.save(output_file)
        print(f"Preview saved: {output_file}")
    
    @staticmethod
    def generate_comparison(bit_file1, shd_file1, w1, h1,
                           bit_file2, shd_file2, w2, h2,
                           output_file, frame_index=0, scale=4):
        """
        Generate a side-by-side comparison of two sprites.
        """
        pages1 = (h1 + 7) // 8
        pages2 = (h2 + 7) // 8
        frame_size1 = w1 * pages1
        frame_size2 = w2 * pages2
        
        with open(bit_file1, 'rb') as f:
            f.seek(frame_index * frame_size1)
            bit_data1 = f.read(frame_size1)
        with open(shd_file1, 'rb') as f:
            f.seek(frame_index * frame_size1)
            shd_data1 = f.read(frame_size1)
        
        with open(bit_file2, 'rb') as f:
            f.seek(frame_index * frame_size2)
            bit_data2 = f.read(frame_size2)
        with open(shd_file2, 'rb') as f:
            f.seek(frame_index * frame_size2)
            shd_data2 = f.read(frame_size2)
        
        # Calculate preview dimensions
        preview_w1 = w1 * scale
        preview_h1 = h1 * scale
        preview_w2 = w2 * scale
        preview_h2 = h2 * scale
        
        gap = 10
        total_width = preview_w1 + gap + preview_w2
        total_height = max(preview_h1, preview_h2)
        
        preview = Image.new('RGB', (total_width, total_height), (128, 128, 128))
        
        # Draw first sprite
        for x in range(w1):
            for y in range(h1):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * w1 + x
                
                color = 0
                if byte_idx < len(bit_data1):
                    if bit_data1[byte_idx] & (1 << bit_pos):
                        color |= 1
                    if shd_data1[byte_idx] & (1 << bit_pos):
                        color |= 2
                
                rgb = GrayscaleSpritePreview.COLORS[color]
                for dy in range(scale):
                    for dx in range(scale):
                        preview.putpixel((x * scale + dx, y * scale + dy), rgb)
        
        # Draw second sprite
        x_offset = preview_w1 + gap
        for x in range(w2):
            for y in range(h2):
                page = y // 8
                bit_pos = y % 8
                byte_idx = page * w2 + x
                
                color = 0
                if byte_idx < len(bit_data2):
                    if bit_data2[byte_idx] & (1 << bit_pos):
                        color |= 1
                    if shd_data2[byte_idx] & (1 << bit_pos):
                        color |= 2
                
                rgb = GrayscaleSpritePreview.COLORS[color]
                for dy in range(scale):
                    for dx in range(scale):
                        preview.putpixel((x_offset + x * scale + dx, y * scale + dy), rgb)
        
        preview.save(output_file)
        print(f"Comparison saved: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Scale Thumby grayscale sprite files (BIT/SHD format)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s sprite.BIT.bin sprite.SHD.bin 72 40 --scale 50
      Scale 72x40 sprite to 50%% (36x20)
  
  %(prog)s sprite.BIT.bin sprite.SHD.bin 100 80 --width 50 --height 40
      Scale to specific dimensions
  
  %(prog)s sprite.BIT.bin sprite.SHD.bin 72 40 --scale 75 --method nearest
      Scale using nearest neighbor interpolation
  
  %(prog)s sprite.BIT.bin sprite.SHD.bin 72 40 --scale 50 --preview
      Scale and generate preview images

Output files will be named: {prefix}_{width}_{height}.BIT.bin / .SHD.bin
        """
    )
    
    parser.add_argument('bit_file', help='Input .BIT.bin file')
    parser.add_argument('shd_file', help='Input .SHD.bin file')
    parser.add_argument('width', type=int, help='Original sprite width')
    parser.add_argument('height', type=int, help='Original sprite height')
    
    size_group = parser.add_mutually_exclusive_group(required=True)
    size_group.add_argument('--scale', type=float, 
                           help='Scale percentage (e.g., 50 for 50%%)')
    size_group.add_argument('--dimensions', nargs=2, type=int, metavar=('W', 'H'),
                           help='Target width and height')
    
    parser.add_argument('--method', choices=['nearest', 'area'], default='area',
                        help='Scaling method (default: area)')
    parser.add_argument('--output', '-o', metavar='PREFIX',
                        help='Output filename prefix')
    parser.add_argument('--preview', action='store_true',
                        help='Generate preview PNG files')
    parser.add_argument('--preview-scale', type=int, default=4,
                        help='Preview upscale factor (default: 4)')
    parser.add_argument('--frame', type=int, default=0,
                        help='Frame index for preview (default: 0)')
    
    args = parser.parse_args()
    
    scaler = GrayscaleSpriteScaler()
    
    # Determine target dimensions
    if args.scale:
        result = scaler.scale_sprite(
            args.bit_file, args.shd_file,
            args.width, args.height,
            scale_percent=args.scale,
            method=args.method,
            output_prefix=args.output
        )
    else:
        dst_w, dst_h = args.dimensions
        result = scaler.scale_sprite(
            args.bit_file, args.shd_file,
            args.width, args.height,
            dst_width=dst_w, dst_height=dst_h,
            method=args.method,
            output_prefix=args.output
        )
    
    if result and args.preview:
        output_bit, output_shd = result
        
        # Parse output dimensions from filename
        parts = Path(output_bit).stem.split('_')
        out_w = int(parts[-2])
        out_h = int(parts[-1].replace('.BIT', ''))
        
        # Generate individual previews
        src_preview = f"preview_source_{args.width}x{args.height}.png"
        dst_preview = f"preview_scaled_{out_w}x{out_h}.png"
        
        GrayscaleSpritePreview.generate_preview(
            args.bit_file, args.shd_file, args.width, args.height,
            src_preview, frame_index=args.frame, scale=args.preview_scale
        )
        
        GrayscaleSpritePreview.generate_preview(
            output_bit, output_shd, out_w, out_h,
            dst_preview, frame_index=args.frame, scale=args.preview_scale
        )
        
        # Generate comparison
        comparison_file = f"preview_comparison_{args.width}x{args.height}_to_{out_w}x{out_h}.png"
        GrayscaleSpritePreview.generate_comparison(
            args.bit_file, args.shd_file, args.width, args.height,
            output_bit, output_shd, out_w, out_h,
            comparison_file, frame_index=args.frame, scale=args.preview_scale
        )


if __name__ == "__main__":
    main()
