# 2. The original data

Everything below is the **DOS** release (the GOG copy is this one): a
`WC.EXE` and a `GAMEDAT` folder. Statements marked **[data]** can be
repeated with `tool/wc1_inspect.py`; the readers live in `tool/wc1/`.

## 2.1 Logical files: INSTALL.DAT

The game never opens a file by name. It asks for *logical file N*, and
`INSTALL.DAT` maps numbers to names: 16-byte records of
`name[13], disk, type, id + 1`. The logical number is the last byte
minus one. [data] `wc1_inspect.py WING files`:

| # | File | # | File | # | File |
|---|------|---|------|---|------|
| 0 | FONTS.FNT | 9 | TITLE.VGA | 17-21 | PCSHIP.V00-V04 |
| 1 | SCRAMBLE.VGA | 10 | BRIEFING.000 | 22-43 | SHIPTYPE.Vnn / SHIP.Vnn (type + 22) |
| 2 | PILOTANM.VGA | 11 | WINGMEN.VGA | 51 | SHIPTYPE.V29 (missiles) |
| 3 | OBJECTS.VGA | 12 | PLANETS.VGA | 58 | CAMP.000 |
| 4 | BRIEFING.VGA | 13 | COMMUNIC.DAT | 59 | WINGLDR.TIM |
| 5 | RECROOM.VGA | 14 | ARROW.VGA | 60 | INTRO.DAT |
| 6 | TALKING.VGA | 15 | MODULE.000 | 63-68 | MIDGAME.V00-V05 |
| 7 | MUSIC.MID | 16 | SAVEGAME.WLD | 71 | SERIES.VGA |
| 8 | COCKPIT.VGA | | | | |

So `FetchDiskPacketRetrying(6, 3, 0)` in wc1-re reads section 3 of
TALKING.VGA. The Secret Missions add files that wc1-re addresses as
logical 52 / 61 / 62 (MODULE / CAMP / BRIEFING `.001`), 80
(TALKING1.VGA), 83 (WINGMEN1.VGA) and further MIDGAME files [src]; a
plain WC1 `INSTALL.DAT` does not list all of them, so open those by
name.

`INTRO.DAT` is the copy-protection question table, not an intro.
`GAME.PAL`, `CONVERT.PAL`, `STRAX.DRV` have no logical number.

## 2.2 The packet archive

Nearly every file is one container format (`tool/wc1/packet.py`,
wc1-re `src/sdl/resources.c`):

```
u32  file size
u32  entry[n]     low 24 bits: offset of the section
                  high 8 bits: compression (1 = LZW, else stored)
                  entry[0]'s offset is also the directory size,
                  so n = offset / 4 - 1
```

A compressed section starts with a `u32` unpacked size, then an LZW
stream: codes of 9 to 12 bits packed LSB-first, `0x100` clears the
table, `0x101` ends the stream, the first free code is `0x102`.

Sections are simply numbered. What a section *is* depends on the file.
[data] The `.VGA` picture archives are stored uncompressed (their
shapes are run-length coded already); the data archives (`MODULE`,
`CAMP`, `BRIEFING`, `FONTS.FNT`, `MUSIC.MID`, `WINGLDR.TIM`) are LZW.
Sections can be empty (size 0).

## 2.3 Shapes

A picture section is a *shape*: a table of frames
(`tool/wc1/shape.py`, wc1-re `src/gr.c`).

```
u32  size (unused)
u32  frameOffset[n]      relative to the section start; the low word
                         of frameOffset[0] is the table's end, so
                         n = that / 4 - 1
frame:
  i16 right, left, top, bottom     extents around the hot spot
  repeated until code == 0:
    u16 code      count = code >> 1, bit 0 = run-length packed
    i16 x, y      where this run starts, relative to the hot spot
    data          count literal bytes, or packed: bytes c with
                  c & 1 -> repeat the next byte c >> 1 times
                  else  -> c >> 1 literal bytes follow
```

Width is `left + right + 1`, height `top + bottom + 1`. Pixels the
runs never touch are transparent - there is no transparent colour
index. A frame is drawn with its **hot spot** at the given screen
position, so a 320-wide background has hot spot (0, 0), a ship sprite
has it at its centre, and overlay parts (a mouth, an eye pair) have it
wherever makes their draw position convenient. Always carry the hot
spot through conversion.

Colours are indices into the 256-colour palette `GAME.PAL` (an IFF
stub; the 768 RGB bytes start at offset 0x30, 8 bits per component).
Scenes change palette entries at run time for fades and for the
cockpit-light effects; the port ignores that so far and uses the base
palette everywhere.

The screen is 320 x 200 with **non-square pixels** (it filled a 4:3
monitor, so a pixel is 1.2 times taller than wide). All coordinates in
wc1-re are in that space.

## 2.4 Which file holds which pictures

[src] resource lists at the top of `src/logic.c` and the
`FetchDiskPacketRetrying` calls; [data] frame counts from
`wc1_inspect.py WING sections FILE`.

