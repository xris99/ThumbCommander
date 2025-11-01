#!/usr/bin/env python3
"""Test that the game loads successfully"""
import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

print("Testing game load...")

# Monkey-patch cutscene player to skip cutscenes
import cutscene_utils
def skip_cutscene(filename, fps, cancel_callback=None):
    print(f"  Skipping cutscene: {filename}")
cutscene_utils.play_cutscene_animation = skip_cutscene

print("Loading ThumbCommander...")
try:
    import ThumbCommander as game
    print("✓ Game loaded successfully!")
    print(f"  - DEFAULT_KEYS type: {type(game.DEFAULT_KEYS)}")
    print(f"  - SHIFT_REQUIRED type: {type(game.SHIFT_REQUIRED)}")
    print(f"  - DEFAULT_KEYS[0]: {game.DEFAULT_KEYS[0]}")
    print(f"  - SHIFT_REQUIRED[0]: {game.SHIFT_REQUIRED[0]}")
except Exception as e:
    print(f"✗ Error loading game: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n✓ All tests passed!")
