# 5. Conversations and talking heads

State today: `talk.py` plays every conversation correctly as *text*
(branches, tokens, colours, the nav map). This chapter documents what
the original shows on top of that, and how to build it.

Source: `SceneDirector` and the shot functions in wc1-re
`src/screens.c`; `LoadFace`, `LongTalk`, `CloseTalk`, `CloseLook`,
`ParseMouthAnimation`, `ParseFaceAnimation` in `src/cmpgn.c`.
Inspect your data with

```bash
python3 tool/wc1_inspect.py WING talk 0 1 0             # series 1, mission 0: all five scenes
python3 tool/wc1_inspect.py WING sections TALKING.VGA
python3 tool/wc1_inspect.py WING shape TALKING.VGA 0 --png /tmp/halcyon
```

## 5.1 The director

A conversation is a list of 13-byte records (layout in 2.8). The
director runs them in order [src]:

```
for each record until shot == -2:
    shot & 0x40      -> overlay on for this record (then mask it off)
    tests != 0       -> ParseTests may redirect to another record
    talker != -2     -> nConversationCharacter = talker
    switch on shot   -> prepare the picture (load a face, draw the room, ...)
    colour changed   -> text colour = asConversationTextColours[colour]
    parse the mouth and face strings into command lists
    if the text is not empty:
        call the shot's function with (text, duration)
```

A record with shot -1 keeps the previous picture. The scene type
passed to `SceneDirector` says where we are and decides the backdrop:

| Type | Scene | Backdrop shape | Called from |
|------|-------|----------------|-------------|
| 0 | briefing | BRIEFING.VGA 0 | `LoadBriefingRoom` |
| 1 | debriefing | BRIEFING.VGA 6 | `DeBriefing` |
| 2 | bar | RECROOM.VGA 1 | `RecRoom` (`src/killbrd.c`) |
| 3 | funeral | black + stars | `funeral_sequence` |
| 4 | colonel's office | BRIEFING.VGA 7 | `Office` |
| 5 | medal ceremony | BRIEFING.VGA 10 | `AwardCampaignMedal` |
| 6 | "Meanwhile..." | none | `ShowMeanwhileTransition` |

## 5.2 Shots

How often each occurs in WC1's 2,885 records is in the last column
[data].

| Shot | Meaning | Function | Count |
|------|---------|----------|-------|
| -1 | keep the picture, new line | | 113 |
| 0 | briefing establishing shot: pilots walk in (22 frames) | `EstablishingShot` | 31 |
| 1 | briefing room long shot | `DrawBriefingLongShot` + `CloseLook` | 57 |
| 2 | colonel at the podium, lip-synced | `DrawPodiumShot` + `CloseLook` | 227 |
| 3 | "Dismissed": pilots get up | `Dismissed` | 38 |
| 4 | nav map; `abs(talker)` = objective to highlight | `UpdateMap` | 134 |
| 5 | back to the long shot | `ReturnToBriefingLongShot` | 40 |
| 6, 7, 8, 16 | medal ceremony: long shot, establishing, pinning, medal chest | `DrawMedalLongShot`, `MedalEstablish`, `PinMedal`, `DrawMedalChest` | 14 |
| 9, 12-15 | funeral long shots (12-15 with star field) | `DrawFuneralLongShot` | 12 |
| 10 | debriefing establishing shot | `DebriefingEstablishingShot` | 41 |
| 11 | debriefing long shot, colonel lip-synced | `CloseLook` | 250 |
| 17 | funeral, wingman | `funeral_wingman` | 8 |
| 20-30 | **talking head**, face = shot - 20 | `LoadFace` + `LongTalk` | 1,920 |
| 31, 32 | faces 11, 12 (Secret Missions 2 only) | | |
| 50-59 | scripted animation n = shot - 50 (only in MIDGAME scenes) | `PlaySceneAnimation` | chapter 6 |

Two thirds of all lines are talking heads. Ten of the remaining
functions are short, hard-coded scenes in `src/screens.c` (lines
~600-930 and ~1470-1580): each draws a backdrop frame plus a few
sprites at fixed coordinates and waits. Port them like the hard-coded
cutscenes of chapter 6.

Faces [src, data]:

| Face | Who | Lines in WC1 | | Face | Who | Lines |
|------|-----|------|-|------|-----|------|
| 0 | Colonel Halcyon | 692 | | 6 | Paladin | 118 |
| 1 | Spirit | 59 | | 7 | Maniac | 98 |
| 2 | Hunter | 117 | | 8 | Knight | 74 |
| 3 | Bossman | 92 | | 9 | the player | 275 |
| 4 | Iceman | 95 | | 10 | Shotglass (barman) | 232 |
| 5 | Angel | 68 | | 11, 12 | SM2: Doomsday, Jazz (TALKING1.VGA) | |

If flash is tight, Halcyon, the player and Shotglass alone cover 62 %
of the talking-head lines.

## 5.3 What a face is made of

`TALKING.VGA` section = face number. 21 frames [data]:

