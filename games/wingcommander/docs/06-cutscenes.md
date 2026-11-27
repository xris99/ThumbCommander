# 6. Cutscenes

The scripted animations of 6.1 are implemented: the converter emits
`mid<NN>.wc` blocks, `scene.py` plays them and `MainGame.meanwhile`
runs them between series. Of the hard-coded scenes of 6.2 the first
group is implemented - hangar run, deck, launch door, fly-off,
landing, death, ejection and stranded, see 6.2's "The first group,
implemented", and the opening cinematic and title menu too (6.2 "The
intro and the title, implemented"); the rest - medals, office, bar,
barracks and endings - are not started. The original has two kinds
of cutscene, and they need different approaches:

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
(series 2-11) [data]. `campaign.post_mission` returns this as
`out.sequence` and `out.series_failed`; `MainGame.mission` plays
`scene.show` for every `out.sequence` 0-7 with variant
`out.series_failed` (MainGame.py:582-584); `MainGame.ending` handles
the two hard-coded endings 0x40 / 0x41 as text pages
(MainGame.py:705-718).

`ShowMeanwhileTransition(scene, variant)` [src]:

1. start music track `0x21 + variant` (33 won, 34 lost);
2. show the word "Meanwhile..." in the intro font (TITLE.VGA 1), wait
   100/60 s;
3. run `SceneDirector(6, ...)` on the scene packet (section
   `variant + 5`);
4. fade to black, stop the music.

`scene.show` (scene.py:604-659) implements this verbatim except for
the music - the port has none yet. The word is the converted
`meanwhile_128_62.COL.bin` held for `100 * 1000 // 60` ms
(`WaitForSceneAdvance`), the director and interpreter run below it,
and the fade is eight `wcgfx.dim_rows` passes over the picture rows
followed by the black fill (6.3).

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
variants, counted by replaying every object script through a
simulation that mirrors the dispatch and label search byte for byte]:
commands `A B D E G L Q R W` only, never `J`, `P`, `X`; properties
`X`, `Y` and `T` everywhere, `S` only in `MIDGAME.V02` (value -10,
shrinking sprites), `F` and `R` **never** - no script ever touches
rotation or flip. The 27 `Q` goals are all on `X` (13) or `Y` (14);
`W` waits 27 times; `R` copies 189 times, in scenes 0-3, 5 v0, 6 v0
and 7 only, never in 4, 5 v1 or 8. The initial disk records still
carry rotation and flip though: four records sit at 30 degrees, both
variants of `MIDGAME.V02`, and they are layer-1 sprites that get
drawn; thirteen records carry the flip bit 0x10 (`V02` v1, `V06` v0,
`V08` v1) and forty a scale outside 0/256 (`V06`/`V08` only). So an
interpreter cannot leave rotation and flip out - those records draw;
the port passes them through `_coeffs` and `wcgfx.blit_rs`
(scene.py:309-374). Sizes range from 1 animation of 7 objects
(`MIDGAME.V04` v1) to 9 animations of 11 (`MIDGAME.V08` v0); 158 of
the 671 records are layer-2 mirrors.

### One frame

`PlaySceneAnimation(text, n, duration)` prints the subtitle (y = 160
in the original's 200 rows; on the device the picture clips at row 78
and the text starts at y = 79, scene.py:76-81), binds each object's
shape and script, then loops [src]:

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
- Scripts: re-emit as a compact fixed-size instruction list, `<BBh`
  four-byte instructions (`_compile_script`, wc1_convert.py:838-919).
  Positions and deltas stay in the **original pixel space** and
  integrate by integer addition exactly as the original does;
  scaling to the device's 8.7 units happens only at the draw site
  (`_x8` / `_y8`, scene.py:59-73). The earlier plan of pre-scaling
  into 8.8 fixed point was dropped: goal tests and completion stay
  exact integer comparisons like the original's, and the agreement
  check confirms both interpreters finish on the same step.
