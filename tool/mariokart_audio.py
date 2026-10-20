#!/usr/bin/env python3
"""
Mario Karts audio asset generator.

Synthesizes the game's sound effects and music as 16-bit mono 15625 Hz
WAVs (the ThumbyColor hardware's IMA-ADPCM sample rate) and encodes them
to the device .ima format with tool/wav_to_ima_converter.py.

Format notes (see thumby_engine/audio/hardware.py and pc.py, and
tool/mariocards_audio.py):
  * the 24-byte IMA header is written by the converter; both the
    hardware decoder and the PC decoder read the high nibble of each
    byte first, so everything is encoded 'high_first';
  * music tracks are whole-file loops: the game plays them with
    audio_set_loop(True, 0, 0), which the hardware decodes as a
    0..end-of-file loop (saved predictor state at the loop point) and
    the PC's pygame backend as a full sound loop;
  * intro_128_80.ima is auto-loaded by the cutscene player whenever
    assets/intro_128_80.COL.bin plays (the player derives the .ima name
    from the .COL.bin name and stops the audio when the cutscene ends).

Usage:
    python3 tool/mariokart_audio.py              # build every asset
    python3 tool/mariokart_audio.py sfx_spin     # build one asset
    python3 tool/mariokart_audio.py --list       # show the asset list
"""

import math
import os
import struct
import sys
import wave
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, 'games', 'mariokart', 'assets')
TMP_DIR = os.path.join(REPO_ROOT, 'build', 'mariokart_audio')
RATE = 15625

# Load the converter (it lives next to this tool - load it by path).
_spec = importlib.util.spec_from_file_location(
    'wav_to_ima_converter',
    os.path.join(REPO_ROOT, 'tool', 'wav_to_ima_converter.py'))
_converter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_converter)


# --- tiny synth ---------------------------------------------------------------

def _env(i, n, attack=0.004, decay=6.0):
    """Standard ADSR-lite envelope: fast linear attack, exponential decay
    scaled so the note reaches ~1/e^decay of its peak at its end."""
    t = i / RATE
    a = min(1.0, t / max(attack, 1e-6)) if n > 1 else 1.0
    d = math.exp(-decay * t / max(n / RATE, 1e-6))
    return a * d


def sine(freq, dur, amp=0.5, decay=6.0, attack=0.004, freq_end=None):
    n = int(dur * RATE)
    out = [0] * n
    if freq_end is None:
        freq_end = freq
    phase = 0.0
    for i in range(n):
        f = freq + (freq_end - freq) * (i / n)
        phase += 2.0 * math.pi * f / RATE
        out[i] = int(32767 * amp * _env(i, n, attack, decay)
                     * math.sin(phase))
    return out


def square(freq, dur, amp=0.3, decay=6.0, attack=0.002):
    n = int(dur * RATE)
    out = [0] * n
    phase = 0.0
    for i in range(n):
        phase += 2.0 * math.pi * freq / RATE
        v = 1.0 if math.sin(phase) >= 0 else -1.0
        out[i] = int(32767 * amp * _env(i, n, attack, decay) * v)
    return out


def triangle(freq, dur, amp=0.5, decay=6.0, attack=0.004):
    n = int(dur * RATE)
    out = [0] * n
    phase = 0.0
    for i in range(n):
        phase += 2.0 * math.pi * freq / RATE
        two_pi = 2.0 * math.pi
        p = phase % two_pi
        v = (4.0 * p / two_pi - 1.0) if p < math.pi \
            else (3.0 - 4.0 * p / two_pi)
        out[i] = int(32767 * amp * _env(i, n, attack, decay) * v)
    return out


def noise(dur, amp=0.3, cutoff=0.12, decay=8.0):
    """White noise through a one-pole low-pass (cutoff = pole
    coefficient, 0..1)."""
    n = int(dur * RATE)
    out = [0] * n
    state = 0.0
    import random
    rng = random.Random(777)
    for i in range(n):
        x = rng.uniform(-1.0, 1.0)
        state += cutoff * (x - state)
        out[i] = int(32767 * amp * _env(i, n, 0.001, decay) * state * 3.0)
    return out


