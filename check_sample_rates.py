#!/usr/bin/env python3
"""Check sample rates of all IMA files"""
import struct
import os
import glob

print("IMA File Sample Rates:")
print("=" * 80)

for ima_file in sorted(glob.glob("*.ima")):
    if os.path.exists(ima_file):
        with open(ima_file, "rb") as f:
            magic = f.read(4)
            if magic == b'IMAA':
                sample_rate = struct.unpack('<I', f.read(4))[0]
                sample_count = struct.unpack('<I', f.read(4))[0]
                duration = sample_count / sample_rate
                print(f"{ima_file:25s} : {sample_rate:6d} Hz  ({duration:6.2f}s, {sample_count:8d} samples)")
            else:
                print(f"{ima_file:25s} : Invalid IMA file (magic={magic})")

print("=" * 80)
