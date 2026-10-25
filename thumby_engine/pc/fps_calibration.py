"""
FPS calibration for the PC target.
Automatically measures rendering overhead and calculates an FPS
correction factor, which pc/engine.py applies to fps_limit().

The correction is stored per emulation mode (thumby_engine.pc.bootstrap
sets the THUMBY_EMULATION_MODE environment variable):
    color  -> key 'fps_correction'        (timed on intro_128_80.COL.bin)
    thumby -> key 'fps_correction_thumby' (timed on intro_74_30.BIT.bin)
Saving always merges into the existing settings dict, so calibrating one
mode never clobbers the other mode's value.
"""

import os
import json
import sys
import struct

# Import the backed-up stdlib time module that was saved by
# thumby_engine.pc.bootstrap() (before sys.modules['time'] was swapped
# for the utime emulation). This avoids the utime patching issue.
_stdlib_time = sys.modules.get('_stdlib_time_backup')
if _stdlib_time is None:
    # Fallback if not run through the PC bootstrap (e.g. direct testing)
    import time as _stdlib_time

SETTINGS_FILE = ".pc_wrapper_settings.json"

# The timed reference renders: the game's intro cutscenes. Paths are
# relative to the game directory (bootstrap() chdirs there).
VIDEO_FILE = "assets/intro_128_80.COL.bin"          # color mode (TDL8)
VIDEO_FILE_THUMBY = "assets/intro_74_30.BIT.bin"    # thumby mode (BIT+SHD)

# Settings keys per emulation mode (must match pc/engine.py)
KEYS = {'color': 'fps_correction', 'thumby': 'fps_correction_thumby'}


def _mode():
    """Active emulation mode as set by thumby_engine.pc.bootstrap()."""
    mode = os.environ.get('THUMBY_EMULATION_MODE', 'color')
    return mode if mode in KEYS else 'color'


def _key():
    """Settings key for the active mode."""
    return KEYS[_mode()]


