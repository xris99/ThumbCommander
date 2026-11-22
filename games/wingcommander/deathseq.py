# deathseq.py - the death scene (docs/06 6.2): the pilot's face in the
# cockpit as the ship dies.
#
# Verbatim port of (wc1-re, GPL-3.0):
#   death_sequence  src/screens.c:1694  (0x439660)
# on the sprite sets tool/wc1_convert.py writes from PILOTANM.VGA
# section 0 (pil00.wcs, the death face, screens.c:1710) and PCSHIP.V0N
# section 3 (ckbg<N>.wcs, the cockpit background, screens.c:1711-1712).
#
# The scene fills the whole picture (rows 16..111, clip bottom 112):
# the original draws into the 320 x 200 space buffer and dumps it over
# the screen. scramble.py's _draw places each piece with the verified
# mapping; the face is anchored at the original (160, 199), which is
# device (64, 111) - the picture's bottom edge. One step every
# STEP_MS; any button breaks the loop (screens.c:1731-1732).
#
# Not ported, documented in docs/06 6.2:
#  - the music (track 0x20) and the explosion sound effect (:1713);
#  - the 60-frame 3D aftermath after the face (screens.c:1743-1756,
#    new_view(4, 0) with the explosion at frame 2): the flight has
#    already shown the kill that killed you;
#  - the palette fade to black: the port dims the picture with
#    G.dim_rows, the same fade the flight uses after a landing
#    (flight.py:429-432), then clears it black (screens.c:1763-1764).

import scramble as S
from time import ticks_ms, ticks_diff
from thumby_engine.platform import display
import ui
import wcdata as D
import wcgfx as G

FULL_Y1 = 112


def death(ship):
    """death_sequence: eight frames of the face, the cockpit behind it
    until the buffer goes clear at frame 7. The clear colour is
    cViewportClearColour = 15 (init.c:13), the space-buffer fill the
    flight uses. Only the four WC1 cockpits have backgrounds; any other
    player ship skips the scene. Returns True when a button cut it."""
    if ship not in (0, 1, 2, 3):
        return False
    face = S._set('pil00.wcs')        # screens.c:1710
    bg = S._set('ckbg%d.wcs' % ship)  # screens.c:1711-1712
    if face is None or bg is None:
        return False
    fb = display.buffer
    display.fill(0)
    clear = ui.pal565(15)             # init.c:13
    t0 = ticks_ms()
    esc = False
    for frame in range(8):            # screens.c:1717
        if frame == 7:                # screens.c:1718-1720
            G.fill_rows(fb, S.PIC_Y0, FULL_Y1, clear)
        else:                         # screens.c:1722-1724 (the
            S._draw(fb, bg, 0, 0, 0, FULL_Y1)   # RefreshCockpitStatus
        S._draw(fb, face, frame, 160, 199, FULL_Y1)    # :1726-1727
        display.update()              # dump_buffer_to_screen :1728
        while ticks_diff(ticks_ms(), t0) < (frame + 1) * S.STEP_MS:
            if S._key():
                esc = True
            display.update()
        if esc:                       # screens.c:1731-1732
            break
    ui.wait_release()
    # screens.c:1763-1764: fade the whole screen to black and clear it
    for _ in range(10):
        G.dim_rows(fb, 0, FULL_Y1)
        display.update()
    G.fill_rows(fb, 0, FULL_Y1, 0)
    return esc


def cleanup():
    """Let go of the cached sets between flights."""
    S.cleanup()
