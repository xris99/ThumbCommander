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

# Also install micropython as a builtin so it's available everywhere (needed for @micropython.viper decorators)
builtins.micropython = micropython_module

# Install const as a builtin so it can be used directly (needed for const(4) in methods)
builtins.const = const

# Patch array module to support 'O' typecode (object arrays) used in MicroPython
import array as _array_module
_original_array = _array_module.array

class MicroPythonArray:
    """Array wrapper that supports MicroPython's 'O' typecode for object arrays"""
    def __init__(self, typecode, initializer=None):
        if typecode == 'O':
            # Object array - just use a list
            self._is_object_array = True
            self._data = list(initializer) if initializer is not None else []
        else:
            # Use standard array for other types
            self._is_object_array = False
            if initializer is not None:
                self._data = _original_array(typecode, initializer)
            else:
                self._data = _original_array(typecode)

    def __getitem__(self, index):
        return self._data[index]

    def __setitem__(self, index, value):
        self._data[index] = value

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def append(self, value):
        if self._is_object_array:
            self._data.append(value)
        else:
            self._data.append(value)

    def extend(self, iterable):
        if self._is_object_array:
            self._data.extend(iterable)
        else:
            self._data.extend(iterable)

    def pop(self, index=-1):
        """Remove and return item at index (default last)"""
        if self._is_object_array:
            return self._data.pop(index)
        else:
            # Standard array doesn't have pop, convert to list, pop, rebuild
            temp = list(self._data)
            result = temp.pop(index)
            self._data = _original_array(self._data.typecode, temp)
            return result

    def __repr__(self):
        if self._is_object_array:
            return f"array('O', {self._data!r})"
        return repr(self._data)

# Replace array.array with our wrapper
_array_module.array = MicroPythonArray

# Also install it in builtins for direct import
builtins.array = MicroPythonArray
