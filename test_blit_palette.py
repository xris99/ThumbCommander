#!/usr/bin/env python3
"""
Test FrameBuffer blit with palette
"""

import sys
sys.path.insert(0, 'pc_wrapper')

from framebuf import FrameBuffer, RGB565, GS8

# Create display framebuffer (RGB565)
display_buffer = bytearray(128 * 128 * 2)
display_fb = FrameBuffer(display_buffer, 128, 128, RGB565)

# Create palette (256 colors)
palette_data = bytearray(256 * 2)
for i in range(256):
    # Create a gradient palette
    r = (i * 31) // 255
    g = (i * 63) // 255
    b = (i * 31) // 255
    color565 = (r << 11) | (g << 5) | b
    palette_data[i * 2] = color565 & 0xFF
    palette_data[i * 2 + 1] = (color565 >> 8) & 0xFF
palette = FrameBuffer(palette_data, 256, 1, RGB565)

# Create source framebuffer (GS8 - indexed color)
source_buffer = bytearray(80 * 60)
for y in range(60):
    for x in range(80):
        # Create a test pattern
        source_buffer[y * 80 + x] = (x + y) % 256
source_fb = FrameBuffer(source_buffer, 80, 60, GS8)

# Test blit with palette
print("Testing blit with palette...")
display_fb.fill(0)
display_fb.blit(source_fb, 24, 34, 0, palette)

# Check if pixels were set
pixels_set = 0
for y in range(128):
    for x in range(128):
        if display_fb.pixel(x, y) != 0:
            pixels_set += 1

print(f"Pixels set: {pixels_set}")
print(f"Expected: {80 * 60} (source size)")

if pixels_set > 0:
    print("✓ Blit with palette is working!")
else:
    print("✗ Blit with palette failed - no pixels set")

# Check a specific pixel
test_x, test_y = 24, 34  # Top-left of blitted area
pixel_color = display_fb.pixel(test_x, test_y)
print(f"Pixel at ({test_x}, {test_y}): 0x{pixel_color:04x}")

# Check center pixel
center_x, center_y = 24 + 40, 34 + 30
pixel_color = display_fb.pixel(center_x, center_y)
print(f"Pixel at ({center_x}, {center_y}): 0x{pixel_color:04x}")
