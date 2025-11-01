"""
Cutscene utilities stub for PC
"""


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
    """Play cutscene animation"""
    print(f"Cutscene: Playing {filename} ({frames} frames)")
    # Simple implementation - just show for a moment
    import time
    if _display:
        _display.fill(0)
        _display.update()
        time.sleep(1.0)  # Show for 1 second


def create_cancel_callback():
    """Create a cancel callback for cutscenes"""
    def callback():
        if _buttonMENU and _buttonMENU.pressed():
            return True
        return False
    return callback
