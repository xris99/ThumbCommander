# platform_loader.py - Loads appropriate platform modules
import sys
import gc
import builtins

# Add const to builtins for PC mode (MicroPython has it as builtin)
if not hasattr(builtins, 'const'):
    builtins.const = lambda x: x

# Import micropython module (our stub on PC, real module on hardware)
import micropython
# Make it available as builtin so code can use micropython.native without importing
builtins.micropython = micropython

# Add gc.mem_free stub for PC mode
if not hasattr(gc, 'mem_free'):
    gc.mem_free = lambda: 999999

# Platform detection
IS_THUMBY_COLOR = False
IS_PC = False

# Try to import ThumbyColor hardware
try:
    import engine_io
    IS_THUMBY_COLOR = True
    from thumbyButton import ButtonClass as HardwareButtonClass
except ImportError:
    try:
        # Try original Thumby
        from thumbyHardware import swL, swR, swU, swD, swA, swB
        from thumbyButton import ButtonClass as HardwareButtonClass
    except ImportError:
        # Running on PC
        IS_PC = True
        IS_THUMBY_COLOR = True  # Pretend to be ThumbyColor for game logic
        print("PC mode detected - using color_native")

# Get platform constants
from platform_constants import get_constants
PC = get_constants(IS_THUMBY_COLOR)

# Audio stubs (will be replaced with real functions on hardware if available)
def _audio_stub(*args, **kwargs):
    """Stub for audio functions on PC"""
    pass

audio_load = _audio_stub
audio_play = _audio_stub
audio_stop = _audio_stub
audio_set_volume = _audio_stub
audio_set_loop = _audio_stub
audio_get_position = lambda: 0  # Return 0 for position
audio_set_end_callback = _audio_stub
audio_clear_end_callback = _audio_stub
audio_open_id = _audio_stub
audio_play_id = _audio_stub
audio_close_ids = _audio_stub

# Import display and sprite classes from color_native (works for both PC and hardware)
from color_native import ColorDisplay, ColorSprite, _rumble
display = ColorDisplay()
Sprite = ColorSprite
rumble = _rumble

# Create buttons
if IS_PC:
    # PC mode - color_native provides ButtonClass
    from color_native import ButtonClass
    import pygame

    # Map keyboard to buttons (German keyboard layout: Z=Y, Y=Z)
    buttonU = ButtonClass(pygame.K_UP)
    buttonD = ButtonClass(pygame.K_DOWN)
    buttonL = ButtonClass(pygame.K_LEFT)
    buttonR = ButtonClass(pygame.K_RIGHT)
    buttonA = ButtonClass(pygame.K_z)       # Z key (Y on German keyboard)
    buttonB = ButtonClass(pygame.K_x)       # X key
    buttonLB = ButtonClass(pygame.K_q)      # Q key
    buttonRB = ButtonClass(pygame.K_w)      # W key
    buttonMENU = ButtonClass(pygame.K_ESCAPE)  # ESC key

    # Register buttons with display for automatic updates
    display.register_button(buttonU)
    display.register_button(buttonD)
    display.register_button(buttonL)
    display.register_button(buttonR)
    display.register_button(buttonA)
    display.register_button(buttonB)
    display.register_button(buttonLB)
    display.register_button(buttonRB)
    display.register_button(buttonMENU)

    print("PC mode initialized successfully!")

elif IS_THUMBY_COLOR:
    # ThumbyColor hardware
    buttonA = HardwareButtonClass(engine_io.A)
    buttonB = HardwareButtonClass(engine_io.B)
    buttonU = HardwareButtonClass(engine_io.UP)
    buttonD = HardwareButtonClass(engine_io.DOWN)
    buttonL = HardwareButtonClass(engine_io.LEFT)
    buttonR = HardwareButtonClass(engine_io.RIGHT)
    buttonLB = HardwareButtonClass(engine_io.LB)
    buttonRB = HardwareButtonClass(engine_io.RB)
    buttonMENU = HardwareButtonClass(engine_io.MENU)

    print(f"ThumbyColor display initialized. Free memory: {gc.mem_free()}")
