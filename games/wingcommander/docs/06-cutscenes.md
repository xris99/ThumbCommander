# 6. Cutscenes

Nothing in this chapter is implemented. The original has two kinds of
cutscene, and they need different approaches:

1. **Scripted animations** - the "Meanwhile..." scenes between series.
   Data-driven: objects with positions and a small bytecode, stored in
   `MIDGAME.Vnn`. Port the *interpreter* once and every scene plays.
2. **Hard-coded scenes** - launch, landing, death, ejection, medals,
   funeral, intro, endings. Each is a C function that draws a few
   sprites at coordinates written in the code. Port each as a short
   table-driven Python scene.

Both are built from the same thing: full-width backdrops, sprites
with hot spots, a frame list per moving object.

## 6.1 Scripted animations (MIDGAME)

Source: `LoadSceneAnimationResources`, `UpdateSceneAnimationObject`,
`PlaySceneAnimation` in wc1-re `src/logic.c`; `ShowMeanwhileTransition`
in `src/pilot.cpp`. Disassemble your data with

```bash
python3 tool/wc1_inspect.py WING midgame 0 0     # scene 0, variant 0 (series won)
python3 tool/wc1_inspect.py WING midgame 0 1     # ... series lost
```

### When they play

After the last mission of a series, `UpdateSeries` reads the series'
`sequence` byte (2.7). Values 0-7 play `MIDGAME.V0<sequence>` with
variant 0 if the series was won and 1 if it was lost; 0x40 and 0x41
are the two hard-coded endings; 0xFF is nothing. WC1 uses scenes 0-3
(series 2-11) [data]. `campaign.post_mission` already returns this as
`out.sequence` and `out.series_failed`; `MainGame.ending` handles only
0x40 / 0x41.

`ShowMeanwhileTransition(scene, variant)` [src]:

1. start music track `0x21 + variant` (33 won, 34 lost);
2. show the word "Meanwhile..." in the intro font (TITLE.VGA 1), wait
   100/60 s;
3. run `SceneDirector(6, ...)` on the scene packet (section
   `variant + 5`);
4. fade to black, stop the music.

The scene packet is an ordinary conversation (2.8) whose records use
shots 50-59: play animation `shot - 50` with the record's text as a
subtitle. In all nine MIDGAME files the packets contain nothing but
shots 50-58 [data] - no talking heads, no branch tests.

### File layout

| Section | Content |
|---------|---------|
| 0 | primary shape - layer 0 objects draw from it (backgrounds) |
| 1 + variant | definitions (below) |
| 3 + variant | secondary shape - layer 1 objects draw from it (sprites) |
| 5 + variant | scene packet |

Definitions section:

```
i16  objectsPerAnimation
SceneAnimationDiskObject[count]        0x36 bytes each
bytecode                               starts right after the table

count = (object[0].scriptOffset - 2) / 0x36
animation n uses objects [n * objectsPerAnimation, (n+1) * objectsPerAnimation)
```

Object record (offsets in bytes) [src `include/wc1.h`
`SceneAnimationDiskObject`]:

```
+0x00 i16 layer          0 = primary shape, 1 = secondary shape, 2 = not drawn
+0x02 i16 scriptOffset   from the start of the section
+0x04 ...                three pointers the game fills in at run time
+0x10 u16 goalFlags
+0x12 i16 delay
+0x14 ...                shape pointer, filled in at run time
+0x18 i16 x, y, rotation, scale, flip
+0x22 i16 deltaX, deltaY, deltaRotation, deltaScale, deltaFlip
+0x2C i16 goalX, goalY, goalRotation, goalScale, goalFlip
```

`scale` 256 = original size; `rotation` in degrees. The field that
wc1-re names `frame` here is passed to `DrawSpriteScaled` as its
*flip* argument, so this chapter calls it flip; which frame to draw
comes from the `D` / `E` commands.

### The bytecode

One script per object. Operands are little-endian `i16` unless noted.

