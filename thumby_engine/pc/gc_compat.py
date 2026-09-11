"""
Garbage collection compatibility module
Wraps Python's gc module with MicroPython-compatible API
"""

import gc as _gc
import sys


def collect():
    """Run garbage collection"""
    _gc.collect()


def mem_free():
    """Get free memory (approximate on PC)"""
    # On PC, we can't get real free memory, so return a large dummy value
    return 100000


def mem_alloc():
    """Get allocated memory (approximate on PC)"""
    # Return a dummy value
    return 50000


def enable():
    """Enable garbage collection"""
    _gc.enable()


def disable():
    """Disable garbage collection"""
    _gc.disable()


def isenabled():
    """Check if garbage collection is enabled"""
    return _gc.isenabled()


def threshold(value=None):
    """Get or set collection threshold"""
    if value is None:
        return _gc.get_threshold()[0]
    else:
        _gc.set_threshold(value)
