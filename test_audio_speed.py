#!/usr/bin/env python3
"""
Test pygame.mixer actual playback speed
Generates known-duration audio and measures actual playback time
to verify if pygame.mixer honors the requested sample rate
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

    # Convert to 16-bit signed integers
    audio = (tone * 32767).astype(np.int16)

    # Create stereo by duplicating mono
    stereo = np.column_stack((audio, audio))

    return stereo, num_samples

def test_playback_speed(sample_rate, duration_sec=2.0):
    """Test actual playback speed at a specific sample rate"""
    print(f"\n{'='*70}")
    print(f"Testing sample rate: {sample_rate} Hz")
    print(f"Expected duration: {duration_sec:.3f} seconds")
    print(f"Expected samples: {int(sample_rate * duration_sec)}")
    print(f"{'='*70}")

    # Re-initialize pygame.mixer for this sample rate
    if pg.mixer.get_init():
        pg.mixer.quit()

    try:
        pg.mixer.pre_init(frequency=sample_rate, size=-16, channels=2, buffer=2048)
        pg.mixer.init()

        actual_freq, actual_size, actual_channels = pg.mixer.get_init()
        print(f"Requested:  {sample_rate} Hz, 16-bit, 2 channels")
        print(f"Actual:     {actual_freq} Hz, {actual_size}-bit, {actual_channels} channels")

        if actual_freq != sample_rate:
            print(f"⚠️  WARNING: pygame.mixer changed sample rate from {sample_rate} to {actual_freq}!")

        # Generate test tone
        print(f"\nGenerating {duration_sec}s test tone at {sample_rate} Hz...")
        audio_data, num_samples = generate_test_tone(sample_rate, duration_sec)

        # Create sound object
        sound = pg.sndarray.make_sound(audio_data)

        # Measure playback time
        print("Playing audio...")
        start_time = time.perf_counter()
        sound.play()

        # Wait for playback to finish
        while pg.mixer.get_busy():
            time.sleep(0.001)

        end_time = time.perf_counter()
        actual_duration = end_time - start_time

        # Calculate results
        expected_duration = duration_sec
        duration_error = actual_duration - expected_duration
        percent_error = (duration_error / expected_duration) * 100

        # If pygame used different sample rate, calculate what duration we'd expect
        if actual_freq != sample_rate:
            adjusted_duration = (num_samples / actual_freq)
            adjusted_error = actual_duration - adjusted_duration
            adjusted_percent = (adjusted_error / adjusted_duration) * 100

            print(f"\n📊 RESULTS:")
            print(f"  Expected duration:     {expected_duration:.3f} s (at {sample_rate} Hz)")
            print(f"  Adjusted duration:     {adjusted_duration:.3f} s (at {actual_freq} Hz)")
            print(f"  Actual duration:       {actual_duration:.3f} s")
            print(f"  Error vs requested:    {duration_error:+.3f} s ({percent_error:+.2f}%)")
            print(f"  Error vs actual rate:  {adjusted_error:+.3f} s ({adjusted_percent:+.2f}%)")

            # This is the effective playback speed multiplier
            speed_multiplier = expected_duration / actual_duration
            print(f"  ⚡ Speed multiplier:    {speed_multiplier:.4f}x")
            print(f"  (Audio plays {speed_multiplier:.4f}x {'faster' if speed_multiplier > 1 else 'slower'} than expected)")
        else:
            print(f"\n📊 RESULTS:")
            print(f"  Expected duration:     {expected_duration:.3f} s")
            print(f"  Actual duration:       {actual_duration:.3f} s")
            print(f"  Error:                 {duration_error:+.3f} s ({percent_error:+.2f}%)")

            if abs(percent_error) < 1.0:
                print(f"  ✅ PASS: Playback speed accurate")
            else:
                print(f"  ❌ FAIL: Playback speed error > 1%")

        return {
            'requested_rate': sample_rate,
            'actual_rate': actual_freq,
            'expected_duration': expected_duration,
            'actual_duration': actual_duration,
            'error_percent': percent_error,
            'speed_multiplier': expected_duration / actual_duration if actual_duration > 0 else 0
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return None
    finally:
        if pg.mixer.get_init():
            pg.mixer.quit()

if __name__ == "__main__":
    print("🎵 pygame.mixer Playback Speed Test")
    print("=" * 70)
    print(f"Platform: {sys.platform}")
    print(f"pygame version: {pg.version.ver}")
    print(f"Python version: {sys.version}")

    # Initialize pygame
    pg.init()

    # Test various sample rates
    test_rates = [15625, 8000, 22050, 44100]
    results = []

    for rate in test_rates:
        result = test_playback_speed(rate, duration_sec=2.0)
        if result:
            results.append(result)
        time.sleep(0.5)  # Brief pause between tests

    # Summary
    print("\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)
    print(f"{'Requested':>10} {'Actual':>10} {'Expected':>10} {'Actual':>10} {'Error':>10} {'Speed':>10}")
    print(f"{'Rate (Hz)':>10} {'Rate (Hz)':>10} {'Time (s)':>10} {'Time (s)':>10} {'(%)':>10} {'Mult':>10}")
    print("-"*70)

    for r in results:
        print(f"{r['requested_rate']:>10} {r['actual_rate']:>10} "
              f"{r['expected_duration']:>10.3f} {r['actual_duration']:>10.3f} "
              f"{r['error_percent']:>+10.2f} {r['speed_multiplier']:>10.4f}x")

    print("="*70)

    # Check if 15625 Hz (cutscene rate) has issues
    cutscene_result = next((r for r in results if r['requested_rate'] == 15625), None)
    if cutscene_result:
        print(f"\n🎬 CUTSCENE AUDIO ANALYSIS (15625 Hz):")
        if cutscene_result['actual_rate'] != 15625:
            print(f"   ⚠️  pygame changed rate to {cutscene_result['actual_rate']} Hz")
            print(f"   ⚡ Audio plays at {cutscene_result['speed_multiplier']:.4f}x speed")
            print(f"   📝 This explains why video/audio sync is off!")
        else:
            if abs(cutscene_result['error_percent']) > 5:
                print(f"   ⚠️  Playback error is {cutscene_result['error_percent']:.2f}%")
                print(f"   📝 This may explain sync issues")
            else:
                print(f"   ✅ Playback speed accurate ({cutscene_result['error_percent']:+.2f}%)")

    print("\n" + "="*70)
