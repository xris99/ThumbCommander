#!/usr/bin/env python3
"""
run_game.py - Run full ThumbCommander game with pygame
"""
import sys
import os

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock micropython module before any imports
def _decorator_passthrough(func):
    """Pass-through decorator for @micropython.native and @micropython.viper"""
    return func

class MockMicropython:
    native = staticmethod(_decorator_passthrough)
    viper = staticmethod(_decorator_passthrough)

    @staticmethod
    def const(x):
        return int(x)

_micropython_mock = MockMicropython()
sys.modules['micropython'] = _micropython_mock

# Also add to builtins so it's available globally without import
import builtins
builtins.micropython = _micropython_mock
builtins.const = _micropython_mock.const  # Make const available globally

# Mock thumbyHardware module
class MockThumbyHardware:
    swL = 0
    swR = 1
    swU = 2
    swD = 3
    swA = 4
    swB = 5

    @staticmethod
    def reset():
        print("Reset called - exiting")
        sys.exit(0)

sys.modules['thumbyHardware'] = MockThumbyHardware()

# Mock thumbyButton module before platform_loader imports it
class MockButtonClass:
    def __init__(self, pin):
        self.pin = pin
        self._pressed = False
        self._just_pressed = False

    def pressed(self):
        return self._pressed

    def justPressed(self):
        result = self._just_pressed
        self._just_pressed = False
        return result

sys.modules['thumbyButton'] = type('Module', (), {'ButtonClass': MockButtonClass})()

# Mock machine module
class MockMachine:
    @staticmethod
    def freq(f=None):
        if f:
            pass  # Ignore frequency setting
        return 200_000_000

sys.modules['machine'] = MockMachine()

# Mock time/utime modules
import time as real_time

class MockTime:
    sleep = staticmethod(real_time.sleep)

    @staticmethod
    def sleep_ms(ms):
        real_time.sleep(ms / 1000.0)

    @staticmethod
    def ticks_ms():
        return int(real_time.time() * 1000)

    @staticmethod
    def ticks_us():
        return int(real_time.time() * 1000000)

    @staticmethod
    def ticks_diff(a, b):
        return a - b

sys.modules['utime'] = MockTime()

# Mock gc module
import gc as real_gc

class MockGC:
    collect = staticmethod(real_gc.collect)

    @staticmethod
    def mem_free():
        return 100000  # Pretend we have plenty of memory

sys.modules['gc'] = MockGC()

# Mock engine module (ThumbyColor uses this for freq)
class MockEngine:
    @staticmethod
    def freq(f=None):
        if f:
            pass  # Ignore frequency setting
        return 300_000_000

sys.modules['engine'] = MockEngine()

# Import pygame platform wrapper first
import pygame_platform

# Mock framebuf module - will use pygame_platform.PygameFrameBuffer
sys.modules['framebuf'] = type('Module', (), {
    'FrameBuffer': pygame_platform.PygameFrameBuffer,
    'RGB565': 1,
    'GS8': 2
})()

# Inject pygame platform into globals so imports work
sys.modules['engine_io'] = type('Module', (), {
    'A': pygame_platform.BUTTON_MAPPINGS['A'],
    'B': pygame_platform.BUTTON_MAPPINGS['B'],
    'UP': pygame_platform.BUTTON_MAPPINGS['UP'],
    'DOWN': pygame_platform.BUTTON_MAPPINGS['DOWN'],
    'LEFT': pygame_platform.BUTTON_MAPPINGS['LEFT'],
    'RIGHT': pygame_platform.BUTTON_MAPPINGS['RIGHT'],
    'LB': pygame_platform.BUTTON_MAPPINGS['LB'],
    'RB': pygame_platform.BUTTON_MAPPINGS['RB'],
    'MENU': pygame_platform.BUTTON_MAPPINGS['MENU']
})()

# Mock ThumbyColor native modules
sys.modules['thumbycolor_native'] = type('Module', (), {
    'ColorDisplay': pygame_platform.PygameDisplay,
    'ColorSprite': pygame_platform.PygameSprite,
    '_rumble': pygame_platform.rumble
})()