def noise_sweep(dur, amp=0.4, f0=300.0, f1=2400.0, decay=10.0):
    """Band-pass-ish noise sweep: noise amplitude modulated by a rising
    sine - reads as an air whoosh (boost)."""
    n = int(dur * RATE)
    out = [0] * n
    state = 0.0
    import random
    rng = random.Random(31337)
    for i in range(n):
        t = i / n
        f = f0 + (f1 - f0) * t
        x = rng.uniform(-1.0, 1.0)
        pole = min(0.95, max(0.05, f / 12000.0))
        state += pole * (x - state)
        mod = 0.3 + 0.7 * math.sin(math.pi * min(1.0, t * 1.2))
        out[i] = int(32767 * amp * _env(i, n, 0.004, decay) * state * 2.0
                     * mod)
    return out


def kick(dur=0.12, amp=0.7):
    """Synth drum: sine pitch drop 160->45 Hz, hard decay."""
    return sine(160.0, dur, amp=amp, decay=14.0, attack=0.001,
                freq_end=45.0)


def midi(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def note(m, dur, wave='square', amp=0.3, decay=6.0, attack=0.002):
    """One note from a MIDI number."""
    f = midi(m)
    if wave == 'sine':
        return sine(f, dur, amp=amp, decay=decay, attack=attack)
    if wave == 'triangle':
        return triangle(f, dur, amp=amp, decay=decay, attack=attack)
    return square(f, dur, amp=amp, decay=decay, attack=attack)


def chord(midis, dur, wave='square', amp=0.22, decay=6.0):
    """Several notes sounding together, mixed."""
    parts = [note(m, dur, wave, amp=amp, decay=decay) for m in midis]
    n = max(len(p) for p in parts)
    out = [0] * n
    for p in parts:
        for i, s in enumerate(p):
            out[i] += s
    return _clamp(out)


def mix(parts):
    """parts: (offset_seconds, sample_list). Mix into one track."""
    total = 0
    for off, p in parts:
        total = max(total, int(off * RATE) + len(p))
    out = [0] * total
    for off, p in parts:
        at = int(off * RATE)
        for i, s in enumerate(p):
            out[at + i] += s
    return _clamp(out)


def _clamp(out):
    for i, s in enumerate(out):
        if s > 30000:
            out[i] = 30000
        elif s < -30000:
            out[i] = -30000
    return out


def _fade(samples, ms=8):
    """Micro fade in/out to keep loops click-free."""
    n = int(ms / 1000 * RATE)
    for i in range(n):
        g = i / n
        samples[i] = int(samples[i] * g)
        samples[len(samples) - 1 - i] = int(
            samples[len(samples) - 1 - i] * g)
    return samples


# --- sound effects -------------------------------------------------------------

def sfx_select():
    """Menu move: short bright blip."""
    return mix([(0.0, square(880, 0.07, amp=0.3, decay=30))])


def sfx_confirm():
    """Menu OK: two-step up-blip."""
    return mix([(0.0, square(660, 0.05, amp=0.3, decay=20)),
                (0.05, square(990, 0.08, amp=0.3, decay=20))])


def sfx_count():
    """Countdown 3/2/1: low square beep."""
    return mix([(0.0, square(587, 0.16, amp=0.42, decay=18)),
                (0.0, square(293, 0.16, amp=0.3, decay=18))])


def sfx_go():
    """GO!: higher, longer beep."""
    return mix([(0.0, square(880, 0.3, amp=0.45, decay=9)),
                (0.0, square(440, 0.3, amp=0.3, decay=9))])


def sfx_pickup():
    """Item box hit: bright two-note ding."""
    return mix([(0.0, square(1046, 0.06, amp=0.34, decay=16)),
                (0.06, square(1568, 0.10, amp=0.34, decay=14))])


def sfx_boost():
    """Mushroom boost: rising air whoosh + engine rev."""
    return mix([(0.0, noise_sweep(0.42, amp=0.5, f0=300, f1=2600,
                                  decay=12)),
                (0.0, square(110, 0.4, amp=0.2, decay=9,
                             attack=0.002, ), ),
                ])


def sfx_star():
    """Star power: ascending shimmer run + shimmer noise."""
    seq = [84, 88, 91, 95, 98]      # G5 B5 D6 F6 G6
    parts = [(i * 0.05, square(midi(m), 0.06, amp=0.3, decay=12))
             for i, m in enumerate(seq)]
    parts.append((0.24, noise(0.18, amp=0.12, cutoff=0.85, decay=9)))
    return mix(parts)


def sfx_spin():
    """Spin-out: crash noise + descending wobble (the classic
    dizzy fall)."""
    return mix([(0.0, noise(0.16, amp=0.5, cutoff=0.5, decay=18)),
                (0.02, sine(300, 0.4, amp=0.4, decay=8, freq_end=90)),
                (0.12, sine(220, 0.3, amp=0.25, decay=8, freq_end=70))])


def sfx_hit():
    """Obstacle / kart impact: low thud + crack."""
    return mix([(0.0, sine(120, 0.2, amp=0.6, decay=16, freq_end=40)),
                (0.0, noise(0.05, amp=0.4, cutoff=0.5, decay=40))])


def sfx_banana():
    """Banana placed: soft plip."""
    return mix([(0.0, triangle(660, 0.07, amp=0.35, decay=16)),
                (0.06, triangle(440, 0.09, amp=0.3, decay=14))])


def sfx_box():
    """Passing a used box: soft tick."""
    return mix([(0.0, square(440, 0.03, amp=0.15, decay=30))])


def sfx_win():
    """Victory fanfare: C major arpeggio landing on C7."""
    seq = [(72, 0.09), (76, 0.09), (79, 0.09), (84, 0.09), (88, 0.09),
           (91, 0.4)]
    parts = []
    t = 0.0
    for m, d in seq:
        parts.append((t, square(midi(m), d, amp=0.34,
                                decay=5 if d > 0.2 else 12)))
        t += d * 0.9
    return mix(parts)


def sfx_lose():
    """Defeat: descending minor phrase."""
    seq = [(64, 0.16), (60, 0.16), (57, 0.16), (52, 0.42)]
    parts = []
    t = 0.0
    for m, d in seq:
        parts.append((t, triangle(midi(m), d, amp=0.4,
                                  decay=4 if d > 0.2 else 10)))
        t += d * 0.95
    return mix(parts)


# --- music ----------------------------------------------------------------------

def music_title():
    """Title screen: bouncy E minor, 138 BPM, 8 beats (2 bars).
    Whole file is the loop."""
    beat = 60.0 / 138.0
    parts = []
    # Kick on every beat.
    for b in range(8):
        parts.append((b * beat, kick(0.1, amp=0.42)))
    # Off-beat hats.
    for b in range(8):
        parts.append((b * beat + beat / 2,
                      noise(0.03, amp=0.12, cutoff=0.9, decay=60)))
    # 8th-note bass line: | E E E E | C C D D | A A A A | B B B B |
    bass = [40, 40, 40, 40, 48, 48, 50, 50,
            45, 45, 45, 45, 47, 47, 47, 47]
    for i, m in enumerate(bass):
        parts.append((i * beat / 2,
                      square(midi(m), beat / 2 * 0.85, amp=0.3,
                             decay=10)))
    # Lead phrase (8th and 16th notes), E minor.
    lead = [
        (0.0, 0.5, 64), (0.5, 0.25, 67), (0.75, 0.25, 71),
        (1.0, 0.5, 69), (1.5, 0.5, 67),
        (2.0, 0.5, 64), (2.5, 0.5, 67),
        (3.0, 1.0, 71),
        (4.0, 0.5, 69), (4.5, 0.5, 74),
        (5.0, 0.5, 76), (5.5, 0.5, 74),
        (6.0, 0.5, 71), (6.5, 0.25, 69), (6.75, 0.25, 67),
        (7.0, 0.75, 71),
    ]
    for at, dur, m in lead:
        parts.append((at * beat, square(midi(m), dur * beat * 0.9,
                                        amp=0.2, decay=12)))
    return _fade(mix(parts), 10)


def music_race():
    """Race: driving C major, 152 BPM, 8 beats (2 bars).
    16th-note bass, 8th-note lead, off-16th hats. Whole-file loop."""
    beat = 60.0 / 152.0
    parts = []
    # Kick: every beat.
    for b in range(8):
        parts.append((b * beat, kick(0.08, amp=0.5)))
    # Hats on the off-16ths.
    for b in range(8):
        parts.append((b * beat + beat / 4,
                      noise(0.02, amp=0.1, cutoff=0.9, decay=60)))
        parts.append((b * beat + beat / 4 * 3,
                      noise(0.02, amp=0.12, cutoff=0.9, decay=60)))
    # 16th-note bass: C C C C | C C E C | F F F F | G G G G
    bass = [48, 48, 48, 48, 48, 48, 52, 48,
            53, 53, 53, 53, 55, 55, 55, 55]
    for i, m in enumerate(bass):
        parts.append((i * beat / 4,
                      square(midi(m), beat / 4 * 0.8, amp=0.28,
                             decay=16)))
    # 8th-note lead, C major phrase.
    lead = [
        (0.0, 0.5, 72), (0.5, 0.5, 76),
        (1.0, 0.5, 79), (1.5, 0.5, 76),
        (2.0, 0.5, 72), (2.5, 0.25, 74), (2.75, 0.25, 76),
        (3.0, 0.5, 77), (3.5, 0.5, 76),
        (4.0, 0.5, 79), (4.5, 0.5, 81),
        (5.0, 0.5, 84), (5.5, 0.25, 81), (5.75, 0.25, 79),
        (6.0, 0.5, 77), (6.5, 0.5, 76),
        (7.0, 0.5, 72), (7.5, 0.5, 74),
    ]
    for at, dur, m in lead:
        parts.append((at * beat, square(midi(m), dur * beat * 0.85,
                                        amp=0.18, decay=14)))
    return _fade(mix(parts), 10)


def intro_music():
    """Intro cutscene score (~2.86 s, matched to the 60-frame @ 21 fps
    cutscene): thump as the star appears, chord stab at the title
    reveal (frame 10 = 0.48 s), star ding at the pop (frame 15),
    engine revs + kick pulses while the karts race (frame 26 =
    1.24 s), and a big final C chord."""
    parts = []
    # Star appears: low thump + hat.
    parts.append((0.05, kick(0.12, amp=0.55)))
    parts.append((0.25, noise(0.03, amp=0.1, cutoff=0.9, decay=60)))
    parts.append((0.40, noise(0.03, amp=0.12, cutoff=0.9, decay=60)))
    # Title reveal (frame 10): C major chord stab.
    parts.append((0.48, chord([48, 60, 64, 67, 72], 0.4, amp=0.2,
                              decay=8)))
    # Star pop: high ding + shimmer.
    parts.append((0.71, sine(midi(88), 0.3, amp=0.3, decay=10)))
    parts.append((0.75, sine(midi(91), 0.3, amp=0.2, decay=10)))
    parts.append((0.71, noise(0.2, amp=0.08, cutoff=0.9, decay=12)))
    # Karts race (frame 26): engine rev + chord + kick/hat pulses.
    parts.append((1.24, square(70, 0.5, amp=0.25, decay=6,
                               attack=0.002, )))
    parts.append((1.24, chord([59, 62, 67], 0.3, amp=0.2, decay=8)))
    for b in (1.24, 1.64, 2.04, 2.44):
        parts.append((b, kick(0.09, amp=0.4)))
    for b in (1.44, 1.84, 2.24):
        parts.append((b, noise(0.03, amp=0.1, cutoff=0.9, decay=60)))
    # Final C chord, long decay out.
    parts.append((2.5, chord([48, 60, 64, 67, 72, 76], 0.4,
                             amp=0.16, decay=6)))
    out = mix(parts)
    # End exactly at the cutscene length (60 frames / 21 fps).
    target = int(60 / 21 * RATE)
    if len(out) > target:
        del out[target:]
    return _fade(out, 12)


# --- build ----------------------------------------------------------------------

ASSETS = {
    'sfx_select': sfx_select,
    'sfx_confirm': sfx_confirm,
    'sfx_count': sfx_count,
    'sfx_go': sfx_go,
    'sfx_pickup': sfx_pickup,
    'sfx_boost': sfx_boost,
    'sfx_star': sfx_star,
    'sfx_spin': sfx_spin,
    'sfx_hit': sfx_hit,
    'sfx_banana': sfx_banana,
    'sfx_box': sfx_box,
    'sfx_win': sfx_win,
    'sfx_lose': sfx_lose,
    'music_title': music_title,
    'music_race': music_race,
    'intro_128_80': intro_music,
}


def build(name):
    """Synthesize one asset and encode it to .ima in the game assets dir."""
    samples = ASSETS[name]()
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    wav_path = os.path.join(TMP_DIR, name + '.wav')
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
    _converter.convert_wav_to_ima(wav_path, 'high_first')
    ima_path = os.path.join(TMP_DIR, name + '.ima')
    os.replace(ima_path, os.path.join(OUT_DIR, name + '.ima'))
    return os.path.getsize(os.path.join(OUT_DIR, name + '.ima'))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--list':
        for n in ASSETS:
            print(n)
        return
    names = sys.argv[1:] or list(ASSETS)
    for n in names:
        if n not in ASSETS:
            raise SystemExit(f'unknown asset: {n}')
        size = build(n)
        print(f'  {n}.ima: {size} bytes')
    print(f'Done. Audio in {OUT_DIR}')


if __name__ == '__main__':
    main()
