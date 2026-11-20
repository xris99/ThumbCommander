# 1. wc1-re: the reference

<https://github.com/neuromancer/wc1-re> (GPL-3.0). This port was written
against commit `62d70df`. Everything the ThumbyColor game does that is
"original" was read out of this source, so learn to navigate it before
changing game rules.

## 1.1 What it is

wc1-re is two things in one tree:

1. **A source reconstruction.** The C and C++ under `src/` compiles,
   with the original compiler (MSVC 4.20), to a byte-identical copy of
   the Wing Commander executable from *Wing Commander: The Kilrathi
   Saga* (1996), the Windows 95 re-release. That executable is itself a
   port of the 1990 DOS game (working title WINGLEADER): 16-bit C for
   the game core, plus a C++ audio library called `ix` that streams
   digital music. Because the result is byte-exact, the code is not an
   interpretation of the game - it *is* the game's logic, with names
   added.
2. **A modern port.** `src/sdl/` replaces Windows (DirectDraw, the
   multimedia timer, the `ix` audio library, the registry) with SDL2,
   switched in by `#ifdef SDL_PORT` in the game files. This "modern"
   build runs on macOS, Windows and Linux, and can play four data sets:
   Kilrathi Saga, the **DOS** game (compressed archives, AdLib / MT-32
   music), FM Towns, and the Super Wing Commander Mac demo.

The ThumbyColor port uses **DOS data** and the **game-core logic**. It
uses nothing of `src/sdl/` as code, but three files there are the best
existing description of DOS-only formats:

| File | Why it matters here |
|------|---------------------|
| `src/sdl/resources.c` | the DOS archive container and its LZW compression |
| `src/sdl/originfx.cpp` | a complete player for the DOS music and sound effects (MIDI sequencer + AdLib driver) |
| `src/sdl/music.c` | how game music commands map onto that player (queueing, leaving at a bar line) |

## 1.2 Reading the source

**Names.** About 1,450 functions exist. Roughly a third carry names
backed by evidence (debug strings, the leaked WINGLEADER main module,
symbol remnants): `inflict_damage`, `set_up_action_sphere`,
`gametrack`, `real_vid_transmit`. The rest are descriptive labels the
reconstruction chose (`DrawBriefingLongShot`,
`UpdateSceneAnimationObject`). Lower-case-with-underscores names are
almost always original. `AGENTS.md` in the wc1-re root states the
project's own rules, including this warning: a descriptive label says
what the code does, not what it was meant for.

**Globals** use Hungarian prefixes: `n`/`s` short, `c` char, `a` array,
`p` pointer, `st` struct, `sz` string, `b` flag, `e` enum. Example:
`aeShipMissionType[0]` is an array of enums, element 0 = the player.
Per-object state is "struct of arrays": one global array per property,
indexed by object number. `world.py`'s `Obj` class gathers the same
properties per object; the property names follow the arrays.

**Types.** The game core was 16-bit: `short` is the normal integer,
positions are 32-bit fixed point with 8 fractional bits, angles are
whole degrees. See chapter 4 for the conventions as ported.

**`#ifdef SDL_PORT`.** Inside game files, code under this guard is the
modern port's addition (speech, FM Towns, Secret Missions 2 fixes).
Code outside it, or under `#else`, is the original. When porting a
rule, read the original branch; use the `SDL_PORT` branch only as
commentary - it often explains a DOS difference.

**Address comments** (`/* Function start: 0x430BC0 */`) tie each
function to the original binary. Ignore them, but they make good
search keys.

## 1.3 Source map

Game core (`src/`), grouped by what this port needs from it. Files in
**bold** are already ported; the others are the source for the work
ahead.

| File | Contents | Ported to |
|------|----------|-----------|
| **spc.c** | object simulation: movement, rotation, collisions, housekeeping | `world.py` |
| **ship.c** | damage, shields, explosions, shock waves, weapons | `world.py` |
| **mission.c** | action spheres, waves, ship setup, formations | `world.py` |
| **geom.c**, **mathfp.c** | fixed-point vectors and angles, `get_right_shape` (which sprite view to draw) | `wcmath.py`, `flight.py` |
| **brains.c**, **smart.c**, **fl.c** | pilot AI: mission behaviours, the nine combat events, manoeuvre tables and scripts | `ai.py` |
| **logic.c** (first half) | mission-type logic per ship, resource lists | `ai.py`, `world.py` |
| **gameflow.c** | `PostMission`, `UpdateSeries`, scoring | `campaign.py` |
| **screens.c** `ParseTests`, `SceneDirector` | conversation branching and shot dispatch | `talk.py` (text only) |
| **cmpgn.c** `AddPCName`, `LoadMissionData` | text tokens, mission record loading | `talk.py`, `wcdata.py` |
| **objdata.c**, **game.c**, **data.c** | ship / weapon statistics, AI tables, cockpit geometry | `tool/wc1/tables.py` |
| **targ.c**, **auto.c**, **nav.c** | objectives, autopilot, nav map | `world.py`, `flight.py` (simplified) |
| cmpgn.c `LoadFace`, `LongTalk`, `CloseTalk`, `ParseMouthAnimation`, `ParseFaceAnimation` | talking heads | chapter 5 |
| screens.c (rest), killbrd.c | briefing-room shots, medals, office, bar, kill board | chapters 5, 6 |
| logic.c `LoadSceneAnimationResources` ... `PlaySceneAnimation`, pilot.cpp `ShowMeanwhileTransition` | scripted cutscene animations | chapter 6 |
| cutscene.c, launch.c, eject.c, ending.c, title.c | hard-coded cutscenes | chapter 6 |
| comm.c, cockpt.c `send_message`, `npc_communication`, `vid_transmit` | radio | chapter 7 |
| music.c | music state machine, `gametrack`, sound-effect dispatch | chapters 8, 9 |
| cockpt.c, damage.c, select.c, view.c | cockpit instruments, damage display, camera views | partly in `flight.py` |
| barracks.c, trainsim.c | save / load screen, training simulator | not ported |
| dib.c, winmain.c, winsys.c, sound.c, `ix/` | Windows back end | irrelevant |