| Frame | Size (face 0) | Content | Drawn at |
|-------|---------------|---------|----------|
| 0 | 320 x 129, hot spot (0, 0) | head and shoulders; transparent around | (0, 0) |
| 1-10 | 45 x 44 | ten mouth shapes | the face's mouth origin |
| 11-20 | 95 x 30 | ten eye / brow expressions | the face's face origin |

The parts' sizes and hot spots differ per face (and can differ per
frame); always read them from the frame.

Origins `{faceX, faceY, mouthX, mouthY}` in 320x200 coordinates
(`aTalkingHeadOrigins`, `src/screens.c`) [src]:

| Face | Origins |
|------|---------|
| 0 | 161, 60, 161, 90 |
| 1 | 161, 60, 161, 87 |
| 2 | 160, 60, 159, 90 |
| 3-9 | 161, 60, 161, 90 |
| 10 | 160, 53, 160, 88 |
| 11 (SM2) | 161, 60, 160, 90 |
| 12 (SM2) | 160, 60, 160, 90 |

One displayed frame is composed by `CloseTalk(talker, mouthFrame,
faceFrame)` in this order [src]:

1. star field, if this conversation character has a window (see 5.4);
2. backdrop frame, or black;
3. head (frame 0) at (0, 0);
4. if `faceFrame > -1`: frame `faceFrame + 11` at the face origin;
5. if `mouthFrame > -1`: frame `mouthFrame + 1` at the mouth origin;
6. if the record had the 0x40 flag: `TALKING.VGA` section 11, frame
   `min(face, 1)`, at (0, 0) (155 x 129; occurs twice in WC1 [data]);
7. conversation characters 5 and 6 add frames 10 / 11 of a special
   shape.

The text is printed below the picture at y = 160, in the record's
colour.

## 5.4 The backdrop behind a head

`talker` sets the *conversation character*, which `LoadFace` turns
into a frame of the scene's backdrop shape [src]:

| Character | Backdrop frame | Stars | Seen in [data] |
|-----------|----------------|-------|----------------|
| 0 | 4 | | briefing: the colonel |
| 1 | 5 | | briefing: a pilot in the audience (the player or a wingman) |
| 2 | 0 | yes, upper part (rows 0-76) | bar: Shotglass, in front of the window |
| 3 | 1 | | bar: seat |
| 4 | 2 | | bar: seat |
| 8 | 1 | yes | briefing scenes of some missions: the colonel (16 lines) |
| 9 | 2 | | same scenes: the player (7 lines) |
| 10, 12 | 0 | | debriefing: the colonel |
| 11, 13 | 1 | | debriefing: the pilots' side (mostly the player) |
| other | none (black) | | |

All backdrop frames are 320 x 128/129 with hot spot (0, 0) [data]. So
seven backdrops cover nearly everything: two briefing, two
debriefing, three bar (plus two more briefing frames for characters
8 and 9).

The port's static pictures (`brief_128_61`, `debrief_128_61`,
`bar_128_61`) are frame 0 of BRIEFING.VGA 0 / 6 and RECROOM.VGA 0 -
the *room*, not the close-up backdrops above. New files are needed.

## 5.5 Lip sync and eye animation

Each record carries two strings.

**Mouth string** (`ParseMouthAnimation`) - a rough phonetic spelling
of the line. Each character becomes one command:

- a letter `a`-`z` selects a mouth frame through this table [src]:

  ```
  a b c d e f g h i j k l m n o p q r s t u v w x y z
  0 5 4 4 1 8 4 7 0 4 4 7 5 4 2 5 6 4 4 4 3 4 6 4 4 4
  ```

- `$` selects frame 9 (closed, resting);
- decimal digits after it give the hold time in ticks (default 1);
- every other character is skipped (upper-case letters and
  punctuation occur a few times in the data and are ignored [data]).

Example: the line "Here are the assignments." has the mouth string
`herarteasinmants`; a listening pause looks like `p10$100`.

**Face string** (`ParseFaceAnimation`) - commands of the form
`<frame><ticks>,`: one hex digit `0`-`F` for the frame, a decimal
hold time, a comma. Frame `A` (10) means "no eye overlay" (the head's
own eyes show). `R` is a marker command (-2). Example:
`RA45,81,01,A35,81,01,` = neutral for 45 ticks, frame 8 for one,
frame 0 for one (a blink), neutral 35, ...

**Playback** (`LongTalk`) - two independent cursors, one per list,
stepped once per displayed frame [src]:

```
when a cursor's countdown is 0:
    if the current command is not the end:  advance one command
    command == end (-1):  frame = -1 (draw nothing)
                          mouth only: start the after-line wait
    command == marker (-2): go back to the first command, then use it
    otherwise:            frame = command.frame
                          (eyes: frame 10 -> -1)
                          countdown = command.ticks * 2
countdown -= 1
the line is over when both lists are at the end and `duration`
(1/60 s units) has passed, or when the player presses a key
```

Two consequences of this exact code, worth copying rather than
"fixing":

- the cursor advances *before* it reads, so the first command of each
  list is skipped on the first pass. Most face strings start with `R`
  (1,585 of 2,104 in WC1 [data]); that leading marker is what gets
  skipped, and the rest then plays once and ends with the eyes
  neutral;
