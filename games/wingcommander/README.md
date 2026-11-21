# Wing Commander for the ThumbyColor

The original *Wing Commander* (1990) on a 128x128 handheld: the real
missions, campaign tree, briefings, ships and cockpits, with the flight
model and pilot AI ported from the reconstructed game source
[neuromancer/wc1-re](https://github.com/neuromancer/wc1-re).

wc1-re runs the original game on PC, Mac and Linux by putting an SDL
layer under the recovered C code. That code needs a 320x200 screen and
several megabytes of RAM, so it cannot run on an RP2350 as it is. This
port does the same job one level up: it keeps the game's **data and
rules** and replaces everything underneath with `thumby_engine`.

No Origin data is in this repository. You convert your own copy of the
game once on a PC; the result stays on your machine and your device.

## Setting it up

You need the DOS version's `WC.EXE` and `GAMEDAT` folder (for example
from the GOG release), plus `numpy` and `Pillow` on the PC.

```bash
# 1. convert your game data (writes games/wingcommander/assets/)
python3 tool/wc1_convert.py /path/to/your/WING
python3 tool/wc1_convert.py /path/to/your/WING --preview   # + PNG sheets

# 2. play on the PC
python3 tool/run_pc.py --game wingcommander

# 3. put it on the ThumbyColor
python3 tool/deploy.py thumbycolor --game wingcommander
python3 tool/deploy.py thumbycolor --game wingcommander --remote
```

The Secret Missions are converted too when their files (`MODULE.001`,
`MODULE.002`, ...) are in `GAMEDAT`; they then appear in the main menu.
The converted pack is about 3 MB.

## Controls

| Button            | In flight                                   |
|-------------------|---------------------------------------------|
| D-pad             | pitch and yaw (up = nose down, as on a stick; can be inverted in Options) |
| A                 | fire the selected guns                      |
| B (tap)           | launch a missile                            |
| B + Up            | next target                                 |
| B + Down          | autopilot to the next nav point             |
| B + Left / Right  | roll                                        |
| RB / LB           | set speed up / down                         |
| LB + RB           | afterburner                                 |
| MENU              | flight computer: autopilot, nav map, communications, gun and missile selection, cockpit on/off, eject |

On the PC: arrows, `Y` = A, `X` = B, `A` / `S` = LB / RB, `Esc` = MENU.

Land by flying into the *Tiger's Claw* once the last objective is
"Return to Tiger's Claw" and the bottom bar shows `LAND` (clearance is
given when no enemy is left, or ask for it under Communications).

## What comes from the original

Read from your game files by the converter and used unchanged:

- every mission: nav points, ships, wings, formations, waves, triggers,
  objectives (`MODULE.00x`), the campaign tree with its score
  thresholds, medals and ship assignments (`CAMP.00x`);
- the briefing, debriefing and bar conversations (`BRIEFING.00x`),
  including all of their branches on your results;
- ship, missile, explosion and asteroid art in all 37 views, the four
  cockpits with their radar and display positions, the fonts, the
  palette and a few full-screen pictures.

Ported from the wc1-re source, function by function (see the headers
of `world.py` and `ai.py` for the mapping):

- ship and weapon statistics, hardpoints, and the view tables;
- flight physics: speed and acceleration, afterburner, turn rates and
  the way a pilot's turn goals are worked off;
- guns (energy, refire delay, convergence, damage over range),
  missiles, shields, four-sided armour, internal damage for AI ships
  and the separate damage table of the player's ship, shock waves;
- pilot AI: the nine combat events, stress and morale, the manoeuvre
  tables of every named pilot and every Kilrathi skill level, and the
  manoeuvre scripts themselves;
- the projection, sprite scaling and view selection of the 3-D view;
- mission scoring, kill scoring, promotions, medals and the series
  tree walk between missions.

## What is different

- No talking heads, animations, cutscenes or music. Conversations are
  shown as text in the speaker's colour over the room picture. The
  sound effects are synthesised by the converter (the PC original has
  no samples).
- The picture is 128x96 with square pixels (the original 320x200 has
  1:1.2 pixels); messages, speeds, gun energy, fuel and missiles moved
  from the cockpit art into the bars above and below it.
