"""Readers for the original Wing Commander (1990, DOS) data files.

Host-side only (CPython): used by tool/wc1_convert.py to turn a player's
own GAMEDAT directory into the compact asset pack the ThumbyColor game
loads. Nothing in here runs on the device.

The file formats and tables were taken from the reconstructed game
source at https://github.com/neuromancer/wc1-re (GPL-3.0):

  packet.py  - Origin packet container + LZW      (src/pload.c,
                                                   src/sdl/resources.c)
  shape.py   - RLE shape packets -> bitmaps       (src/gr.c)
  gfx.py     - resampling, palette matching and the output formats
  mission.py - MODULE / CAMP / BRIEFING records   (src/cmpgn.c,
                                                   include/wcdata.h)
  tables.py  - ship and weapon statistics, AI and campaign tables the
               game keeps inside WC.EXE           (src/objdata.c,
                                                   src/game.c, ...)
"""
