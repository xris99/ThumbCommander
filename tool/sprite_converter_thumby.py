#!/usr/bin/env python3
"""
Sprite Converter for ThumbCommander
Converts embedded bytearray sprites to .bin files and updates the code to load them.
"""

import os
import re

# Define the embedded sprites with their data
sprites = {
    "cockpit_66_18": {
        "width": 66,
        "height": 18,
        "BIT": bytearray([255,252,255,253,253,255,251,251,251,247,247,239,239,239,223,31,159,31,31,31,35,29,61,29,63,31,63,157,61,29,35,31,31,31,31,31,63,63,31,31,63,31,31,63,31,63,31,31,31,159,223,223,223,239,239,239,247,247,251,251,251,253,253,255,252,255,
               255,255,255,255,255,255,255,127,127,63,63,63,159,15,11,6,0,0,0,0,0,0,0,0,0,0,0,86,0,0,0,0,0,0,0,0,0,0,0,0,8,20,8,0,0,0,0,0,0,0,2,11,15,159,31,63,63,127,127,255,255,255,255,255,255,255,
               3,3,3,1,1,0,0,0,0,0,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,3,3,3,3,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,0,0,0,0,0,1,1,3,3,3]),
        "SHD": bytearray([1,3,3,2,2,6,4,4,12,12,24,24,16,48,48,96,160,96,160,224,124,98,226,226,226,226,226,226,226,98,124,96,96,96,96,96,96,224,224,224,224,224,224,224,224,224,224,160,96,224,96,96,48,48,16,24,24,12,12,4,6,6,2,3,3,1,
               0,0,0,0,0,0,128,128,192,192,224,96,144,112,220,247,188,223,239,255,127,119,127,127,119,127,127,119,127,128,128,128,128,128,128,128,128,127,127,66,74,87,74,66,127,127,225,225,255,253,247,220,112,144,96,224,192,192,128,128,0,0,0,0,0,0,
               0,2,2,2,3,3,3,3,3,1,0,2,1,3,0,0,0,0,0,3,0,0,0,0,0,0,0,0,0,3,3,3,3,3,3,3,3,0,0,0,0,0,0,0,0,0,3,0,0,0,0,0,3,1,2,0,1,3,3,3,3,3,3,2,2,0])
    },
    "target_7_7": {
        "width": 7,
        "height": 7,
        "BIT": bytearray([65,34,0,0,0,34,65]),
        "SHD": bytearray([0,0,0,0,0,0,0])
    },
    "targetactive_7_7": {
        "width": 7,
        "height": 7,
        "BIT": bytearray([127,99,65,65,65,99,127]),
        "SHD": bytearray([62,65,65,65,65,65,62])
    },
    "radar_15_15": {
        "width": 15,
        "height": 15,
        "BIT": bytearray([192,152,132,130,130,128,129,255,129,128,130,130,132,152,192,
               1,4,16,32,32,0,64,127,64,0,32,32,16,12,1]),
        "SHD": bytearray([192,152,132,130,130,128,129,255,129,128,130,130,132,152,192,
               1,4,16,32,32,0,64,127,64,0,32,32,16,12,1])
    },
    "shield_70_70": {
        "width": 70,
        "height": 70,
        "BIT": bytearray([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,192,224,224,32,48,112,112,24,8,8,24,56,24,24,24,24,24,24,24,56,120,112,240,240,224,224,224,192,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,128,192,224,240,88,4,2,3,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,8,13,15,31,31,126,222,252,248,240,224,192,128,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,192,240,60,7,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,7,15,95,255,255,255,252,240,192,0,0,0,0,0,
               0,0,0,240,255,63,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,15,255,255,255,255,255,240,0,0,0,
               0,0,0,255,243,17,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,255,255,255,255,255,255,0,0,0,
               0,0,0,3,24,200,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,224,252,255,255,255,255,63,3,0,0,0,
               0,0,0,0,0,0,3,14,14,94,232,32,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,32,96,224,224,250,255,127,31,15,3,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,0,0,1,2,6,15,30,24,32,96,96,224,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,128,128,192,224,208,240,224,224,224,112,112,56,62,30,15,7,3,1,0,0,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,3,3,3,6,4,4,4,6,6,6,6,6,7,7,7,7,7,3,3,3,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]),
        "SHD": bytearray([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,192,224,224,32,48,112,112,24,8,8,24,56,8,24,16,24,24,24,24,48,112,96,240,240,192,192,192,128,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,0,192,224,240,88,4,2,3,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,8,13,15,31,31,110,204,128,0,0,0,0,128,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,192,224,60,7,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,7,14,94,255,254,247,32,0,0,0,0,0,0,0,
               0,0,0,240,255,63,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,15,255,252,0,0,1,0,0,0,0,
               0,0,0,191,243,17,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2,0,253,196,0,0,0,0,0,0,0,
               0,0,0,3,24,200,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,224,252,255,79,0,0,0,0,0,0,0,
               0,0,0,0,0,0,3,14,14,94,232,32,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,32,96,224,224,58,31,29,23,0,0,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,0,0,1,2,6,15,30,24,32,96,96,224,192,128,128,0,0,0,0,0,0,0,0,0,0,0,0,0,0,128,128,192,128,128,192,224,208,240,224,224,224,112,112,56,46,14,15,7,3,1,0,0,0,0,0,0,0,0,0,0,0,
               0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,3,3,3,6,4,4,4,6,6,6,6,6,7,7,7,3,1,1,3,2,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0])
    }
}

