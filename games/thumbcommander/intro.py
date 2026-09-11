# intro.py - boot intro for the original Thumby (1-bit target).
#
# Plays intro_74_30 (BIT/SHD) on an 8 Hz timer while the rest of the
# game loads. MainGame.py (Thumby branch) calls intro.init()/intro.start()
# at load time and intro.finish() once the title is reached. The color
# targets play a TDL8 cutscene instead and never import this module.
from time import sleep
from machine import Timer
from gc import collect

from thumby_engine.platform import display, PC, create_sprite

framecount = 0
frame = 0
intro_sprite = None
frametimer = Timer()

def init():
    global frame, framecount, intro_sprite

    display.fill(0)
    display.update()

    intro_sprite = create_sprite(74, 30, ("assets/intro_74_30.BIT.bin", "assets/intro_74_30.SHD.bin"), 0, 0, 0)
    # Center the sprite
    intro_sprite.x = (PC.WIDTH - intro_sprite.width) // 2
    intro_sprite.y = (PC.HEIGHT - intro_sprite.height) // 2

    framecount = intro_sprite.frameCount
    frame = 0

def drawframe(dummy):
    global frame, framecount, intro_sprite

    if intro_sprite is None:
        return

    intro_sprite.setFrame(frame)

    # Clear screen for each frame (important for color version)
    display.fill(0)
    display.drawSprite(intro_sprite)
    display.update()

    frame += 1
    if frame >= framecount:
        frametimer.deinit()
        sleep(1)

def start():
    frametimer.init(freq=8, mode=Timer.PERIODIC, callback=drawframe)

def finish():
    """Wait for intro to complete"""
    while frame < framecount:
        pass

    # Clean up
    global intro_sprite
    del intro_sprite
    collect()
