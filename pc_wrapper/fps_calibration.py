"""
FPS Calibration for PC Wrapper
Automatically measures rendering overhead and calculates FPS correction factor
"""

import os
import json
import time as _stdlib_time  # Use stdlib time explicitly to avoid utime conflict
import struct

SETTINGS_FILE = ".pc_wrapper_settings.json"

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
        # Import required modules
        from platform_constants import get_constants
        from thumbycolor_native import ColorDisplay
        import cutscene_utils
        import pc_wrapper.audio as audio
        
        # Initialize
        PC = get_constants(is_thumby_color=True)
        display = ColorDisplay()
        
        # Mock button
        class MockButton:
            def pressed(self):
                return False
        
        button_menu = MockButton()
        
        # Initialize cutscene_utils
        cutscene_utils.init_cutscene_utils(
            display,
            PC,
            lambda f: audio.load(f),
            lambda: audio.play(),
            lambda: audio.stop(),
            button_menu
        )
        
        # Get video info
        video_file = "intro_128_80.COL.bin"
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
        
        # Disable audio for calibration
        original_audio_load = cutscene_utils.audio_load
        cutscene_utils.audio_load = None
        
        # Measure actual playback time
        start = _stdlib_time.perf_counter()
        cutscene_utils.play_cutscene_animation(video_file, fps=target_fps, frame_callback=None)
        actual_duration = _stdlib_time.perf_counter() - start
        
        # Restore audio
        cutscene_utils.audio_load = original_audio_load
        
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

def get_fps_correction():
    """
    Get FPS correction factor, calibrating if necessary
    Returns correction factor to apply: corrected_fps = target_fps * correction_factor
    """
    # Try to load existing settings
    settings = load_settings()
    
    if settings and 'fps_correction' in settings:
        correction = settings['fps_correction']
        print(f"[FPS Calibration] Using saved correction factor: {correction:.4f}")
        return correction
    
    # Need to calibrate
    print(f"[FPS Calibration] No calibration found, running calibration...")
    correction = calibrate_fps()
    
    # Save settings
    settings = {
        'fps_correction': correction,
        'calibration_date': _stdlib_time.strftime('%Y-%m-%d %H:%M:%S', _stdlib_time.localtime()),
        'version': '1.0'
    }
    save_settings(settings)
    
    return correction

def recalibrate():
    """Force recalibration (can be called manually)"""
    if os.path.exists(SETTINGS_FILE):
        os.remove(SETTINGS_FILE)
        print(f"[FPS Calibration] Removed {SETTINGS_FILE}")
    
    return get_fps_correction()
