# ThumbCommander Testing Guide

This guide explains how to test ThumbCommander on your PC using pygame.

## Two Testing Modes

### 1. Component Testing Mode (`test_pygame.py`)

**Purpose:** Test individual components without running the full game
**Use when:** You want to verify display, input, and basic mechanics

```bash
python3 test_pygame.py
```

**What it does:**
- Shows a test screen with button states
- Displays heat level simulation
- Shows animated bouncing box
- Tests keyboard input detection
- Verifies display rendering

**Good for:**
- ✓ Verifying keyboard controls work
- ✓ Testing display rendering
- ✓ Checking button input detection
- ✓ Quick validation of pygame setup

---

### 2. Full Game Mode (`run_game.py`)

**Purpose:** Run the complete ThumbCommander game
**Use when:** You want to test gameplay, AI, and all game features

```bash
python3 run_game.py
```

**What it does:**
- Loads the complete ThumbCommander game
- Runs the main menu
- Allows you to play all game modes:
  - **Asteroid Dodge** (game mode 0)
  - **Dog Fight** (game mode 1)
  - **Campaign** (game mode 2)
- Tests weapon heat system in real gameplay
- Tests enemy lead targeting AI
- Full game loop with menus

**Good for:**
- ✓ Testing weapon heat mechanics
- ✓ Testing enemy AI lead targeting
- ✓ Playing through missions
- ✓ Testing menu navigation
- ✓ Full gameplay experience
- ✓ Validating new features

---

## Controls (Both Modes)

Compatible with German QWERTZ and English QWERTY keyboards:

| Action | Key | Notes |
|--------|-----|-------|
| Move Up | ↑ (Arrow Up) | D-pad up |
| Move Down | ↓ (Arrow Down) | D-pad down |
| Move Left | ← (Arrow Left) | D-pad left |
| Move Right | → (Arrow Right) | D-pad right |
| Fire | **Y** | A button (primary action) |
| Secondary | X | B button |
| Previous Target | **Q** | LB button |
| Next Target | **W** | RB button |
| Menu/Pause | ESC | Menu button |

---

## Testing Your New Features

### Testing Weapon Heat System

1. Run full game mode:
   ```bash
   python3 run_game.py
   ```

2. Select "Dog Fight" from menu

3. Test rapid fire:
   - Hold or mash **Y key** rapidly
   - After ~5 shots, weapon should lock (overheat)
   - Heat bars (bottom right) should fill to maximum
   - Target reticle changes when overheated
   - Wait ~1 second for cooldown

4. Test burst fire:
   - Fire 3-4 shots
   - Pause briefly
   - Repeat
   - Heat should stay manageable

**Expected behavior:**
- 5 bars show heat level (0-5)
- Bars fill as you fire
- At 5 bars (100% heat), weapon locks
- Cannot fire when overheated
- Bars drain slowly when not firing
- Target reticle changes when overheated

---

### Testing Lead Targeting AI

1. Run full game mode:
   ```bash
   python3 run_game.py
   ```

2. Select "Dog Fight" from menu

3. Test scenarios:

**A. Stationary Target (you)**
   - Don't move or move very little
   - Enemies should hit you frequently
   - Expected: ~70-80% hit rate

**B. Straight Line Movement**
   - Move in one direction consistently
   - Enemies predict your path
   - Expected: ~60-70% hit rate (they lead your movement)

**C. Evasive Maneuvers**
   - Change direction frequently
   - Move erratically
   - Expected: ~30-40% hit rate (harder to predict)

**D. Chase Position**
   - Get behind an enemy
   - Enemy is in "CHASE" state
   - Expected: Enemy fires accurately when you're behind

**Expected AI behavior:**
- Enemies track your velocity
- They fire ahead of your position
- High-skill enemies (0.8-1.0) are very accurate
- Low-skill enemies (0.6-0.7) miss more often
- Moving unpredictably makes you harder to hit

---

## Troubleshooting

### "pygame not found"
```bash
pip install pygame
```

### Window doesn't open
- Check if you have display server running
- Try running in windowed environment

### Controls don't work
- Make sure window has focus (click on it)
- Press keys while game window is active
- Check keyboard layout matches controls

### Game crashes on load
- Verify all .COL.bin asset files exist
- Check console for error messages
- Ensure you're on pygame-test-harness branch

### Sprites look wrong
- This is expected - pygame uses placeholder colored rectangles
- Red = enemies
- Brown = asteroids
- Blue = shields
- Actual sprite loading not implemented in test harness

---

## Performance

**Target:** 60 FPS
**Display:** 512x512 window (4x scaled from 128x128)
**Platform:** Should run on any modern PC

If performance is poor:
- Close other applications
- Reduce window size in pygame_platform.py (change SCALE_FACTOR)
- Check CPU usage

---

## What's Not Implemented in Pygame Test

These features are stubbed out and won't work:
- ❌ Audio playback (silent)
- ❌ Cutscene animations (skipped)
- ❌ Actual sprite graphics (colored rectangles shown)
- ❌ Rumble/haptics

These features work fully:
- ✅ All game logic
- ✅ Enemy AI
- ✅ Weapon systems
- ✅ Collision detection
- ✅ Menu navigation
- ✅ Campaign system
- ✅ All input controls

---

## Development Workflow

**Recommended workflow for testing changes:**

1. **Make changes to game code** (ThumbCommander.py, etc.)
2. **Run component test** to verify no crashes:
   ```bash
   python3 test_pygame.py
   ```
3. **Run full game** to test gameplay:
   ```bash
   python3 run_game.py
   ```
4. **Validate new features** in actual gameplay
5. **Deploy to hardware** for final testing

---

## Quick Reference

```bash
# Install pygame
pip install pygame

# Component testing (basic functionality)
python3 test_pygame.py

# Full game testing (complete gameplay)
python3 run_game.py

# Controls: Arrows + Y(Fire) + X + Q/W + ESC
```

---

## Summary

- **Use `test_pygame.py`** for quick validation of display/input
- **Use `run_game.py`** for full gameplay testing
- Both support German QWERTZ keyboards
- Test your features in full game mode
- Deploy to hardware for final validation

Good luck testing! 🎮
