"""
Engine module for PC
Provides compatibility with ThumbyColor engine module timing and input
"""

import time
import os
import json

# FPS control
_fps_limit_value = 60
_fps_limit_period_ms = 1000.0 / 60.0  # milliseconds per frame
# Use perf_counter for high-precision timing (not time.time() which returns int on MicroPython)
_last_tick_time = time.perf_counter()
_fps_limit_enabled = True

# FPS calibration correction factor
_fps_correction_factor = None
_fps_correction_loaded = False
_SETTINGS_FILE = ".pc_wrapper_settings.json"

def _load_fps_correction():
    """Load FPS correction factor from settings file"""
    global _fps_correction_factor, _fps_correction_loaded

    if _fps_correction_loaded:
        return

    _fps_correction_loaded = True

    if os.path.exists(_SETTINGS_FILE):
        try:
            with open(_SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                if 'fps_correction' in settings:
                    _fps_correction_factor = settings['fps_correction']
                    print(f"[Engine] Loaded FPS correction factor: {_fps_correction_factor:.4f}")
        except Exception as e:
            print(f"[Engine] Failed to load FPS correction: {e}")

# Import button update function for input polling
try:
    from pc_wrapper.thumbyButton import update_button_state
except ImportError:
    try:
        from thumbyButton import update_button_state
    except ImportError:
        update_button_state = None


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
        # Load correction factor if not already loaded
        _load_fps_correction()

        # Store the requested FPS (what game asked for)
        _fps_limit_value = fps

        if fps > 0:
            # Apply correction factor to compensate for rendering overhead
            if _fps_correction_factor is not None:
                corrected_fps = fps * _fps_correction_factor
                _fps_limit_period_ms = 1000.0 / corrected_fps
                print(f"[Engine] FPS limit: {fps} → {corrected_fps:.2f} (corrected)")
            else:
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
    current_time = time.perf_counter()
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
    if update_button_state is not None:
        update_button_state()

    # Update tick time
    _last_tick_time = time.perf_counter()

    return True
