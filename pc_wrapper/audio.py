"""
Audio module stub for PC
Provides ThumbyColor audio API stubs
"""

import os


# Audio state
class AudioState:
    def __init__(self):
        self.loaded_file = None
        self.playing = False
        self.loop = False
        self.loop_start = 0
        self.loop_end = 0
        self.volume = 100
        self.position = 0
        self.end_callback = None
        self.audio_ids = {}


_audio_state = AudioState()


def load(filename):
    """Load audio file"""
    if os.path.exists(filename):
        _audio_state.loaded_file = filename
        print(f"Audio: Loaded {filename}")
    else:
        print(f"Audio: File not found: {filename}")


def play():
    """Start playback"""
    _audio_state.playing = True
    _audio_state.position = 0
    print(f"Audio: Playing {_audio_state.loaded_file}")


def stop():
    """Stop playback"""
    _audio_state.playing = False
    _audio_state.position = 0
    print("Audio: Stopped")


def set_volume(volume):
    """Set volume (0-150)"""
    _audio_state.volume = max(0, min(150, volume))
    print(f"Audio: Volume set to {_audio_state.volume}")


def set_loop(loop, start=0, end=0):
    """Set loop mode"""
    _audio_state.loop = loop
    _audio_state.loop_start = start
    _audio_state.loop_end = end
    print(f"Audio: Loop set to {loop}")


def get_position():
    """Get current playback position"""
    return _audio_state.position


def set_end_callback(callback):
    """Set callback for when playback ends"""
    _audio_state.end_callback = callback


def clear_end_callback():
    """Clear end callback"""
    _audio_state.end_callback = None


def open_id(filename, audio_id):
    """Open audio file with ID"""
    if os.path.exists(filename):
        _audio_state.audio_ids[audio_id] = filename
        print(f"Audio: Opened {filename} as ID {audio_id}")
    else:
        print(f"Audio: File not found: {filename}")


def play_id(audio_id):
    """Play audio by ID"""
    if audio_id in _audio_state.audio_ids:
        filename = _audio_state.audio_ids[audio_id]
        _audio_state.loaded_file = filename
        _audio_state.playing = True
        _audio_state.position = 0
        print(f"Audio: Playing ID {audio_id} ({filename})")
    else:
        print(f"Audio: ID {audio_id} not found")


def close_ids():
    """Close all audio IDs"""
    _audio_state.audio_ids.clear()
    print("Audio: Closed all IDs")