def save_sprite_files(sprites, output_dir="Games/ThumbCommander"):
    """Save sprite bytearrays as .bin files"""
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    for sprite_name, sprite_data in sprites.items():
        # Save BIT data
        bit_filename = os.path.join(output_dir, f"{sprite_name}.BIT.bin")
        with open(bit_filename, 'wb') as f:
            f.write(sprite_data["BIT"])
        print(f"Created: {bit_filename} ({len(sprite_data['BIT'])} bytes)")
        
        # Save SHD data
        shd_filename = os.path.join(output_dir, f"{sprite_name}.SHD.bin")
        with open(shd_filename, 'wb') as f:
            f.write(sprite_data["SHD"])
        print(f"Created: {shd_filename} ({len(sprite_data['SHD'])} bytes)")

def generate_modified_code():
    """Generate the modified Ship class initialization code"""
    
    modified_code = '''
class Ship:
    def __init__(self):
        # Platform-specific cockpit sprite
        if IS_THUMBY_COLOR:
            # Load color versions
            self.cockpit_sprite = create_sprite(118, 53, loc+"cockpit_118_53.COL.bin", SHIP_X, SHIP_Y, 0)
            self.cockpit_top_sprite = create_sprite(118, 8, loc+"cockpit_top_118_8.COL.bin", SHIP_X, 0, 0)
            self.stick_left_sprite = create_sprite(28, 16, loc+"stick_left_28_16.COL.bin", SHIP_X+44, SHIP_Y+37, 0)
            self.stick_right_sprite = create_sprite(28, 16, loc+"stick_right_28_16.COL.bin", SHIP_X+46, SHIP_Y+37, 0)
            self.stick_back_sprite = create_sprite(28, 16, loc+"stick_back_28_16.COL.bin", SHIP_X+45, SHIP_Y+38, 0)
            self.stick_forward_sprite = create_sprite(28, 16, loc+"stick_forward_28_16.COL.bin", SHIP_X+45, SHIP_Y+36, 0)
            self.target_sprite = create_sprite(24, 24, loc+"target_24_24.COL.bin", CENTER_X-12, CENTER_Y-12, 0)
            self.target_active_sprite = create_sprite(24, 24, loc+"targetactive_24_24.COL.bin", CENTER_X-12, CENTER_Y-12, 0)
            self.radar_sprite = create_sprite(24, 24, loc+"radar_24_24.COL.bin", SHIP_X + PC.RADAR_X, SHIP_Y + PC.RADAR_Y, 0)
            self.radar_frame = 0
            self.radar_framecount = self.radar_sprite.frameCount - 1
            self.fx = FXEngine()
        else:
            # Load grayscale sprites from files
            self.cockpit_sprite = Sprite(66, 18, (loc+"cockpit_66_18.BIT.bin", loc+"cockpit_66_18.SHD.bin"), SHIP_X, SHIP_Y, 1)
            self.target_sprite = Sprite(7, 7, (loc+"target_7_7.BIT.bin", loc+"target_7_7.SHD.bin"), CENTER_X-3, CENTER_Y-3, 0)
            self.target_active_sprite = Sprite(7, 7, (loc+"targetactive_7_7.BIT.bin", loc+"targetactive_7_7.SHD.bin"), CENTER_X-3, CENTER_Y-3, 0)
            self.radar_sprite = Sprite(15, 15, (loc+"radar_15_15.BIT.bin", loc+"radar_15_15.SHD.bin"), PC.RADAR_X, PC.RADAR_Y, 0)
            self.fx = None
        
        self.laser = []
        self.fire_time = 0
        self.laser_energy = 5
        self.last_time = 0
        self.afterburner_time = 0
        display.setFont(PC.FONT_FILE, PC.FONT_WIDTH, PC.FONT_HEIGHT, PC.FONT_SPACE)

# Also update the Enemies class for shield sprite:
class Enemies:
    def __init__(self, num=1):
        enemies = array('O', [None] * num)
        for i in range(num):
            enemies[i] = self.new_enemy()
        
        # Create shield sprite with platform awareness
        if IS_THUMBY_COLOR:
            self.shieldSprite = create_sprite(70, 70, loc+"shield_70_70.COL.bin", 0, 0, 0)
        else:
            self.shieldSprite = Sprite(70, 70, (loc+"shield_70_70.BIT.bin", loc+"shield_70_70.SHD.bin"), 0, 0, 0)
        
        self.enemies = enemies
        self.last_time = 0
'''
    
    return modified_code

def main():
    print("ThumbCommander Sprite Converter")
    print("=" * 40)
    
    # Save sprite files
    print("\nSaving sprite files...")
    save_sprite_files(sprites)
    
    # Print instructions
    print("\n" + "=" * 40)
    print("CONVERSION COMPLETE!")
    print("\nFiles created in 'Games/ThumbCommander/' directory:")
    print("- cockpit_66_18.BIT.bin / cockpit_66_18.SHD.bin")
    print("- target_7_7.BIT.bin / target_7_7.SHD.bin")
    print("- targetactive_7_7.BIT.bin / targetactive_7_7.SHD.bin")
    print("- radar_15_15.BIT.bin / radar_15_15.SHD.bin")
    print("- shield_70_70.BIT.bin / shield_70_70.SHD.bin")
    
    print("\n" + "=" * 40)
    print("CODE MODIFICATIONS NEEDED:")
    print("\n1. Remove the embedded bytearray definitions from ThumbCommander.py")
    print("   (lines with cockpit, cockpitSHD, target, targetSHD, etc.)")
    
    print("\n2. Update the Ship and Enemies class __init__ methods to load from files")
    print("   (The modified code has been printed above)")
    
    print("\n3. Copy all .bin files to your Thumby's /Games/ThumbCommander/ directory")
    
    # Optionally save the modified code snippet
    with open("modified_ship_init.txt", "w") as f:
        f.write(generate_modified_code())
    print("\nModified code snippet saved to: modified_ship_init.txt")

if __name__ == "__main__":
    main()
