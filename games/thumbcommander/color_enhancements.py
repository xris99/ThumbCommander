# color_enhancements.py - ThumbyColor/PC-only enhancements.
#
# Used to be exec()'d into MainGame's namespace; now MainGame calls
# apply(globals()), which binds the same names into that dict. The
# module itself keeps no state - everything lives in the caller.
# Imported only on the color targets (the original Thumby never
# pays the RAM cost).

import json
import gc
from array import array
from time import sleep, sleep_ms

from thumby_engine.platform import (display, PC, IS_THUMBY_COLOR,
                                    buttonLB, buttonRB, buttonMENU,
                                    audio_stop, audio_set_loop,
                                    audio_set_volume,
                                    audio_set_end_callback,
                                    audio_clear_end_callback,
                                    audio_open_id, audio_play_id,
                                    audio_close_ids)
from thumby_engine.util.fpmath import fpsin, fpcos

try:
    from micropython import const
except ImportError:
    const = lambda x: x

def apply(main_globals):
    """Bind SettingsMenu, rumble, FXEngine, draw_hull_status,
    draw_half_circle_energy and CampaignBackground into the
    caller's globals dict - the names the old exec()'d file made."""
    print("Loading ThumbyColor enhancements...")
    original_rumble = main_globals['rumble']

    def draw_half_circle_energy(display, x_center, y_center, radius, energy, max_energy=5):
        energy_fp = (energy << 16) // max_energy
        angle_span = 81 + ((431 * energy_fp) >> 16)
        start_angle = 512 - (angle_span >> 1)
        end_angle = 512 + (angle_span >> 1)
        if energy_fp < 32768:
            red = 31
            green = (energy_fp * 126) >> 16
        else:
            red = ((65536 - energy_fp) * 62) >> 16
            green = 63
        color = (red << 11) | (green << 5)
        for i in range(51):
            angle = start_angle + ((end_angle - start_angle) * i) // 50
            display.drawFilledRectangle(x_center + ((radius * fpsin(angle)) >> 16),
                                        y_center + ((radius * fpcos(angle)) >> 16), 2, 2, color)

    def draw_hull_status(display, lifes_left):
        # Lives indicator with icons
        display.drawText("HULL:", 5, 11, PC.LIGHTGRAY)
        for i in range(5):
            # Filled life icon
            display.drawFilledRectangle(35 + i*8, 11, 6, 6, PC.GREEN if i < lifes_left else PC.DARKGRAY)

    class CampaignBackground:
        def __init__(self):
            self.backgounrd = 'assets/camp_background_128_128.COL.bin'
            self.briefing = 'assets/mission_briefing_128_88.COL.bin'
            self.debrief = 'assets/mission_debrief_128_55.COL.bin'

        def run(self, num):
            if num == 0:
                display.draw_sprite_from_file(self.backgounrd)
            elif num == 1:
                display.draw_sprite_from_file(self.briefing, y=20)
            elif num == 2:
                display.draw_sprite_from_file(self.debrief, y=20)

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
            audio_open_id('assets/engine.ima', self.ENGINE)
            audio_open_id('assets/laser.ima', self.LASER)
            audio_open_id('assets/shield.ima', self.SHIELD)
            audio_open_id('assets/explode_as.ima', self.EXPLODE_AS)
            audio_open_id('assets/explode_sh.ima', self.EXPLODE_SH)
            audio_open_id('assets/afterburner.ima', self.AFTERBURNER)
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
            sleep_ms(50)
            audio_close_ids()
            gc.collect()

    # SettingsMenu extension - vibration/volume items
    class ThumbyColorSettingsMenu(main_globals['SettingsMenu']):
        vibration_enabled = True
        volume_level = 100

        def __init__(self):
            self.load_color_settings()
            super().__init__()

        @staticmethod
        def load_color_settings():
            try:
                with open("settings.json", "r") as f:
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
                main_globals['KEYMAPS'] = array('O', main_globals['DEFAULT_KEYS'])
                main_globals['SHIFT_REQUIRED'] = array('B', [False, False, False,
                                                             False, False, False,
                                                             True, True,
                                                             not IS_THUMBY_COLOR,
                                                             not IS_THUMBY_COLOR,
                                                             True])
                ThumbyColorSettingsMenu.vibration_enabled = True
                ThumbyColorSettingsMenu.volume_level = 75
                audio_set_volume(ThumbyColorSettingsMenu.volume_level)
                self.update_menu()
                sleep(0.3)
                return True
            elif i == 14:  # Back (moved due to new items)
                main_globals['save_keymaps'](main_globals['KEYMAPS'])
                self.save_color_settings()
                return False  # Exit
            return None  # Not handled

        def save_color_settings(self):
            try:
                with open("settings.json", "w") as f:
                    f.write(json.dumps({
                        "vibration_enabled": ThumbyColorSettingsMenu.vibration_enabled,
                        "volume_level": ThumbyColorSettingsMenu.volume_level
                    }))
            except:
                pass

    # Settings-aware rumble wrapper
    def rumble(duration):
        if ThumbyColorSettingsMenu.vibration_enabled:
            original_rumble(duration)

    main_globals['SettingsMenu'] = ThumbyColorSettingsMenu
    main_globals['rumble'] = rumble
    main_globals['FXEngine'] = FXEngine
    main_globals['draw_hull_status'] = draw_hull_status
    main_globals['draw_half_circle_energy'] = draw_half_circle_energy
    main_globals['CampaignBackground'] = CampaignBackground

    ThumbyColorSettingsMenu.load_color_settings()
    print("ThumbyColor enhancements loaded successfully!")
    print(f"  Resolution: {PC.WIDTH}x{PC.HEIGHT}")
