"""
MicroPython compatibility layer for PC
Provides decorators and functions that exist in MicroPython but not in CPython
"""

# MicroPython decorators - these are no-ops in CPython
class micropython:
    @staticmethod
    def viper(func):
        """Viper decorator - no-op in CPython"""
        return func

    @staticmethod
    def native(func):
        """Native decorator - no-op in CPython"""
        return func

    @staticmethod
    def asm_thumb(func):
        """ASM thumb decorator - no-op in CPython"""
        return func


def const(value):
    """MicroPython const - returns the value as-is in CPython"""
    return value


# Install micropython module in sys.modules so it can be imported
import sys
sys.modules['micropython'] = micropython
