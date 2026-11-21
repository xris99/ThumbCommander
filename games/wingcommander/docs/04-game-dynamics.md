# 4. How the game works

This chapter describes the game as the port runs it, and names the
wc1-re function behind each rule. Numbers that matter are in the code;
the aim here is the structure, so you know where a behaviour lives
before you change it.

## 4.1 The outer loop (MainGame.py)

```
title -> main menu (new / continue / campaign / options)
  loop:
    carrier menu:  rec room (bar talk, kill board) | barracks (record, save) | fly
    fly:  briefing  ->  mission plan  ->  flight  ->  debriefing
          ->  mission report  ->  campaign update  ->  (ending)
```

In the original each arrow is a scene with art and music (chapter 6
lists them). The port shows a menu, the conversation text over a
static picture, and text pages.

`campaign.State` is the saved game (`wc_save.json`): campaign, series,
mission, ship, rank, kills, medals, badges, score, wingman deaths and
kill counts. One save slot.

## 4.2 Campaign structure (campaign.py)

A campaign is a tree of **series** (star systems). A series has 2-4
missions. After the last mission of a series, the summed mission score
is compared with the series' required score: at or above it you move
to the *win* series, below it to the *lose* series, each with a ship
assignment (`UpdateSeries`, wc1-re `src/gameflow.c`). Series 12 and 13
are the two endings.

After every mission (`PostMission` + `UpdateSeries` ->
`campaign.post_mission`):

- kills and missions flown update badges; every fifth kill and every
  mission flown with a full score add a promotion point; you are
  promoted when a random 0-5 plus the points exceeds 7; ejecting
  costs a point (and the first ejection earns the Golden Sun);
- the mission's medal is awarded if the medal score reaches the value
  in `CAMP.00x` (losing your wingman lowers the score used);
- wingmen who died stay dead: their bar seat is empty and conversation
  branches test for it.

Mission score is the sum of the per-objective scores of the objectives
achieved (16 score bytes per mission in `CAMP.00x`), computed by
`World.players_score` from the objective flags that
`cleanup_objectives` settles when the flight ends.

## 4.3 A mission as data

A mission (chapter 2.6) is 16 nav points, 16 objectives and 32 ships.
The ships are not all present at once: each nav point lists up to ten
ship records that exist *there*.

- **Action sphere** (`set_up_action_sphere`, wc1-re `src/mission.c`):
  arriving at a nav point removes every ship that belongs to another
  sphere, creates this sphere's ships (`init_ship`), places wingmen in
  formation (`set_formation_position`) and arms the nav point's
  triggers. A trigger changes the type of another nav point, which is
  how "the next wave is now allowed" is expressed.
- **Waves** (`set_up_next_wave`): the nav records after an active
  sphere can hold further ship lists. When no Kilrathi are left and
  the next wave record is armed, its ships jump in 5,000-10,000 units
  around the player.
- **Objectives** have a type (reach a nav point, destroy a ship,
  protect a ship, return home) and an index. `track_objectives` marks
  them during flight; `cleanup_objectives` decides success for the
  "protect" kinds at the end.
- **Ship records** give type, side, AI rating (which pilot table to
  use), mission type (patrol, escort, strike, defend, wingman, ...),
  leader and formation, and for named pilots the roster index.

## 4.4 Conventions of the simulation (wcmath.py, world.py)

| | |
|---|---|
| Game turn | 1/10 s by the clock (`flight.TURN_MS`, option "Speed"), independent of the picture rate - see 4.4.1 |
| Position | integers with 8 fractional bits (24.8), three per object |
| Axes | left-handed: x right, y up, z forward |
| Orientation | a 3x3 matrix of ints with 14 fractional bits; rows = right, up, forward |
| Angles | whole degrees; the sine table is indexed by degree |
| Rotation | applied as pitch, yaw, roll steps in degrees per turn (`rotate_object`) |
| Objects | 44 slots: 0-9 are ships (0 = the player), 10-43 bolts, missiles, explosions, debris, rocks, mines |
| Random | `rnd(n)` / `rndle(n)` mirror the original's `RandomWord` helpers |

`Obj` carries every per-object property; names follow the original
arrays (`aeShipMissionType` -> `mtype`, `acShipRating` -> `rating`).
Only the ten ship slots are full `Obj` instances. Slots 10-43 are
`Lite` objects that own just the fields a bolt or an explosion
changes and read the rest as class defaults - a RAM measure with one
rule attached (12.3).

### 4.4.1 Time: turns by the clock, pictures in between

The original has no time scaling: every number in the simulation
(speed, turn rate, gun delay, the pilots' intervals) is "per turn",
and a turn is a displayed frame. How long a turn lasts was the
machine's business in 1990 and is a setting in Kilrathi Saga (20
frames per second, adjustable 8-32, chapter 1.4). The game's own
units say what was meant [src]:

