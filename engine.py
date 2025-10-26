"""
engine.py - PC stub for ThumbyColor engine module
Provides CPU frequency control stubs for PC
"""

def freq(hz=None):
    """Stub for CPU frequency control - does nothing on PC"""
    if hz is None:
        # Return a fake frequency
        return 300_000_000
    # Setting frequency does nothing on PC
    pass
