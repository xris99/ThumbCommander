# 10. A music interpreter for the ThumbyColor

**This chapter is a design proposal. None of it has been built or
measured.** Facts about the original come from chapters 8 and 9;
facts about the engine from `thumby_engine/audio/hardware.py`.
Everything about speed and about how MicroPython behaves with two
cores is marked [guess] and must be measured on a device before the
design is trusted - 10.9 says how, and that is step one.

The goal as stated by the project owner: understand the in-flight
music, then write an interpreter "like AdLib" that plays the original
songs in the background, on the second core if possible.

## 10.1 What has to exist

```
 MUSIC.MID songs ──┐
 WINGLDR.TIM bank ─┤  converter (PC): validate, repack
 effect records ───┘        │
                            ▼
 core 0 (game)        mus.wc, tim.wc on flash
   music.py  gametrack / changetrack / stingers   (8.7)  -> track numbers
   loads the next song into a spare buffer, posts commands
                            │  shared arrays, no locks
                            ▼
 core 1 (one viper loop, never allocates)
   sequencer   MIDI events + 0xFE control events, leave flag     (8.1)
   driver      channels, voice allocation, pitch, level, 60 Hz   (8.3)
   effects     8-byte records on spare voices                    (9.1)
   synth       N two-operator FM voices -> one sample
   output      PWM duty, sample-accurate timing
```

Three separable pieces, in rising difficulty:

1. **The decisions** (which track now): pure game logic, 80 lines,
   testable today without sound.
2. **Sequencer + driver**: deterministic integer code. Its output is
   a stream of "set voice v to these parameters" - on the original, a
   stream of OPL register writes. It can be verified **exactly**
   against wc1-re (10.8).
3. **The synthesiser**: turns voice parameters into samples. This is
   where the CPU goes and where approximations are allowed.

## 10.2 What the engine does today

`thumby_engine/audio/hardware.py` [src]:

- `_thread.start_new_thread(audio_loop, ())` starts one
  `@micropython.viper` function on core 1 per sound. It creates
  `PWM(Pin(23), freq=120000)`, decodes IMA ADPCM nibble by nibble from
  two 800-byte buffers, calls `pwm.duty_u16(sample)` and **busy-waits**
  on `time.ticks_us()` until the next sample time. Rates: 15,625 Hz
  and lower. The thread ends when the sound ends.
- A `machine.Timer` at 30 Hz on core 0 refills whichever buffer the
  loop has finished (`fill_buffers`).
- The two sides share one `array('I')` of 19 fields (`bufstate`):
  positions, flags, volume, loop points, stop request, done flag.
- One sound at a time: `play_id` replaces whatever is playing.

Consequences for music:

- MicroPython on the RP2 has exactly one extra thread, and it is core
  1. Music and effects must therefore live in **one** loop. A music
  thread next to the engine's audio thread is not possible.
- While that loop runs, core 1 is fully occupied (busy-wait). That is
  already the case whenever a sound plays.
- The pattern "viper loop on core 1 + flat shared array" is proven on
  the hardware by the engine. The design below keeps it.

## 10.3 Proposed structure

A game-local module `wcaudio.py` (GPL, in `games/wingcommander/`)
that replaces the engine's audio loop while this game runs, with the
same small API the game uses (`open_id`, `play_id`, `set_volume`,
`stop`) plus music calls. Reason: the engine is shared by other games
and has its own licence; prove the mixer here first, then offer the
generic part to `thumby_engine`.

The loop runs for as long as the game does (not per sound):

```
forever, once per output sample:
    1. sample = sum of active FM voices
               + current ADPCM effect sample (if the old effects stay)
    2. write PWM duty
    3. wait for the next sample time (ticks_us, as the engine does)
    4. at most ONE small job from this list, so no sample is late:
         - a MIDI tick is due: play the events that are due (bounded)
         - a 60 Hz service step is due: service ONE voice / effect
         - a command from core 0 is waiting: take it
```

Job slicing (4) matters: a tick with a 12-note chord plus the 60 Hz
service for nine voices must not land in a single 64-microsecond
sample period. Spread over neighbouring samples it is inaudible
(64 us of skew).

Core 0 never touches synth state. It writes into a command block
(`array('i')`): requested track, mode (start / queue / leave / stop),
branch selector, effect requests, and a counter written last; core 1
copies the command when it sees the counter change and writes back
status: playing track, queued track, song-finished flag, sequence
position, a late-sample counter for diagnostics. Single writer per
field, as in `bufstate`.

Loading a song is file I/O and belongs on core 0: read the song into
a second preallocated `bytearray`, then post "queued song is in
buffer B". Core 1 switches buffers when the playing song ends. Two
buffers of the largest song (22.3 KB, the title track; the largest
in-flight song is 13.3 KB) are needed [data].

