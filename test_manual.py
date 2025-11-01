#!/usr/bin/env python3
"""Manual test - window stays open for 10 seconds"""
import os
os.environ['SDL_AUDIODRIVER'] = 'dummy'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from platform_loader import display, PC, buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, buttonMENU
import time

print("Manual test - window open for 10 seconds")
print("Try pressing: arrows, Z, X, Q, W, ESC")
print()

# Check button registration
print(f"Buttons registered with display: {hasattr(display, '_buttons')}")
if hasattr(display, '_buttons'):
    print(f"Number of buttons: {len(display._buttons)}")

start = time.time()
frame = 0
while time.time() - start < 10:
    frame += 1

    # Draw background
    display.fill(PC.BLACK)

    # Draw title
    display.drawText("BUTTON TEST", 20, 10, PC.WHITE)
    display.drawText(f"Frame: {frame}", 20, 30, PC.YELLOW)

    # Check button states and display
    y = 50
    if buttonU.pressed():
        display.drawText("UP: PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("UP: released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonD.pressed():
        display.drawText("DOWN: PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("DOWN: released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonL.pressed():
        display.drawText("LEFT: PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("LEFT: released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonR.pressed():
        display.drawText("RIGHT: PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("RIGHT: released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonA.pressed():
        display.drawText("A (Z): PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("A (Z): released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonB.pressed():
        display.drawText("B (X): PRESSED", 10, y, PC.GREEN)
    else:
        display.drawText("B (X): released", 10, y, PC.DARKGRAY)
    y += 10

    if buttonMENU.pressed():
        display.drawText("MENU (ESC): PRESSED", 10, y, PC.GREEN)
        break
    else:
        display.drawText("MENU (ESC): released", 10, y, PC.DARKGRAY)

    display.update()

print("\n✓ Manual test complete")
