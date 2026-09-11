"""
Thumby hardware module stub for PC
"""

import sys


# Button pin constants (for original Thumby compatibility)
swA = 4
swB = 5
swU = 0
swD = 1
swL = 2
swR = 3


def reset():
    """Reset the system - exit on PC"""
    print("Reset called - exiting")
    sys.exit(0)
