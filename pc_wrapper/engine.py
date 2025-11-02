"""
Engine module for PC
Provides compatibility with ThumbyColor engine module timing and input
"""

import time

# FPS control
_fps_limit_value = 60
_fps_limit_period_ms = 1000.0 / 60.0  # milliseconds per frame
_last_tick_time = time.time()
_fps_limit_enabled = True

# Import button class for input polling
try:
    from pc_wrapper.thumbyButton import ButtonClass
except ImportError:
    try:
        from thumbyButton import ButtonClass
    except ImportError:
        ButtonClass = None


def freq(frequency):
    """Set CPU frequency - no-op on PC"""
    pass


def fps_limit(fps=None):
    """
    Get or set FPS limit

    Args:
        fps: If provided, sets the FPS limit. If None, returns current limit.

    Returns:
        Current FPS limit value
    """
    global _fps_limit_value, _fps_limit_period_ms, _fps_limit_enabled

    if fps is not None:
        _fps_limit_value = fps
        if fps > 0:
            _fps_limit_period_ms = 1000.0 / fps
            _fps_limit_enabled = True
        else:
            _fps_limit_enabled = False

    return _fps_limit_value if _fps_limit_enabled else float('inf')


def time_to_next_tick():
    """
    Calculate milliseconds remaining until next scheduled frame

    Returns:
        Milliseconds to wait (0 if FPS limit disabled or time has passed)
    """
    global _last_tick_time, _fps_limit_period_ms, _fps_limit_enabled

    if not _fps_limit_enabled:
        return 0

    # Calculate elapsed time since last tick
    current_time = time.time()
    elapsed_ms = (current_time - _last_tick_time) * 1000.0

    # Calculate remaining time
    remaining_ms = _fps_limit_period_ms - elapsed_ms

    return int(remaining_ms) if remaining_ms > 0 else 0


def tick():
    """
    Execute one engine tick

    This function:
    1. Enforces FPS limiting (busy-waits if needed)
    2. Updates button states (polls input)
    3. Updates timing for next frame

    Returns:
        True if tick executed, False if skipped due to FPS limiting
    """
    global _last_tick_time, _fps_limit_enabled

    # FPS limiting - busy wait if needed
    if _fps_limit_enabled:
        wait_ms = time_to_next_tick()
        if wait_ms > 0:
            # Sleep for most of the wait time
            if wait_ms > 1:
                time.sleep((wait_ms - 1) / 1000.0)
            # Busy wait for remaining time for precision
            while time_to_next_tick() > 0:
                pass

    # Update button states (poll input)
    if ButtonClass is not None:
        ButtonClass.update_all_buttons()

    # Update tick time
    _last_tick_time = time.time()

    return True
