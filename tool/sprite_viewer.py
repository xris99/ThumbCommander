#!/usr/bin/env python3
"""
Sprite Sheet Viewer for ThumbCommander sprites
Displays enemy and asteroid sprites with frame numbers
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont
import struct
import tkinter as tk
from tkinter import ttk, filedialog

class SpriteViewer:
    def __init__(self):
        self.sprites = [
            # Asteroids
            {"name": "Asteroid 1", "file": "astroid1_56_47.BIT.bin", "shadow": "astroid1_56_47.SHD.bin", "width": 56, "height": 47},
            {"name": "Asteroid 2", "file": "astroid2_56_47.BIT.bin", "shadow": "astroid2_56_47.SHD.bin", "width": 56, "height": 47},
            # Enemies
            {"name": "Enemy 1", "file": "enemy1_70_59.BIT.bin", "shadow": "enemy1_70_59.SHD.bin", "width": 70, "height": 59},
            # Explosion (bonus)
            {"name": "Explosion", "file": "explode_56_54.BIT.bin", "shadow": "explode_56_54.SHD.bin", "width": 56, "height": 54},
        ]
        
    def read_grayscale_sprite(self, filename, width, height):
        """Read a grayscale sprite file and return list of frame images"""
        frames = []
        
        # Calculate bytes per frame (height is packed into bytes)
        bytes_per_frame = width * ((height + 7) // 8)
        
        try:
            # Read main bitmap
            with open(filename, 'rb') as f:
                data = f.read()
            
            # Read shadow bitmap if exists
            shadow_data = None
            shadow_file = filename.replace('.BIT.bin', '.SHD.bin')
            if os.path.exists(shadow_file):
                with open(shadow_file, 'rb') as f:
                    shadow_data = f.read()
            
            # Calculate number of frames
            frame_count = len(data) // bytes_per_frame
            
            # Process each frame
            for frame in range(frame_count):
                # Create image for this frame
                img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                pixels = img.load()
                
                # Get frame data
                frame_start = frame * bytes_per_frame
                frame_data = data[frame_start:frame_start + bytes_per_frame]
                frame_shadow = None
                if shadow_data:
                    frame_shadow = shadow_data[frame_start:frame_start + bytes_per_frame]
                
                # Decode pixels
                for x in range(width):
                    for y in range(height):
                        # Calculate byte and bit position
                        byte_row = y // 8
                        bit_pos = y % 8
                        byte_index = byte_row * width + x
                        
                        if byte_index < len(frame_data):
                            # Get bit value
                            bit_mask = 1 << bit_pos
                            bit_value = (frame_data[byte_index] & bit_mask) != 0
                            shadow_value = False
                            
                            if frame_shadow and byte_index < len(frame_shadow):
                                shadow_value = (frame_shadow[byte_index] & bit_mask) != 0
                            
                            # Set pixel color based on bit values
                            # Using grayscale palette: BLACK, WHITE, DARKGRAY, LIGHTGRAY
                            if bit_value and shadow_value:
                                # Both set = light gray
                                pixels[x, y] = (192, 192, 192, 255)
                            elif bit_value:
                                # Only bit set = white
                                pixels[x, y] = (255, 255, 255, 255)
                            elif shadow_value:
                                # Only shadow set = dark gray
                                pixels[x, y] = (64, 64, 64, 255)
                            else:
                                # Neither set = black
                                pixels[x, y] = (0, 0, 0, 255)
                
                frames.append(img)
                
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            # Return empty frame
            img = Image.new('RGBA', (width, height), (255, 0, 0, 255))
            frames = [img]
            
        return frames
    
    def read_color_sprite(self, filename):
        """Read a color sprite file (.COL format) and return list of frame images"""
        frames = []
        
        try:
            with open(filename, 'rb') as f:
                # Read header
                header = f.read(8)
                width, height, frame_count, flags = struct.unpack('<HHHH', header)
                
                # Read each frame
                for frame in range(frame_count):
                    # Create image
                    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
                    pixels = img.load()
                    
                    # Read frame data (RGB565)
                    frame_size = width * height * 2
                    frame_data = f.read(frame_size)
                    
                    # Convert RGB565 to RGBA
                    for y in range(height):
                        for x in range(width):
                            pixel_idx = (y * width + x) * 2
                            if pixel_idx + 1 < len(frame_data):
                                # RGB565 format
                                rgb565 = frame_data[pixel_idx] | (frame_data[pixel_idx + 1] << 8)
                                r = ((rgb565 >> 11) & 0x1F) << 3
                                g = ((rgb565 >> 5) & 0x3F) << 2
                                b = (rgb565 & 0x1F) << 3
                                pixels[x, y] = (r, g, b, 255)
                    
                    frames.append(img)
                    
        except Exception as e:
            print(f"Error reading color sprite {filename}: {e}")
            
        return frames
    
    def create_sprite_sheet(self, frames, title, scale=3):
        """Create a sprite sheet image from frames"""
        if not frames:
            return None
            
        # Calculate grid size
        cols = min(8, len(frames))  # Max 8 columns
        rows = (len(frames) + cols - 1) // cols
        
        # Get frame size
        frame_width = frames[0].width * scale
        frame_height = frames[0].height * scale
        
        # Add padding and space for numbers
        padding = 10
        number_height = 20
        cell_width = frame_width + padding * 2
        cell_height = frame_height + padding * 2 + number_height
        
        # Create sheet
        sheet_width = cols * cell_width + padding * 2
        sheet_height = rows * cell_height + padding * 2 + 30  # Extra for title
        sheet = Image.new('RGBA', (sheet_width, sheet_height), (200, 200, 200, 255))
        draw = ImageDraw.Draw(sheet)
        
        # Try to load a font
        try:
            font = ImageFont.truetype("arial.ttf", 16)
            title_font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()
            title_font = font
        
        # Draw title
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text(((sheet_width - title_width) // 2, 5), title, fill=(0, 0, 0), font=title_font)
        
        # Draw frames
        for i, frame in enumerate(frames):
            row = i // cols
            col = i % cols
            
            # Calculate position
            x = padding + col * cell_width + padding
            y = 35 + padding + row * cell_height + padding
            
            # Scale and draw frame
            scaled_frame = frame.resize((frame_width, frame_height), Image.NEAREST)
            
            # Draw border
            draw.rectangle([x-2, y-2, x+frame_width+1, y+frame_height+1], outline=(0, 0, 0), width=2)
            
            # Paste frame
            sheet.paste(scaled_frame, (x, y))
            
            # Draw frame number
            number_text = str(i)
            text_bbox = draw.textbbox((0, 0), number_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_x = x + (frame_width - text_width) // 2
            text_y = y + frame_height + 5
            draw.text((text_x, text_y), number_text, fill=(0, 0, 0), font=font)
        
        return sheet
    
    def create_window(self):
        """Create the main window"""
        root = tk.Tk()
        root.title("ThumbCommander Sprite Viewer")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Process each sprite type
        for sprite_info in self.sprites:
            frames = self.read_grayscale_sprite(
                sprite_info["file"], 
                sprite_info["width"], 
                sprite_info["height"]
            )
            
            if frames:
                # Create sprite sheet
                sheet = self.create_sprite_sheet(frames, sprite_info["name"])
                
                if sheet:
                    # Create tab
                    frame = ttk.Frame(notebook)
                    notebook.add(frame, text=sprite_info["name"])
                    
                    # Create canvas with scrollbars
                    canvas = tk.Canvas(frame, bg='white')
                    h_scrollbar = ttk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
                    v_scrollbar = ttk.Scrollbar(frame, orient='vertical', command=canvas.yview)
                    
                    canvas.configure(xscrollcommand=h_scrollbar.set, yscrollcommand=v_scrollbar.set)
                    
                    # Layout
                    canvas.grid(row=0, column=0, sticky='nsew')
                    h_scrollbar.grid(row=1, column=0, sticky='ew')
                    v_scrollbar.grid(row=0, column=1, sticky='ns')
                    
                    frame.grid_rowconfigure(0, weight=1)
                    frame.grid_columnconfigure(0, weight=1)
                    
                    # Convert PIL image to PhotoImage
                    photo = self.pil_to_photo(sheet)
                    
                    # Add to canvas
                    canvas.create_image(0, 0, anchor='nw', image=photo)
                    canvas.configure(scrollregion=canvas.bbox('all'))
                    
                    # Keep reference to prevent garbage collection
                    canvas.photo = photo
                    
                    # Info label
                    info_text = f"Frames: {len(frames)}, Size: {sprite_info['width']}x{sprite_info['height']}"
                    info_label = ttk.Label(frame, text=info_text)
                    info_label.grid(row=2, column=0, columnspan=2, pady=5)
        
        # Menu bar
        menubar = tk.Menu(root)
        root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open Sprite File...", command=lambda: self.open_sprite_file(notebook))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=root.quit)
        
        # Set window size
        root.geometry("800x600")
        
        return root
    
    def pil_to_photo(self, pil_image):
        """Convert PIL image to PhotoImage"""
        from PIL import ImageTk
        return ImageTk.PhotoImage(pil_image)
    
    def open_sprite_file(self, notebook):
        """Open a custom sprite file"""
        filename = filedialog.askopenfilename(
            title="Select sprite file",
            filetypes=[
                ("Grayscale sprites", "*.BIT.bin"),
                ("Color sprites", "*.COL.bin"),
                ("All files", "*.*")
            ]
        )
        
        if filename:
            # Try to determine sprite dimensions from filename
            base_name = os.path.basename(filename)
            parts = base_name.split('_')
            
            if len(parts) >= 3:
                try:
                    width = int(parts[-2])
                    height = int(parts[-1].split('.')[0])
                    
                    # Read sprite
                    if filename.endswith('.COL.bin'):
                        frames = self.read_color_sprite(filename)
                    else:
                        frames = self.read_grayscale_sprite(filename, width, height)
                    
                    if frames:
                        # Create sprite sheet
                        sheet = self.create_sprite_sheet(frames, base_name)
                        
                        if sheet:
                            # Save as image
                            save_path = filename.replace('.BIT.bin', '_sheet.png').replace('.COL.bin', '_sheet.png')
                            sheet.save(save_path)
                            print(f"Saved sprite sheet to: {save_path}")
                            
                except ValueError:
                    print(f"Could not parse dimensions from filename: {base_name}")

def main():
    # Change to the game directory if provided
    if len(sys.argv) > 1:
        game_dir = sys.argv[1]
        if os.path.exists(game_dir):
            os.chdir(game_dir)
            print(f"Working directory: {os.getcwd()}")
    
    # Create viewer
    viewer = SpriteViewer()
    
    # Check if sprite files exist
    missing_files = []
    for sprite in viewer.sprites:
        if not os.path.exists(sprite["file"]):
            missing_files.append(sprite["file"])
    
    if missing_files:
        print("Warning: Some sprite files not found:")
        for f in missing_files:
            print(f"  - {f}")
        print("\nPlease run this script from the ThumbCommander game directory")
        print("or provide the path as an argument: python sprite_viewer.py /path/to/game")
    
    # Create and run GUI
    root = viewer.create_window()
    root.mainloop()

if __name__ == "__main__":
    main()