| File | Section(s) | Contents | Used by (wc1-re) |
|------|-----------|----------|------------------|
| SHIPTYPE.Vnn | 0 | fighter, 37 views | `load_ship`, `get_right_shape` |
| SHIP.Vnn | 0-36 | capital ship, one view per section | same |
| SHIPTYPE.V29 | 0 | missiles | |
| OBJECTS.VGA | 0-17 | thrusters, 3 explosions, debris, bolts, sparks, rock, jump flash, mine, 2 asteroids | flight |
| PCSHIP.V0n | 0-3 | cockpit front / left / right / rear, 320x200 | `aCockpitPrimaryResources` |
| | 4 | the pilot in the cockpit (4 frames) | `pCockpitPilotShape` |
| | 5 | cockpit part shown during ejection | `ejection_sequence` |
| | 6 | cockpit geometry (not a shape) | view window, instrument positions |
| | 7 | damage marks for the cockpit (22 frames) | `pCockpitDamageShape` |
| | 8 | the ship on the flight deck (2 frames) | `scramble`, `landing` |
| | 9 | weapon symbols for the displays (30 frames) | `pCockpitWeaponShapePtr` |
| COCKPIT.VGA | 0 | crosshair, lock, brackets | `pTgtLockShapePtr` |
| | 1, 2 | in-flight computer screen, nav map symbols | `src/nav.c` |
| | 4, 5 | indicator lights, cockpit explosion (8 frames) | `pCockpitIndicatorShape`, `pCockpitExplosionShape` |
| | 6, 7 | backdrops for the chase and rear views | `pCinematicViewBackdropPtr`, `pLogicRearViewBackdropPtr` |
| PLANETS.VGA | 0-11 | stars (38 frames) and planets | `init_constellation` |
| TALKING.VGA | 0-10 | talking heads, 21 frames each | `LoadFace` (chapter 5) |
| | 11 | conversation overlay, 2 frames | `CloseTalk` |
| WINGMEN.VGA | 0-11 | radio portraits | `LoadCommPortraitShape` (chapter 7) |
| BRIEFING.VGA | 0-5 | briefing room: backdrops, seated pilots, colonel at the podium, map frame | `LoadBriefingRoom`, `DrawPodiumShot` |
| | 6 | debriefing | `DeBriefing` |
| | 7 | colonel's office | `Office` |
| | 8, 10 | medal ceremony | `AwardCampaignMedal` |
| | 9 | funeral | `funeral_sequence` |
| RECROOM.VGA | 0, 1 | bar backdrop and close-up backdrops | `RecRoom` |
| | 2 | kill board | `ShowChalkBoard` |
| | 3-10 | one seated pilot per section, 6 frames | `RecRoom` (`personality + 3`) |
| | 11 | bar animations (41 frames) | `RecRoom` |
| | 12 | barracks (51 frames) | `BarracksScreen` |
| SCRAMBLE.VGA | 0 | hangar run (27 frames) | `PlayScrambleHangarScene` |
| | 1-4 | flight deck, pilots, deck crew | `scramble` |
| | 5, 6, 9 | landing | `landing` |
| | 7 | canopy closing | `LaunchPlayerShip` |
| | 8 | launch tube | `ShowCarrierLaunchSequence` |
| PILOTANM.VGA | 0 | death in the cockpit | `death_sequence` |
| | 1, 2 | ejection | `ejection_sequence` |
| | 3 | pilot hand on the stick (18 frames) | `pCurrentPilotHandShapePtr` |
| TITLE.VGA | 0, 1, 4 | intro: logo, big font, text | `Title_Sequence` |
| | 5 | title and ending pictures (18 frames, 320x200) | title, `ShowCampaignVictorySequence` |
| | 2, 3, 16, 17 | endings | `ShowTigerClawEscapeScene`, `ShowTheEndScreen` |
| MIDGAME.Vnn | 0, 3, 4 | cutscene sprites | chapter 6 |
| SERIES.VGA | 0 | the campaign tree picture | |
| ARROW.VGA | 0 | mouse pointers | |

Which function fetches which section is read from the source. The
short descriptions of *what* the frames show were checked by eye only
for TALKING, WINGMEN, the ships, cockpits and effects; the others are
inferred from the function that uses them. Export a section with
`wc1_inspect.py WING shape FILE N --png DIR` before building on a
description.

## 2.5 Fonts: FONTS.FNT

Four sections, one font each [data]. Layout (`convert_fonts`):

```
u16 height
u8  ink            the pixel value that means "set"
u8  ?
u8  width[256]     at offset 4
u8  offsetLow[256] at 0x104
u8  offsetHigh[256] at 0x204
glyph data         one byte per pixel, width x height per character
```

## 2.6 Missions: MODULE.00x

Six LZW sections of fixed-size records for 64 mission slots; slot =
`series * 4 + mission` (`tool/wc1/mission.py`, wc1-re
`LoadMissionData` in `src/cmpgn.c`, layouts in `include/wcdata.h`):

