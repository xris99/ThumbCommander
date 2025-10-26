"""
machine.py - PC stub for MicroPython machine module
"""

def freq(hz=None):
    """Stub for CPU frequency control - does nothing on PC"""
    if hz is None:
        # Return a fake frequency
        return 300_000_000
    # Setting frequency does nothing on PC
    pass

def reset():
    """Reset the system - exits on PC"""
    print("Machine reset called - exiting...")
    import sys
    sys.exit(0)

def soft_reset():
    """Soft reset - exits on PC"""
    reset()