Why not run the sequencer on core 0 from a timer? Timer callbacks run
between bytecodes of the main program; a long viper blit delays them
by milliseconds, and music timing would wobble with the frame rate
[guess, standard MicroPython behaviour].

## 10.4 Voices and the budget [guess]

The original has 9 voices and steals the oldest when it runs out. The
songs hold 6 or fewer notes for 73 % of the time and 9 or fewer for
97 % (8.1), and held notes with percussive timbres fall silent long
before their note-off.

Proposal: **6 voices for music + 2 for effects** to start, the
music-voice count being a constant. Voice stealing already exists in
the driver, so fewer voices degrade gracefully (the oldest note
drops), exactly as the AdLib version did against the MT-32 score.

Cost estimate. One operator per sample is: phase add, two table
lookups, a shift, a sign fix - perhaps 150-250 CPU cycles in viper
code, which keeps most variables in memory rather than registers. Two
operators per voice, 8 voices, 15,625 samples per second:

```
16 operators x 200 cycles x 15,625 Hz = 50 million cycles per second
```

At the 300 MHz the game sets, that is about a sixth of core 1 - on
paper comfortable. The per-sample call to `pwm.duty_u16` and the two
`ticks_us` calls of the timing loop are fixed overhead on top; the
engine's ADPCM loop already pays it. **The real number can be off by
a factor of three in either direction.** Levers if it is too slow, in
order of preference:

1. skip silent voices (envelope fully attenuated) - free and large;
2. fewer voices (5 + 1);
3. lower sample rate (12,500 or 10,000 Hz are engine-supported
   rates); FM sidebands alias more, so judge by ear;
4. move the synth inner loop into a native C module (`.mpy` built
   with MicroPython's `mpy_ld.py`). The game already ships native
   code in its `.mpy` files (viper, `-march=armv7emsp`), so the
   loader exists; whether the ThumbyColor firmware accepts a C native
   module was not tested.

## 10.5 The synthesiser core

Model: Yamaha OPL2 two-operator FM, because the timbres are OPL2
register values (8.2). The reference implementation is in wc1-re:
`third_party/ymfm/ymfm_fm.ipp` and `ymfm_opl.cpp` (BSD-3-Clause).
The functions to read: `fm_operator::compute_volume`,
`fm_channel::output_2op`, `fm_operator::clock_envelope`,
`attenuation_increment`, `abs_sin_attenuation`,
`attenuation_to_volume`, and the OPL `cache_operator_data`.

**One voice, one sample** (from `output_2op`, all integers):

```
fb       = feedback amount 0-7 (register 0xC0 bits 1-3)
mod_in   = (m_prev1 + m_prev2) >> (10 - fb)      if fb else 0
m        = operator(phase_m + mod_in)            13-bit signed
m_prev2, m_prev1 = m_prev1, m
if connection == 0 (FM; every music timbre):
    out = operator(phase_c + (m >> 1))
else (additive; one effect timbre):
    out = m + operator(phase_c)
phase_m += inc_m;  phase_c += inc_c
```

**One operator** (`compute_volume`): the phase's top 10 bits index a
1024-step waveform table that stores *attenuation* in 4.8 fixed point
with the sign in bit 15; add the envelope's attenuation (10 bits,
4.6 fixed point, shifted left 2); convert to linear through an
exponent table:

```
la   = WAVE[w][phase10]                  w = register 0xE0 & 3
att  = (la & 0x7FFF) + (env << 2)
out  = EXP[att & 0xFF] >> (att >> 8)     13 bits; 0 once att is large
out  = -out if la & 0x8000
```

