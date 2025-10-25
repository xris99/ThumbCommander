# color_enhancements.py - Color-specific enhancements loaded via exec() on ThumbyColor only
from random import randint
from platform_loader import audio_load, audio_play, audio_stop, audio_set_loop, audio_set_volume, audio_get_position, audio_set_end_callback, audio_clear_end_callback, audio_open_id, audio_play_id, audio_close_ids, buttonMENU
import gc

# Try to import time and add sleep_ms if needed
try:
    import time
    # Add sleep_ms if it doesn't exist (Python's time module doesn't have sleep_ms)
    if not hasattr(time, 'sleep_ms'):
        time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)
except:
    # Create a simple stub if time doesn't exist
    class MockTime:
        @staticmethod
        def sleep(s):
            pass
        @staticmethod
        def sleep_ms(ms):
            pass
    time = MockTime()

# Import game globals that we'll be modifying
from platform_constants import get_constants
PC = get_constants(True)  # Force ThumbyColor constants

print("Loading ThumbyColor enhancements...")

# Enhanced visual effects using full resolution
def draw_engine_trail(display, x, y, intensity):
    """Draw engine exhaust trail"""
    # Multiple layers for better effect
    trail_length = int(10 * intensity)
    
    for i in range(trail_length):
        # Fade color from white to blue to nothing
        fade = 1.0 - (i / trail_length)
        
        if fade > 0.7:
            color = display.WHITE
        elif fade > 0.4:
            color = display.LASER_BLUE
        else:
            color = 0x000F  # Very dim blue
        
        # Random spread for flame effect
        offset_x = randint(-2, 2)
        display.setPixel(x + offset_x, y + i, color)


# Store original methods
original_enemies_run = Enemies.run

# Enhanced enemy rendering
def enhanced_enemies_run(self, laser=[], mission_phase_complete=False):
    """Enhanced enemy rendering with color coding"""
    # Call original
    original_enemies_run(self, laser, mission_phase_complete)
    
    # Add additional effects
    for enemy in self.enemies:
        if enemy[6] != 0 and enemy[2] > 0:  # Not exploding and visible
            # Add engine glow for enemies
            mySprite = getSprite(enemy[2], enemy[6])
            x = project_a(enemy[0], enemy[2], CENTER_X, mySprite.scaledWidth)
            y = project_a(enemy[1], enemy[2], CENTER_Y, mySprite.scaledHeight)
            
            if 0 <= x < PC.WIDTH and 0 <= y < PC.HEIGHT:
                # Enemy engine glow (purple)
                glow_x = x + mySprite.scaledWidth // 2
                glow_y = y + mySprite.scaledHeight - 5
                display.drawFilledRectangle(glow_x - 2, glow_y, 4, 3, display.ENEMY_PURPLE)

def draw_half_circle_energy(display, x_center, y_center, radius, energy, max_energy=5):
    from math import pi, sin, cos
    full_angle_rad = pi  # 180 degrees

    min_angle = 0.5  # Minimal visible arc in radians for 0 energy
    angle_span = min_angle + (full_angle_rad - min_angle) * (energy / max_energy)

    start_angle = pi - angle_span / 2
    end_angle = pi + angle_span / 2

    t = energy / max_energy  # Interpolation factor for color
    if t < 0.5:
        red = 31
        green = int(2 * t * 63)
    else:
        red = int((1 - 2 * (t - 0.5)) * 31)
        green = 63
    color = (red << 11) | (green << 5)
  
    for i in range(51):
        angle = start_angle + (end_angle - start_angle) * i / 50
        x = int(x_center + radius * sin(angle))
        y = int(y_center + radius * cos(angle)) 
        display.drawFilledRectangle(x, y,2,2, color)  # Draw a pixel; adjust color if needed

def draw_hull_status(display, lifes_left):
    # Lives indicator with icons
    display.drawText("HULL:", 5, 10, display.LIGHTGRAY)
    for i in range(5):
        # Filled life icon
        display.drawFilledRectangle(35 + i*8, 10, 6, 6, PC.GREEN if i < lifes_left else PC.DARKGRAY)
      
class CampaignBackground:
    def __init__(self):
        self.backgounrd = loc+"camp_background_128_128.COL.bin"
        self.briefing = loc+"mission_briefing_128_88.COL.bin"
        self.debrief = loc+"mission_debrief_128_55.COL.bin"
    def run(self, num):
        if num == 0:
            display.draw_fullwidth_sprite(self.backgounrd)
        elif num == 1:
            display.draw_fullwidth_sprite(self.briefing, 20)
        elif num == 2:
          display.draw_fullwidth_sprite(self.debrief, 20)
    def __del__(self):
        del self.backgounrd

