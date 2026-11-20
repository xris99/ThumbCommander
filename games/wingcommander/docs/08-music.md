# 8. Music

Nothing is implemented. This chapter is the specification: the song
format, the instrument format, how the original AdLib driver turns
both into register writes, and the rules by which the game picks and
changes music. Chapter 10 turns it into a design for the ThumbyColor.

The DOS game's music system is Origin's **OriginFX**: standard MIDI
files with a few private control events, played by a driver
(`STRAX.DRV`) on an AdLib card (Yamaha YM3812 "OPL2", 9 two-operator
FM voices), a Roland MT-32, or the PC speaker. The AdLib version is
the one to port: its instrument data is small and fully specified.

Sources: wc1-re `src/sdl/originfx.cpp` (sequencer and AdLib driver,
written from the DOS binaries; cited below as **[ofx]**),
`src/sdl/music.c` (song queue), `src/music.c` (the game's music
decisions). Kilrathi Saga itself streams recorded music; `src/music.c`
therefore talks to a "streamer", and the port redirects the same
calls to OriginFX when DOS data is in use.

```bash
python3 tool/wc1_inspect.py WING songs                      # every song: length, loops, exits
python3 tool/wc1_inspect.py WING music --track 1 --events   # control events of one song
python3 tool/wc1_inspect.py WING music --export /tmp/mid    # the .mid files (Origin data)
python3 tool/wc1_inspect.py WING timbres                    # the AdLib instrument bank
```

## 8.1 The songs: MUSIC.MID

A packet archive (2.2) with 41 LZW sections, 207 KB unpacked. Each
section is one MIDI file [data]:

- `MThd`, format 1, **480 ticks per quarter note**, 5 to 19 `MTrk`
  chunks;
- tempo by the usual meta event 0x51 (default 500,000 us per quarter
  note); several songs change tempo while playing;
- channels 1-8 (0-based) carry melodic parts, channel 9 percussion;
  channel 0 is unused;
- events used: note on / off, program change, pitch bend (572 in all
  songs together), and of the controllers only 7 (volume, 990
  times), 10 (pan, 319) and 121 (reset, 5) - the modulation wheel
  never occurs - plus Origin's status byte **0xFE**.

### Reading events [ofx `OriginFxReadTrackEvent`]

Standard MIDI with three particularities:

1. Running status survives meta, system-exclusive **and 0xFE**
   events (standard MIDI cancels it).
2. Channel messages with status 0xC0-0xDF have one data byte, all
   others two.
3. `FE <type> <length> <data...>` - the length is a single byte, not
   a variable-length quantity.

### Sequencing [ofx `OriginFxPlayDueEvents`, `OriginFxAdvanceSequencer`]

Each `MTrk` has its own cursor and a wait counter (ticks until its
next event). One tick lasts `tempo / 480` microseconds. Per tick:
decrement every unfinished track's wait; then, repeatedly, take the
first track whose wait is 0, play its event, and read the delta time
that follows into its wait. The song ends when every track has ended
(meta 0x2F, or data exhausted).

Because the sequencer reads a delta *after* each event, a jump lands
on a delta time: the target of a jump is the byte offset of a delta
inside the track.

### Control events [ofx `OriginFxPlayTrackEvent`]

| Type | Data | Meaning |
|------|------|---------|
| 0 | i16 offset | **loop**: jump, unless the song has been told to leave |
| 1 | - | **end**: finish the whole song now, if it has been told to leave |
| 2 | i16 offset | **exit**: jump only if the song has been told to leave (used to skip from a bar line to the ending) |
| 3 | u8 n | marker: sets the "sequence position" the game can read |
| 4 | i16 offset, u8 v | jump if the branch selector != v |
| 5 | i16 offset, u8 v | jump if the branch selector == v |
| 0xFF | (empty) | occurs once per track next to the loop point in most songs [data]; the player ignores it and its purpose is unknown |