- Only scene 2 scales sprites (`AS`); `wcgfx.blit_rs` already draws a
  scaled sprite. Everything else is a plain blit with transparency.

Storage as converted (`mid<NN>.wc`, only the frames the scripts
reference) [data, measured from the built assets]:

| File | Frames | KB |
|------|--------|----|
| mid00.wc | 46 | 41 |
| mid01.wc | 22 | 70 |
| mid02.wc | 29 | 68 |
| mid03.wc | 21 | 30 |

The four WC1 scenes take 0.2 MB with both variants. The five Secret
Missions 2 files (mid04-08, unused by WC1) add about 0.7 MB more,
the bulk being mid05 at 474 KB. (The old 51 frames / 214 KB figure
for V00 and the 0.8 MB total estimated the cost of the *full* frame
rectangles at screen scale without compression.)

**Runtime** (`scene.py`) - implemented:

- one list of integers per object, built once per variant by
  `load_variant` (scene.py:564-584); a cutscene run may allocate,
  it is not the flight loop;
- the interpreter loop above, driven by time: the reference port
  advances one step per displayed frame at its throttle's 16 fps
  (62 ms, chapter 1.4) [src]; the game itself ran one turn per frame
  and a turn is 1/10 s (docs/04 4.4.1). The port holds every step
  outside flight to that turn: one script step every `STEP_MS` = 100
  ms (scene.py:86) drawn after it. If drawing runs past 100 ms, the
  steps that became due execute without presenting and only the last
  picture shows;