| Op | Operands | Effect |
|----|----------|--------|
| `L` | prop, value | load: property = value |
| `A` | prop, value | add: property += value, and remember value as the property's delta |
| `Q` | prop, value | set a goal for the property (goal flags: R 1, S 2, X 4, Y 8, F 0x10) |
| `X` | 5 values | set x, y, rotation, scale, flip at once |
| `R` | u8 set, u8 index | copy x, y, rotation, scale, flip from object `index` of animation `set` (continue where an earlier animation left its objects) |
| `D` | u8 frames..., 0xFF | draw the listed frames at (x, y) with rotation / scale / flip, then **end this object's turn for this frame**. For layer 0 each following frame is drawn 320 pixels further right (a wide panorama in tiles). Layer 2 draws nothing |
| `E` | u8 frames..., 0xFF | draw like `D` (every layer steps 320), mark the animation **complete**, stay on this command |
| `B` | label | a label; no effect when executed |
| `G` | label | go to the label (searched from the script's start) and continue |
| `J` | label | go to the label and end this object's turn |
| `P` | | end this object's turn |
| `W` | frames | the animation ends after this many more frames |
| 0 | | end of script |

Properties: `X`, `Y`, `R` rotation (wrapped to 0-359), `S` scale
(clamped to 0x40-0x1FFF), `F` flip, `T` the object's delay.

What the shipped data actually uses [data, all nine files, both
variants]: commands `A B D E G L Q R W` only (never `J`, `P`, `X`);
properties `X`, `Y` and `T` everywhere, `S` only in `MIDGAME.V02`,
and rotation and flip **never**. A first interpreter can leave
rotation and flip out and still play everything. Sizes range from
1 animation of 7 objects to 9 animations of 11 objects per variant.

### One frame

`PlaySceneAnimation(text, n, duration)` prints the subtitle (y = 160),
binds each object's shape and script, then loops [src]:

```
every displayed frame:
    for each object of the animation, in order:
        UpdateSceneAnimationObject
    if a W countdown is running: decrement; at 0 the animation is complete
    present the frame
until complete
if no W was used: wait duration / 2 (in 1/60 s) or a key press
```

`UpdateSceneAnimationObject` [src]:

```
if object.delay > 0:  re-run from the last D command   (hold the picture)
else:                 continue from the saved cursor
run commands until one ends the turn (D, E, J, P) or the script ends
if object.delay > 0:  delay -= 1; return "not complete"
save the cursor; object.delay = the delay set by LT / AT this turn
if no E ran and goals are set:
    complete if any goal is reached; "reached" depends on the sign of
    the property's last delta: delta < 0 -> value <= goal,
    delta > 0 -> value >= goal, delta == 0 -> value == goal
```

So `D[16] LT3 D[17] LT3 ...` is a frame-by-frame animation holding
each frame for three extra frames, `B0 D[1,2] AX-2 G0` scrolls a
two-tile background two pixels per frame forever, and `QX-80` in
another object ends the scene when that object has scrolled to
x = -80. Objects draw in table order every frame, so layer-0
backgrounds listed first repaint the whole picture - there is no
separate clear.

Example, first animation of `MIDGAME.V00` variant 0 [data]: nine
objects - a static backdrop; a two-tile background scrolling at -2;
a sprite at -2; two sprites at -4; a two-tile foreground at -4 that
carries the goal `QX-80`; and three **layer-2 objects** that mirror
three of the sprites' movements without being drawn. The scene is a
parallax pan that ends when the foreground has moved 80 pixels. The
second animation starts every object with `R0,n` - copying the
position object n had at the end of the first animation, the
invisible ones included - and then plays frame-by-frame sprite
animations with `LT3` holds; a `W60` ends it. Layer 2 is thus how a
scene hands positions from one animation to the next.

A key press fast-forwards: the game runs the scripts without drawing
until completion (or just sets the countdown to 0 when `W` is used).

### Porting plan

**Converter** (`convert_midgame`):

- Per scene and variant, walk the scene packet, collect which
  animations it plays, disassemble their objects, and collect the set
  of frames each shape really uses (`D` / `E` lists). Convert only
  those.
- Layer 0 (backdrops): scale to 128 x 61 like the other pictures.
  Tiles are 320 wide = exactly 128 scaled pixels, so panoramas stay
  seamless if every tile is scaled as its own 320-wide canvas.
- Layer 1 (sprites): `.wcs` at screen scale (`res` 64). Sprites up to
  268 x 128 exist; at screen scale that is 107 x 61 = 6.5 KB, inside
  the cache's 8,000-byte buffers.
- Scripts: re-emit as a compact fixed-size instruction list with
  coordinates and deltas **pre-scaled** (x by 0.40, y by 0.48). Keep
  fractional precision: a delta of -2 px per frame becomes -0.8, so
  store positions and deltas as 8.8 fixed point.
- Only scene 2 scales sprites (`AS`); `wcgfx.blit_rs` already draws a
  scaled sprite. Everything else is a plain blit with transparency.

Storage, every frame at screen scale without compression [data,
frame rectangles including transparent pixels]:

| File | Frames | KB |
|------|--------|----|
| MIDGAME.V00 | 51 | 214 |
| MIDGAME.V01 | 22 | 257 |
| MIDGAME.V02 | 29 | 203 |
| MIDGAME.V03 | 21 | 147 |

About 0.8 MB for WC1's four scenes with both variants; converting
only frames that scripts reference will reduce it.

**Runtime** (`scene.py`, new):

- one `Obj`-like record per animation object in preallocated arrays;
- the interpreter loop above, driven by time: the original advances
  one step per displayed frame, 16 frames per second (62 ms, chapter
  1.4) [src]. Run one script step every 62 ms by `time.ticks_ms()`
  and draw after each step; with the engine at 20 or 30 fps that
  needs no change to holds or deltas. If drawing a scene takes longer
  than 62 ms, do the steps that are due and draw once;
- subtitles through the existing font code, below the picture;
- A or B skips, as in the original.

**Check**: a script that renders every animation of every scene to
PNG strips on the PC and compares object positions per step against a
Python reference interpreter working on the *unscaled* data.

## 6.2 Hard-coded scenes

Each row is a function to read and re-express. "Art" gives the
sections; music and sound numbers refer to chapters 8 and 9.

| Scene | Function (wc1-re) | Art | Music | Sounds |
|-------|-------------------|-----|-------|--------|
| Run to the hangar | `PlayScrambleHangarScene`, `AnimateScrambleWalk` (`src/cutscene.c`) | SCRAMBLE.VGA 0 | 27 | 14 |
| On the flight deck, climbing in | `scramble` | SCRAMBLE.VGA 1-4, PCSHIP 8 | | 17, 15, 16 |
| Canopy closes, cockpit comes alive | `LaunchPlayerShip` (`src/launch.c`) | SCRAMBLE.VGA 7, cockpit | | 20 |
| Launch tube | `ShowCarrierLaunchSequence` | SCRAMBLE.VGA 4, 8 | 28 | 11, 18, 19 |
| Landing; deck crew comments on the damage | `landing(damageLevel)` | SCRAMBLE.VGA 1, 3-6, 9, PCSHIP 8 | 29 | 17, 15 |
| Death in the cockpit | `death_sequence` (`src/screens.c`) | PILOTANM.VGA 0, PCSHIP 3 | 32 | 4 |
| Ejection, drifting in space | `ejection_sequence`, `stranded_sequence` (`src/eject.c`) | PILOTANM.VGA 1, 2, PCSHIP 0, 3, 5 | 31 | 33, 34 |
| Funeral (player or wingman) | `funeral_sequence`, `funeral_player`, `funeral_wingman` | BRIEFING.VGA 9 | 32 | 29, 31, 36 |
| Medal ceremony | `AwardCampaignMedal` and the shot functions | BRIEFING.VGA 8, 10 | 38-40 | |
| Colonel's office (promotion, transfer) | `Office` (`src/cmpgn.c`) | BRIEFING.VGA 7 | | |
| Bar with seated pilots | `RecRoom` (`src/killbrd.c`) | RECROOM.VGA 0, 1, 3-11 | 30 | |
| Barracks | `BarracksScreen` (`src/barracks.c`) | RECROOM.VGA 12 | 35 | 35 |
| Intro and credits | `Title_Sequence`, `intro_drawbackgroundships` (`src/title.c`) | TITLE.VGA 0, 1, 4 and further sections not traced | 19, 23 | |
| Victory ending | `ShowCampaignVictorySequence` (`src/ending.c`) | TITLE.VGA 2, 3, 5 | 33 | |
| Retreat ending | `ShowTigerClawEscapeScene` | TITLE.VGA 2, OBJECTS.VGA 14 | 34 | |
| "The End" | `ShowTheEndScreen` | TITLE.VGA 1, 17 | 23 | |

(The music numbers are the `spacetrack` arguments at those call
sites; see the table in 8.6.)

### How they are written

All follow one pattern [src]. Example, the hangar run:

```
load SCRAMBLE.VGA section 0; start music 27; play sound 14
for 24 steps:
    draw background frames 0,1,0,1 side by side at x, x+320, x+640, x+960
    draw the left runner:  frame cycling 7..19, at (leftX,  127 - frame height)
    draw the right runner: frame cycling 7..19, at (rightX, 137 - frame height)
    plus a per-pair overlay frame (which two pilots run is random)
    x -= 12; leftX += 2; rightX += 3
24 steps with background frame 2 and runner frames 21..26 (the stairs)
24 more steps as the first block
```

`scramble` and `landing` use five "actors" (`aScrambleAnimationActors`):
each has a shape, position, per-step delta, scale, angle, flip, and a
frame list in which `0x40` means "stop here" and `0x80 | n` "jump to
entry n". `landing` picks one of three canopy frame lists and one of
four comments by the ship's damage level
(`apLandingCanopyFrames`, `apszLandingDamageComments`).

### Porting plan

1. **Give every scene the same tiny format** [guess]: a list of
   *steps*; a step is (duration in frames, list of draws); a draw is
   (sprite set, frame or frame-list reference, x, y, dx, dy). The
   converter emits it from tables you transcribe out of the C
   function - this is manual work per scene, 50 to 200 lines of C
   each.
2. **Reuse the 6.1 interpreter.** Its object model (position, delta,
   frame list, hold) covers these scenes. Writing the hard-coded
   scenes as MIDGAME-style scripts in the converter means one runtime
   for both kinds.
3. **Order by value**: launch and landing are seen every mission;
   death and ejection often; medals, funeral, intro and endings
   rarely. Do the first group first.
4. **Select frames.** Screen-scale storage without compression
   [data]: SCRAMBLE.VGA 181 KB (148 frames), PILOTANM.VGA 104 KB,
   BRIEFING.VGA 297 KB, RECROOM.VGA 98 KB, TITLE.VGA 349 KB. Halving
   animation frame counts (each frame held twice as long) is hard
   to see on a 128-pixel screen and saves most of it.

### Hooks in the port

| Moment | Where to call |
|--------|---------------|
| before a mission | `Game.mission`, between briefing and `fly()` (hangar run, deck, launch) |
| after a flight | `Game.mission` after `fly()` returns: `R_LANDED` -> landing with `world.damage_level()`; `R_DEAD` -> death, funeral; `R_EJECTED` -> ejection |
| after the debriefing | medal (`out.medal`), office (`out.office`: promotion or transfer) |
| end of a series | `out.sequence` -> Meanwhile scene, then endings (`Game.ending`) |

All of these exist as text pages or flashes today, so each scene can
be added on its own, with the text page as the fallback when its
asset file is missing.

## 6.3 Things the scenes rely on that the port lacks

- **Palette effects.** Fades (`FadeViewportPaletteToColour`) and
  colour cycling are palette operations in the original. On an RGB565
  frame buffer a fade is `wcgfx.dim_rows` over the picture rows; it
  exists and is used for landing today.
- **Big text.** "Meanwhile...", the intro and "The End" use the
  proportional picture font in TITLE.VGA section 1 (60 frames, one per
  glyph), not FONTS.FNT. Convert it as a sprite set or render those
  few strings to pictures in the converter.
- **Scaled sprite draws** (`DrawSpriteScaled` with rotation):
  `wcgfx.blit_rs` covers them.
- **Timing.** Scene code counts frames of 62 ms and 1/60 s timer
  ticks (1.4 in chapter 1). Keep the frame counts as they are and run
  the steps by the clock.