- an `R` in the middle (518 strings) sends the cursor back to the
  start, so the part before it loops for as long as the line lasts.

**Time base.** The loop does one pass per displayed frame, and frames
outside flight are held to 16 per second (62 ms,
`ThrottleFrameAndDrawFps`, chapter 1.4) [src]. A tick is two passes,
so about 125 ms. `duration` is in 1/60 s
(`SetMultimediaTimerCallback`). On the ThumbyColor, drive both from
`time.ticks_ms()`: one tick = 125 ms, `duration * 1000 // 60` ms after
the line. With no speech, the mouth finishes long before a reader
does, so also wait for a button, as `talk.py` does now.

The podium shots reuse the mouth list without a head [src
`CloseLook`]: shot 2 draws frame `mouth` of BRIEFING.VGA 2 at
(225, 34); shot 11 draws frame `mouth + 17` of the debriefing shape at
(`nDebriefingPodiumX`, 53).

## 5.6 Extraction plan

Do not scale the 21 frames independently: after resampling to 40 % /
48 %, separately rounded hot spots put the mouth up to a pixel off the
face, and averaged edges leave a visible seam. Instead:

```
for each face:
    head = frame 0 on a 320x129 RGBA canvas
    for m in 0..9:   canvas_m = head with mouth frame m+1 drawn at the mouth origin
    for e in 0..9:   canvas_e = head with eye frame e+11 drawn at the face origin
    scale head and every canvas to 128x62 with gfx.resample
    head_small  = crop to the head's bounding box
    mouth patch = the rectangle (bounding box of all ten mouth frames,
                  in scaled coordinates) cut from each canvas_m
    eye patch   = likewise from each canvas_e
```

Patches cut from the *composited and scaled* picture line up exactly
and can be opaque rectangles (no transparency test when drawing). The
head keeps index 0 = transparent so the backdrop shows around it.

Proposed file `head<NN>.wc` [guess]:

```
4s  'WCH1'
u8  head x, y, w, h          position and size inside the 128x62 picture
u8  mouth x, y, w, h
u8  eye x, y, w, h
head pixels                  w*h palette indices, 0 = transparent
10 mouth patches             w*h each, opaque
10 eye patches               w*h each, opaque
```

Measured for WC1 at screen scale: a head's bounding box is about
70 x 60 pixels, a mouth patch about 22 x 21, an eye patch about
33 x 14; **11 to 16 KB per face, about 150 KB for all eleven**
[data, computed from frame sizes; the composite method may add a
little]. One face fits RAM comfortably (about 15 KB); load it on a
face change, as `LoadFace` does, and free the previous one.

Backdrops: seven 128 x 62 pictures as `.COL.bin` (16 KB each) or as
palette indices (8 KB each). Indices are better here: the head is
indexed too, and one `wcgfx.blit_indexed` path can draw both.

The star field behind Shotglass can be a fixed pattern in the first
version; the original animates PLANETS.VGA stars
(`InitializeConstellationField`).

## 5.7 Runtime plan (talk.py)

1. In `Talk.run`, where the shot is decoded: for 20-32 call a new
   `load_face(shot - 20, character)` when the face or character
   changed; keep `speaker` logic for the name line.
2. Parse the mouth and face strings into two preallocated
   `bytearray`s of (frame, ticks) pairs. The longest lists in WC1 are
   73 mouth commands and 13 face commands [data]; the original's
   buffers hold about 80. Ticks can exceed 255 (`$100` is common, and
   larger values occur), so store them as 16 bits.
3. Replace the static wait in `Talk.say` with a loop: step both
   cursors by elapsed time, redraw only the mouth and eye rectangles
   that changed (blit the patch; when the frame is -1 blit the patch
   region from the head itself - keep the head in RAM for that), call
   `display.update()`.
4. Draw order on a face change: backdrop, head, then patches. The text
   area below does not change during the animation.
5. Missing files must not break the game: no `head<NN>.wc` -> today's
   text-only path.

Screen layout: the picture area is rows 16-111 (96 rows). A 128 x 62
conversation picture leaves 34 rows for text inside the picture area,
as today.

Test: extend `tool/wc1_selfplay.py` to take a screenshot inside a
briefing and check that the head rectangle is not empty; add a
converter preview sheet (`--preview`) that shows each face with all
ten mouths - errors in origins are obvious there at a glance.

## 5.8 Open points

- Characters 5 and 6 ("special shape" frames 10 / 11) and the overlay
  (0x40) each occur once or twice per campaign; which pictures they
  are was not looked at. Check before deciding to skip them.
- Conversation text colours: the 12-entry table is already in
  `ai.wc`; Secret Missions 2 adds two (indices 12, 13 -> palette 9 and
  13) [src].
- `EstablishingShot`, `Dismissed` and the debriefing shots animate 14
  seated pilots (`aBriefingCharacters`, `DrawBriefingCharacter`) with
  per-pilot frame lists, skipping dead pilots. That table was not
  transcribed.