- the engine tick, not the turn, is the push rate: every wait loop
  calls `display.update`, and each call spins to the next tick and
  blits the buffer again (`color.py:204-211`). The panel scans that
  buffer by DMA while the blit rewrites it, and racing those re-blits
  of a still picture shows as flicker - the device report on the
  title. The two cinematics set the tick to their picture's own rate
  while they run (`titleseq.title`: 10 Hz for the turn; `Game.intro`:
  10 Hz against the intro's 140 ms pace, `introfx.py:62`), and hand
  the menu back the 20 Hz it polls its buttons at. Flight keeps its
  25 (`flight.PICTURES`, docs/04 4.4.1);
- subtitles through the existing font code, below the picture;
- `A` fast-forwards as in the original: `_skip` runs the scripts
  without drawing, or zeroes the `W` countdown; `B` or `MENU` leaves
  the whole scene (the director's skip break, screens.c:1461).

**Check** - implemented as `tool/wc1_scene.py`: every object position
of every animation of every variant is stepped side by side against
`tool/wc1/refscene.py` running on the *unscaled* disk data; the draw
entries must match and both interpreters must finish on the same step
with the same `W` globals. All 18 variants pass: positions agree to
the last (worst error 0.000 device pixels), draw positions within one
pixel of the rounding at the draw site. `--preview` writes PNG strips
of the distinct frames to `/tmp/wc1_scene_previews`.

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
| after the debriefing | wingman funeral (`out.wingman_lost`, `gameflow.c:468-469` - plays even when the player ejected, before the office), medal (`out.medal`), office (`out.office`: promotion or transfer) |
| end of a series | `out.sequence` -> Meanwhile scene, then endings (`Game.ending`) |

All of these exist as text pages or flashes today, so each scene can
be added on its own, with the text page as the fallback when its
asset file is missing.

### The first group, implemented

The first group of 6.2 is implemented: hangar run, climbing into the
fighter on the deck, the launch canopy, the fly-off, landing, death,
ejection and stranded; the funeral follows, ported as the same kind of
verbatim module. These are **not** the step-4 scripts of the
porting plan: each scene is a verbatim port of its C function, with
the original's coordinates, frame numbers and step counts transcribed
into the Python module and every constant commented with its wc1-re
symbol. One shared engine in `scramble.py`, which streams every drawn
sprite through one scratch, a `bytearray(VIEW_N)` of 12,288 bytes
claimed with the module (`scramble.py:94`) and given back to the
heap when the module is popped (docs/12 12.2); the other modules are
small:

| Module | Ports |
|--------|-------|
| `scramble.py` | `PlayScrambleHangarScene` (`cutscene.c:281`), `AnimateScrambleWalk` (`:200`), `scramble` (`:620`), `landing` (`:801`), the actor machinery `DrawScrambleActor` (`:378`) / `ConfigureScrambleActor` (`:437`) and `DrawScrambleFrame` (`:456`); plus the shared helpers `_cx` / `_cy` / `_draw` / `_draws` / `_steps` the other modules use |
| `launchseq.py` | `DrawLaunchDoorFrame` (`launch.c:55`), `LaunchPlayerShip` (`:103`), `ShowCarrierLaunchSequence` (`:164`) - phases A, B and C (A in `_approach`); `GetTransformedShapeBounds` (`gr.c:1311`) |
| `deathseq.py` | `death_sequence` (`screens.c:1694`) |
| `ejectseq.py` | `ejection_sequence` (`eject.c:32`: stages 1 and 2 plus the 3-D chase `_chase` (`:143-181`) - `view.c`'s scripted eye, `spc.c`'s camera cases, `geom.c`'s cull order and `flight.py`'s projection/`right_shape`/`dirv` mirrors) and `stranded_sequence` (`:202`); the stranding check `check_stranded` (`cockpt.c:3013`) with `any_enemy` (`logic.c:906`) and `distance_from_*` (`geom.c:687-703`) |
| `funeralseq.py` | `funeral_sequence` (`cutscene.c:1103`) including the volley and particle machinery (`:1257-1338`) and the descent (`:1340-1368`), `funeral_player` (`:998`) as the talking-head composite, `funeral_wingman` (`:1069`) behind shot 17's eulogy lines (`screens.c:1443-1445`); `InitializeConstellationField` (`view.c:279`) and `DrawConstellationField` (`:330`) as the star field behind the crowd, with `asConstellationFrame` / `asConstellationVelocity` (`:17-22`); the heads' special shape is `fun.wcs` frames 10 / 11, fetched at `:1166-1167` and drawn by `talk.py` (`cmpgn.c:462-473`) |

| `titleseq.py` | `Title_Sequence` (`title.c:135`) with `DrawTitleLogo` (`:78-113`) and `GetLineLength` / `print_subtitle` (`mono.c`) - the five phases and the eleven credit blocks (`:191-289`) with their `PH_*` frame counts and the New Game / Continue menu of `:319-497` driven by buttons; plus the canned world the cinematic flies: `advance` / `update_canned_sequence` (`mono.c`), the view-script trio (`view.c`), `set_eye`'s case 15, `rotate_eye_to_goal` and the canned gate (`spc.c`), `fire_fixed_projectile_weapon` (`ship.c`), the whole hazard chain (`winmain.c`), the `screenX` gates, `ClampVectorTo30` and `point_at` (`geom.c`), `intro_drawbackgroundships` (`eventmgr.c`), `set_up_action_sphere` and the ship init (`mission.c`), `kilrathi_near` (`cockpt.c`), `signed_random` and the clamped `find_ratio` (`logic.c`), `Update_3Space` / `house_keep` / `Draw_3Space_Frame` / `RenderSpaceViewFrame` (`main.c`) and `GetShapeFrameExtent` (`cutscene.c`) |

Two draw bands, as in the original. Hangar, deck and landing draw
into the conversation picture - `stSceneBuffer`, 320 x 128
(`main.c:501-515`), on the device rows 16..77; door, fly-off, death
and ejection fill the whole picture, the original's 320 x 200 space
buffer dumped over the screen, on the device rows 16..111 with clip
bottom 112. Original pixel positions map through the fixed point of
3.1 (`_x8` / `_y8`, `scene.py:59-73`; `_cx` / `_cy` add the picture
origin). One step per displayed frame, held to the turn's 100 ms like
6.1: the original's `nFrameSkip` is 1 (`init.c:202`), so every pass
renders and applies the deltas, and the port does the same. Any button
breaks
a sequence, as every original loop checks `bEscapePressedFlag` (e.g.
`cutscene.c:274-275`). When a sprite file is missing the whole scene
skips and the game behaves as it did before this chapter.

Art, converted by `tool/wc1_convert.py`:

- `scr<NN>.wcs` - SCRAMBLE.VGA sections 0-9: the hangar corridor and
  stairs, the flight deck, the blast door (`scr07`, `launch.c:118-119`),
  the Tiger's Claw and its deck crew (`scr08`, `scr04`), and the
  landing view (`scr09`);
- `pil00.wcs`, `pil01.wcs`, `pil02.wcs` - PILOTANM.VGA sections 0, 1
  and 2: the pilot's death face, the ejection seat and the 13 frames
  of the tumbling ejected pilot (`eject.c:97-99`);
- `ckint<NN>.wcs`, `ckbg<NN>.wcs`, `ckslide<NN>.wcs` - PCSHIP.V0N
  sections 0, 3 and 5: the cockpit interior, background and sliding
  panels of the death and ejection scenes.
- `fun.wcs` - BRIEFING.VGA section 9: the funeral composites - flag
  bearer `f0`/`f1`, guard poses `f2`/`f3`, rifle poses `f4`/`f5`, the
  casket `f8`, volley sparks `f9`, foreground trees `f6`/`f7`, and the
  overlay frames `f10`/`f11` the eulogy heads draw behind them
  (`cutscene.c:1166-1167`, `cmpgn.c:462-473`);
- `con.wcs` - PLANETS.VGA section 0: the constellation - 32 particle
  frames and 6 star frames, one to four pixels each, drifted and
  recycled every frame (`view.c:279-398`); converted with a lower
  alpha threshold than usual so the dots survive the area averaging
  (3.1);
- `ti0.wcs`, `ti0geo.wc`, `ti1.wcs`, `ti1wd.wc`, `ti4.wcs` -
  TITLE.VGA sections 0, 1 and 4: the three tiles of the WING COMMANDER
  logo (packet 9 section 0, fetched at `title.c:185-186`) with
  `ti0geo.wc`, the converter's copy of the original-pixel frame
  headers behind `DrawTitleLogo`'s `GetTransformedShapeBounds` anchors
  (`title.c:91-112`); the 60 glyph frames of the intro picture font
  (`title.c:164`) with `ti1wd.wc`, one byte per glyph frame of the
  original `GetShapeFrameExtent` right edge (`cutscene.c`); and the
  option graphics of the title menu (`title.c:330`); together 13.5 KB.

The fly-off reuses the converted `sh<NN>.wcs` ship sets
(`launch.c:196-197`); the canopy shows the flight cockpit's static art
`ck<N>.wc`; the deck and landing canopy frames are the existing
`cksc<N>.wcs` (PCSHIP section 8). The new scene art is about 0.39 MB
altogether; the funeral's `fun.wcs` adds 22 KB (`con.wcs` is 433
bytes) and the title's logo, intro font and bars 13.5 KB (`ti0.wcs`,
`ti0geo.wc`, `ti1.wcs`, `ti1wd.wc`, `ti4.wcs`).

