# 9. Sound effects

State today: five sounds (`sfx_laser`, `sfx_missile`, `sfx_hit`,
`sfx_boom`, `sfx_pop`) that `convert_sounds` synthesises with numpy
and stores as IMA ADPCM. They are placeholders, not Origin data. The
engine plays one stream at a time, so a new sound cuts off the last.

The DOS original has **no sampled sound at all**. Every effect is a
note (or a short series of notes) played on the same FM chip as the
music, with timbres from the same bank (8.2). Kilrathi Saga replaced
them with `sfxNN.wav` recordings, which the DOS data does not
contain. So "the original effects" on the ThumbyColor means: the FM
player of chapter 10 plus the table below.

Sources: wc1-re `src/sdl/originfx.cpp` (`g_aabOriginFxSoundRecords`,
`OriginFxServiceSoundEffects`, `SdlPlayOriginFxSoundEffect`) - cited
as **[ofx]** - and the `PlaySfxWaveFileByNumber(number, object,
looping)` call sites in the game core.

## 9.1 A sound-effect record

Eight bytes per effect, indexed by the game's sound number minus one
[ofx; the table sits inside `WC.EXE`]:

```
0  flags      1 = chain: when this record ends, continue with the next record
              2 = glide: step the note toward `target`, retriggering each step
              4 = held: lasts until stopped (no countdown)
              8 = repeat: retrigger when the duration ends
1  program + 1     (0 = no sound)
2  note
3  velocity
4  duration, low byte    in 1/60 s
5  duration, high byte
6  glide target note
7  unused
```

Playing one (`OriginFxStartSoundEffectRecord`): select the program on
the effect's channel, set channel volume and pan, note on. Then, 60
times a second (`OriginFxServiceSoundEffects`), unless the record is
"held":

```
remaining -= 1; when it reaches 0:
    note off
    glide:   if note != target: note += 1 or -= 1, retrigger
             else note = start note
    repeat:  retrigger
    if retriggered: note on again, remaining = duration
    elif chain:     continue with the next record in the table
    else:           finished: all notes off on the channel
```

The timbre does most of the work: a short duration with a percussive
timbre is a click, a long one with a noisy timbre an explosion. The
pitch envelope and vibrato of the timbre (8.3) apply as for music.

## 9.2 The table

[ofx, 36 records; note and velocity are 64 unless stated; the "use"
column is from the call sites in the game core]

| # | Flags | Program | Ticks | Use |
|---|-------|---------|-------|-----|
| 1 | | 0 | 60 | missile launch (`fire_weapon`, any missile type) |
| 2 | glide | 1 | 1 | ship fly-by; the game sets note 0 and target 127 before each one, so it sweeps the whole range (`servicetrack`) |
| 3 | | 38 | 60 | engine sputter with a damaged drive (`accelerate`, `your_afterburner`) |
| 4 | | 3 | 60 | explosion (`explode`; also death and ejection scenes) |
| 5 | | 6 | 6 | mass driver and turret shot |
| 6 | | 7 | 30 | asteroid passing close (`servicetrack`) |
| 7 | | 8 | 10 | target-lock malfunction; an object effect in `src/spc.c:1328` (1 time in 4) |
| 8 | | 9 | 60 | laser and neutron gun shot |
| 9 | | 10 | 6 | bolt absorbed by a shield (`inflict_damage`) |
| 10 | | 11 | 10 | bolt hits armour |
| 11 | held | 12 | 60 | launch tube |
| 12 | held | 13 | 60 | afterburner |
| 13 | | 14 | 6 | tumbling debris |
| 14 | repeat | 18 | 60 | hangar run |
| 15 | held | 19 | 60 | flight deck / landing |
| 16 | | 20 | 60 | flight deck |
| 17 | held | 21 | 60 | flight deck / landing |
| 18 | glide | 22 | 6 | launch; note 84 gliding to 57 |
| 19 | | 23 | 60 | launch |
| 20 | glide | 40 | 2 | canopy / cockpit start; note 24 gliding to 127 |
| 21 | | 41 | 40 | missile lock: each tick while locking (`decrement_lock_time`) |
| 22 | | 42 | 40 | missile lock acquired |
| 23 | | 44 | 5 | display static (`malf_noise`); the only OPL rhythm-voice timbre |
| 24 | | 45 | 5 | target locked (`PlayTargetLockSfx`) |
| 25 | | 46 | 5 | menu click: displays, radio, nav map, weapon selection |
| 26 | | 47 | 40 | no call found |
| 27 | | 63 | 40 | explosion inside the cockpit (`cockpit_explosion`) |
| 28 | | 124 | 40 | collision (`object_collision`) |
| 29 | | 61 | 40 | funeral |
| 30 | | 62 | 40 | funeral: rifle volley |
| 31 | | 105 | 60 | malfunction (`malf_sound`); funeral |
| 32 | repeat | 106 | 40 | shields-low alarm (`update_lights`: both shields nearly gone) |
| 33 | | 108 | 60 | ejection |
| 34 | | 109 | 80 | ejection |
| 35 | | 110 | 40 | barracks |
| 36 | | 111 | 60 | funeral |