def load_settings():
    """Load settings from file if it exists"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[FPS Calibration] Failed to load settings: {e}")
    return None

def save_settings(settings):
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        print(f"[FPS Calibration] Settings saved to {SETTINGS_FILE}")
        return True
    except Exception as e:
        print(f"[FPS Calibration] Failed to save settings: {e}")
        return False

def _store(correction):
    """Merge a correction value into the settings file (keeps the value
    stored for the *other* emulation mode)."""
    settings = load_settings() or {}
    settings[_key()] = correction
    settings['calibration_date'] = _stdlib_time.strftime(
        '%Y-%m-%d %H:%M:%S', _stdlib_time.localtime())
    settings['version'] = '1.0'
    save_settings(settings)

def calibrate_fps():
    """
    Run FPS calibration using intro cutscene
    Returns correction factor: corrected_fps = target_fps * correction_factor
    """
    print("\n" + "="*70)
    print("FPS CALIBRATION")
    print("="*70)
    print("First run detected - calibrating FPS for your system...")
    print("This will play the intro cutscene to measure rendering performance.")
    print("="*70 + "\n")

    try:
        # Drive the calibration through the platform module: it has
        # already created the display and initialized the color
        # cutscene player (thumby_engine.cutscene.color).
        import thumby_engine.platform as platform
        from thumby_engine.cutscene import color as cutscene

        # Get video info
        video_file = VIDEO_FILE
        if not os.path.exists(video_file):
            print(f"[FPS Calibration] Warning: {video_file} not found, using default correction")
            return 1.3  # Default ~30% overhead

        with open(video_file, 'rb') as f:
            magic = f.read(4)
            if magic != b'TDL8':
                print(f"[FPS Calibration] Invalid video file, using default correction")
                return 1.3

            width, height, frame_count = struct.unpack('<HHH', f.read(6))

        target_fps = 21
        expected_duration = frame_count / target_fps

        print(f"Calibrating with intro cutscene:")
        print(f"  {frame_count} frames at target {target_fps} FPS")
        print(f"  Expected duration: {expected_duration:.2f}s")
        print(f"\nPlaying cutscene (no audio for calibration)...")

        # Disable audio for calibration (the cutscene module derives the
        # .ima name and skips loading when audio_load is None)
        original_audio_load = cutscene.audio_load
        cutscene.audio_load = None

        try:
            # Measure actual playback time (no frame callback: the run
            # cannot be cancelled, so the measurement is deterministic)
            start = _stdlib_time.perf_counter()
            platform.play_cutscene_animation(video_file, fps=target_fps,
                                             frame_callback=None)
            actual_duration = _stdlib_time.perf_counter() - start
        finally:
            # Restore audio
            cutscene.audio_load = original_audio_load

        # Calculate actual FPS and correction factor
        actual_fps = frame_count / actual_duration
        correction_factor = target_fps / actual_fps

        print(f"\nCalibration results:")
        print(f"  Actual duration: {actual_duration:.2f}s")
        print(f"  Actual FPS: {actual_fps:.2f}")
        print(f"  Correction factor: {correction_factor:.4f}")
        print(f"  (To achieve {target_fps} FPS, set to {target_fps * correction_factor:.1f} FPS)")

        return correction_factor

    except Exception as e:
        print(f"[FPS Calibration] Error during calibration: {e}")
        print(f"[FPS Calibration] Using default correction factor")
        import traceback
        traceback.print_exc()
        return 1.3  # Default ~30% overhead

def calibrate_fps_thumby():
    """
    Thumby-mode FPS calibration using the 1-bit grayscale intro cutscene
    (intro_74_30.BIT.bin + .SHD.bin) at the boot-intro's native 8 fps.
    Returns correction factor: corrected_fps = target_fps * factor
    """
    print("\n" + "="*70)
    print("FPS CALIBRATION (Thumby mode)")
    print("="*70)
    print("First run detected - calibrating FPS for your system...")
    print("This will play the grayscale intro to measure rendering overhead.")
    print("="*70 + "\n")

    try:
        # The platform module (already imported at calibration time by
        # the launcher's bootstrap) has created the Grayscale display
        # and initialized the grayscale cutscene player.
        import thumby_engine.platform as platform

        video_file = VIDEO_FILE_THUMBY
        shd_file = video_file.replace('.BIT.bin', '.SHD.bin')
        if not os.path.exists(video_file) or not os.path.exists(shd_file):
            print(f"[FPS Calibration] Warning: {video_file} "
                  f"(or its .SHD) not found, using default correction")
            return 1.0  # grayscale blits are cheap; assume no overhead

        # Dimensions + frame count from the filename and file size
        # (same parsing the grayscale cutscene player uses).
        width, height = 74, 30
        bitmap_byte_count = width * ((height + 7) // 8)  # 296 bytes/frame
        frame_count = os.stat(video_file)[6] // bitmap_byte_count

        target_fps = 8
        expected_duration = frame_count / target_fps

        print(f"Calibrating with grayscale intro:")
        print(f"  {frame_count} frames at target {target_fps} FPS")
        print(f"  Expected duration: {expected_duration:.2f}s")
        print(f"\nPlaying cutscene...")

        # Grayscale cutscenes have no audio track; nothing to disable.
        # No frame callback: the run cannot be cancelled, so the
        # measurement is deterministic.
        start = _stdlib_time.perf_counter()
        platform.play_cutscene_animation(video_file, fps=target_fps,
                                         frame_callback=None)
        actual_duration = _stdlib_time.perf_counter() - start

        actual_fps = frame_count / actual_duration
        correction_factor = target_fps / actual_fps if actual_fps > 0 else 1.0

        print(f"\nCalibration results:")
        print(f"  Actual duration: {actual_duration:.2f}s")
        print(f"  Actual FPS: {actual_fps:.2f}")
        print(f"  Correction factor: {correction_factor:.4f}")
        print(f"  (To achieve {target_fps} FPS, set to "
              f"{target_fps * correction_factor:.1f} FPS)")

        return correction_factor

    except Exception as e:
        print(f"[FPS Calibration] Error during calibration: {e}")
        print(f"[FPS Calibration] Using default correction factor")
        import traceback
        traceback.print_exc()
        return 1.0

def get_fps_correction():
    """
    Get FPS correction factor, calibrating if necessary
    Returns correction factor to apply: corrected_fps = target_fps * correction_factor
    """
    # Try to load existing settings
    settings = load_settings()
    key = _key()

    if settings and key in settings:
        correction = settings[key]
        print(f"[FPS Calibration] Using saved correction factor: {correction:.4f}")
        return correction

    # Need to calibrate (per active mode)
    print(f"[FPS Calibration] No calibration found, running calibration...")
    correction = (calibrate_fps_thumby() if _mode() == 'thumby'
                  else calibrate_fps())

    _store(correction)

    return correction

def recalibrate():
    """Force recalibration (can be called manually)"""
    key = _key()
    settings = load_settings()
    if settings and key in settings:
        del settings[key]
        save_settings(settings)
        kept = ', '.join(k for k in settings if k in KEYS)
        print(f"[FPS Calibration] Removed {key} from {SETTINGS_FILE} "
              f"(kept: {kept or 'nothing'})")
    elif os.path.exists(SETTINGS_FILE):
        os.remove(SETTINGS_FILE)
        print(f"[FPS Calibration] Removed {SETTINGS_FILE}")

    return get_fps_correction()