Deliberately not ported, each noted in the module header so the scene
can still be read against its C function: the scenes' music and sound
effects (chapters 8 and 9); the death scene's 60-frame 3-D aftermath (`screens.c:1743-1756` - the
flight has already shown the kill that killed you); the launch's
animated cockpit instruments - `update_cockpit` (`cockpt.c:3151`)
draws the scanner, readouts and pilot as dynamic overlays over the
dumped space buffer, never the frame art. Of these overlays only the
pilot's hand on the flight stick is ported - `flight.draw_pilot_hand`
composites `pil03.wcs` (PILOTANM.VGA section 3) over the flight
cockpit, the grip fixed between the legs and the pose following the
pitch and yaw keys (`cockpt.c:2634` `determine_pilot_hand`, `:2665`) -
together with `flight.draw_stick`, the device's own joystick under the
hand: the original flight data carries no stick to draw (`logic.c:83`
loads no stick shape - the cockpit art is only the legs and the seat
cushion, and the hand moves over them), so the port draws a base plate
on the cushion between the knees, a grey shaft and a red ball at the
grip origin, bent by the same -9 .. 9 axes that pick the hand's pose;
the scanner and readouts stay absent. The device picture is the
space buffer itself, so the door scene redraws the doors still
approaching over a background the original clears on every pass
(`RefreshCockpitStatus`, `main.c:2136-2142`, clears whenever
`nFrameSkipCounter <= 1` - all cutscene loops set it to 1) - sections
that have passed by are deleted, not painted over - and the
instruments are absent (laying the static `ck<N>.wc` art over the
doors was wrong: it clipped the tunnel into the small ck glass window
and painted the dashboard across the parts passing by); the original's
palette fades - the port dims with `wcgfx.dim_rows` and clears to
black, as elsewhere; and `pIntroFont` - the stranded message uses the
small `ui.text` font, ported before the intro font became `ti1.wcs`
and kept so (6.3 "Big text").

