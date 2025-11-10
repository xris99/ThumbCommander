#!/usr/bin/env python3
"""
Validate expected playtime of intro video vs audio
"""

import sys
import os
import struct

def analyze_ima_audio(filename):
    """Analyze IMA ADPCM audio file"""
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Check for 4-byte header (sample rate)
    if len(data) >= 4:
        potential_rate = struct.unpack('<I', data[:4])[0]
        if potential_rate in [8000, 15625, 22050, 44100]:
            audio_data = data[4:]
            sample_rate = potential_rate
        else:
            audio_data = data
            sample_rate = 15625  # Assume default
        
        # IMA ADPCM: 2 samples per byte (4 bits per sample)
        num_samples = len(audio_data) * 2
        
        return {
            'file_size': len(data),
            'data_size': len(audio_data),
            'num_samples': num_samples,
            'sample_rate': sample_rate,
            'duration': num_samples / sample_rate
        }
    
    return None

def analyze_video_frames(filename):
    """Analyze video file to extract frame count"""
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Try to parse header
    # Format might be: [frame_count][width][height][fps][frame_data...]
    if len(data) >= 8:
        # Try different header formats
        frame_count = struct.unpack('<H', data[0:2])[0]
        width = struct.unpack('<H', data[2:4])[0]
        height = struct.unpack('<H', data[4:6])[0]
        
        # Check if this looks valid
        if 50 < frame_count < 5000 and 50 < width < 200 and 50 < height < 200:
            return {
                'file_size': len(data),
                'frame_count': frame_count,
                'width': width,
                'height': height
            }
    
    # Alternative: Maybe frame count is at a different position or 4 bytes
    frame_count_32 = struct.unpack('<I', data[0:4])[0]
    if 50 < frame_count_32 < 5000:
        return {
            'file_size': len(data),
            'frame_count': frame_count_32,
            'width': None,
            'height': None
        }
    
    return None

print("=" * 70)
print("CUTSCENE TIMING VALIDATION")
print("=" * 70)

# Find intro files
video_file = "intro_128_80.COL.bin"
audio_file = "intro_128_80.ima"

print(f"\nFiles:")
print(f"  Video: {video_file}")
print(f"  Audio: {audio_file}")

# Analyze audio
print(f"\n{'=' * 70}")
print("AUDIO ANALYSIS")
print("=" * 70)

audio_info = analyze_ima_audio(audio_file)
if audio_info:
    print(f"File size:           {audio_info['file_size']:,} bytes")
    print(f"Audio data:          {audio_info['data_size']:,} bytes")
    print(f"Sample rate:         {audio_info['sample_rate']} Hz")
    print(f"Number of samples:   {audio_info['num_samples']:,}")
    print(f"Duration:            {audio_info['duration']:.3f} seconds")

# Analyze video
print(f"\n{'=' * 70}")
print("VIDEO ANALYSIS")
print("=" * 70)

video_info = analyze_video_frames(video_file)
if video_info:
    print(f"File size:           {video_info['file_size']:,} bytes")
    print(f"Frame count:         {video_info['frame_count']}")
    if video_info['width']:
        print(f"Dimensions:          {video_info['width']}x{video_info['height']}")
    
    # Calculate durations at different FPS
    fps_values = [21, 26]
    durations = {}
    for fps in fps_values:
        dur = video_info['frame_count'] / fps
        durations[fps] = dur
        print(f"Duration at {fps:2d} FPS:  {dur:.3f} seconds ({video_info['frame_count']} frames)")

# Compare
if audio_info and video_info:
    print(f"\n{'=' * 70}")
    print("SYNC ANALYSIS")
    print("=" * 70)
    
    audio_dur = audio_info['duration']
    
    print(f"\nAudio duration:      {audio_dur:.3f} s  (at {audio_info['sample_rate']} Hz)")
    
    for fps in fps_values:
        video_dur = durations[fps]
        diff = audio_dur - video_dur
        pct = (diff / audio_dur) * 100
        
        print(f"Video at {fps} FPS:      {video_dur:.3f} s  (diff: {diff:+.3f} s, {pct:+.1f}%)")
    
    # Calculate perfect sync
    perfect_fps = video_info['frame_count'] / audio_dur
    perfect_audio_rate = audio_info['num_samples'] / durations[21]
    
    print(f"\n{'=' * 70}")
    print("PERFECT SYNC CALCULATIONS")
    print("=" * 70)
    print(f"For audio at {audio_info['sample_rate']} Hz:")
    print(f"  Video needs:       {perfect_fps:.2f} FPS")
    print(f"\nFor video at 21 FPS:")
    print(f"  Audio needs:       {perfect_audio_rate:.0f} Hz")
    
    print(f"\n{'=' * 70}")
    print("CONCLUSION")
    print("=" * 70)
    
    diff_21 = abs(audio_dur - durations[21])
    diff_26 = abs(audio_dur - durations[26])
    
    if diff_21 < diff_26:
        print(f"✓ 21 FPS is closer to audio duration (off by {diff_21:.3f}s)")
    else:
        print(f"✓ 26 FPS is closer to audio duration (off by {diff_26:.3f}s)")
    
    if diff_21 > 1.0:
        print(f"\n⚠️  MISMATCH DETECTED!")
        print(f"  Audio and video durations differ significantly at 21 FPS")
        print(f"  This means hardware is adjusting playback rates")
        print(f"\n📝 RECOMMENDATION: Implement dynamic audio resampling")
        print(f"  1. Measure actual video playtime")
        print(f"  2. Calculate: required_rate = num_samples / video_time")
        print(f"  3. Resample audio to match video duration")

print("=" * 70)