Jump target = (byte offset of the event's data) - (signed offset),
relative to the track start. Before jumping, the driver sends "all
notes off" on the track's current channel.

"Told to leave" is one flag per playing song (`leaveAtLoop`), set when
the game queues another song or asks the current one to finish
(8.5). This is what makes transitions musical: combat music does not
cut off, it runs to its next exit point - a bar line - and plays its
ending.

### What the 41 songs look like [data, `wc1_inspect.py WING songs`]

- 29 songs loop, and 24 of those have exit points (between 2 and 41
  per song) that jump to an ending or straight to the end of the
  track.
- 12 songs play once and stop: the stingers 6-11, the logo fanfare 19
  (which carries 112 markers and nothing else), 21, 22, 27-29.
- Song 30 uses type 1 (end when leaving) at 11 points instead of
  exits.
- Songs 23 and 32 start with a type 5 event: with branch selector 1
  they begin at a later section. The port sets the selector from
  `nFuneralSequenceActive`, which selects the funeral arrangement of
  song 32.
- Song 31 has an intro: it loops back to tick 30,720, not to 0.
- **In every song, every `MTrk` that has jumps has the same jumps at
  the same ticks with the same target ticks.** A song can therefore
  be flattened into one event stream with song-level loop and exit
  points (chapter 10 relies on this).
- All songs played once through last 1,456 seconds. The longest is
  song 23 (165 s), the shortest 21 and 22 (under 2 s).
- Notes held at the same time (all channels): at most 14; 6 or fewer
  for 73 % of the playing time, 9 or fewer for 97 %.

## 8.2 The instruments: WINGLDR.TIM

Section 1 is the AdLib bank: one count byte (79), then 79 timbres of
48 bytes [data]. A program change selects the timbre whose byte 47
equals the program number (the first timbre if none matches) [ofx
`OriginFxFindTimbre`].

| Offset | Size | Meaning |
|--------|------|---------|
| 0-4 | 5 | modulator operator: values for OPL registers 0x20, 0x40, 0x60, 0x80, 0xE0 |
| 5-9 | 5 | carrier operator: the same five registers |
| 10 | 1 | register 0xC0: feedback (bits 1-3) and connection (bit 0: 1 = additive, 0 = FM) |
| 11 | 1 | rhythm voice: 0 = melodic; 6-10 = bass drum, snare, tom, cymbal, hi-hat of the OPL rhythm mode |
| 12 | 1 | carrier velocity sensitivity (0-7) |
| 13 | 1 | modulator velocity sensitivity (0-7) |
| 14 | 1 | pitch-bend range |
| 15 | 1 | modulation-wheel depth scale |
| 16 | 1 | vibrato rate |
| 17 | 1 | vibrato depth |
| 18 | i16 | pitch envelope: start value |
| 20, 22 | i16, i16 | stage 2: rate, target |
| 24, 26 | i16, i16 | stage 3: rate, target |
| 28, 30 | i16, i16 | stage 4: rate, target |
| 32, 34 | i16, i16 | release stage: rate, target |
| 36 | i16 | detune |
| 38 | 1 | non-zero: the next timbre in the bank is layered with this one (one note starts both) |
| 39 | i8 | key tracking (see 8.3) |
| 40-46 | 7 | not read by the player; zero in every timbre [data] |
| 47 | 1 | program number |

Pitch quantities are in 1/256 semitone. What the bank contains
[data]:

- program numbers 0-149 with gaps; the songs use only 2, 4, 24, 25,
  47-51, 58, 70, 72-75, 82-84, 93, 94, 97, 112, 113, 121, 122. Of
  these, **72, 73 and 82 are not in the bank** (songs 19, 36 and 35
  ask for them) and so play with the first timbre, program 2. The
  same holds for percussion program 139 (pseudo-channel 25);
- the percussion timbres (113, 114, 128-147) are ordinary
  two-operator timbres, not rhythm-mode voices;
- exactly one timbre uses an OPL rhythm voice (program 44, bass
  drum), and only a sound effect selects it - **the music never
  enters OPL rhythm mode**;
- exactly one timbre is layered (program 127, with 149);
- most melodic timbres have pitch-bend range 96 and vibrato rate
  20-25.

Sections 0 (MT-32, 9,140 bytes) and 2 (PC speaker, 961 bytes) are not
described here.

## 8.3 The driver

All of this is **[ofx]**; function names in parentheses.

**Channels.** 26 logical channels. 0-8 are MIDI channels. A note on
MIDI channel 9 is percussion: two 77-entry tables
(`g_abOriginFxPercussionChannels`, `...Pitches`) map the MIDI note
number to one of the pseudo-channels 9-25 and a fixed pitch; notes
that map to 0 are dropped. At start-up channels 9-25 get the programs
`0x80 0x72 0x83 0x71 0x86 0x87 0x85 0x84 0x81 0x88 0x8D 0x8F 0x90
0x91 0x93 0x8C 0x8B` (`g_abOriginFxPercussionPrograms`). A controller
on channel 9 is applied to all of 9-25. Per channel: program, volume
(starts at 0xFF), pan (64), pitch bend (0x2000), modulation rate and
depth (from the timbre).

**Voices.** Nine OPL voices. Note on (`OriginFxStartTimbre`): take
the free voice that has been free longest; if none is free, steal the
voice that has been sounding longest. Program the operators from the
timbre, set levels, write the frequency with key-on. A layered timbre
starts a second voice with the next timbre. Note off
(`OriginFxStopTimbre`): find the voice by channel, note and timbre,
clear key-on (the OPL envelope's release does the rest), and put the
voice's pitch envelope into the release stage.

**Operator slots.** For voice v (0-8) the register offsets are
modulator `{0,1,2,8,9,10,16,17,18}[v]`, carrier
`{3,4,5,11,12,13,19,20,21}[v]`; per-voice registers are 0xA0+v,
0xB0+v, 0xC0+v. At reset the driver writes 0x20 to register 1
(waveform select on), 0 to 8 and 0xBD.

**Pitch** (`OriginFxWriteVoiceFrequency`), in 1/256 semitone:

```
key   = (note - 60) * 256
if keytrack < 0:  key = -key;  shift = ~keytrack    else shift = keytrack
key   = (key >> shift) + 60 * 256              (arithmetic shift)
pitch = key + envelopePitch + detune + vibratoPitch
        + ((bend - 0x2000) * bendRange >> 8)   (bendRange: timbre of the
                                                channel's program, byte 14)
note     = pitch / 256 (floor),  fraction = pitch mod 256
index    = (note + 6) mod 12
block    = (note + 6) / 12 - 2, clamped to 0..7
fnum     = F[index] + (F[index + 1] - F[index]) * fraction / 256
F        = 485 514 544 577 611 647 686 727 770 816 864 915 970
write 0xA0+v = fnum & 0xFF
write 0xB0+v = (fnum >> 8) | (block << 2) | (key on ? 0x20 : 0)
```

The resulting frequency is `fnum * 49716 / 2^(20 - block)` Hz (the
OPL2 formula, 49,716 Hz being the chip's sample rate at a 3.579545
MHz clock). Check: note 60 -> index 6, block 3, fnum 686 -> 260.2 Hz
(middle C is 261.6).

**Level** (`OriginFxWriteVoiceLevels`). Register 0x40 holds key
scaling (top 2 bits, kept) and attenuation (low 6 bits, 0 = loudest,
0.75 dB per step):

```
carrier:    att = (timbre[6] & 0x3F) + ((63 - velocity) >> (7 - sens))
                                                sens = min(timbre[12], 7)
            att = 63 - (volume * (63 - att) >> 8)       volume: 0x80..0xFF
            clamp 0..63
modulator:  only if timbre[13] is not 0:
            att = (timbre[1] & 0x3F) + ((63 - velocity) >> (7 - timbre[13]))
```

Velocity is used as 0-127 against 63, so velocities above 63 make the
shift operand negative: the shift is arithmetic and rounds toward
minus infinity. With sensitivity 0 the shift is 7, which leaves 0 or
-1 - velocity then hardly matters. Pan (controller 10) scales the level per output side
and only matters in stereo; for mono ignore it.

**The 60 Hz service** (`OriginFxService`) runs 60 times a second for
every voice that has a timbre (sounding or releasing):

```
pitch envelope: state starts at 2 on note on, value = timbre[18]
    in state s (2, 3, 4, or 0 = release) with a non-zero target offset:
        move value toward target by rate; when closer than rate:
        value = target, state += 1        (so 2 -> 3 -> 4 -> 5 = hold;
                                           release 0 -> 1 = done)
vibrato: if the channel's modulation rate is not 0:
    phase = (phase + rate) & 0xFF
    tri   = phase as signed 8-bit, folded into -64..63
            (if out of range: phase' = (0x80 - phase) & 0xFF, tri = signed)
    vibratoPitch = depth * tri >> 4
if anything changed: rewrite the frequency (key stays on while state > 1)
```

**Controllers** (`OriginFxApplyControlChange`): 1 modulation wheel ->
`depth = (timbre[15] * value >> 7) + timbre[17]`; 7 volume ->
`value + 0x80`; 10 pan; 121 reset (depth from the timbre, volume
0xFF, bend centred); 123 all notes off on the channel. Program change
(`OriginFxSetProgram`) silences the channel's notes and takes
modulation rate and depth from the new timbre. Pitch bend is 14 bits
(`data1 | data2 << 7`).

**Rhythm mode** exists in the driver (timbre byte 11; the melodic
allocator drops to 6 voices and voices 6-10 use register 0xBD bits
0x10, 0x08, 0x04, 0x02, 0x01) but is reached only through sound
effect 23 (9.2). A music-only player can omit it.

## 8.4 What a faithful player needs

Summing up 8.1-8.3, to play the songs as the AdLib original does:

1. a sequencer for the MIDI subset with the five control events and
   the leave flag;
2. the timbre bank and the two percussion tables (154 bytes) plus the
   percussion program list;
3. nine two-operator FM voices with the OPL2's operator features that
   the timbres use: multiplier, attack / decay / sustain / release,
   total level, key scaling, feedback, four waveforms, tremolo and
   vibrato flags (registers 0x20-0xE0 are passed through verbatim, so
   whatever a timbre sets must be honoured or knowingly dropped);
4. the driver layer: voice allocation, pitch, level, the 60 Hz pitch
   envelope and vibrato.

## 8.5 How the game asks for music

One entry point: `spacetrack(track, mode, enabled)` (`src/music.c`).
It does nothing when music is off. `mode`:

| Mode | KS name | With OriginFX (`SdlOriginFxMusicCommand`) |
|------|---------|-------------------------------------------|
| 0, 2 | start / switch | load the song and start it **now**, replacing the current one |
| 1, 3 | break / interrupt | **queue** it: tell the playing song to leave; start the new one when the old one ends. If nothing is playing, start now |
| 4 | stop | stop |

Two rules make the calls safe to repeat: a command is **ignored if a
song is already queued, or if the requested track is the one
playing**. The flight code relies on this - it asks for "the right
track" several times a second.

Other calls: `SetMusBreakpt` = tell the playing song to leave with
nothing queued (`wait_for_end_of_music` then waits for it to finish -
scenes use this so a fanfare ends cleanly); `StopMusic` = stop at
once. When a song ends and nothing is queued, `nMusicTrackComplete`
becomes 1; the flight code reads that flag.

## 8.6 The tracks and where they are used

[src: every `spacetrack` call site; data: lengths and structure]

| # | Seconds | Kind | Used for |
|---|---------|------|----------|
| 0 | 63 | loop, exits | combat, ship intact |
| 1 | 11 | loop, exits | combat, enemy on your tail |
| 2 | 17 | loop, exits | combat, you are on your target's tail |
| 3 | 19 | loop, exits | missile chasing you |
| 4 | 25 | loop, exits | combat, heavy damage |
| 5 | 22 | loop, exits | combat, light damage |
| 6 | 5 | once | stinger: you killed an ordinary enemy (3 times in 4) |
| 7 | 14 | once | stinger: a friendly ship died |
| 8 | 12 | once | stinger: your wingman died |
| 9 | 6 | once | stinger: you killed an ace (or the 1-in-4 alternative for 6) |
| 10 | 7 | once | stinger: the last Kilrathi nearby died |
| 11 | 19 | once | stinger: the ship you escort or defend died |
| 12 | 31 | loop, exits | flying home, mission not a success |
| 13 | 29 | loop, exits | flying home after a successful patrol |
| 14 | 32 | loop, exits | flying home after another successful mission |
| 15 | 49 | loop, exits | cruising: patrol and default |
| 16 | 32 | loop, exits | cruising: defend, rendezvous |
| 17 | 30 | loop, exits | cruising: strike |
| 18 | 31 | loop, exits | cruising: escort |
| 19 | 25 | once | Origin FX logo (DOS only; `src/sdl/dos_intro.c`) |
| 20 | 40 | loop | training simulator |
| 21 | 2 | once | simulator: next wave |
| 22 | 2 | once | simulator: game over |
| 23 | 165 | loop, exits, branch | title sequence; "The End" |
| 24 | 17 | loop, exits | preloaded with the briefing tracks; no call that starts it was found |
| 25 | 31 | loop, exits | briefing room |
| 26 | 11 | loop, exits | briefing: back from the map |
| 27 | 24 | once | scramble: run to the hangar |
| 28 | 14 | once | launch |
| 29 | 20 | once | landing |
| 30 | 97 | loop, ends when leaving | bar and kill board |
| 31 | 46 | intro + loop, exits | ejection |
| 32 | 100 | loop, branch | death (branch 0) and funeral (branch 1) |
| 33 | 53 | loop, exits | debriefing after a good mission; "Meanwhile" after a won series; victory ending |
| 34 | 44 | loop, exits | debriefing after a poor mission; "Meanwhile" after a lost series; retreat ending |
| 35 | 125 | loop | barracks |
| 36 | 108 | loop | colonel's office |
| 37 | 24 | loop, exits | no call found |
| 38 | 24 | loop, exits | medal ceremony, medal 3 |
| 39 | 17 | loop, exits | medal ceremony, medals 0 and 1 |
| 40 | 17 | loop, exits | medal ceremony, medals 2 and 4 |

"Good mission" for the debriefing: the player's mission score is more
than 70 % of the full score (`DeBriefing`, `src/cmpgn.c`).

## 8.7 Music in flight

Two functions in `src/music.c` do everything; both are small enough
to port line by line. Flight music is active from launch to landing
(`nInFlightMusicActive`), not in the simulator.

### The steady state: `gametrack()` -> `changetrack()`

Called every flight frame from `servicetrack()`. It acts only every
16th frame, or at once when the current song has ended:

```
if in combat:
    if a missile targets the player:                        track = 3
    elif an enemy that targets the player is on his tail:   track = 1
    elif the player is on the tail of his target:           track = 2
    else by calculate_damage_level():  >= 2 -> 4,  1 -> 5,  0 -> 0
    if no Kilrathi ship that is not retreating is within 16,000:
        combat = off
else:
    track = changetrack()
    if any Kilrathi has an attack objective:  combat = on
spacetrack(track, 1, 0)          # queue; ignored if unchanged or one is queued
```

`changetrack()`:

```
by the player's mission type:  escort 18, strike 17,
                               defend or rendezvous 16, otherwise 15
if the current objective is "return to base":
    if triumph(0):   13 for a patrol, otherwise 14
    else:            12
```

`calculate_damage_level()` (`src/main.c`) sums the lost fraction of
the four armour sides (each 0-4), doubles it, adds the core damage
scaled to 30 and five times the accumulated system damage; under 5 is
level 0, under 40 level 1, under 70 level 2, else 3. `World.
damage_level` in the port is this function.

Because every request is queued, a change of situation is heard at
the playing song's next exit point: the songs have 5 to 41 of them,
so the wait is a few seconds at most.

One call bypasses the queue logic of `gametrack`:
`update_missile_warning` (`src/cockpt.c`) queues track 3 the moment a
missile locks on, without waiting for the 16-frame poll.

### Stingers: `new_space_music_changes(attacker, victim)`

Called from `explode` for every ship that dies:

```
victim is Kilrathi:
    no fighting Kilrathi left within 16,000:        queue 10
    else if the player made the kill:
        ordinary pilot and 3 times out of 4:        queue 6
        otherwise:                                  queue 9
victim is your wingman:                             queue 8
victim is another Confederation ship:
    it is the ship you escort or defend:            queue 11
    otherwise:                                      queue 7
```

A stinger plays once. When it ends, `nMusicTrackComplete` makes the
next `gametrack()` act immediately, so the steady-state music
resumes without a gap. Remember the "ignored if something is queued"
rule: a stinger requested while another change is pending is lost.

### Launch and landing

Launch: the launch scene plays track 28; `LaunchPlayerShip` then
queues `changetrack()` so the cruise music follows the fanfare
(`src/launch.c`). Landing starts track 29 at once.

### What the port already has for this

Everything the rules read exists in `world.py` / `ai.py`:
`World.damage_level`, `Brain.missile_on_tail`, `detect_enemy_tail`,
`enemies_left`, the player's mission type and current objective,
`explode(attacker, victim)`. A `music.py` with `gametrack`,
`changetrack` and `new_space_music_changes` is perhaps 80 lines and
can be written and unit-tested (it only produces track numbers)
before any sound exists.

## 8.8 Differences in Kilrathi Saga

For orientation only - the port targets the DOS behaviour above.
KS maps track numbers to recorded streams (`SelectFlightMusicTrack`,
`MapMusicTrackToStreamerCommand`) and treats tracks 0-5 and 12-18 as
"intensity" levels of one continuous flight stream. Tracks 25, 38, 39
and 40 are not restarted when already playing (a guard marked "for
QA" in `ProcessMusicScriptCommand`).
