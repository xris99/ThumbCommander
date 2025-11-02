"""
Engine module stub for PC
Provides compatibility with ThumbyColor engine module
"""

import time

# FPS control
_fps_limit = 60
_last_tick = time.time()
_frame_time = 1.0 / 60.0

def freq(frequency):
    """Set CPU frequency - no-op on PC"""
    pass

def fps_limit(fps):
    """Set FPS limit"""
    global _fps_limit, _frame_time
    _fps_limit = fps
    _frame_time = 1.0 / fps if fps > 0 else 0

def time_to_next_tick():
    """Return time until next tick in milliseconds"""
    global _last_tick, _frame_time
    elapsed = time.time() - _last_tick
    remaining = _frame_time - elapsed
    return int(remaining * 1000) if remaining > 0 else 0

def tick():
    """Mark frame tick"""
    global _last_tick
    _last_tick = time.time()
