#!/usr/bin/env python3
"""
Test script to verify multiprocessing setup works correctly
"""

print("[Test] Starting multiprocessing test...", flush=True)

import sys
import os

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PC_WRAPPER_DIR = os.path.join(SCRIPT_DIR, 'pc_wrapper')
sys.path.insert(0, PC_WRAPPER_DIR)

print(f"[Test] Python version: {sys.version}", flush=True)
print(f"[Test] Platform: {sys.platform}", flush=True)

# Set multiprocessing method
import multiprocessing as mp
print(f"[Test] Initial mp method: {mp.get_start_method()}", flush=True)

if sys.platform != 'win32':
    try:
        mp.set_start_method('fork')
        print("[Test] Set mp method to 'fork'", flush=True)
    except RuntimeError as e:
        print(f"[Test] Could not set fork: {e}", flush=True)

print(f"[Test] Final mp method: {mp.get_start_method()}", flush=True)

# Import our _thread module
import pc_wrapper._thread as _thread

print("[Test] Imported _thread module", flush=True)

# Define a simple audio_loop function
def audio_loop():
    print("[Test] audio_loop() called!", flush=True)
    import time
    for i in range(5):
        print(f"[Test] audio_loop iteration {i}", flush=True)
        time.sleep(0.1)
    print("[Test] audio_loop() finished", flush=True)

# Try to start it
print("[Test] Calling start_new_thread with audio_loop...", flush=True)
tid = _thread.start_new_thread(audio_loop, ())
print(f"[Test] start_new_thread returned: {tid}", flush=True)

# Wait a bit
import time
print("[Test] Waiting for audio_loop to finish...", flush=True)
time.sleep(2)

print("[Test] Test complete!", flush=True)
