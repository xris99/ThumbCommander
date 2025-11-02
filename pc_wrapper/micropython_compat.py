"""
MicroPython compatibility layer for PC
Provides decorators and functions that exist in MicroPython but not in CPython
"""

import sys
from types import ModuleType


def const(value):
    """MicroPython const - returns the value as-is in CPython"""
    return value


def viper(func):
    """Viper decorator - no-op in CPython"""
    return func


def native(func):
    """Native decorator - no-op in CPython"""
    return func


def asm_thumb(func):
    """ASM thumb decorator - no-op in CPython"""
    return func


# Viper-specific pointer types - these are no-ops in CPython
class ptr32:
    """Pointer to 32-bit integers - for viper compatibility"""
    def __init__(self, obj):
        if isinstance(obj, (list, bytearray, bytes, memoryview)):
            self._obj = obj
        elif hasattr(obj, '__iter__'):
            self._obj = list(obj)
        else:
            self._obj = [obj]

    def __getitem__(self, index):
        if isinstance(self._obj, (bytearray, bytes, memoryview)):
            # For byte-like objects, return 4-byte chunks as 32-bit int
            idx = index * 4
            if idx + 3 < len(self._obj):
                return (self._obj[idx] | (self._obj[idx+1] << 8) |
                        (self._obj[idx+2] << 16) | (self._obj[idx+3] << 24))
            return 0
        return self._obj[index] if index < len(self._obj) else 0

    def __setitem__(self, index, value):
        if isinstance(self._obj, bytearray):
            idx = index * 4
            if idx + 3 < len(self._obj):
                self._obj[idx] = value & 0xFF
                self._obj[idx+1] = (value >> 8) & 0xFF
                self._obj[idx+2] = (value >> 16) & 0xFF
                self._obj[idx+3] = (value >> 24) & 0xFF
        elif index < len(self._obj):
            self._obj[index] = value


class ptr8:
    """Pointer to 8-bit integers - for viper compatibility"""
    def __init__(self, obj):
        self._obj = obj

    def __getitem__(self, index):
        if hasattr(self._obj, '__getitem__') and index < len(self._obj):
            return self._obj[index]
        return 0

    def __setitem__(self, index, value):
        if hasattr(self._obj, '__setitem__') and index < len(self._obj):
            self._obj[index] = value & 0xFF


class ptr16:
    """Pointer to 16-bit integers - for viper compatibility"""
    def __init__(self, obj):
        self._obj = obj

    def __getitem__(self, index):
        if isinstance(self._obj, (bytearray, bytes, memoryview)):
            idx = index * 2
            if idx + 1 < len(self._obj):
                return self._obj[idx] | (self._obj[idx+1] << 8)
            return 0
        elif index < len(self._obj):
            return self._obj[index]
        return 0

    def __setitem__(self, index, value):
        if isinstance(self._obj, bytearray):
            idx = index * 2
            if idx + 1 < len(self._obj):
                self._obj[idx] = value & 0xFF
                self._obj[idx+1] = (value >> 8) & 0xFF
        elif index < len(self._obj):
            self._obj[index] = value


# Create a proper module object for micropython
micropython_module = ModuleType('micropython')
micropython_module.const = const
micropython_module.viper = viper
micropython_module.native = native
micropython_module.asm_thumb = asm_thumb

# Add pointer types to the module so they can be imported globally in viper functions
import builtins
builtins.ptr32 = ptr32
builtins.ptr8 = ptr8
builtins.ptr16 = ptr16

# Install micropython module in sys.modules so it can be imported
sys.modules['micropython'] = micropython_module