- the speed display multiplies the per-turn speed by ten to show
  km/s (`src/cockpt.c`: `speed = ((anShipSpeed[0] >> 8) * 10)`);
- the turn rates in the ship table, times ten, are the degrees per
  second printed in the manual (Hornet: 8, 9, 8 per turn; 80, 90, 80
  dps).

So the nominal rate is **10 turns per second**. At 20 a Hornet turns
180 degrees in a second and a Dralthi crosses gun range in half a
second - that is the "too fast" of the first device test.

The port separates the two rates (`flight.Flight.frame`):

| | |
|---|---|
| Turn | every `turn_ms` = `TURN_MS[speed]` = 100, 80, 67 or 50 ms (option "Speed": original, 1.25x, 1.5x, 2x; 2x is Kilrathi Saga's default). `controls()` and `World.update()` run only then |
| Picture | every frame the engine allows, up to 25 per second (`flight.PICTURES`, `display.setFPS` in `MainGame.fly`); device and PC use the same code, so both fly at the same speed. Not 30: the firmware's `time_to_next_tick()` rounds the period to whole ms while `tick()` compares with the exact period (33.33 ms), and at 30 the ThumbyColor flickered black under load - firing, enemies, long flights - at both speeds; at 25 (40 ms) it does not, with sound on or off (device test). Keep the cap at a whole number of ms |
| Between turns | `set_view(f)`, f = 0..256 = the part of a turn that has passed since the last one. The picture shows the world that far *between the last two turns*: the camera matrix `cam` is the player's matrix turned back by `rates * (256 - f) / 256` (`wcmath.unturn256`, roll then yaw then pitch, sine interpolated to 1/256 degree), the eye and every object are moved back by `velocity * (256 - f) / 256`. This is exact, not a guess: `World.move` changes a velocity first and then adds it to the position, and `rotate_object` turns by the rates the player has after the turn. Nothing in the world is changed by it |
| Buttons | presses are collected every frame (`latch`) and used at the next turn, so a tap between two turns is not lost |
| Slow device | a turn that is more than one turn late is not caught up: the game slows down, it never jumps |
| Counters | everything that counts time counts turns (`w.tick`, message time, blink). Do not count pictures |

`flight.PACE = False` gives the old behaviour, a turn per call of
`frame()`; the test tools set it so that their results do not depend
on the speed of the PC. After a flight the log has one line,
`WC rate pictures/s 24.4 turns/s 9.8 slow 7 worst 100ms sound 0`; if the second number is below
the chosen rate, the device does not manage a turn in `turn_ms`.

Why back and not ahead: the first version carried the view *forward*
by the current rates and velocities. Every change of a rate (the stick
eases in and out over three turns) or of a course (an enemy curving)
made the next real turn land behind the guess, and objects jumped
forward and back by a pixel or more - visible on the PC as a stutter
while turning. Stepping back between two real states cannot overshoot.
Measured over the same sortie with irregular frame times: screen
reversals of 2 pixels or more went from 222 to 13 (the rest are real
changes of direction by the test pilot), and a steady turn has none.
The cost is that a turn is completely on screen one turn (100 ms)
after it was computed; it starts to show at once.

Culling for big objects: an object is skipped when its centre is
outside the view cone *and* it is small for its distance
(`radius * 3 < dist`), and the off-screen margin grows with its
projected size (`100 + FX * radius / vz`). Before, a carrier alongside
vanished while its hull still filled half the picture.

The `WC rate` line also gives `slow` (frames over 50 ms) and `worst`
(the longest frame in ms, flight computer pauses not counted).

### 4.4.2 Space dust and stars (`sky.py`)

Ported behaviour of `update_star_field` and `start_dust` (wc1-re
`src/spc.c`) and the dust limits of `src/geom.c` [src]; the specks are
drawn as plain pixels, not the original's sprites.

- **Dust**: 15 specks standing still in space. Once per turn, a speck
  that is behind the ship, outside the view, nearer than the ship's
  radius or further than 1400 units is placed ahead again with chance
  2/8: forward distance `2 * (rand(0, v) + radius) + rand(0, 350)` with
  `v` = ten turns of forward speed (`rand(0, 40) + radius` when flying
  backwards), sideways and up by ten turns of the ship's sideways motion
  plus up to half the distance at random. The ship flies through them.
  Each is drawn as a line from where it was half a turn ago to where it
  is (so the streak grows with speed), brighter and 2 x 2 when near.
- **Stars**: 26 directions (no parallax). A star that leaves the view is
  put back, in the same turn, just beyond the edge the view turns
  towards - between the edge and one turn's rotation past it - at a
  random angle inside the view on the other axis, and left alone until
  it has come in (given up after 12 turns). The original uses 45 degrees
  and a 1-in-8 chance per turn; with that the field emptied while
  turning at this screen size (measured: 25 stars straight ahead, 5 to 9
  while turning; now 17 to 21).
- **Cost**: `sky.mpy` is 5.2 KB (about 6 KB of RAM in flight); per
  picture two projections per speck and one per star.

## 4.5 One game turn (World.update = Update_3Space)

```
for every object:
    explosions age and disappear
    house_keep      lifetimes, afterburner fuel, gun cooling, dying ships
    collide         bolts and missiles against solids, ships against ships and rocks
    rotate_object   apply this turn's pitch / yaw / roll
    brain.think     AI ships and missiles decide (not the player)
    rotate_object_to_goal   work off the AI's turn goals at the ship's turn rates
    gun energy recharges (faster when shields are full)
for every object:
    move            accelerate towards the set speed, add velocity to position
    replenish_shields, burn fuel
every 10 turns:
    track_objectives; if no enemy is left, set_up_next_wave
hazard_turn         asteroid and mine fields around the player
```

The player's inputs are applied by `flight.controls` before the turn
(rotation rates, set speed, afterburner, firing).

**Movement** (`move` = `accelerate_and_move_object`): each ship has a
set speed and a current speed that approaches it by the type's
acceleration; velocity is speed along the forward axis, except while
drifting (afterburner cut, "kill engines" manoeuvres), when the old
velocity persists.

**Guns** (`fire_guns` -> `fire_weapon`): each gun hardpoint fires a
bolt object if the ship has energy and the type's refire delay has
passed; bolts converge at the target's range, live a fixed number of
turns and lose damage with distance. **Missiles** are objects with
their own small brain (`Brain.missile`): dumbfire flies straight;
the guided kinds turn towards their target at the missile type's turn
rate; a heat-seeker gives up when the target leaves a 70-degree cone;
friend-or-foe picks the nearest ship of the other side by itself.

**Damage** (`inflict_damage`, wc1-re `src/ship.c`):

1. the blow's direction against the ship's forward axis picks the
   front or rear **shield**; the shield absorbs what it has;
2. what is left hits the **armour** of one of four sides (front, rear,
   left, right, chosen by the direction against the right axis);
3. what is left after armour is **internal damage**: for AI ships a
   table of systems that can fail (`internal_damage`), for the player
   the original's separate table (`your_internal_damage`, with the
   `PLAYER_DAMAGE_SYSTEMS` rows) that breaks guns, shields, the
   computer, the ejection seat and so on, and can wound the pilot
   (`pilot_hit`, four hits kill);