The ejection's 3-D chase (`eject.c:143-181`) is ported in `ejectseq`
as `_chase`: 201 pictures at the turn's 100 ms, the camera driven
by `view.c`'s parse/update/initialize trio (`EJECT_SCRIPT`: the eye
hangs 600 m below the pilot for 70 passes, rides him for 80 more,
then chases a point 700 m behind for the fly-by; mode 4 starts on
pass 151 and the scripted view switches off with the script's -1
entry), `spc.c`'s camera cases 10, 11 and 4, and the pilot and the
dying fighter drawn through the flight's own projection - the culls
follow `geom.c:1240-1299`'s order and `right_shape` and `dirv`
mirror `flight.py`, so the tumbling pilot, the receding ship and its
fireball come out as the flight renders them, depth-sorted far to
near (`flight.py:386-402`). The deviations are noted in the `_chase`
header: the live simulation stands still while the chase runs on
local snapshots (it never moves `world.o[0]`, so the stranding check
below reads the mission's own positions); velocities, the pilot's 5 m
kick and the ship's rotation are per-turn numbers, unscaled, since
the chase's pass is the turn's 100 ms (`PASS_MS` = `TURN_MS`);
`init_ijk` resets the eye's basis
to identity, so `eject.c:145-151`'s basis-swap lines are dead code
the port skips; the pilot's class, radius and scale come from
`types.wc` type 56 (DEBRIS class 6, radius 6, scale 512) and his
tumble runs `pil02.wcs` one frame per pass with no `right_shape`, as
the original's DEBRIS branch does; stars never respawn because the
eye's pitch and yaw stay 0; the shock wave, the mission-ship state
and the explosion sound (`ship.c:1373-1434`) are not ported, and a
dying fighter shows exactly the one fireball `ship.c:1325-1360`
builds (`spc.c:955-956`'s extra onboard explosions belong to
capitals only); when the ship's counter runs out the original makes
debris chunks (`spc.c:968-969`) and the port simply drops the ship
from the scene.

The fly-off's phase A (`launch.c:200-288`) is ported in `launchseq`
as `_approach`: 100 pictures at 100 ms on the same `view.c`/`spc.c`
machinery as the chase, but only its first half is exercised -
`asCarrierLaunchViewData` (`launch.c:34-36`) holds no command 13 or
14, so `parse_view_script` runs the script to its -1 entry inside
`initialize_scripted_view` (`view.c:198-206`) and every pass takes
`set_eye_direction_and_position`'s camera case 15 (`spc.c:458-464`).
The fighter and the carrier edge are pinned at original-space screen
positions instead of projected (the centre the original adds back at
`winmain.c:95-96` is the fixed 160, 100), so the scene needs no
transform engine: the fighter climbs and shrinks on the
`launch.c:12-22` schedule, the carrier slides in from x = 520 with
the deck line, and the star and dust backdrop streams past the
scripted eye that free-flies along the carrier's right at twice the
scripted velocity (case 15 and `launch.c:280-282` add the velocity to
the position twice a pass, so the port doubles it and advances once).
`MainGame.py:554` hands the flight's own world to `flyoff` so the eye
can start on the carrier the player landed on (`launch.c:199-200`,
`gameflow.c:363-364`); the selfplay call without a world and flights
that ended without a carrier skip the approach and play the deck
slide. The approach also needs the flight's code, which `fly()` let
go with the flight; `launchseq` lands it again inside a guarded
import (docs/12 12.2), so when the room after the flight will not
take it phase A is skipped and the deck slide plays instead of an
out-of-memory ending the game. Stars stand still while the dust
streams - the eye neither pitches nor yaws, the chase's deviation.

The scenes are hooked in `MainGame.py:490-610` in gameflow.c's order:
before `fly()` the hangar run (gameflow.c:337), the deck climb-in
(`:341`) and the closing canopy (`:354`); on `R_DEAD` the death
sequence (`:401`); on `R_LANDED` the fly-off and then
`landing(world.damage_level(), ship)` (`:362-369`); on `R_EJECTED` the
ejection, the stranding check and, if the carrier was lost, the
stranded message that ends the campaign (`:372-375`).
`scramble.cleanup()` and `launchseq.cleanup()` let go of the sprite
sets between flights. `MainGame.py` releases the two modules
themselves around the flight: their names drop before `fly()` pops
them (`:497-505`, `:663-666`) so the 12,288-byte scratch and the
scene code become the flight's room (docs/12 12.1), and every
post-flight path re-claims them and lets them go again (`:525-528`,
`:558-561`, `:586-597`). `ejectseq` follows the same rule inside: it
lands its own 8.5 KB of code and no scene helper at import, never
the flight either - the chase's projection stands mirrored in its
own numbers (`ejectseq.py:139-155`) - and claims `scramble` and
`sky` inside itself with its scene asks guarded (docs/12 12.4),
dropping the module and the seat helper after the scene
(`:586-597`).

**Check** - `tool/wc1_selfplay.py` holds the pilot still while a scene
plays: the PC emulation runs an engine tick inside every
`display.update()` (`thumby_engine/pc`, `display/color.py:205-209`),
so without the freeze every scene would advance the simulation a few
frames early. It counts the picture and text pixels each scene draws
(rows 16..111 and 79..111): landing must draw its damage comment text,
the death and ejection faces must show, the stranded message must
show. The title cinematic keeps the same freeze, with one exception: the
pilot returns when `titleseq.hold` goes False, so the New Game /
Continue menu is driven like any other screen while the two and a
half minutes of intro play untouched; the run photographs its stages
(`titleA`, `titleB`, `titleC`, `titleD`, `titleE`, `titlemenu`) and
fails if one is missing. A full sortie passes; the run that
verified the finished port passed after 1604 frames, writing 50
screenshots to `build/wc1_selfplay/`.

### The intro and the title, implemented

The opening cinematic and the title menu are implemented in
`titleseq.py`, a verbatim port of `Title_Sequence` (`title.c:135`)
holding `DrawTitleLogo` (`:78-113`) and `print_subtitle`'s placement
(`mono.c:205`) in the same module. The Origin FX opening
(`introfx.play`, `dos_intro.c:239`) plays once per program start
before the cinematic (`MainGame.py:732-734`); `Game.title` follows and
`main()` goes straight from the title menu into a campaign when one is
picked (`:735-739`).

The frame counts are the original's: 25 opening frames (`:191`), 110
of plain flight (`:221`), 100 of the logo zoom with the distance
stepping -4 after each draw while it is above 16 (`:225`,
`:235-236`), eleven credit blocks of 70 drawn frames plus 40 of
rendering (`:257`, `:275`, `nIntroCreditCount` 11 at `:22`) and 150
to close (`:289`) - 1595 frames at the turn's 100 ms, two and a half
minutes, close on the title music's 165 s (docs/08-music.md, track
23). Every rendered frame waits for its boundary there (`_pace`,
`titleseq.py`), the clock every scene outside flight runs on: with
`nFrameSkipCounter` pinned to 1 (`:189`) every pass is a turn and a
picture, so the cinematic draws a picture every 100 ms, ten turns a
second (docs/04 4.4.1). The FX opening with the flyby and logo spans
the Origin FX music's 25 s (docs/08 cue 19; the original measured at
about 24): its ~177 pictures at `FX_MS` = 140 ms; the menu comes up a
little over three minutes after the program boots. The logo draws its
three `ti0.wcs` tiles with the original's
scale (`0x1000 / distance`, `:85`) and the `ti0geo.wc` sidecar's
original-pixel anchors, keeping the one-pixel left-seam overlap of
`bounds.left - 1` (`:95`); the 16.16 blit comes from scramble.py.

