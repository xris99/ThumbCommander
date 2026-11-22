# Wing Commander on the ThumbyColor - developer handbook

This folder is the handover for whoever continues the port (a person or
another model). It explains where the game comes from, how its data is
read and converted, how the running game works, and - in most detail -
the parts that are **not built yet**: the radio, music, the original
sound effects, and the hard-coded scenes that have not been started
(6.2: medals, funeral, office, bar, barracks, intro, credits,
endings).

Read `../README.md` first for what the game is and how to run it. Then:

| # | File | What it answers |
|---|------|-----------------|
| 1 | [01-wc1-re.md](01-wc1-re.md) | What wc1-re is, how its source is organised, how to read and run it as the reference |
| 2 | [02-original-data.md](02-original-data.md) | Every original file format the port touches, and which file holds what |
| 3 | [03-converter-and-assets.md](03-converter-and-assets.md) | The converter pipeline, the converted file formats, how to add a new asset type |
| 4 | [04-game-dynamics.md](04-game-dynamics.md) | Game flow, the simulation and its time base (10 turns per second), AI, damage, scoring - with the wc1-re function behind each part |
| 5 | [05-conversations-and-talking-heads.md](05-conversations-and-talking-heads.md) | The conversation director, lip sync and eye animation, how to extract and draw the heads |
| 6 | [06-cutscenes.md](06-cutscenes.md) | The scripted "Meanwhile..." animations (a bytecode) and the hard-coded scenes |
| 7 | [07-inflight-comm.md](07-inflight-comm.md) | Radio messages, who says what when, the VDU portraits |
| 8 | [08-music.md](08-music.md) | The OriginFX music format, the AdLib driver, and the rules that pick the music in flight |
| 9 | [09-sound-effects.md](09-sound-effects.md) | The original sound-effect records and which game event plays which |
| 10 | [10-thumby-music-interpreter.md](10-thumby-music-interpreter.md) | Design for an FM music player on the ThumbyColor's second core |
| 11 | [11-roadmap.md](11-roadmap.md) | Work packages in order, each with a definition of done |
| 12 | [12-memory.md](12-memory.md) | The RAM budget on the device, the rules that keep the game inside it, how to read the memory log |

## Status at handover

| Area | State |
|------|-------|
| Missions, campaign tree, scoring, promotions, medals (as text) | done, all 3 campaigns |
| Flight model, weapons, damage, pilot AI, manoeuvres | done (see chapter 4 for what is simplified) |
| 3-D view, cockpits, radar, displays | done |
| Briefing / debriefing / bar conversations | text plus **talking heads** with lip sync, eye animation and the close-up backdrops; all branch tests work |
| "Meanwhile..." scripted cutscenes between series | done (chapter 6 6.1); every object position checked step by step against the original interpreter |
| Hard-coded cutscenes | first group done: hangar run, deck, launch door, fly-off, landing, death, ejection and stranded (chapter 6 6.2); medals, funeral, office, bar, barracks, intro, credits and endings not started |
| Radio | four orders and a landing request with made-up lines; original table is converted (`comm.wc`) but unused (chapter 7) |
| Music | none - format, driver and game rules documented (chapters 8, 10) |
| Sound effects | five synthesised placeholders; original records documented (chapter 9) |
| Real hardware | runs on a ThumbyColor: menus, briefing, flight, landing, a second sortie. 63 KB of heap free while flying (chapter 12). **Frame rate has not been measured** |
| Real MicroPython | confirmed by the same run |

## How sure each statement is

Statements in these chapters carry one of three marks where it matters:

- **[src]** read in the wc1-re source (file and function are named);
- **[data]** checked against a real DOS installation with
  `tool/wc1_inspect.py` - you can repeat the check on your own copy;
- **[guess]** an estimate or a design proposal that nobody has measured
  or built. Chapter 10 is mostly this, and says so.

wc1-re reconstructs the *Kilrathi Saga* (Windows, 1996) executable. Its
SDL port also plays DOS data, and where the DOS game differs the port
says so in comments citing DOS addresses (`003:0587`, `STRAX.DRV ...`).
Those DOS-side statements are second-hand: wc1-re's authors read them
out of the DOS binaries, this project did not.

## Ground rules

1. **No Origin data in the repository.** `games/wingcommander/assets/`
   is git-ignored and built by each player from their own copy. That
   covers pictures, text, music and timbres alike. Keep quoted game
   text in docs and tests to the odd short example. Folders written by
   `wc1_inspect.py --png/--export` hold Origin data too.
2. **GPL-3.0.** Everything under `games/wingcommander/` and `tool/wc1*`
   derives from wc1-re and carries its licence. The engine
   (`thumby_engine/`) and the other games keep their own.
3. **Port names, not just behaviour.** Functions keep their wc1-re names
   (`inflict_damage`, `set_up_action_sphere`, `intelligence_events`) so
   both sources can be read side by side. Keep doing that.
4. **Convert on the PC, stay simple on the device.** Anything that can
   be decided at conversion time (scaling, palette matching, parsing
   variable-length formats) belongs in `tool/`. The device reads
   fixed-layout records with `struct.unpack_from` and `seek`.
5. **No allocation in the flight loop.** MicroPython's collector stops
   the game for milliseconds. Buffers are created once; byte strings
   are reused; sprite files are opened only on a cache miss.
6. **Test on the PC first.** `tool/wc1_selfplay.py` (a whole sortie
   through the buttons) and `tool/wc1_check.py` (every mission) must
   stay green. Add a self-running check for each new feature.

## The target machine in numbers

| | |
|---|---|
| CPU | RP2350, two Cortex-M33 cores; the game raises the clock to 300 MHz (`engine.freq`) |
| RAM | 520 KB total, of which 231 KB of MicroPython heap are free when the game starts (measured). The game's code takes about 80 KB of that, its fixed buffers 42 KB - see chapter 12 before planning any buffer |
| Flash | 16 MB, shared by firmware, all games and their assets (this game's assets: about 4.4 MB) |
| Screen | 128 x 128, RGB565, `display.buffer` is a `bytearray` |
| Sound | one PWM output (GPIO 23); the engine plays one IMA-ADPCM stream from a viper loop on core 1 |
| Code | MicroPython about 1.27; `@micropython.viper` / `.native` allowed; `.mpy` built with `-march=armv7emsp` |
| Screen layout used | rows 0-15 status bar, rows 16-111 the 128x96 picture, rows 112-127 status bar |

The PC emulation (`thumby_engine/pc`, CPython + pygame) is where all
development so far happened. It emulates viper pointer types but not
MicroPython's memory limits or speed.

## Quick start for the next developer

```bash
# reference source (read-only)
git clone https://github.com/neuromancer/wc1-re

# convert your own game data, then run the checks
python3 tool/wc1_convert.py /path/to/WING
python3 tool/wc1_selfplay.py
python3 tool/wc1_check.py -v

# look inside the original files (chapters 5-9 use this throughout)
python3 tool/wc1_inspect.py /path/to/WING sections TALKING.VGA
python3 tool/wc1_inspect.py /path/to/WING talk 0 1 0
python3 tool/wc1_inspect.py /path/to/WING midgame 0 0
python3 tool/wc1_inspect.py /path/to/WING songs
```

Start with chapter 11; it orders the work and says what to measure on a
real device before building the expensive parts.