# Mock audio module - use functions not bound methods
class AudioModule:
    @staticmethod
    def load(filename):
        pass

    @staticmethod
    def play():
        pass

    @staticmethod
    def stop():
        pass

    @staticmethod
    def set_volume(volume):
        pass

    @staticmethod
    def set_loop(loop, start=0, end=0):
        pass

    @staticmethod
    def get_position():
        return 0

    @staticmethod
    def set_end_callback(callback):
        pass

    @staticmethod
    def clear_end_callback():
        pass

    @staticmethod
    def open_id(filename, id):
        pass

    @staticmethod
    def play_id(id):
        pass

    @staticmethod
    def close_ids():
        pass

sys.modules['audio'] = AudioModule()

# Mock cutscene utils
def mock_init_cutscene_utils(*args):
    pass

sys.modules['cutscene_utils'] = type('Module', (), {
    'init_cutscene_utils': mock_init_cutscene_utils,
    'play_cutscene_animation': pygame_platform.play_cutscene_animation,
    'create_cancel_callback': pygame_platform.create_cancel_callback
})()

# Mock Intro module
sys.modules['Intro'] = type('Module', (), {
    '__init__': lambda self: None,
    'start': lambda: None,
    'finish': lambda: None
})()

print("=" * 60)
print("ThumbCommander - Full Game Mode")
print("=" * 60)
print("Controls (German QWERTZ keyboard compatible):")
print("  Arrow Keys  - Movement")
print("  Y           - Fire (A button)")
print("  X           - B button")
print("  Q/W         - LB/RB (target cycling)")
print("  ESC         - Menu")
print("=" * 60)
print()
print("Loading game...")

# Patch platform_loader to force ThumbyColor detection
import platform_loader
platform_loader.IS_THUMBY_COLOR = True
platform_loader.display = pygame_platform.display
platform_loader.Sprite = pygame_platform.Sprite
platform_loader.buttonA = pygame_platform.buttonA
platform_loader.buttonB = pygame_platform.buttonB
platform_loader.buttonU = pygame_platform.buttonU
platform_loader.buttonD = pygame_platform.buttonD
platform_loader.buttonL = pygame_platform.buttonL
platform_loader.buttonR = pygame_platform.buttonR
platform_loader.buttonLB = pygame_platform.buttonLB
platform_loader.buttonRB = pygame_platform.buttonRB
platform_loader.buttonMENU = pygame_platform.buttonMENU
platform_loader.rumble = pygame_platform.rumble
platform_loader.play_cutscene_animation = pygame_platform.play_cutscene_animation
platform_loader.create_cancel_callback = pygame_platform.create_cancel_callback
platform_loader.audio_load = pygame_platform.audio_load
platform_loader.audio_play = pygame_platform.audio_play
platform_loader.audio_stop = pygame_platform.audio_stop
platform_loader.audio_set_volume = pygame_platform.audio_set_volume
platform_loader.audio_set_loop = pygame_platform.audio_set_loop
platform_loader.audio_get_position = pygame_platform.audio_get_position

# Override input functions to update button states
original_inputJustPressed = platform_loader.inputJustPressed
original_dpadPressed = platform_loader.dpadPressed

def wrapped_inputJustPressed():
    pygame_platform.update_buttons()
    return original_inputJustPressed()

def wrapped_dpadPressed():
    pygame_platform.update_buttons()
    return original_dpadPressed()

platform_loader.inputJustPressed = wrapped_inputJustPressed
platform_loader.dpadPressed = wrapped_dpadPressed

print("Starting ThumbCommander...")
print()

# Import and run the game - this will start the main game loop
try:
    import ThumbCommander
except KeyboardInterrupt:
    print("\nGame interrupted by user")
except Exception as e:
    print(f"\nError running game: {e}")
    import traceback
    traceback.print_exc()

print("\nGame ended. Thanks for playing!")