The title flies the original's own canned world, not authored
choreography: a Mission built from game.c's title data - the intro
camera script `asIntroCameraSequence` (`game.c:110-113`), the canned
command sequences `asCannedSequence32..45` (`:116-196`),
`aMissionNavPoints[16..19]` (`:199-226`) and `aMissionShips[32..45]`
(`:229-290`) - through world.py's physics: the ships accelerate along
their canned headings (world.py's `move`), the canned command scripts
run (`advance` / `update_canned_sequence`, mono.c), the hazard chain
of winmain.c spawns, turns and recycles rocks and mines past the
camera (`title.c:253`, `winmain.c:435-454`), and the intro fleet
explodes on entry into the asteroid field's nav
(`set_up_action_sphere`'s explode-on-entry, mission.c) - the
original's transition into the credits, where the ships vanish and the
rocks take over. The eye is the scripted one the intro script's cmd3
installs, camera case 15 (`spc.c:496`): `view.c`'s parse / update /
initialize trio, `set_eye`'s turn with `rotate_eye_to_goal` and
`ClampVectorTo30`'s rotation decay added after world.py's
`rotate_object`, which does not apply it; phase D scales the eye's
forward vector by `0x9600`, ten times the intro speed, like
`ScaleFixedVector` (`title.c:246`) for the entry into the field, and
the credit phase drops it to a 40-unit drift - a documented deviation
on the owner's instruction: the port draws the dust as streaks from the
eye's motion (the original's was single pixels) and they cross the
112-row screen far too fast at 150 under credit text. `match_ship_to_eye`
holds the hazard chain's reference speed at 100 whatever the eye does.
The draw is flight.py's renderer
port run in the title's space - `Draw_3Space_Frame`'s pipeline
(`main.c:2018-2033`: transform, `draw_stars`, depth sort, sorted draw
to the whole picture), the verbatim `screenX` marker gates of geom.c
painting the parallel lists the explode-on-entry gate and the hazard
spawn consult while the drawing culls (+/-40 000, vz < 60) stay
drawing-only, and geom.c's scale-cull gate replaced by flight.py's
tiny gate so distant ships survive as specks as the original's do.
Stars are the world's Lites drawn by `draw_stars`; sky.py's dust field
stands in for the procedural dust of `set_eye` (`spc.c:821-852`) and
`draw_exhaust`'s engine plumes are not ported. The rest is in the
module header: the eye is slot 0 (the original's eye is object 61 and
world.py's NSHIP is 10; the hazard chain's `match_ship_to_eye` writes
the eye there too), world.py's unclamped `find_ratio` replaced by a
local clamped one as logic.c has it, cmd3 firing through world.py's
`fire_weapon` with its shot counter, world.py's `LITE` guard forcing
marker flags and distance-table entries into parallel lists,
`intro_drawbackgroundships`' black silhouettes (`eventmgr.c:1089-1112`,
`title.c:199`) as a second blit pass over the drawn objects with a
zeroed palette (`DrawSolidColourSpriteScaled`) while the dust streaks
keep their colour and have their black point painted over, and phase D
held for four drawn turns after the sphere entry before the credits so
the harness photographs the explosions where the original goes
straight into the first credit.

