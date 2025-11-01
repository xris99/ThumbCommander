"""
MicroPython machine module stub for PC
"""


def freq(frequency=None):
    """Get or set CPU frequency - no-op on PC"""
    if frequency is None:
        return 200_000_000  # Return a dummy frequency
    # Setting frequency is a no-op on PC
    pass
