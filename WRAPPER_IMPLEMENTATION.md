# PC Wrapper Implementation Details

## Overview

This wrapper allows the ThumbyColor version of ThumbCommander to run on a PC without any modifications to the game code. All compatibility is handled through wrapper modules that are injected before the game starts.

## Architecture

### Module Injection Strategy

The wrapper uses Python's `sys.modules` to inject compatibility modules before the game imports them:

```python
sys.path.insert(0, PC_WRAPPER_DIR)  # Add wrapper to path first
sys.modules['micropython'] = micropython_compat  # Inject modules
sys.modules['framebuf'] = framebuf
# ... etc
```

This ensures that when the game code does `import framebuf`, it gets our PC-compatible version instead of trying to import the MicroPython module.

## Key Components

### 1. MicroPython Compatibility (`micropython_compat.py`)

**Purpose**: Make MicroPython-specific decorators and functions work in CPython.

**Implementation**:
- `@micropython.viper` → no-op decorator (returns function unchanged)
- `@micropython.native` → no-op decorator
- `const(value)` → returns value as-is

The viper decorator in MicroPython compiles functions to native code for speed. On PC, we can't do this, but the Python code runs fine without it.

### 2. Framebuffer (`framebuf.py`)

**Purpose**: Implement MicroPython's `framebuf.FrameBuffer` class with RGB565 support.

**Key Features**:
- RGB565 format support (16-bit color: 5R 6G 5B)
- Pixel-level operations (get/set)
- Drawing primitives (line, rectangle, filled rectangle)
- Blit operation for copying framebuffers
- Compatible buffer layout with MicroPython

**RGB565 Implementation**:
```python
# Set pixel: store as 2 bytes (little endian)
self.buffer[idx] = color & 0xFF
self.buffer[idx + 1] = (color >> 8) & 0xFF

# Get pixel: reconstruct from 2 bytes
return self.buffer[idx] | (self.buffer[idx + 1] << 8)
```

### 3. Display Wrapper (`thumbycolor_native.py`)

**Purpose**: Emulate ThumbyColor's display using pygame.

**Key Features**:

#### ColorDisplay Class
- Creates a pygame window (128x128 scaled to 512x512)
- Maintains an internal RGB565 framebuffer
- Converts RGB565 to RGB888 for pygame rendering
- Provides all ThumbyColor display methods:
  - `fill(color)` - fill screen
  - `setPixel(x, y, color)` - set pixel
  - `drawLine()`, `drawRectangle()`, `drawFilledRectangle()`
  - `drawText()` - text rendering
  - `drawSprite()`, `drawSpriteWithScale()` - sprite rendering
  - `draw_sprite_from_file()` - load and draw .COL.bin files
  - `update()` - blit framebuffer to screen

#### RGB565 to RGB888 Conversion
```python
def rgb565_to_rgb888(self, color565):
    r = ((color565 >> 11) & 0x1F) * 255 // 31
    g = ((color565 >> 5) & 0x3F) * 255 // 63
    b = (color565 & 0x1F) * 255 // 31
    return (r, g, b)
```

#### ColorSprite Class
- Loads sprites from .COL.bin files
- Parses filenames to extract dimensions (e.g., `sprite_56_47.COL.bin`)
- Supports frame-based animation
- Implements scaling with nearest-neighbor algorithm
- Handles mirroring (mirrorX, mirrorY)
- Respects transparent color key

**Sprite File Format**:
- RGB565 format (2 bytes per pixel, little endian)
- Multiple frames concatenated
- Filename encodes dimensions: `name_WIDTH_HEIGHT.COL.bin`

### 4. Input System (`thumbyButton.py`)

**Purpose**: Map keyboard keys to Thumby button states.

**Implementation**:
- Maintains button state for each button (current, previous, just_pressed)
- Updates all buttons once per frame from pygame key states
- Provides Thumby-compatible API:
  - `pressed()` - check if button is currently pressed
  - `justPressed()` - check if button was just pressed this frame

**Keyboard Mapping**:
```python
key_mapping = {
    'A': pygame.K_z,          # Fire
    'B': pygame.K_x,          # Secondary
    'UP': pygame.K_UP,        # D-Pad Up
    'DOWN': pygame.K_DOWN,    # D-Pad Down
    'LEFT': pygame.K_LEFT,    # D-Pad Left
    'RIGHT': pygame.K_RIGHT,  # D-Pad Right
    'LB': pygame.K_a,         # Left Bumper
    'RB': pygame.K_s,         # Right Bumper
    'MENU': pygame.K_ESCAPE,  # Menu
}
```

