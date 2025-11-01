"""
Cutscene utilities for PC
Plays animated cutscenes from .COL.bin and .ima files
"""

import os
import time


# Module-level variables
_display = None
_PC = None
_audio_load = None
_audio_play = None
_audio_stop = None
_buttonMENU = None


def init_cutscene_utils(display, PC, audio_load, audio_play, audio_stop, buttonMENU):
    """Initialize cutscene utilities"""
    global _display, _PC, _audio_load, _audio_play, _audio_stop, _buttonMENU
    _display = display
    _PC = PC
    _audio_load = audio_load
    _audio_play = audio_play
    _audio_stop = audio_stop
    _buttonMENU = buttonMENU


def play_cutscene_animation(filename, frames, cancel_callback=None):
    """
    Play cutscene animation from file

    Args:
        filename: Path to .COL.bin or .ima file
        frames: Number of frames in animation
        cancel_callback: Optional callback that returns True to cancel
    """
    if not _display:
        print(f"Cutscene: No display available for {filename}")
        return

    print(f"Cutscene: Playing {filename} ({frames} frames)")

    # Load audio if .ima file exists
    audio_file = filename.replace('.COL.bin', '.ima')
    if os.path.exists(audio_file) and _audio_load:
        _audio_load(audio_file)
        if _audio_play:
            _audio_play()

    # Animation parameters
    frame_delay = 1.0 / 20.0  # 20 FPS for cutscenes

    # Play animation
    for frame in range(frames):
        # Check for cancel
        if cancel_callback and cancel_callback():
            print("Cutscene cancelled by user")
            break

        # Display frame
        _display.fill(0)
        if os.path.exists(filename):
            # Draw the current frame
            _display.draw_sprite_from_file(filename, 0, 0, frame)

        _display.update()

        # Frame delay
        time.sleep(frame_delay)

    # Stop audio if playing
    if _audio_stop:
        _audio_stop()

    # Final display update
    _display.fill(0)
    _display.update()


def create_cancel_callback():
    """Create a cancel callback for cutscenes"""
    def callback():
        if _buttonMENU and _buttonMENU.pressed():
            return True
        return False
    return callback
