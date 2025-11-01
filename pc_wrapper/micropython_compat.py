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


# Create a proper module object for micropython
micropython_module = ModuleType('micropython')
micropython_module.const = const
micropython_module.viper = viper
micropython_module.native = native
micropython_module.asm_thumb = asm_thumb

# Install micropython module in sys.modules so it can be imported
sys.modules['micropython'] = micropython_module