Both tables can be generated; they match the chip (checked against
the first entries of ymfm's tables):

```
LOGSIN[i] = round(-log2(sin((i + 0.5) * pi / 512)) * 256)      i = 0..255   (0x859, 0x6C3, ...)
EXP[i]    = (round((2 ** ((255 - i) / 256) - 1) * 1024) | 0x400) << 2       (0x3FA -> ...)
```

`LOGSIN` is a quarter wave; the four OPL2 waveforms are sine,
half-sine (negative half silent), absolute sine, and quarter-sine
pulses. Build four 1024-entry `array('H')` tables once (8 KB) rather
than folding the quarter wave per sample. The timbres use all four
[data].

**Frequency.** The driver produces `fnum` and `block` (8.3). The
operator's frequency is `fnum * 2^(block - 20) * 49716 Hz * MULT`,
with MULT from register 0x20's low 4 bits through the table
`0.5 1 2 3 4 5 6 7 8 9 10 10 12 12 15 15`. For a 32-bit phase at
output rate R: `inc = fnum * MULT2 * 2^(block + 11) * 49716 / R`
(MULT2 = twice MULT). Precompute `49716 / R` as a fixed-point
constant; compute `inc` in the driver at note-on and on pitch
changes, not per sample. Mind the width: for high blocks with large
multipliers the product no longer fits 32 bits. Those partials lie
above half the sample rate anyway; clamp them, or use a narrower
phase accumulator.

**Envelope.** Per operator: attack, decay, sustain level, release
(registers 0x60, 0x80), sustained or percussive (0x20 bit 5), rate
scaling by key (0x20 bit 4), total level and key-scale level (0x40),
tremolo (0x20 bit 7), chip vibrato (0x20 bit 6). The music timbres
use every one of these somewhere [data]. ymfm's `clock_envelope` is
the exact algorithm; it steps at the chip's 49,716 Hz. Two ways to
run it at a lower rate:

- exact: keep ymfm's envelope counter and advance it by `49716 / R`
  (about 3.18 at 15,625 Hz) steps per sample - costly;
- practical: update envelopes at control rate (every 16 or 32
  samples), adding the attenuation the exact algorithm would have
  added in that time. Precompute, per 6-bit rate, "attenuation units
  per control step" in the converter by running the exact algorithm.
  Attack is not linear (`att += (~att * inc) >> 4`), so tabulate the
  attack curve too.

Start with the practical form; keep the exact form in the PC
reference (10.7) to hear the difference.

**In order of audible importance**, if something must go: chip
vibrato (a 7-cent wobble; the driver's own vibrato from 8.3 is the
musically important one and is cheap), tremolo, rate scaling,
key-scale level. Feedback, the four waveforms, and attack / decay /
sustain / release are not optional - they are the timbre.

**Mixing.** An operator peaks at about +-8,168 (ymfm then shifts the
chip's output right by one). Sum, scale so that six
loud voices do not clip, clamp, add 32,768, write as PWM duty. With
`PWM_FREQ = 120000` at a 300 MHz system clock the PWM has about 11
bits of resolution; do not expect more dynamic range than that.

## 10.6 Sequencer and driver on the device

Port `src/sdl/originfx.cpp` function by function - these two layers
are about 1,400 generously spaced lines of C, already integer-only,
and chapters 8.1 and 8.3 are their summary. Keep its names
(`OriginFxPlayTrackEvent` -> `play_track_event`).

Decisions for the port:

- **Keep the per-track cursors.** Do not merge the `MTrk` chunks into
  one stream, although every song's tracks jump together (8.1): a
  jump lands on a *delta*, and where that lies among same-tick events
  differs per track. Up to 19 cursors, each with a wait counter, cost
  nothing at about 1,000 ticks per second.
- **Store songs as they are.** `mus.wc` = an index plus the 41
  unpacked MIDI sections (207 KB). The converter runs the full parser
  over every song and refuses bad data, so the device parser can
  trust it and skip bounds checks.
- **Tempo without floats.** Floats allocate; allocation on core 1 is
  forbidden. One tick lasts `tempo / 480` microseconds. Keep an
  accumulator in samples: per sample add `480,000`; a tick is due
  each time it reaches `(tempo // 1000) * R` (tempo in microseconds,
  R in Hz; `500 * 15625` fits 32 bits, `500000 * 15625` does not).
  The rounding of tempo to milliseconds changes the speed by at most
  0.2 % - or let the converter replace each tempo event with an exact
  16.16 "samples per tick" for the chosen R.
- **60 Hz service**: a second accumulator; add 60 per sample, step
  when it reaches R.
- **Timbre lookup by table**: the bank is searched linearly by program
  number in the original; build a 256-entry program -> offset table
  at load time (remember: unknown programs map to the first timbre).
- **Leave out**: stereo pan, OPL rhythm mode (unless effect 23 is
  wanted), the MT-32 path.
- **Effects**: 9.1's service routine, on the voices reserved for
  them, with the tag and priority rules of 9.3.

Memory on the device [guess, from sizes]: waveform and exponent
tables 9 KB, timbre bank 3.8 KB, two song buffers 45 KB, voice and
channel state under 2 KB - about 60 KB. Check against `mem_free()`
in flight before committing; one song buffer of 14 KB during flight
plus a 23 KB one only in menus is the fallback.

## 10.7 The PC side

The PC emulation plays sound through pygame at 15,625 Hz
(`thumby_engine/audio/pc.py`). Pure-Python per-sample synthesis is too
slow there, so split the code:

| Module | Runs on | Notes |
|--------|---------|-------|
| `ofx_seq.py` | both | sequencer + driver; plain integer Python; produces voice-parameter updates. On the device it is called from the viper loop or written in viper itself |
| `ofx_synth.py` | device | the viper sample loop |
| `tool/wc1/ofx_ref.py` | PC | numpy block synthesiser with the *exact* envelope; renders a song to WAV; feeds pygame in the emulator |

`ofx_ref.py` is also the listening tool: render all 41 songs to WAV
on the PC first. If the songs do not sound right there, nothing on
the device will fix it.

The device loop has to call the sequencer without allocating. In
practice that means the sequencer and driver are viper functions over
preallocated arrays too (state in `array('i')`, songs and timbres in
`bytearray`s) - write them that way from the start and let the PC
run the same file through the viper emulation in `thumby_engine/pc`.

## 10.8 Verification

1. **Sequencer and driver - exact.** Build a small host program from
   wc1-re's `originfx.cpp` and `ymfm` that plays a song and logs
   every `OriginFxWriteRegister(reg, value)` with its output-sample
   index. Make the Python driver log the same (keep a "register
   view" of its voice parameters for the test). At the same sample
   rate the two logs must be identical, including after `leave`
   commands at scripted times. wc1-re builds in this project's
   environment (`make modern`); the harness itself was not written.
2. **Synth against the reference chip.** For each timbre play one
   note for a second on ymfm and on `ofx_ref.py`; compare spectra, or
   simply waveforms - with the exact envelope they should match
   closely.
3. **Device synth against PC synth.** Same integer algorithm, so the
   viper loop under emulation must match `ofx_ref.py` run in its
   "practical envelope" mode sample for sample.
4. **Decisions.** Unit-test `gametrack` / `changetrack` /
   `new_space_music_changes` with made-up world states; then log the
   track requests of a `wc1_selfplay.py` run and read them.

## 10.9 Measure first

Before writing the synthesiser, put three numbers on the table with
throwaway scripts on a real ThumbyColor:

| Question | How | Decides |
|----------|-----|---------|
| How long does one operator take in viper? | a viper loop doing the 10.5 operator maths 100,000 times, timed with `ticks_us` | voice count, sample rate, or the need for a C module |
| What does the output path cost? | the engine's loop with decoding removed: `duty_u16` + the `ticks_us` wait, count how many iterations fit in a second | the fixed overhead per sample |
| What stalls core 1? | a core-1 loop that records the largest gap between iterations while core 0 (a) runs the flight loop, (b) calls `gc.collect()`, (c) writes a file | whether saving or collecting must be kept away from music |

About (c): as far as is known, the RP2 port of MicroPython pauses the
other core while it erases or writes flash, and the collector may
hold it briefly; the engine's ADPCM player would suffer the same
today [guess]. If file writes stall audio, the rule is simple - the
game only writes in menus (`wc_save.json`, `wc_settings.json`), where
a short gap or a deliberate fade is acceptable.

Also read `mem_free()` at flight start on the device (the game
already prints it).

## 10.10 If real-time FM does not fit

Fallback ladder, each rung usable on its own:

1. **Fewer voices, lower rate** (10.4).
2. **C native module** for the inner loop.
3. **Pre-rendered music.** Render songs on the PC to the engine's IMA
   ADPCM and play them through the existing loop. All 41 songs once
   through are 1,456 s: 11.4 MB at 15,625 Hz, 5.8 MB at 8,000 Hz -
   too much for a shared 16 MB flash. A selection is feasible: the
   seven combat and cruise loops that carry the flight (0, 1, 3, 15,
   16, 17, 18: about 235 s, 1.8 MB at 15,625 Hz or 0.9 MB at 8,000 Hz)
   plus the stingers 6-11 (63 s, 0.5 MB / 0.25 MB). Loop points and exit points become
   sample offsets (`set_loop` exists in the engine; "leave at the
   next exit" needs a small addition). Effects would then cut the
   music unless the loop mixes two ADPCM streams.
4. **Simpler synthesis**: square or triangle voices driven by the
   same sequencer - recognisable tunes at a few percent of the cost.
   Worth having anyway as the first audible milestone, because it
   exercises everything except the FM operator.

## 10.11 Build order

1. `music.py`: decisions only, with tests. Log requests during
   self-play.
2. Converter: `mus.wc`, `tim.wc`, effect table; validation by the
   reference parser.
3. `ofx_seq` on the PC + register-log test against wc1-re.
4. `ofx_ref.py`: render everything to WAV, listen.
5. Device measurements (10.9).
6. Square-wave back end on the device through the new loop: music is
   audible, timing and transitions can be judged.
7. FM operator in viper, tuned to the measured budget.
8. Effects on the same voices; retire the five ADPCM placeholders.
9. Hook the scenes of chapter 6 to their tracks.