class FXEngine:
    ENGINE = const(0)
    LASER = const(1)
    SHIELD = const(2)
    EXPLODE_AS = const(3)
    EXPLODE_SH = const(4)
    AFTERBURNER = const(5)
    
    def __init__(self):
        # Open all sound files and keep handles
        audio_open_id(loc+"engine.ima", self.ENGINE)
        audio_open_id(loc+"laser.ima", self.LASER)
        audio_open_id(loc+"shield.ima", self.SHIELD)
        audio_open_id(loc+"explode_as.ima", self.EXPLODE_AS)
        audio_open_id(loc+"explode_sh.ima", self.EXPLODE_SH)
        audio_open_id(loc+"afterburner.ima", self.AFTERBURNER)
        self._engine()
    
    def _engine(self):
        audio_clear_end_callback()
        audio_play_id(self.ENGINE)
        audio_set_loop(True)
    
    def play(self, fx:int):
        audio_set_loop(False)
        audio_set_end_callback(self._engine)
        audio_play_id(fx)
    
    def __del__(self):
        audio_stop()
        time.sleep_ms(50)
        audio_close_ids()
        gc.collect()

# ThumbyColor SettingsMenu - Method overrides only
class ThumbyColorSettingsMenu(SettingsMenu):
    vibration_enabled = True
    volume_level = 100
  
    def __init__(self):
        self.load_color_settings()
        super().__init__()
      
    @staticmethod
    def load_color_settings():
        try:
            with open(loc + "settings.json", "r") as f:
                data = json.loads(f.read())
                ThumbyColorSettingsMenu.vibration_enabled = data.get("vibration_enabled", True)
                ThumbyColorSettingsMenu.volume_level = max(0, min(100, data.get("volume_level", 75)))
                audio_set_volume(ThumbyColorSettingsMenu.volume_level)
        except:
            pass
    
    def get_menu_items(self):
        base = super().get_menu_items()
        return base[:-2] + [
            f"VIBRATION: {'ON' if ThumbyColorSettingsMenu.vibration_enabled else 'OFF'}", 
            f"VOLUME: {ThumbyColorSettingsMenu.volume_level}%"
        ] + base[-2:]
    
    def get_pressed_key(self):
        if buttonLB.pressed(): return 'LB'
        elif buttonRB.pressed(): return 'RB'
        elif buttonMENU.pressed(): return 'MENU'
        else: return super().get_pressed_key()
    
    def handle_special_action(self, i):
        global KEYMAPS
        if i == 11:  # Vibration
            ThumbyColorSettingsMenu.vibration_enabled = not ThumbyColorSettingsMenu.vibration_enabled
            self.update_menu()
            if ThumbyColorSettingsMenu.vibration_enabled: 
                rumble(100)
            sleep(0.2)
            return True
        elif i == 12:  # Volume
            volume_levels = [0, 25, 50, 75, 100, 125, 150]
            try:
                current_index = volume_levels.index(ThumbyColorSettingsMenu.volume_level)
                next_index = (current_index + 1) % len(volume_levels)
            except ValueError:
                # Current volume not in list, start from 25%
                next_index = 1
            ThumbyColorSettingsMenu.volume_level = volume_levels[next_index]
            audio_set_volume(ThumbyColorSettingsMenu.volume_level)
            self.update_menu()
            sleep(0.2)
            return True
        elif i == 13:  # Reset defaults (moved due to new items)
            KEYMAPS = array('O', DEFAULT_KEYS)
            SHIFT_REQUIRED = array('B', [False,False,False,False,False,False,True,True,not IS_THUMBY_COLOR,not IS_THUMBY_COLOR,True])
            ThumbyColorSettingsMenu.vibration_enabled = True
            ThumbyColorSettingsMenu.volume_level = 75
            audio_set_volume(ThumbyColorSettingsMenu.volume_level)
            self.update_menu()
            sleep(0.3)
            return True
        elif i == 14:  # Back (moved due to new items)
            save_keymaps(KEYMAPS)
            self.save_color_settings()
            return False  # Exit
        return None  # Not handled
    
    def save_color_settings(self):
        try:
            with open(loc + "settings.json", "w") as f:
                f.write(json.dumps({
                    "vibration_enabled": ThumbyColorSettingsMenu.vibration_enabled, 
                    "volume_level": ThumbyColorSettingsMenu.volume_level
                }))
        except:
            pass

# Override the global SettingsMenu class
SettingsMenu = ThumbyColorSettingsMenu

# Enhanced rumble function that respects vibration settings
original_rumble = rumble

def rumble(duration):
    """Settings-aware rumble wrapper"""
    if SettingsMenu.vibration_enabled: original_rumble(duration)
      
ThumbyColorSettingsMenu.load_color_settings()

print("ThumbyColor enhancements loaded successfully!")
print(f"  Resolution: {PC.WIDTH}x{PC.HEIGHT}")