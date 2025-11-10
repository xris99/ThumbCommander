#!/usr/bin/env python3
"""
Test different pygame.mixer buffer sizes to see effect on playback speed
"""

import sys
import time
import numpy as np
import pygame as pg

def generate_test_tone(sample_rate, duration_sec, frequency=440):
    """Generate a sine wave test tone"""
    num_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, num_samples, False)
    tone = np.sin(frequency * 2 * np.pi * t)
    audio = (tone * 32767).astype(np.int16)
    stereo = np.column_stack((audio, audio))
    return stereo, num_samples

def test_buffer_size(sample_rate, buffer_size, duration_sec=2.0):
    """Test playback speed with a specific buffer size"""
    if pg.mixer.get_init():
        pg.mixer.quit()

    try:
        pg.mixer.pre_init(frequency=sample_rate, size=-16, channels=2, buffer=buffer_size)
        pg.mixer.init()

        # Generate test tone
        audio_data, num_samples = generate_test_tone(sample_rate, duration_sec)
        sound = pg.sndarray.make_sound(audio_data)

        # Measure playback time
        start_time = time.perf_counter()
        sound.play()

        while pg.mixer.get_busy():
            time.sleep(0.001)

        end_time = time.perf_counter()
        actual_duration = end_time - start_time

        error_percent = ((actual_duration - duration_sec) / duration_sec) * 100
        speed_multiplier = duration_sec / actual_duration

        return {
            'buffer': buffer_size,
            'expected': duration_sec,
            'actual': actual_duration,
            'error': error_percent,
            'speed': speed_multiplier
        }

    except Exception as e:
        print(f"Error with buffer {buffer_size}: {e}")
        return None
    finally:
        if pg.mixer.get_init():
            pg.mixer.quit()

if __name__ == "__main__":
    print("🔊 pygame.mixer Buffer Size Test")
    print("="*70)
    
    pg.init()
    
    # Test with 15625 Hz (cutscene rate) and various buffer sizes
    sample_rate = 15625
    buffer_sizes = [512, 1024, 2048, 4096, 8192]
    
    print(f"\nTesting sample rate: {sample_rate} Hz")
    print(f"Test duration: 2.0 seconds\n")
    
    results = []
    for buf_size in buffer_sizes:
        print(f"Testing buffer size {buf_size}...")
        result = test_buffer_size(sample_rate, buf_size)
        if result:
            results.append(result)
        time.sleep(0.3)
    
    # Summary
    print("\n" + "="*70)
    print("📋 RESULTS")
    print("="*70)
    print(f"{'Buffer':>10} {'Expected':>10} {'Actual':>10} {'Error':>10} {'Speed':>10}")
    print(f"{'Size':>10} {'Time (s)':>10} {'Time (s)':>10} {'(%)':>10} {'Mult':>10}")
    print("-"*70)
    
    for r in results:
        print(f"{r['buffer']:>10} {r['expected']:>10.3f} {r['actual']:>10.3f} "
              f"{r['error']:>+10.2f} {r['speed']:>10.4f}x")
    
    print("="*70)
    
    # Find best buffer size
    best = min(results, key=lambda x: abs(x['error']))
    print(f"\n✅ Best buffer size: {best['buffer']} (error: {best['error']:+.2f}%)")
    print("="*70)
