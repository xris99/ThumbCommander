# 3. The converter and the converted assets

The device never sees an original file. `tool/wc1_convert.py` reads
them on a PC and writes `games/wingcommander/assets/`: small files
with fixed layouts that MicroPython can `seek` into.

```
tool/wc1_convert.py     the pipeline (class Converter, one method per asset kind)
tool/wc1/packet.py      archive container + LZW
tool/wc1/shape.py       shape frames -> indexed bitmaps, palette reader
tool/wc1/gfx.py         resampling, palette matching, .wcs and .COL.bin writers
tool/wc1/mission.py     MODULE / CAMP / BRIEFING record readers (checks, --dump)
tool/wc1/tables.py      tables copied out of wc1-re (what WC.EXE compiles in)
tool/wc1_inspect.py     read-only viewer for everything not converted yet
```

Run: `python3 tool/wc1_convert.py WING [--out DIR] [--preview]
[--quiet] [--dump SERIES MISSION]`. `--preview` also writes PNG contact
sheets to `assets/_preview/` - use it after every change to a picture
converter. Needs numpy; Pillow for previews.

## 3.1 The scaling rule

The original is 320x200 with pixels 1.2 times taller than wide. The
ThumbyColor shows a 128x96 picture with square pixels. So:

```
x_thumby = x_orig * 128 / 320 = x * 0.40      (gfx.SCREEN_SX)
y_thumby = y_orig *  96 / 200 = y * 0.48      (gfx.SCREEN_SY)
```

The different factors are the aspect correction. Every coordinate
copied from wc1-re (a mouth origin, a sprite position in a cutscene,
a display rectangle) goes through these two factors.

Pictures are **resampled by area averaging in RGB with premultiplied
alpha**, then matched to the nearest palette entry (weights 2:4:3 for
R:G:B). Nearest-neighbour scaling to 40 % destroys thin features
(cockpit struts, eyes). Flight sprites are stored 1.25 times finer
than screen scale (`SHIP_RES = 80`, in 64ths) because the renderer
zooms them; effects that would exceed 1,400 pixels per frame are
stored coarser.

`gfx.scale_frame` pads a frame so its hot spot falls on a whole output
pixel, and returns the scaled hot spot. Sprites that must line up with
each other after scaling (overlays on a head, tiles of a background)
need more care - see 5.6.

## 3.2 Converted files

All little-endian. Loaders are in `wcdata.py`.

| File | Built from | Layout |
|------|-----------|--------|
| `pal.wc` | GAME.PAL | 256 x u16 RGB565 |
| `types.wc` | `tables.TYPES` etc. | header `u8 types, fields, max weapons, name size`; then one int32 array per field (struct of arrays), weapon loadouts, names, 56 child offsets, the 2 x 186 view-direction tables, animation streams |
| `ai.wc` | `tables.*` | `'WCA1'`, manoeuvre tables for 13 named pilots and 5 Kilrathi levels, aggression / recovery / turn interval, formations, gun delays, conversation colours, pilot roster, rank and medal names, player damage table |
| `sh<NN>.wcs` | SHIPTYPE / SHIP .Vnn | sprite set, 37 views |
| `ms.wcs`, `fx<NN>.wcs`, `hud.wcs` | SHIPTYPE.V29, OBJECTS.VGA, COCKPIT.VGA 0 | sprite sets |
| `ck<N>.wc` | PCSHIP.V0N sections 0 and 6 | `'WCK1'`, view window, radar, two display rectangles (u8 each, already scaled), then 128x96 palette indices, 0 = see-through |
| `font<N>.wc` | FONTS.FNT | `u8 height, u8 bytes per row, u8 width[256]`, 256 glyphs at 1 bit per pixel (MSB left); **not scaled** |
| `mod<C>.wc` | MODULE.00C | `'WCM1', u16 count, u16 stride`, 64 mission records (header + nav + objectives + ships + aux, unpacked and concatenated), then the series names |
| `camp<C>.wc` | CAMP.00C | `'WCC1', u8 n, u16 size[n]`, the sections |
| `brf<C>.wc` | BRIEFING.00C | `'WCB1', u32 n`, `n x (u32 offset, u32 size)`, the unpacked packets. Records are byte-identical to the original, **including the mouth and face strings** |
| `comm.wc`, `comm2.wc` | COMMUNIC.DAT, COMMSM2.DAT | byte copies (currently unused) |
| `*_128_NN.COL.bin` | TITLE / RECROOM / BRIEFING .VGA | the engine's picture format: `u16 w, h, frames, flags`, RGB565 rows |
| `sfx_*.ima` | synthesised in `convert_sounds` | the engine's IMA-ADPCM format, 15,625 Hz; **not Origin data** |

