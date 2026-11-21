# 12. Memory on the device

RAM is the tightest resource of this port. The first run on a real
ThumbyColor ended in `MemoryError` at launch; this chapter records
what was learned, how the game budgets its heap since, and what to do
when a new feature needs room.

## 12.1 The numbers from a real device

**The first build** died at launch. Its log (figures taken without
collecting first, so they include garbage):

| Moment | Free heap (bytes) |
|--------|-------------------|
| engine audio and cutscene helpers loaded | 187,376 |
| game modules for the menus loaded, tables read | 88,672 |
| crash while allocating the third pool of the frame cache | 43,600 |

It failed asking for 8,000 contiguous bytes while 43 KB were free in
total: the heap was **fragmented**, and the margin was small as well.

**The reworked build** (this chapter's plan) flies. Its `WC mem`
lines, each taken after a collection, on the same device:

| Line | Free heap | Cost of the step | What the step is |
|------|-----------|------------------|------------------|
| start | 230,768 | | the engine is up; `MainGame` and `wcdata` are loaded |
| buffers | 188,512 | 42,256 | frame cache and cockpit buffer |
| code | 126,096 | 62,416 | `ui`, `wcgfx`, `flight`, `world`, `ai`, `wcmath` (53,929 bytes as `.mpy` files: loaded code takes about 1.16 times its file size) |
| ready | 96,896 | 29,200 | ship and AI tables, two fonts, palette, sound handles |
| launch | 87,776 | 9,120 | `campaign` module, saved game, campaign and mission records; the briefing is already released |
| flight | 63,360 | 24,416 | the world (44 objects), the pilot AI, sprite set tables |
| landed | 64,896 | | the `Flight` object is gone; the world is still held for scoring |
| launch (second sortie) | 87,744 | | 32 bytes below the first: nothing leaks between flights |
| flight (second sortie) | 63,456 | | |

So: **about 231 KB of heap when the game starts, 63 KB free while
flying, 88 KB free in the menus.**

Three facts explain most of it:

1. **Code lives in RAM.** A `.mpy` loaded from the file system is
   copied to the heap. The game's modules are 74 KB as files and
   somewhat more once loaded (names, constants, function and class
   objects). Only firmware-frozen modules run from flash.
2. **An instance costs RAM per attribute.** MicroPython stores
   instance attributes in a hash table of 8 bytes per slot, sized in
   steps (..., 29, 37, 47, 59, 73, 97, ...). An object with 76
   attributes takes a 97-slot table: 776 bytes, about 1 KB with its
   lists. `__slots__` does not change that in MicroPython.
3. **The allocator never moves a block.** Whatever is allocated late
   lands in the gaps between older blocks; a large request can fail
   although the sum of the gaps would be enough.

## 12.2 The memory plan

`MainGame.py` documents and implements it at the top of the file:

1. **Big blocks first, once.** Right after `wcdata` is imported - and
   before any other game module - the game allocates the frame cache
   (`CACHE`) and the cockpit buffer (`CKBUF`) and keeps them for the
   whole session. `Flight` receives them as arguments and only resets
   the cache. Nothing in a flight allocates more than a few KB at a
   time any more.
2. **All flight code next, in one go.** `flight`, `world`, `ai`,
   `wcmath` are imported at start-up, not at launch: their code lands
   compactly at the bottom of the heap, and running out of memory
   would show at start instead of after a briefing.
3. **Everything else is small and short-lived.** A conversation's
   packet (8 KB on average, 11.6 KB at most) and the `talk` module are
   loaded for one
   conversation and dropped again (`Game.talk`); the module is removed
   from `sys.modules` so its code is freed too.
4. **Collect early.** `gc_pace()` sets `gc.threshold` at flight start
   so a collection runs whenever half of the free heap has been used
   up, instead of when the heap is full.

What changed against the first version, and the estimated effect:

| Change | Saves |
|--------|-------|
| frame cache 10 x 2,112 + 3 x 8,000 = 45.1 KB -> three pools, 28.4 KB (below) | 16.7 KB |
| `world.Lite` for the 34 non-ship object slots (12.3) | about 20 KB |
| briefing packet and `talk` module not held during the flight | 10 to 16 KB |
| cockpit read straight into its buffer (no second copy while loading) | 12 KB of peak |
| unused `Obj` fields removed (72 attributes: a 73-slot table) | about 2 KB |

The savings are estimates from sizes - the first build never got far
enough to be measured the same way. What is measured is the result
(12.1): the whole flight setup now costs 24 KB on top of the buffers,
and the largest single request during a session is the 11.6 KB of a
conversation packet, asked for when 88 KB are free.

### The frame cache

`wcdata.POOLS = ((10, 640), (7, 2112), (2, 3600))`:

| Pool | Slots x bytes | Holds |
|------|---------------|-------|
| tiny | 10 x 640 | bolts, missiles, sparks, debris |
| small | 7 x 2,112 | fighters, explosions |
| big | 2 x 3,600 | capital ships |

A frame goes to the smallest pool it fits; the least recently used
slot of that pool is replaced. A frame larger than the last pool
cannot be shown, so the converter guarantees the limit:
`MAX_SHIP_PIXELS = 3600` in `tool/wc1_convert.py` stores a capital
ship coarser until its largest view fits (the Tiger's Claw at `res`
56, the Exeter at 60, four others at 70-78; all fighters stay at 80).
**The two constants belong together.** At start-up `assets_stale()`
reads the header of every ship set and shows a notice if the data on
the device was converted for a larger buffer.

Measured on the PC over all 76 missions with a frame drawn every
turn: 0.25 sprite file reads per frame on average, at most 7 in one
frame, 3 or more in 1.3 % of the frames. The earlier 45 KB layout
did worse on the same run (0.33 reads per frame, at most 13, 1.9 %),
because it had 13 slots where this one has 19: small sprites no
longer occupy fighter-sized slots. A read is a file open, seek
and read on flash - if frames stutter when many objects appear at
once, give the tiny or small pool more slots before anything else.

## 12.3 Light objects

`World.o` has 44 slots: 0-9 are ships (`world.Obj`, every field),
10-43 are bolts, missiles, explosions, debris, rocks and mines
(`world.Lite`).

A `Lite` instance owns only the 33 fields named in `world.LITE` (plus
`i` and `m`); all other `Obj` fields exist on `Lite` as **class
attributes** holding the value `Obj.clear()` would give them. Code
that reads `ob.rating` or `ob.sh[0]` on a bolt gets the default, as
before. The rule that keeps this safe:

> Never write a field through a `Lite` object unless it is in
> `world.LITE` and reset in `Lite.clear()`.

A write to another field would create an instance attribute that
`clear()` does not reset, so the value would leak into whatever
reuses the slot. `tool/wc1_check.py` enforces the rule on the PC: it
checks that every `Lite` default equals a fresh `Obj`'s, then makes
any other write through a `Lite` object raise, and flies all
missions. Run it after touching `world.py` or `ai.py`.

`LITE` holds 35 names with `i` and `m`; the table step is 37. Two
more fields are free; the 38th costs every light object another 80
bytes (the next step is 47 slots).

The shield, armour and weapon lists are tuples on `Lite`, so an
accidental `ob.sh[0] = ...` on a non-ship fails loudly.

## 12.4 Rules for new code

- **A buffer above about 2 KB that a feature needs repeatedly is
  allocated at start-up**, next to `CACHE`, and reused. If two
  features never run at the same time (a talking head and a flight),
  let them share one buffer.
- **Read into buffers** (`f.readinto(buf)`), never
  `bytearray(f.read())` - the second form needs the memory twice.
- **Do not hold a file's contents to use a few records.** `seek` and
  read the record (`wcdata.Mission`, `SpriteSet`).
- **Classes with many instances get few attributes.** Mind the table
  steps (12.1). Prefer one `bytearray` or `array` for N things over N
  objects.
- **Code that runs rarely goes in its own module** and is unloaded
  after use, like `talk`: import inside the function, `del` the local
  name, `sys.modules.pop(name)`, `collect()`. A module can only be
  freed if no object of its classes is still alive.
- **No allocation per frame in the flight loop**, as before.

## 12.5 Reading the log

The game prints the free heap after a collection at fixed points:

```
WC mem start    after the engine, before the game allocated anything
WC mem buffers  frame cache and cockpit buffer allocated
WC mem code     all flight code loaded
WC mem ready    tables, fonts, sound handles; the menu's baseline
WC mem launch   at "Launch", before the flight is built
WC mem flight   flight built: what is left while flying
WC mem landed   flight objects released
```

Differences between consecutive lines are the cost of each step.
`flight` is the number that matters: it must cover the garbage of a
few frames. It was 63 KB when this was written. Below roughly 20 KB
expect stutter from frequent collections; below 10 KB, crashes in
busy scenes [guess - neither limit has been tried]. Compare the two
`launch` lines of consecutive sorties to catch a leak.

`main.py` also prints `FREE` when the game dies. That figure is taken
without collecting, so it is a lower bound.

## 12.6 If it is still not enough

In order of effort:

1. **Compile without line numbers**: `mpy-cross -O3` drops the line
   tables (a few KB over all modules) at the price of tracebacks
   without line numbers. Useful once the game is stable.
2. **Cockpit off** frees nothing at present, because `CKBUF` is
   allocated at start regardless. Allocating it only when the option
   is on returns 12 KB to players who fly without the cockpit art.
3. **Fewer object slots**: `NOBJ` 44 -> 36 saves about 3 KB and caps
   the number of simultaneous bolts and debris.
4. **Split `flight.py`**: the flight computer (pause menu, nav map,
   radio menu, weapon selection) is about a seventh of the module and
   could load on demand.
5. **Split `world.py` / `ai.py` by phase**: mission setup code
   (`init_ship`, `set_up_action_sphere`, formations) versus per-turn
   code. Harder, because both are needed during a flight.
6. **Unload the flight code between flights** to make room for
   talking heads and cutscenes: `flight`, `world`, `ai` are only
   needed while flying. This contradicts step 2 of the plan (loading
   compactly, once), so it should come with a measurement of whether
   the reloaded code still finds room; the result of a flight would
   have to be copied into a small object first, because the `World`
   instance keeps the module alive.
7. **Freeze the modules into the firmware.** Frozen bytecode runs
   from flash and costs no heap at all - this alone would free about
   80 KB. It needs a custom firmware build, which is why it is last.

## 12.7 What the measured budget means for the plans

| Feature | Needs (estimate) | Runs when | Room there | Verdict |
|---------|------------------|-----------|------------|---------|
| radio (chapter 7) | portraits under 30 KB on flash, drawn through the frame cache; the 12 KB message table read by `seek`; some code | in flight | 63 KB | fits |
| talking heads (chapter 5) | about 15 KB per face, one at a time, plus code | menus | 88 KB minus the 12 KB packet | fits |
| cutscenes (chapter 6) | interpreter code, sprites through the frame cache, one backdrop | menus | 88 KB | fits if frames stay within the cache pools; a 128 x 61 backdrop (7.8 KB) needs its own buffer or streaming from the file |
| music player (chapter 10) | tables 9 KB, timbres 4 KB, song buffers 14 to 45 KB, state 2 KB, plus perhaps 10 KB of code | always, also in flight | 63 KB | **tight**: about 40 KB with one 14 KB buffer per song slot and two slots; that leaves some 20 KB in flight, at the edge of 12.5's limit |

For the music player, plan from the start with the small variant
(song buffers sized for the largest in-flight song, 13.3 KB; the long
title track loaded only in the menus into both buffers' space), and
expect to need one of the levers of 12.6 - unloading `talk`-style
modules is already done, so the next candidates are the flight
computer split (4) and compiling with `-O3` (1).

The tables step (29 KB at `ready`) is larger than its files suggest
(types 9 KB, AI 2 KB, fonts 8 KB) and has not been looked into;
it is the first place to look for a few more KB.