Text follows `GetLineLength` and `print_subtitle` (`mono.c`): letters
`A`..`z` take the glyph frame `c - 65` and advance its right extent
plus 2, `.` is frame 58 and `,` frame 59 (`mono.c:183-190`), a space
advances 6 and a newline ends the line; the extents come from
`ti1wd.wc`, one byte per glyph frame of the original
`GetShapeFrameExtent` right edge. The block is centred on the
original's 200-row screen (y = (200 - 16 * lines) / 2,
`mono.c:219-222`) and every line centred across the 320, the 16-pixel
line pitch (`:243`) becoming about 9 device rows under the y * 14 / 25
mapping; an earlier port centred in the 128 device rows instead, which
the mapping ran a second time and left the text at the top - corrected
in this change. The strings are the
verbatim opening text and the eleven DOS credits (`title.c:12-35`),
drawn in the converted intro font itself - `ti1.wcs`' glyph frames of
TITLE.VGA section 1 through the `print_subtitle` port, not `ui.text` -
and the colour argument `print_subtitle` takes selects nothing in the
original: the glyph shapes carry their own colours. A device
deviation: the original read its glyphs from RAM, while every glyph
read here goes through `SpriteSet.read` - an open, a seek and a close
on flash (`wcdata.py:194-198`) - so drawing the block glyph by glyph
put some seventy opens and closes into each drawn frame of phase A
and ran the opening pan at one frame per second on the device. The
port now renders each text block once into a full-screen index canvas
and blits that canvas over the scene every drawn frame, the anchors
and the mapping untouched. The canvas is the title's own: MainGame
claims its 14,336 bytes while the heap is fresh, just before it
imports the cinematic, and gives them back whole when the title
ends (docs/12 12.2); when the ask fails the title runs its
text-less path. The
menu draws the
option frames of `ti4.wcs` at the SDL regions (left 49, top 48 with 43
a row, `title.c:345-346`) - frames 2 and 3 are never drawn, the DOS
build keeping those options at -1 (`:334-341`) - and is driven by
UP / DOWN / A / B / MENU instead of the mouse cursor and region
hit-tests (`:116-132`, `:461-462`), a yellow `>` marking the selection
where the original's option frame carries its cursor; it plays one
cycle rather than looping until a key ends it (`:176`); and
Continue really loads a saved campaign here, which the DOS build
never allowed (`menuOptions[2]` stays -1, `:432-434`; `main.c:375-379`
has no case 1). The music and sound hooks (`:159`, `:187`,
`:302-303`, `:316`) are not ported, as everywhere in this chapter;
the fade to black mirrors 6.3's dim and fill.

## 6.3 Things the scenes rely on that the port lacks

- **Palette effects.** Fades (`FadeViewportPaletteToColour`) and
  colour cycling are palette operations in the original. On an RGB565
  frame buffer a fade is `wcgfx.dim_rows` over the picture rows; it
  exists and is used for landing today.
- **Big text.** The proportional picture font of TITLE.VGA section 1
  (60 frames, one per glyph) is converted as `ti1.wcs` with the width
  table `ti1wd.wc` and drawn by the title's `print_subtitle` port
  (6.2). "Meanwhile..." is held as a converted picture
  (`meanwhile_128_62.COL.bin`); "The End" waits for the endings,
  which are not started.
- **Scaled sprite draws** (`DrawSpriteScaled` with rotation):
  `wcgfx.blit_rs` covers them.
- **Timing.** The reference port's scene code counts frames of its
  throttle's 62 ms and 1/60 s timer ticks (1.4 in chapter 1); the
  game's own pace was the turn, 1/10 s (docs/04 4.4.1). Keep the frame
  counts as they are and run the steps by the clock, 100 ms outside
  flight.
