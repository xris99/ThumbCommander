# ThumbCommander PC Wrapper - Implementation Summary

## ✅ Final Architecture

### Design Philosophy
**Use original hardware implementation unchanged, provide only necessary engine stubs**

```
Original thumbycolor_native.py (root directory - UNCHANGED)
    ↓ imports
pc_wrapper/engine_draw.back_fb() → BackFrameBuffer object
    ↓
engine_draw.BackFrameBuffer.blit() → renders to pygame surface
    ↓
pc_wrapper/engine.tick() → handles timing + button input
    ↓
pygame window displays game
```

## Key Files

### Root Directory (Game Files - Unchanged)
- `thumbycolor_native.py` - Original hardware implementation (uses @micropython.viper decorators)
- `cutscene_utils.py` - Original cutscene handling with GS8 palette support
- `ThumbCommander.py` - Main game file (minimal path fix for PC)
- `platform_loader.py` - Platform detection and module loading
- All other game files unchanged

### PC Wrapper Directory (pc_wrapper/)

#### 1. `engine_draw.py` ⭐ Key Module
```python
class BackFrameBuffer:
    """Mimics hardware engine's back framebuffer"""
    def blit(self, source_fb, x, y, key=-1, palette=None):
        """
        Renders framebuffer to pygame surface
        - Converts RGB565 to RGB888
        - Draws to pygame window
        - Handles pygame events
        """

def back_fb():
    """Returns singleton BackFrameBuffer instance"""
```

**Purpose:** Original `thumbycolor_native.py` calls `back_fb()` in `__init__` and `blit()` in `update()`. This provides pygame rendering without modifying the original code.

#### 2. `engine.py` ⭐ Timing & Input
```python
def fps_limit(fps=None):
    """Get/set FPS limit (mimics hardware engine)"""

def time_to_next_tick():
    """Returns milliseconds until next frame"""

def tick():
    """
    Main engine loop:
    1. FPS limiting (busy-wait for precision)
    2. Button input polling (calls ButtonClass.update_all_buttons())
    3. Timing update
    """
```

**Purpose:** Provides timing functions that original `thumbycolor_native.py` expects. `tick()` handles both timing and button input.

#### 3. `framebuf.py` - FrameBuffer Implementation
```python
class FrameBuffer:
    """1:1 copy of MicroPython FrameBuffer"""

    # Supported formats:
    - RGB565 (16-bit color)
    - GS8 (8-bit indexed color for cutscenes)

    # Methods:
    - pixel(x, y, col=None)
    - fill(col) / fill_rect(x, y, w, h, col)
    - text(s, x, y, col)  # Uses embedded 8x8 font
    - line(x0, y0, x1, y1, col)
    - rect(x, y, w, h, col, fill=False)
    - blit(source, x, y, key=-1, palette=None)  # Palette support for GS8→RGB565
    - scroll(dx, dy)
```

**Key Fix:** Added GS8 format support in `pixel()` method - critical for cutscene rendering.

#### 4. `micropython_compat.py` - MicroPython Compatibility
```python
# Decorators (no-ops on PC)
@micropython.viper → return function unchanged
@micropython.native → return function unchanged
const(value) → return value

# Pointer types for viper functions
ptr8, ptr16, ptr32 → wrap arrays for pointer-like access

# Critical: Install as builtin
builtins.micropython = micropython_module
```

**Purpose:** Makes `@micropython.viper` decorators in original `thumbycolor_native.py` work on PC.

#### 5. `thumbyButton.py` - Button Input
```python
class ButtonClass:
    """Maps keyboard keys to button states"""

    @classmethod
    def update_all_buttons():
        """
        Called by engine.tick()
        Polls pygame keyboard state
        Updates button states (current, previous, just_pressed)
        """

    def pressed(self):
        """Returns True if button currently pressed"""

    def justPressed(self):
        """Returns True if button pressed this frame"""
```