`include/wcdata.h` holds the on-disk record layouts (mission, nav
point, ship, series) and `include/wc1.h` the enums (`ObjectClass`,
`ShipMissionType`, `ShipManeuver`, ...). The constants at the top of
`world.py` and `ai.py` mirror those enums.

## 1.4 How the modern port is put together

Understanding the layering shows which parts are reusable ideas:

```
 game core (src/*.c)        unchanged rules, 320x200 8-bit frame buffer
        |   calls what used to be Win32 / ix
 src/sdl/compat.c, video.c, input.c, timer.c, audio.c
        |   SDL2 window, palette -> RGB, keyboard/joystick, 60 Hz timer
 src/sdl/resources.c        opens DOS / KS / FM Towns archives alike
 src/sdl/originfx.cpp       DOS music + effects on an emulated YM3812
 src/sdl/mt32.c, speech.c   optional MT-32 emulation, optional voice packs
```

- The game draws into an 8-bit 320x200 buffer and calls `DIBslam` /
  `DIBslamReal` to show it; the port converts through the palette.
  Scene code is paced by that flip (it waits for vertical blank) and by
  a frame timer whose unit is 1/60 s (`SetMultimediaTimerCallback`:
  `period * 1000 / 60` ms).
- All data access goes through `FetchDiskPacketRetrying(logicalFile,
  section, flags)`. The logical file number comes from `INSTALL.DAT`
  (chapter 2). Seeing `FetchDiskPacketRetrying(6, face, 0)` therefore
  means "section `face` of TALKING.VGA".
- Kilrathi Saga replaced the DOS game's synthesised sound with
  recordings: music is streamed digital audio driven by a script, and
  effects are `sfxNN.wav` files. The DOS data has neither; it has
  `MUSIC.MID` and timbres, and the effect definitions sit inside
  `WC.EXE`. That is why the game-side file `src/music.c` talks about a
  "streamer" while `src/sdl/originfx.cpp` contains a MIDI sequencer:
  the first is KS, the second is what the port added for DOS data.

Why the C code itself is not compiled for the device: the modern
binary needs about 2.6 MB of static data and a 320x200 frame buffer;
the ThumbyColor has 520 KB of RAM and a 128x128 screen, and games on it
are MicroPython packages. Hence the port keeps data and rules and
rewrites everything else.

## 1.5 Running the reference

Build (from wc1-re's README; needs Python 3.10+, a C/C++20 compiler,
SDL2, LZO2, CMake, Rust):

```sh
git submodule update --init --recursive
make -j modern        # command-line binary: out-modern/wc1-modern
make -j modern-gui    # with the launcher
```

Run it from the folder that contains your `GAMEDAT`:

```sh
cd /path/to/WING && /path/to/wc1-re/out-modern/wc1-modern
```

The original has a hidden start-up path that jumps straight into a
mission; wc1-re's Makefile wraps it:

```sh
make run-modern-mission MODERN_RUN_DIR=/path/to/WING SERIES=1 MISSION=0
```

Use this to compare behaviour (what a wingman says when, how a
cutscene looks, which music plays). For exact numbers prefer reading
the source to watching the game.

A headless build was made during this project (`out-modern/wc1-modern`
existed) but the port's logic was verified by reading source and data,
not by instrumenting that binary. Instrumenting it - for example
printing every `spacetrack()` call, or dumping the frame buffer after
each cutscene step - is a cheap way to produce reference traces for
the features in chapters 5 to 9.

## 1.6 Where the modern port and the DOS game differ

Keep these in mind when a comment in wc1-re seems to contradict the
data in your `GAMEDAT`:

- DOS archives store their sections LZW-compressed; the code that
  unpacks them is the port's `src/sdl/resources.c`, not the game core.
  Comments that cite `SM2.EXE` or `WC.EXP` addresses describe the
  Kilrathi Saga expansion and FM Towns executables. The port plays the
  expansions "the Kilrathi Saga way" on DOS data as well.
- Secret Missions 2 adds faces 11 and 12 (TALKING1.VGA), two comm
  portraits (WINGMEN1.VGA), its own message table (COMMSM2.DAT) and
  cutscene files `MIDGAME.V06` to `V08`. The handling is in `SDL_PORT`
  blocks (`SdlPlayingSm2()`).
- The DOS game shows an Origin FX logo before the title; KS dropped
  it. `src/sdl/dos_intro.c` restores it.
- Speech (`src/sdl/speech.c`, `voices/`) is a modern addition for
  user-supplied recordings. The DOS game has no speech. Its only
  relevance here: `SdlVoiceMouthFrame` shows how to retime the mouth
  animation if speech were ever added.