### The sprite set (.wcs)

```
4s  'WCS1'
u8  frame count
u8  res            stored pixels per screen pixel, in 64ths (64 = 1:1)
u16 largest frame, bytes
per frame:  u32 data offset, u8 w, u8 h, i8 hot_x, i8 hot_y
pixels      8-bit palette indices, row major, 0 = transparent
```

Limits: a frame is at most 255 x 255 and the hot spot must fit an
`i8`. `wcdata.SpriteSet` keeps only the frame table in RAM and opens
the file when a frame is needed. `wcdata.FrameCache` holds decoded
frames in fixed pools (10 buffers of 2,112 bytes, 3 of 8,000) so the
flight loop never allocates; a frame larger than 8,000 bytes cannot be
shown through the cache.

Index 0 doubles as "transparent", so the palette matcher never
returns 0 for an opaque pixel.

## 3.3 What is *not* converted yet

| Needed for | Source | Suggested output | Chapter |
|-----------|--------|------------------|---------|
| talking heads | TALKING.VGA 0-11 (TALKING1.VGA) | one file per face: head + mouth and eye patches | 5 |
| briefing-room shots, medals, office | BRIEFING.VGA 1-5, 7-10 | sprite sets + a table of positions | 5, 6 |
| bar | RECROOM.VGA 1, 3-11 | sprite sets | 5 |
| "Meanwhile..." scenes | MIDGAME.Vnn | sprite sets + a compiled script | 6 |
| launch, landing, death, ejection | SCRAMBLE.VGA, PILOTANM.VGA, PCSHIP 5, 8 | sprite sets + scene tables | 6 |
| radio portraits | WINGMEN.VGA | one small sprite set | 7 |
| music | MUSIC.MID, WINGLDR.TIM 1 | compiled songs + timbre bank | 8, 10 |
| sound effects | records from wc1-re | a table next to the timbres | 9 |

## 3.4 Adding an asset kind: the recipe

1. **Look first.** `wc1_inspect.py WING sections FILE`, then
   `shape FILE N --png /tmp/x` and view the frames. Note sizes and hot
   spots.
2. **Find the consumer in wc1-re** (grep `FetchDiskPacketRetrying(<logical>,`)
   and read how frames are positioned and timed.
3. **Add a `convert_<kind>` method** to `Converter`, call it from
   `run()`, write through `self.write` / `gfx.write_sprite_set` so the
   size total and `--preview` keep working. Give the file a 4-byte
   magic with a version digit.
4. **Budget it.** Print the size in the converter's log. Flash is
   shared with every other game; a picture at screen scale costs
   `w * h` bytes as indices (128 x 62 = 7.9 KB).
5. **Add the loader** to `wcdata.py`: read the header once, `seek` for
   the rest, reuse buffers.
6. **Register it in `tool/deploy.py`.** New Python modules must be
   added to the `wingcommander` entry's module list or they will not
   reach the device; new asset extensions too (`.wc`, `.wcs`, `.ima`
   and `.COL.bin` are already copied).
7. **Extend `tool/wc1_selfplay.py`** so the new screen is reached
   without a human, and assert on something visible (a non-black
   pixel count in the picture area is enough to catch a blank screen).

## 3.5 Size budget so far

About 3 MB for three campaigns: ship sprites 1.4 MB, mission and
campaign records 0.7 MB, conversations 0.7 MB, everything else under
0.3 MB. Measured for the missing kinds, at screen scale and
without compression: all eleven talking heads about 150 KB (5.6);
the four "Meanwhile" scenes about 0.8 MB and the other scene archives
about 1 MB if every frame is kept (6.1, 6.2); radio portraits under
50 KB; the songs 207 KB and the timbre bank 4 KB (8.1, 8.2).

## 3.6 Deployment

`python3 tool/deploy.py thumbycolor --game wingcommander` compiles the
Python files with `mpy-cross` and builds a tree to copy to the device;
`--remote` copies it. The game is registered for the ThumbyColor only
(the monochrome Thumby cannot run it). The asset folder is taken from
your local `assets/` - convert before deploying.