### 5. Hardware Stubs

All hardware-specific modules are stubbed out:

#### Audio (`audio.py`)
- Logs audio operations but doesn't play sound
- Maintains state for compatibility
- All functions are no-ops

#### Engine (`engine.py`, `engine_io.py`)
- `engine.freq()` - no-op (CPU frequency control)
- `engine_io.*` - button constants

#### Time (`utime.py`)
- Wraps Python's `time` module
- Provides MicroPython's tick functions:
  - `ticks_ms()`, `ticks_us()` - millisecond/microsecond counters
  - `ticks_diff()` - calculate tick differences
  - `sleep_ms()`, `sleep_us()` - sleep functions

#### Machine (`machine.py`)
- `freq()` - no-op frequency control

#### GC (`gc_compat.py`)
- Wraps Python's `gc` module
- `mem_free()`, `mem_alloc()` - return dummy values (PC has plenty of RAM)

## How Game Code Remains Unchanged

The game code uses MicroPython features like this:

```python
@micropython.viper
def rotate_z_x(x:int, y:int, angle:int) -> int:
    a:int = fpmul(x, fpcos(angle))
    b:int = fpmul(y, fpsin(angle))
    return int(a - b)
```

Our wrapper makes this work by:
1. **Decorator**: `@micropython.viper` becomes a no-op, function runs as normal Python
2. **Type Hints**: `:int` type hints are valid Python 3 syntax, ignored at runtime
3. **Fixed Point Math**: Functions like `fpmul` are defined in game code, work in both MicroPython and Python

The game's platform detection:
```python
try:
    import engine_io
    IS_THUMBY_COLOR = True
except ImportError:
    IS_THUMBY_COLOR = False
```

Works because we provide `engine_io` module, so the game thinks it's running on ThumbyColor!

## Framebuffer Flow

1. **Game creates framebuffer**:
   ```python
   hud_buffer = bytearray(24 * 24 * 2)
   hud_fb = FrameBuffer(hud_buffer, 24, 24, RGB565)
   ```

2. **Game draws to framebuffer**:
   ```python
   hud_fb.rect(x, y, w, h, color, True)
   hud_fb.pixel(x, y, color)
   ```

3. **Game blits to display framebuffer**:
   ```python
   display.internal_fb.blit(hud_fb, x, y, key)
   ```

4. **Display updates pygame window**:
   ```python
   display.update()  # Converts RGB565 → RGB888 → pygame
   ```

## Performance Considerations

### Fast Operations
- Framebuffer operations are in-memory (bytearray)
- Drawing primitives use simple algorithms
- No GPU acceleration needed for 128x128

### Slow Operations
- Sprite rendering (pixel-by-pixel)
- RGB565 to RGB888 conversion (128x128 pixels)
- Full screen update every frame

### Optimizations Possible
- Use numpy for faster buffer operations
- Use pygame surfaces instead of pixel-by-pixel
- Batch sprite rendering
- Convert sprites to pygame surfaces once

However, for 128x128 at 60 FPS, current implementation is sufficient on modern PCs.

## Testing the Wrapper

To run the game:
```bash
pip install pygame
python run_pc.py
```

The wrapper will:
1. Set up Python path to include pc_wrapper
2. Inject all compatibility modules
3. Create dummy /lib directory and font files
4. Import and run ThumbCommander.py

## Debugging

Enable debug output by modifying wrapper modules to add print statements:
- `thumbycolor_native.py` - sprite loading and rendering
- `thumbyButton.py` - button presses
- `audio.py` - audio operations

## Limitations

1. **No Sound**: Audio is stubbed out (could be implemented with pygame.mixer)
2. **No Rumble**: Haptic feedback not available on PC
3. **Performance**: Not representative of actual hardware
4. **File Paths**: Some paths may need adjustment (currently assumes game directory structure)

## Future Enhancements

1. **Audio Support**: Implement audio playback using pygame.mixer or similar
2. **Better Sprite Rendering**: Use pygame surfaces for faster rendering
3. **Gamepad Support**: Add support for USB game controllers
4. **Save State**: Implement save/load functionality
5. **Recording**: Add video recording capability
6. **Debugging Tools**: Add sprite viewer, memory monitor, etc.
