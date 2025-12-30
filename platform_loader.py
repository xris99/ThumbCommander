# platform_loader.py - Updated with memory-efficient imports using try/except
import sys
import gc
import micropython
from thumbyButton import ButtonClass

# Platform detection
IS_THUMBY_COLOR = False

try:
    import engine_io
    IS_THUMBY_COLOR = True
except ImportError:
    from thumbyHardware import swL, swR, swU, swD, swA, swB

# Get platform constants
from platform_constants import get_constants
PC = get_constants(IS_THUMBY_COLOR)

# Initialize all variables to None first
display = None
Sprite = None
rumble = None
audio_load = None
audio_play = None
audio_stop = None
audio_set_volume = None
audio_set_loop = None
audio_get_position = None
audio_set_end_callback = None
audio_clear_end_callback = None
audio_open_id = None
audio_play_id = None
audio_close_ids = None
play_cutscene_animation = None
create_cancel_callback = None
create_sprite = None

# Platform-specific imports using try/except
if IS_THUMBY_COLOR:
    buttonA = ButtonClass(engine_io.A)
    buttonB = ButtonClass(engine_io.B)
    buttonU = ButtonClass(engine_io.UP)
    buttonD = ButtonClass(engine_io.DOWN)
    buttonL = ButtonClass(engine_io.LEFT)
    buttonR = ButtonClass(engine_io.RIGHT)
    buttonLB = ButtonClass(engine_io.LB)
    buttonRB = ButtonClass(engine_io.RB)
    buttonMENU = ButtonClass(engine_io.MENU)
    # Try to import ThumbyColor display and sprite classes
    try:
        from thumbycolor_native import ColorDisplay, ColorSprite, _rumble, create_sprite as _create_sprite
        display = ColorDisplay()
        Sprite = ColorSprite
        rumble = _rumble
        create_sprite = _create_sprite
        print(f"ThumbyColor display initialized. Free memory: {gc.mem_free()}")
    except ImportError as e:
        print(f"Warning: Could not import thumbycolor_native: {e}")
    
    try:
        from audio import (load, play, stop, set_volume, set_loop, get_position, set_end_callback, clear_end_callback, open_id, play_id, close_ids)        
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
        from cutscene_utils import init_cutscene_utils, play_cutscene_animation as _play_cutscene, create_cancel_callback as _create_cancel
        play_cutscene_animation = _play_cutscene
        create_cancel_callback = _create_cancel
        init_cutscene_utils(display, PC, audio_load, audio_play, audio_stop, buttonMENU)
        print(f"Audio and Color Cutscene initialized. Free memory: {gc.mem_free()}")
    except ImportError as e:
        print(f"Warning: Could not import audio module or color_cutscene: {e}")
  
# original Thumby
else:
    from grayscale import display as _display, Sprite as _Sprite, play_cutscene_animation as _play_cutscene, create_cancel_callback as _create_cancel, create_sprite as _create_sprite  
    display = _display
    Sprite = _Sprite
    buttonA = ButtonClass(swA) # Left (A) button
    buttonB = ButtonClass(swB) # Right (B) button
    buttonU = ButtonClass(swU) # D-pad up
    buttonD = ButtonClass(swD) # D-pad down
    buttonL = ButtonClass(swL) # D-pad left
    buttonR = ButtonClass(swR) # D-pad right
    buttonLB = buttonL
    buttonRB = buttonR
    buttonMENU = buttonB
    play_cutscene_animation = _play_cutscene
    create_cancel_callback = _create_cancel
    create_sprite = _create_sprite
    print(f"Thumby display initialized. Free memory: {gc.mem_free()}")

# Helper functions
@micropython.native
def dpadPressed():
    """Returns true if any dpad buttons are currently pressed on the thumby."""
    return (buttonU.pressed() or buttonD.pressed() or buttonL.pressed() or buttonR.pressed())
  
@micropython.native
def inputJustPressed():
    """Returns true if any buttons were just pressed on the thumby."""
    return (buttonA.justPressed() or buttonB.justPressed() or buttonU.justPressed() or 
            buttonD.justPressed() or buttonL.justPressed() or buttonR.justPressed() or 
            buttonLB.justPressed() or buttonRB.justPressed() or buttonMENU.justPressed())