else:
    # Original Thumby
    buttonA = HardwareButtonClass(swA)
    buttonB = HardwareButtonClass(swB)
    buttonU = HardwareButtonClass(swU)
    buttonD = HardwareButtonClass(swD)
    buttonL = HardwareButtonClass(swL)
    buttonR = HardwareButtonClass(swR)
    buttonLB = buttonL
    buttonRB = buttonR
    buttonMENU = buttonB

# Import cutscene utilities
try:
    from cutscene_utils import init_cutscene_utils, play_cutscene_animation as _play_cutscene, create_cancel_callback as _create_cancel

    if IS_PC:
        # PC mode - no audio
        init_cutscene_utils(display, PC, None, None, None, buttonMENU)
        print("PC mode: Cutscene support initialized (audio disabled)")
    else:
        # Hardware - try to import audio
        try:
            from audio import (load, play, stop, set_volume, set_loop, get_position,
                             set_end_callback, clear_end_callback, open_id, play_id, close_ids)
            audio_load = load
            audio_play = play
            audio_stop = stop
            audio_set_volume = set_volume
            audio_set_loop = set_loop
            audio_get_position = get_position
            audio_set_end_callback = set_end_callback
            audio_clear_end_callback = clear_end_callback
            audio_open_id = open_id
            audio_play_id = play_id
            audio_close_ids = close_ids
            init_cutscene_utils(display, PC, audio_load, audio_play, audio_stop, buttonMENU)
            print(f"Audio and cutscenes initialized. Free memory: {gc.mem_free()}")
        except ImportError as e:
            init_cutscene_utils(display, PC, None, None, None, buttonMENU)
            print(f"Cutscenes initialized without audio: {e}")

    play_cutscene_animation = _play_cutscene
    create_cancel_callback = _create_cancel
except ImportError as e:
    print(f"Warning: Could not import cutscene_utils: {e}")
    play_cutscene_animation = None
    create_cancel_callback = None

# Platform-specific sprite creation
def create_sprite(width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False, scale=1.00):
    return Sprite(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)

# ThumbyColor-specific sprite creation with memory management
if IS_THUMBY_COLOR:
    def create_sprite(width, height, bitmap_data, x=0, y=0, key=-1, mirrorX=False, mirrorY=False, scale=1.00):
        """ThumbyColor version that prioritizes color sprites with memory management"""
        # Force GC before creating new sprites
        gc.collect()

        color_file = ""
        if isinstance(bitmap_data, tuple) and isinstance(bitmap_data[0], str):
            base_file = bitmap_data[0]
            # Calculate output dimensions
            output_width = int(width * scale)
            output_height = int(height * scale)
            color_file = base_file.split("_")[0] + f'_{output_width}_{output_height}.COL.bin'
        elif isinstance(bitmap_data, str):
            # Try color version first
            color_file = bitmap_data
        else:
            # Fall back to standard sprite
            return Sprite(width, height, bitmap_data, x, y, key, mirrorX, mirrorY)

        print(f"Loading sprite: {color_file}")
        sprite = Sprite(0, 0, color_file, x, y, key, mirrorX, mirrorY)
        print(f"Free memory after loading Sprite: {gc.mem_free()}")
        return sprite

# Helper functions - these work the same on all platforms
def dpadPressed():
    """Returns true if any dpad buttons are currently pressed"""
    return (buttonU.pressed() or buttonD.pressed() or buttonL.pressed() or buttonR.pressed())

def inputJustPressed():
    """Returns true if any buttons were just pressed"""
    return (buttonA.justPressed() or buttonB.justPressed() or buttonU.justPressed() or
            buttonD.justPressed() or buttonL.justPressed() or buttonR.justPressed() or
            buttonLB.justPressed() or buttonRB.justPressed() or buttonMENU.justPressed())
