# platform module - the single seam between a game and the hardware.
#
# A game does:
#     from thumby_engine.platform import display, PC, Sprite, ...
# and gets a stable, platform-neutral API no matter which target it runs on:
#
#   * ThumbyColor (RP2350):  RGB565 display, 9 buttons, IMA-ADPCM audio,
#                            TDL8 palette-delta cutscenes
#   * Thumby      (RP2040):  72x40 1-bit 4-level dither, 6 buttons,
#                            no audio, silent 1-bit cutscenes
#
# Detection is hardware-only: the engine_io firmware module exists on the
# ThumbyColor, not on the original Thumby. The PC target is invisible to
# this module: tool/run_pc.py installs the CPython/pygame emulation
# (thumby_engine.pc) into sys.modules before the game is imported, so the
# PC runs the very same ThumbyColor path.
#
# On import this module: (1) detects the target, (2) wires the matching
# display / input / audio / cutscene modules, (3) exposes the public API.
# It is the only engine module that a game must import.

from gc import mem_free

# --- Target detection ------------------------------------------------------
# The engine_io firmware module exists on ThumbyColor (and its PC
# emulation) but not on the original Thumby.
IS_THUMBY_COLOR = False
try:
    import engine_io
    IS_THUMBY_COLOR = True
except ImportError:
    pass
IS_THUMBY = not IS_THUMBY_COLOR

# --- Shared constants (engine fields; games extend the same object) --------
from .constants import get_constants
PC = get_constants(IS_THUMBY_COLOR)

# Buttons: every target provides a ButtonClass with pressed()/justPressed()
# (firmware thumbyButton on the devices, the PC emulation on a PC).
from thumbyButton import ButtonClass

# --- Public API (initialized per platform below) ---------------------------
display = None
Sprite = None
create_sprite = None
play_cutscene_animation = None
create_cancel_callback = None
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

buttonA = buttonB = buttonU = buttonD = buttonL = buttonR = None
buttonLB = buttonRB = buttonMENU = None

if IS_THUMBY_COLOR:
    # --- ThumbyColor (the PC emulation presents itself as one) --------------
    import engine_io
    buttonA = ButtonClass(engine_io.A)
    buttonB = ButtonClass(engine_io.B)
    buttonU = ButtonClass(engine_io.UP)
    buttonD = ButtonClass(engine_io.DOWN)
    buttonL = ButtonClass(engine_io.LEFT)
    buttonR = ButtonClass(engine_io.RIGHT)
    buttonLB = ButtonClass(engine_io.LB)
    buttonRB = ButtonClass(engine_io.RB)
    buttonMENU = ButtonClass(engine_io.MENU)

    from ..display.color import (ColorDisplay, ColorSprite,
                                 _rumble, create_sprite as _create_sprite)
    display = ColorDisplay()
    Sprite = ColorSprite
    rumble = _rumble
    create_sprite = _create_sprite
    print(f"ThumbyColor display initialized. Free memory: {mem_free()}")

    # Audio: the IMA-ADPCM driver on the ThumbyColor. On a PC the emulation
    # pre-registers its pygame.mixer implementation under this same module
    # name, so the same import picks up that backend instead.
    from ..audio.hardware import (load, play, stop, set_volume, set_loop,
                                   get_position, set_end_callback,
                                   clear_end_callback, open_id, play_id,
                                   close_ids)
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

    from ..cutscene.color import (init_cutscene_utils,
                                  play_cutscene_animation as _play_cutscene,
                                  create_cancel_callback as _create_cancel)
    play_cutscene_animation = _play_cutscene
    create_cancel_callback = _create_cancel
    init_cutscene_utils(display, PC, audio_load, audio_play, audio_stop,
                        buttonMENU)
    print(f"Audio and color cutscene initialized. Free memory: {mem_free()}")

else:
    # --- Original Thumby (no audio, 1-bit cutscenes) ------------------------
    from thumbyHardware import swL, swR, swU, swD, swA, swB
    buttonA = ButtonClass(swA)   # Left (A) button
    buttonB = ButtonClass(swB)   # Right (B) button
    buttonU = ButtonClass(swU)   # D-pad up
    buttonD = ButtonClass(swD)   # D-pad down
    buttonL = ButtonClass(swL)   # D-pad left
    buttonR = ButtonClass(swR)   # D-pad right
    buttonLB = buttonL
    buttonRB = buttonR
    buttonMENU = buttonB

    from ..display.grayscale import Grayscale, Sprite as _Sprite
    from ..display.grayscale import create_sprite as _create_sprite
    display = Grayscale()
    display.enableGrayscale()
    Sprite = _Sprite
    create_sprite = _create_sprite

    from ..cutscene.grayscale import (init_grayscale_cutscene,
                                      play_cutscene_animation as _play_cutscene,
                                      create_cancel_callback as _create_cancel)
    play_cutscene_animation = _play_cutscene
    create_cancel_callback = _create_cancel
    init_grayscale_cutscene(display, PC, buttonMENU)

    print(f"Thumby display initialized. Free memory: {mem_free()}")


# --- Input helpers ----------------------------------------------------------
@micropython.native
def dpadPressed():
    """True if any d-pad button is currently pressed."""
    return (buttonU.pressed() or buttonD.pressed() or
            buttonL.pressed() or buttonR.pressed())


@micropython.native
def inputJustPressed():
    """True if any button was just pressed."""
    return (buttonA.justPressed() or buttonB.justPressed() or
            buttonU.justPressed() or buttonD.justPressed() or
            buttonL.justPressed() or buttonR.justPressed() or
            buttonLB.justPressed() or buttonRB.justPressed() or
            buttonMENU.justPressed())