Kilrathi Saga's own table (`aabSoundEffectDescriptors`,
`src/music.c`) has the same 36 records plus a 37th; only the DOS list
above matters here.

## 9.3 Volume, position, priority

`PlaySfxWaveFileByNumber(number, object, looping)` [src]:

- `object` -1 means "in the cockpit": full volume, centred.
- Otherwise volume falls with distance from the camera:
  `127 - ((distance / 500) >> 8)` with distance in the game's 24.8
  units; under 10 the effect is not played at all. Pan follows the
  direction (mono: ignore).
- The DOS driver takes a *priority* where the Windows code passes
  `looping`; the fly-by uses priority 8.

`SdlPlayOriginFxSoundEffect` [ofx]: 32 effect slots share 8 channels.
An effect carries a **tag** (the source object). Starting an effect
whose tag is already playing replaces that one on the same channel -
so a gun that fires again restarts its own sound instead of piling
up. Sound 8 alternates between two tags so rapid laser fire overlaps
once. With all 8 channels busy, the oldest effect of equal or lower
priority is stopped; if none qualifies the new effect is dropped.

In wc1-re's port the effects have their own emulated chip, so they
never compete with the music for the nine voices. On a real AdLib
card they did. On the ThumbyColor the voice budget is the scarce
resource (10.4): two or three voices reserved for effects, with the
rules above deciding who gets them, is the proposal.

## 9.4 What the port plays now, and the mapping

`World.sound(sid)` queues one of five ids; `MainGame` loads the five
files with `audio_open_id`, and `Flight.frame` plays only the last id
queued in a frame (`audio_play_id`). Mapping to the
original numbers for the day the FM player exists:

| Port id | File | Original number(s) |
|---------|------|--------------------|
| 0 | sfx_laser | 8 (laser, neutron), 5 (mass driver) |
| 1 | sfx_missile | 1 |
| 2 | sfx_hit | 9 (shield), 10 (armour) |
| 3 | sfx_boom | 4 |
| 4 | sfx_pop | 28 (collision), 13 (debris) |

Not triggered at all yet: afterburner (12), fly-by (2), lock tones
(21, 22, 24), clicks (25), alarms (32), static (23), and everything
belonging to cutscenes.

## 9.5 Two ways forward

**A. FM effects through the music player** (the original way).
Needs chapter 10's synthesiser. Cost: the 8-byte table above (288
bytes) and a service routine of about 60 lines. Gain: all 36 original
effects, mixed with the music, at no extra flash.

**B. Pre-rendered samples.** Render each effect once on the PC
(drive `originfx.cpp` + `ymfm` from a small host program, or use the
PC reference of chapter 10) to IMA ADPCM. Most effects are under a
second: about 36 files, roughly 150 KB at 15,625 Hz [guess]. Works
with the engine as it is, but only one sound at a time and none over
music unless the audio loop learns to mix.

A is the goal the user stated (an FM interpreter). B is a cheap
intermediate step that makes the *right* sounds audible before the
synthesiser exists, and its renderings double as reference
recordings for testing A.
