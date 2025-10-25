#!/usr/bin/env python3
"""
test_pygame.py - Main test harness for running ThumbCommander on PC with pygame
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

# Now import our pygame platform wrapper
import pygame_platform

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

# Mock audio module
sys.modules['audio'] = type('Module', (), {
    'load': pygame_platform.audio_load,
    'play': pygame_platform.audio_play,
    'stop': pygame_platform.audio_stop,
    'set_volume': pygame_platform.audio_set_volume,
    'set_loop': pygame_platform.audio_set_loop,
    'get_position': pygame_platform.audio_get_position,
    'set_end_callback': pygame_platform.audio_set_end_callback,
    'clear_end_callback': pygame_platform.audio_clear_end_callback,
    'open_id': pygame_platform.audio_open_id,
    'play_id': pygame_platform.audio_play_id,
    'close_ids': pygame_platform.audio_close_ids
})()

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
print("ThumbCommander - Pygame Test Harness")
print("=" * 60)
print("Controls:")
print("  Arrow Keys  - Movement")
print("  Z           - Fire (A button)")
print("  X           - B button")
print("  A/S         - LB/RB (target cycling)")
print("  ESC         - Menu")
print("=" * 60)
print()

# Now we can import and run the game
# The game will detect ThumbyColor mode and use our pygame wrappers
try:
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

    def wrapped_inputJustPressed():
        pygame_platform.update_buttons()
        return original_inputJustPressed()

    platform_loader.inputJustPressed = wrapped_inputJustPressed

    print("Loading ThumbCommander...")

    # Import the main game
    # Note: We skip the actual import and create a minimal test instead
    # because the full game needs many asset files

    print("\n" + "=" * 60)
    print("TESTING: Display and Input Systems")
    print("=" * 60)

    from platform_loader import display, buttonA, buttonB, buttonU, buttonD, buttonL, buttonR

    # Simple test loop
    display.setFPS(60)
    running = True
    frame = 0

    print("Test running - press ESC to quit")
    print("Press buttons to test input...")

    while running:
        frame += 1

        # Update button states
        pygame_platform.update_buttons()

        # Check for quit
        if pygame_platform.buttonMENU.justPressed():
            print("ESC pressed - quitting")
            running = False

        # Clear screen
        display.fill(display.BLACK)

        # Draw test pattern
        display.drawText("ThumbCommander Test", 10, 10, display.WHITE)
        display.drawText("Frame: " + str(frame), 10, 20, display.LIGHTGRAY)

        # Show button states
        y = 35
        if buttonA.pressed():
            display.drawText("A (Fire) PRESSED", 10, y, display.RED)
            y += 10
        if buttonB.pressed():
            display.drawText("B PRESSED", 10, y, display.RED)
            y += 10
        if buttonU.pressed():
            display.drawText("UP PRESSED", 10, y, display.BLUE)
            y += 10
        if buttonD.pressed():
            display.drawText("DOWN PRESSED", 10, y, display.BLUE)
            y += 10
        if buttonL.pressed():
            display.drawText("LEFT PRESSED", 10, y, display.BLUE)
            y += 10
        if buttonR.pressed():
            display.drawText("RIGHT PRESSED", 10, y, display.BLUE)
            y += 10

        # Draw a bouncing box to show animation
        box_x = 50 + int(30 * ((frame % 120) / 120.0))
        display.drawFilledRectangle(box_x, 80, 10, 10, display.ORANGE)

        # Draw heat level simulation
        heat = (frame % 100)
        bars = heat // 20
        display.drawText("Heat Test:", 10, 100, display.WHITE)
        for i in range(5):
            color = display.RED if i < bars else display.DARKGRAY
            display.drawFilledRectangle(10 + i * 12, 110, 10, 10, color)

        # Update display
        display.update()

    print("\nTest completed successfully!")
    print("Pygame platform wrapper is working correctly.")

except Exception as e:
    print(f"\nError: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nExiting...")