4. a ship whose core is gone starts dying (`SM_DYING`), tumbles, then
   `explode` spawns explosion and debris objects, a shock wave that
   damages neighbours, and scores the kill (`score_for_kill`).

Shields recharge over time (`replenish_shields`); armour does not.

**Collisions** (`collide`): the original tests positions once per
turn, so fast bolts can pass through thin targets. The port uses a
swept test along the turn's path. Ships that touch `bump` each other: they exchange
velocity and both take damage that grows with the square of the
closing speed (capped).

## 4.6 Pilots (ai.py)

A pilot does not think every turn: `anPilotTurnInterval` gives each
skill level a period. `Brain.think` dispatches on object class:
missile, capital ship, or fighter (`ship`).

A fighter's turn:

1. **Avoid collisions** (`prevent_collision`): if something is on the
   flight path within a distance scaled by closing speed, steer away.
   This runs every turn in the port (the original runs it at the
   pilot's interval), which was needed to stop AI ships from ramming.
2. **Follow the mission type**: `patrol` (fly the nav route, engage
   what is found), `wingman` (hold formation with the leader, obey
   radio orders, break to attack), `defend` / `strike` (go to the
   assigned ship), `run_away`, `reach_warp`, `coming_home`.
3. **When engaged, classify the situation**
   (`intelligence_events`, wc1-re `src/smart.c`) into an event:

   | Event | Situation |
   |-------|-----------|
   | 0 | ordinary engagement |
   | 1 | target nearly stopped |
   | 2 | target far away |
   | 3 | enemy behind me, close |
   | 4 | head-on pass |
   | 5 | I am on the target's tail |
   | 6 | missile chasing me |
   | 7 | just took a hit (cool-down) |
   | 8 | never produced by the classifier; the tables have the row |

   Each event moves **stress** (`handle_stress`): threatening events
   add the pilot's aggression value (a missile adds twice), being on
   the enemy's tail subtracts it, quiet moments subtract the recovery
   value; the ship's damage state shifts and caps the result.
4. **Pick a manoeuvre** (`process_maneuver_node` ->
   `pick_regular_maneuver`): a table per pilot - 13 named pilots, 5
   Kilrathi skill levels - with nine event rows; each row holds three
   (threshold, manoeuvre A, manoeuvre B) entries chosen by stress and
   chance. This table is why Maniac flies differently from Iceman.
5. **Run one step of the manoeuvre** (`perform_maneuver`, wc1-re
   `src/fl.c`): scripts such as tight loop, hard brake, sit-and-spin,
   burnout, fish hook, split, roll-over, kick-stop. A script sets turn
   goals in degrees, a set speed, and afterburner or drift flags, and
   says when it is complete.
6. **Fire** (`fire_when_ready` -> `fire`): when the target sits
   inside the aiming cone and range. Wingmen hold fire while the
   player is in their line of fire - except Maniac.

Capital ships (`capital`) follow their route and fire turrets at
enemies in range. In the port turret fire ignores ships of the same
side.

## 4.7 The view (flight.py, wcgfx.py)

- Camera = the player's orientation matrix. An object's position is
  transformed into camera space (`wcmath.to_frame`), projected with a
  focal length of half the picture width, and drawn back to front.
- **Sprite choice** (`right_shape` = `get_right_shape`, wc1-re
  `src/geom.c`): the direction from which the camera sees the ship, in
  the ship's own frame, is quantised to 62 directions; tables map each
  direction to one of 37 stored views plus a mirror flag.
- **Sprite size**: `type scale * 160 / (distance - radius)`; the
  sprite is also rotated by the roll difference between ship and
  camera. `wcgfx.blit_rs` is the rotate-and-scale blitter (viper).
- The cockpit is a 128x96 indexed overlay with a see-through window;
  radar, shield / armour display, target display and the text line are
  drawn on top. Speeds, energy, fuel and missile count moved from the
  cockpit art into the two 16-row bars.

## 4.8 Controls and the flight computer

D-pad pitch / yaw; A guns; B tap missile; B + Up next target; B + Down
autopilot; B + Left / Right roll; RB / LB speed; LB + RB afterburner;
MENU opens the flight computer (autopilot, nav map, communications,
weapon selection, cockpit on / off, eject).

Autopilot (`autopilot_ok`, `autopilot`) is refused with enemies or
hazards nearby; otherwise it puts the flight a short way out from the
next objective, pointing at it, and `check_sphere` sets up the action
sphere on arrival. The original plays an outside-view fly-by here
(`auto_pilot_sequence`, `src/auto.c`).

A flight ends with one of: landed (`R_LANDED` = 1), ejected (2), dead
(4), aborted (5).

## 4.9 Conversations (talk.py)

`Talk.run(title, packet, which)` walks the 13-byte records of a scene.
For each record it evaluates the branch tests (`ParseTests`, codes
1-38: objective achieved, kills at least N, wingman alive, rank,
medal awarded, ...), and either jumps to another record or shows the
line: tokens expanded (`AddPCName`), text in the record's colour,
speaker name taken from the shot number. Shot 4 shows the nav map.
The mouth and face strings and the shot types are read and ignored -
chapter 5 is about using them.

## 4.10 What is simplified, and where the original is

| Port | Original | wc1-re |
|------|----------|--------|
| autopilot jumps | fly-by camera, formation shots | `src/auto.c` |
| landing: fly into the carrier with clearance | approach from the front, request, landing cutscene | `src/targ.c`, `cutscene.c landing` |
| missiles track without waiting | lock-on time, lock tone, IR vs image lock | `src/cockpt.c decrement_lock_time` |
| asteroid / mine fields: rocks spawned around the player | field objects with density and bounds | `src/targ.c`, `src/spc.c` |
| capital ships: route + turrets | plus launch bays, flak patterns | `src/brains.c`, `src/logic.c` |
| radio: 4 orders, stock replies | full menus, taunts, all 11 message kinds | chapter 7 |
| Kilrathi aces: ordinary pilots with the ace tables | named, taunt, tracked across missions | `src/comm.c`, `src/mission.c` |
| one camera (cockpit front) | left / right / rear views, chase, missile camera | `src/view.c` |
| damage display: bars | cockpit damage art, flickering displays | `src/damage.c`, `src/cockpt.c` |
| difficulty | untuned: the test bot dies in most missions it does not win quickly | - |
| no training simulator | | `src/trainsim.c` |

## 4.11 Checks

- `tool/wc1_selfplay.py [--seed N]` drives the real buttons from the
  title through briefing, a full sortie, landing and the save, and
  writes screenshots to `build/wc1_selfplay/`. Passes on seeds 1-5.
- `tool/wc1_check.py -v` loads and flies every mission of every
  converted campaign with a simple bot: 76 missions, no crash. It
  proves that data loads and the simulation survives, not that a
  mission is winnable.

Neither can see timing, memory or sound. Those need a device.
