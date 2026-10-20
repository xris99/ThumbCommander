# color_enhancements.py - ThumbyColor/PC-only enhancements for
# MarioKarts.
#
# MainGame.py calls apply(globals()), which binds the same names into
# that dict: the FXEngine (all SFX + the race music, opened once with
# fixed ids), the color SettingsMenu (vibration/volume items) and a
# settings-aware rumble wrapper. The module itself keeps no state -
# everything lives in the caller. Imported only on the color targets
# (the original Thumby never pays the RAM cost).

import json
from gc import collect
from time import sleep
from array import array

from thumby_engine.platform import (display, PC, IS_THUMBY_COLOR,
                                    buttonLB, buttonRB, buttonMENU,
                                    audio_stop, audio_set_loop,
                                    audio_set_volume,
                                    audio_set_end_callback,
                                    audio_clear_end_callback,
                                    audio_open_id, audio_play_id,
                                    audio_close_ids)
from thumbyHardware import reset

try:
    from micropython import const
except ImportError:
    const = lambda x: x


def apply(main_globals):
    """Bind SettingsMenu, rumble and FXEngine into the caller's
    globals dict - the names the base MainGame module expects."""
    print("Loading ThumbyColor enhancements...")
    original_rumble = main_globals['rumble']

    class FXEngine:
        SELECT = const(0)
        CONFIRM = const(1)
        COUNT = const(2)
        GO = const(3)
        PICKUP = const(4)
        BOOST = const(5)
        STAR = const(6)
        SPIN = const(7)
        HIT = const(8)
        BANANA = const(9)
        BOX = const(10)
        WIN = const(11)
        LOSE = const(12)
        MUSIC = const(13)

        def __init__(self, music="assets/music_race.ima"):
            # Open all sound files and keep the handles
            audio_open_id("assets/sfx_select.ima", self.SELECT)
            audio_open_id("assets/sfx_confirm.ima", self.CONFIRM)
            audio_open_id("assets/sfx_count.ima", self.COUNT)
            audio_open_id("assets/sfx_go.ima", self.GO)
            audio_open_id("assets/sfx_pickup.ima", self.PICKUP)
            audio_open_id("assets/sfx_boost.ima", self.BOOST)
            audio_open_id("assets/sfx_star.ima", self.STAR)
            audio_open_id("assets/sfx_spin.ima", self.SPIN)
            audio_open_id("assets/sfx_hit.ima", self.HIT)
            audio_open_id("assets/sfx_banana.ima", self.BANANA)
            audio_open_id("assets/sfx_box.ima", self.BOX)
            audio_open_id("assets/sfx_win.ima", self.WIN)
            audio_open_id("assets/sfx_lose.ima", self.LOSE)
            audio_open_id(music, self.MUSIC)
            self.play_music()

        def play_music(self):
            audio_clear_end_callback()
            audio_play_id(self.MUSIC)
            audio_set_loop(True)

        def play(self, fx: int):
            audio_set_loop(False)
            audio_set_end_callback(self.play_music)
            audio_play_id(fx)

        def __del__(self):
            # Runs from the GC (also at interpreter shutdown) - the audio
            # backend may already be gone, so never let this raise.
            try:
                audio_clear_end_callback()
                audio_stop()
                sleep(0.05)
                audio_close_ids()
            except BaseException:
                pass
            collect()

    # SettingsMenu extension - vibration/volume items
    class ThumbyColorSettingsMenu(main_globals['SettingsMenu']):
        vibration_enabled = True
        volume_level = 75

        def __init__(self):
            self.load_color_settings()
            super().__init__()

        @staticmethod
        def load_color_settings():
            try:
                with open("settings.json", "r") as f:
                    data = json.loads(f.read())
                    ThumbyColorSettingsMenu.vibration_enabled = data.get("vibration_enabled", True)
                    ThumbyColorSettingsMenu.volume_level = max(0, min(150, data.get("volume_level", 75)))
                    audio_set_volume(ThumbyColorSettingsMenu.volume_level)
            except:
                pass

        def get_menu_items(self):
            base = super().get_menu_items()
            return base[:-3] + [
                f"VIBRATION: {'ON' if ThumbyColorSettingsMenu.vibration_enabled else 'OFF'}",
                f"VOLUME: {ThumbyColorSettingsMenu.volume_level}%"
            ] + base[-3:]

        def handle_special_action(self, i):
            if i == 6:  # Vibration
                ThumbyColorSettingsMenu.vibration_enabled = not ThumbyColorSettingsMenu.vibration_enabled
                self.update_menu()
                if ThumbyColorSettingsMenu.vibration_enabled:
                    original_rumble(100)
                return True
            elif i == 7:  # Volume
                levels = [0, 25, 50, 75, 100, 125, 150]
                try:
                    current_index = levels.index(ThumbyColorSettingsMenu.volume_level)
                except ValueError:
                    current_index = 3
                ThumbyColorSettingsMenu.volume_level = levels[(current_index + 1) % len(levels)]
                audio_set_volume(ThumbyColorSettingsMenu.volume_level)
                self.update_menu()
                return True
            elif i == 8:  # Reset defaults
                main_globals['KEYMAPS'] = array('O', main_globals['DEFAULT_KEYS'])
                main_globals['rebuild_buttons']()
                ThumbyColorSettingsMenu.vibration_enabled = True
                ThumbyColorSettingsMenu.volume_level = 75
                audio_set_volume(ThumbyColorSettingsMenu.volume_level)
                self.update_menu()
                return True
            elif i == 9:  # Quit
                # Persist before the reboot, or the last adjustments
                # (volume/vibration) would be lost with the session.
                self.save_color_settings()
                reset()
                return True
            elif i == 10:  # Back
                main_globals['save_keymaps'](main_globals['KEYMAPS'])
                self.save_color_settings()
                return False
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

    ThumbyColorSettingsMenu.load_color_settings()
    print("ThumbyColor enhancements loaded successfully!")
    print(f"  Resolution: {PC.WIDTH}x{PC.HEIGHT}")
