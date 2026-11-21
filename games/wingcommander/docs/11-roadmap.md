# 11. Roadmap

Work packages in a sensible order. Each has a definition of done that
can be checked without judgement calls. "PC" means verifiable on the
emulation; "device" means it needs a real ThumbyColor.

The owner's stated priorities: cutscenes; talking heads (a selection
or all); in-flight messages; understanding in-flight music and, as
the goal, an FM music interpreter running in the background.

## 0. First: put the game on a device

The game runs on a ThumbyColor after a rework for RAM (chapter 12
has the measured budget: 63 KB free in flight, 88 KB in the menus).
How fast it runs is still open. Everything below adds RAM and CPU
load, so that part of the baseline comes first.

- Deploy (`tool/deploy.py thumbycolor --game wingcommander`) and fly
  mission 1.
- Record: the `WC mem` lines of the log (12.5); the `WC rate` line
  printed after a flight (4.4.1) for a dogfight with six ships -
  turns per second must reach the chosen rate (10 at "original"),
  pictures per second say how much is left; load time of a mission.
- Run the three audio measurements of 10.9.

Done when these numbers are written into `../README.md` under
"Status". If the picture rate is below about 15, optimise the flight
loop before adding features (candidates: `flight.draw_object` sprite
loads, `world.collide`, the AI's per-turn collision prediction).

## 1. Radio (chapter 7) - PC

Smallest package, no new art needed for the text part, and it makes
flights feel like the original at once.

1. `World.send_message` with the original filter; delivery loop in
   `Flight`; lines from `comm.wc`; duration formula.
2. All call sites of table 7.3.
3. Two-step menu and `request()` with the conditions of 7.4.
4. Portraits: `convert_portraits`, drawn in the right display.

Done when: a headless test shows every (personality, line) pair
renders non-empty text; `wc1_selfplay.py` logs at least one wingman
message per sortie; the menu test walks every state; `wc1_check.py`
is still green.

## 2. Music decisions (8.7) - PC

`music.py` with `gametrack`, `changetrack`,
`new_space_music_changes`, the missile-lock shortcut, and a command
queue with the "ignored if queued or unchanged" rule. Output for now:
a log of `(tick, track, mode)`.

Done when: unit tests cover each branch of both functions; a
self-play log shows cruise -> combat -> stinger -> cruise ->
homeward tracks in a plausible order.

## 3. Talking heads (chapter 5) - PC, then device for RAM

1. `convert_heads` with the composite-then-scale method (5.6) and a
   `--preview` sheet per face.
2. Backdrops for the conversation characters (5.4).
3. `Talk`: face loading, the two animation cursors exactly as in 5.5,
   partial redraws.
4. Podium lip sync for shots 2 and 11 (optional second step).

Selection if flash or time is short: faces 0, 9, 10 first (62 % of
the lines), then the eight pilots.

Done when: every briefing, debriefing and bar scene of campaign 0
plays through in a headless run without error (walk all records with
both outcomes of each branch test forced); preview sheets show mouths
and eyes in the right place for all eleven faces; on the device,
`mem_free()` during a conversation stays above a margin you choose
after step 0.

## 4. Scene interpreter and "Meanwhile" scenes (6.1) - PC

1. `convert_midgame`: frames in use, scaled scripts.
2. `scene.py`: the interpreter; subtitles; skip.
3. Hook into `Game.ending` / the end-of-series path.

Done when: all eight scene variants of WC1 (MIDGAME.V00-V03, won and
lost) play to completion headless; a reference interpreter on the
unscaled data agrees with the device interpreter on every object's
position at every step (scaled); screenshots of each animation's
first and last frame are in `build/`.

## 5. Launch and landing (6.2) - PC

Transcribe `PlayScrambleHangarScene`, `scramble`, `LaunchPlayerShip`,
`ShowCarrierLaunchSequence`, `landing` into scene scripts for the
step 4 interpreter. Landing uses `world.damage_level()` for the
canopy list and the deck crew's comment.

Done when: a full `wc1_selfplay.py` sortie shows hangar -> deck ->
launch before the flight and landing after it, each skippable, each
falling back to today's behaviour when its asset file is missing.

## 6. Death, ejection, medals, funeral, office, intro, endings - PC

Same method, lower priority, one function at a time (table in 6.2).

## 7. Sound: sequencer and driver (chapters 8, 10) - PC

1. Converter: `mus.wc`, `tim.wc`, effect table, percussion tables.
2. `ofx_seq`: port of the sequencer and driver layers.
3. Host harness from wc1-re that logs OPL register writes;
   comparison test.
4. `ofx_ref.py`: numpy synthesiser; render all songs to WAV.

Done when: register logs are identical for all 41 songs over their
first full loop, and for three songs with a `leave` command at a
scripted time; the WAVs sound like the DOS game (compare with wc1-re
running your DOS data: it plays these songs through the same driver).

## 8. Sound on the device (chapter 10) - device

Follow 10.11 from step 5: measurements, the unified audio loop with a
square-wave back end, then the FM operator, then effects.

Done when: cruise music plays during a flight at a steady frame rate;
the late-sample counter stays at zero through a dogfight; a kill
produces its stinger and the music returns; the original effects
replace the five placeholders.

## 9. Gameplay fidelity

Independent of the above, from 4.10: missile lock-on (with its tones,
once sound exists), landing approach, real asteroid and mine fields,
Kilrathi aces (names, taunts, persistence), the other cockpit views,
the damage display, difficulty tuning against the original. Each is
a port of a named wc1-re function.

## Risks and unknowns

| Risk | Why it matters | How to retire it |
|------|----------------|------------------|
| Frame rate on the device is unmeasured | every feature assumes headroom | step 0 |
| Free RAM is short | 63 KB free in flight, 88 KB in the menus (measured); heads need about 15 KB, music about 40 KB in its small variant | chapter 12.7 goes through each planned feature; 12.6 lists the levers |
| viper FM may be too slow | decides the whole audio design | 10.9 before writing the synth; fallbacks in 10.10 |
| Core 1 stalls during flash writes or collection | audible gaps | 10.9 (c); write files only in menus |
| Flash budget | 16 MB shared; assets today 3 MB; all scene art at screen scale is about 2 MB more uncompressed | convert only frames that are used; halve animation frame counts |
| Descriptions of art not looked at | several "what the frames show" entries in 2.4 are inferred from code | export and view before converting |

## Conventions for whoever continues

- One feature, one asset file, one fallback: a missing file must
  leave the game playable (that is how text-only conversations and
  placeholder sounds coexist with the originals later).
- Put every table copied from wc1-re into `tool/wc1/tables.py` with a
  comment naming the source file and symbol.
- New converted formats get a 4-byte magic with a version digit and a
  paragraph in chapter 3.
- When something in these chapters turns out wrong, fix the chapter
  in the same change. The marks [src] / [data] / [guess] are there so
  that a reader knows which statements were only believed.
