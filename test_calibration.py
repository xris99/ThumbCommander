#!/usr/bin/env python3
"""Test FPS calibration system"""

import os
import sys

os.environ['RUNNING_ON_PC'] = '1'
sys.path.insert(0, 'pc_wrapper')

import micropython_compat
from pc_wrapper import fps_calibration

print("Testing FPS calibration...")
print(f"Settings file: {fps_calibration.SETTINGS_FILE}")
print(f"Exists: {os.path.exists(fps_calibration.SETTINGS_FILE)}")

if not os.path.exists(fps_calibration.SETTINGS_FILE):
    print("\nRunning calibration...")
    correction = fps_calibration.get_fps_correction()
    print(f"\nCalibration result: {correction:.4f}")
else:
    print("\nLoading existing calibration...")
    settings = fps_calibration.load_settings()
    print(f"Correction factor: {settings.get('fps_correction'):.4f}")
    print(f"Calibration date: {settings.get('calibration_date')}")

# Test that engine.py can load it
print("\nTesting engine.py loading...")
import pc_wrapper.engine as engine
engine._load_fps_correction()
print(f"Engine loaded correction: {engine._fps_correction_factor:.4f if engine._fps_correction_factor else 'None'}")

# Test FPS setting
print("\nTesting FPS adjustment...")
print("Setting FPS to 21...")
engine.fps_limit(21)
expected_period = 1000.0 / 21
actual_period = engine._fps_limit_period_ms
print(f"Expected period: {expected_period:.3f} ms")
print(f"Actual period: {actual_period:.3f} ms")
if engine._fps_correction_factor:
    corrected_fps = 21 * engine._fps_correction_factor
    print(f"Corrected FPS: {corrected_fps:.2f}")

print("\nTest complete!")