- The autopilot jumps instead of showing the fly-by, and can only be
  refused for enemies or hazards nearby.
- Simplified: asteroid and mine fields, capital-ship behaviour and
  turrets, escort / defend / strike missions, the radio (four orders
  and the landing request), missile lock (missiles track without the
  lock-on wait), Kilrathi aces (no taunts, not tracked between
  missions). Landing works from any side. There is one saved game, no
  training simulator, no medal ceremony, no funeral.
- Gun bolts use a swept hit test, so they cannot pass through a ship
  between two turns as they can in the original.

## Files

```
MainGame.py   menus, the Tiger's Claw, one mission from briefing to report
world.py      the simulation: ships, weapons, damage, action spheres
ai.py         pilot intelligence and manoeuvre scripts
flight.py     cockpit, 3-D view, controls, flight computer
talk.py       conversation director with the original branch tests
campaign.py   series tree, scoring, promotions, saved game
wcdata.py     loaders for the converted files
wcgfx.py      pixel loops (viper): rotated / scaled sprites, text
wcmath.py     integer 3-D math in the original's conventions
sky.py        space dust and stars of a flight
ui.py         menus, text pages, nav map
tool/wc1_convert.py, tool/wc1/   the converter (PC only)
tool/wc1_inspect.py              looks inside the original files (PC only)
tool/wc1_selfplay.py             plays a whole sortie through the buttons
tool/wc1_check.py                flies every mission of every campaign
docs/                            developer handbook - start at docs/README.md
```

## Continuing the work

[docs/README.md](docs/README.md) is a handbook for whoever develops
this further: how wc1-re is organised, the original file formats, the
converter, how the game works inside, and specifications for what is
still missing - talking heads, cutscenes, the radio, the original
music and sound effects - with a roadmap.

## Testing

```bash
python3 tool/wc1_selfplay.py     # title -> briefing -> flight -> landing -> save
python3 tool/wc1_check.py -v     # all missions of all converted campaigns
```

Both run headless on the PC emulation and need the converted assets.
`wc1_selfplay.py` writes screenshots to `build/wc1_selfplay/`.

## Status

Developed on the PC emulation and confirmed on a real ThumbyColor:
menus, briefing, flight, landing and a second sortie run, with about
63 KB of heap free while flying. RAM is the tight resource; how the
game stays inside it is described in
[docs/12-memory.md](docs/12-memory.md). The clock-based game speed
(see "Game speed") has been tested on the PC only; the rates the
device reaches have not been measured yet - they are in the `WC rate`
line printed after a flight.

The game prints `WC mem <step> <free bytes>` lines to the serial
console at start-up and around each flight. If it runs out of memory,
those lines show where.

Data converted before this rework has capital ships that are too
large for the new frame cache: run `tool/wc1_convert.py` again and
copy the `assets` folder to the device. The game shows a notice at
start if it finds old data.

## Space dust and stars

Dust specks stand in space and stream past as streaks that lengthen
with speed; stars that leave the view while turning come back at the
edge the view turns towards. Rules from the original (see
docs/04-game-dynamics.md, 4.4.2).

## Game speed

The simulation runs by the clock, not by the frame rate: ten game
turns per second, the rate the original's own units are written for
(its speed display and the manual's turn rates both assume it).
Pictures are drawn as often as the device manages, up to 25 per
second, each showing the world part of the way between the last two
turns, so motion is smooth without guessing ahead. Device and PC
therefore fly at the same speed.

Options -> Speed selects `original` (10 turns per second), `1.25x`,
`1.5x` or `2x` (20, the default cap of Kilrathi Saga on Windows).
After each flight the log shows what was reached:
`WC rate pictures/s 24.4 turns/s 9.8 slow 7 worst 100ms sound 1`
(`slow`: frames over 50 ms, `worst`: the longest one, `sound`: sound
effects on). If the device cannot keep up,
the game slows down rather than skipping turns.

## License

The game logic is derived from wc1-re and is therefore GPL-3.0; see
[LICENSE.txt](LICENSE.txt). Wing Commander is (c) Origin Systems /
Electronic Arts; no game data is distributed here.