| Section | Record | Count per mission | Contents |
|---------|--------|-------------------|----------|
| 0 | 24 bytes (12 x i16) | 1 | entry nav point, home ship, player ship (-1 = empty slot), 8 initial values |
| 1 | 77 bytes | 16 | nav point: name[30], type, position (3 x i32), radius, 4 triggers, 2 preload types, up to 10 ship indices |
| 2 | 64 bytes | 16 | objective: type, index, text[60] |
| 3 | 42 bytes | 32 | ship: type, side, leader, mission type, home nav point, position, heading, formation, speed, AI rating, pilot, state, target |
| 4 | 40 bytes | 1 | auxiliary data |
| 5 | | | per-series names (`$S` in conversations) |

A nav point is an **action sphere**: a place with a radius, a list of
ships that exist there, and triggers that bring in further ships
(waves) when earlier ones are gone. `wc1_convert.py WING --dump S M`
prints a mission in readable form.

## 2.7 Campaign: CAMP.00x

Section 1 holds one 0x5A-byte record per series (1-based) [data]:

```
+0  i16 debrief pilot      +2 i8 number of missions
+3  i16 score needed to "win" the series
+5  i8  sequence           cutscene after the series (see below)
+6  i8  win series, +7 win ship, +8 lose series, +9 lose ship
+10 4 x 20 bytes           per mission: medal, medal score,
                           16 objective scores
```

`sequence` selects the "Meanwhile..." animation (chapter 6): in WC1
series 2-3 use scene 0, 4-6 scene 1, 7-8 scene 2, 9-11 scene 3; 0x40
(series 12) is the victory ending, 0x41 (series 13) the retreat
ending; series 1 has 0xFF, none [data]. Sections 0 and 2 are small
tables (416 and 104 bytes) that the port does not read and that were
not analysed.

## 2.8 Conversations: BRIEFING.00x

One section per mission slot (`series * 4 + mission`). Each section
[src `SceneDirector`, data]:

```
u32[10]   five pairs (scene offset, text base offset):
          0 briefing, 1 debriefing, 2-4 the three bar conversations
scene:    13-byte records until shot == -2
  i8  shot            what to show (chapter 5)
  i8  text colour     index into a 12-entry colour table; -1 = keep
  i8  talker          "conversation character" (backdrop), or a
                      nav-point number for map shots; -2 = keep
  i16 duration        wait after the line, in 1/60 s
  i16 tests           offset of a branch-test string, 0 = none
  i16 text            offset of the line
  i16 mouth           offset of the lip-sync string
  i16 face            offset of the eye-animation string
text:     NUL-terminated strings; all offsets are relative to the
          text base
```

WC1 has 56 slots and 2,885 records; the two expansions 1,257 and
1,268 [data]. Lines are at most about 130 characters. Tokens in the
text (`$C` callsign, `$R` rank, `$W3` a wingman's name, ...) are
listed in `talk.py` `expand`; branch tests in `talk.py` `branch`.

## 2.9 Radio: COMMUNIC.DAT

Not an archive. A flat table of 80-byte NUL-terminated strings:
`offset = (personality * 11 + line) * 80`; 14 personalities x 11 lines
= 12,320 bytes [data]. `COMMSM2.DAT` is the same for Secret Missions
2. See chapter 7.

## 2.10 Music: MUSIC.MID and WINGLDR.TIM

`MUSIC.MID` is a packet archive of 41 sections; each is a complete
standard MIDI file (format 1, 480 ticks per quarter note) extended
with Origin's `0xFE` control events [data]. `WINGLDR.TIM` has three
sections of instrument definitions: 0 = Roland MT-32, 1 = AdLib (one
count byte, then 79 timbres of 48 bytes), 2 = PC speaker. Chapter 8
describes both completely. `STRAX.DRV`, `SUPERTM.DRV`, `TM.DRV` are
the DOS sound drivers (code); the port does not read them.

## 2.11 Cutscene scripts: MIDGAME.Vnn

Seven sections [data]:

| Section | Contents |
|---------|----------|
| 0 | primary shape (backgrounds; may be empty) |
| 1, 2 | animation definitions for variant 0 (series won) and 1 (series lost) |
| 3, 4 | secondary shape (sprites) for variant 0 / 1 |
| 5, 6 | scene packet for variant 0 / 1: `u32 scene offset, u32 text base`, then conversation records as in 2.8 |

Chapter 6 documents the definition format.

## 2.12 What is inside WC.EXE

The executable is not parsed. Tables that the game compiles in were
copied from the wc1-re source into `tool/wc1/tables.py`: ship and
weapon statistics, hardpoints, the 62-direction view tables, formation
offsets, every AI table, pilot names and ranks, the player's damage
table, conversation colours, the talking-head origins and the
phoneme table (`TALKING_HEAD_ORIGINS`, `SM2_HEAD_ORIGINS`,
`MOUTH_FRAMES_BY_PHONEME`; chapter 5 plays them in `talk.py`).
The hard-coded cutscene coordinates were transcribed straight into
the scene modules instead: `scramble.py`, `launchseq.py`,
`deathseq.py`, `ejectseq.py`, each constant commented with its
wc1-re symbol. Still to be copied when their features are built (all
in wc1-re, with file names in the later chapters): the sound-effect
records, percussion maps, Kilrathi ace names.