**Keyboard Mapping:**
- Arrow Keys → D-pad
- Z → Button A (Fire)
- X → Button B
- A → Left Bumper
- S → Right Bumper
- ESC → Menu

#### 6. Other Modules
- `audio.py` - Audio playback stubs (loads/plays .ima files)
- `engine_io.py` - Hardware button constants
- `utime.py`, `machine.py`, `gc_compat.py` - MicroPython compatibility
- `grayscale.py`, `Intro.py`, `thumbyHardware.py` - Grayscale Thumby support

## Data Flow

### Rendering Flow
```
1. Game draws to display.internal_fb (FrameBuffer RGB565)
   ↓
2. display.update() called
   ↓
3. thumbycolor_native.update():
   - Waits for next tick: while time_to_next_tick() > 0: pass
   - Blits to engine: self.engine_fb.blit(self.internal_fb, 0, 0)
   - Calls tick()
   ↓
4. BackFrameBuffer.blit():
   - Converts RGB565 → RGB888
   - Draws to pygame surface
   - pygame.display.flip()
   ↓
5. engine.tick():
   - Enforces FPS limit
   - Polls button input
   - Updates timing
```

### Cutscene Rendering (GS8 with Palette)
```
1. cutscene_utils.py loads 8-bit indexed frames (GS8 format)
   ↓
2. Creates palette (256 RGB565 colors)
   ↓
3. Blits GS8 frame to display with palette:
   display.internal_fb.blit(gs8_frame, x, y, 0, palette)
   ↓
4. FrameBuffer.blit() reads GS8 pixels, maps through palette, writes RGB565
   ↓
5. Normal rendering flow continues
```

## Testing

### Run Comprehensive Test
```bash
python test_comprehensive.py
```

**Tests:**
1. ✅ Module imports (all pc_wrapper modules)
2. ✅ FrameBuffer GS8 support + palette blit
3. ✅ Engine timing functions (fps_limit, time_to_next_tick, tick)
4. ✅ Original thumbycolor_native.py import
5. ✅ Game startup (platform_loader, display initialization)

### Run Game
```bash
python run_pc.py
```

**Expected Output:**
```
ThumbyColor display initialized. Free memory: 100000
Audio and Color Cutscene initialized. Free memory: 100000
Playing 8-bit delta cutscene: 128x80, 495 frames (intro)
Playing 8-bit delta cutscene: 128x80, 210 frames (title)
[Game menu appears]
```

## What Works

✅ **Cutscenes** - GS8 format with palette mapping
✅ **Sprites** - .COL.bin loading and rendering with transparency
✅ **Text** - Embedded 8x8 font rendering
✅ **Background images** - Full-width sprite loading
✅ **Button input** - Keyboard mapping with pressed/justPressed
✅ **Audio** - .ima file playback
✅ **FPS limiting** - Precise timing with busy-wait
✅ **Viper functions** - @micropython.viper decorators work

## Files Changed in Game

**Minimal changes for PC compatibility:**

### ThumbCommander.py
```python
# Added PC path fallback
import os
if os.path.exists("/Games/ThumbCommander/"):
    loc = "/Games/ThumbCommander/"
else:
    loc = ""  # Current directory for PC
```

### platform_loader.py
```python
# Added micropython import (line 4)
import micropython
```

### Other files
- `platform_constants.py`, `campaign_engine.py` - Added `import micropython` and `const` fallback
- No other changes to game logic!

## Summary

This implementation follows your exact architectural requirements:

1. ✅ **Original `thumbycolor_native.py` used unchanged** (from root directory)
2. ✅ **`engine_draw.py` provides `back_fb()` object** for pygame rendering
3. ✅ **`back_fb.blit()` renders to pygame surface** (converts RGB565→RGB888)
4. ✅ **`engine.tick()` handles timing + button polling** (mimics hardware engine)
5. ✅ **Original cutscene_utils.py used** (GS8 palette rendering works)
6. ✅ **Minimal game file changes** (only path fallback and micropython imports)

The wrapper provides only what the hardware engine would provide, keeping all game logic in the original files!
