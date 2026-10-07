#!/usr/bin/env python3
"""Original soft "desert" background music for the intro film — synthesized, no samples, no rights issues.

    tools/make_intro_music.py [--out state/intro-music.wav] [--seconds 81]

Layers: a low drone (D), wind (filtered noise), slow plucked phrases in maqam Hijaz on D
(D Eb F# G A Bb C D — Karplus-Strong strings, oud-like), a soft frame-drum pulse, a simple reverb.
"""
import argparse
import wave

import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def note_hz(semitones_from_d3):
    return 146.83 * 2 ** (semitones_from_d3 / 12)


# maqam Hijaz on D: intervals in semitones
HIJAZ = [0, 1, 4, 5, 7, 8, 10, 12, 13, 16, 17, 19]


def pluck(freq, dur, bright=0.5, decay=0.996):
    """Karplus-Strong plucked string."""
    n = int(dur * SR)
    period = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, period)
    # soften the excitation (a thumb, not a pick)
    for _ in range(2):
        buf = 0.5 * (buf + np.roll(buf, 1))
    out = np.empty(n)
    for i in range(n):
        j = i % period
        out[i] = buf[j]
        buf[j] = decay * (bright * buf[j] + (1 - bright) * buf[(j + 1) % period])
    env = np.minimum(1, np.arange(n) / (0.004 * SR))
    return out * env


def drone(seconds):
    t = np.arange(int(seconds * SR)) / SR
    f = note_hz(-12)            # D2
    x = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t + 0.3) + 0.25 * np.sin(2 * np.pi * 3 * f * t + 1.1)
         + 0.35 * np.sin(2 * np.pi * note_hz(-5) * t))                       # + A2: open fifth
    swell = 0.75 + 0.25 * np.sin(2 * np.pi * t / 11.0)                      # slow breathing
    return x * swell


def wind(seconds):
    n = int(seconds * SR)
    w = rng.normal(0, 1, n)
    # low-pass by cumulative smoothing, then a slowly moving amplitude
    for a in (0.02, 0.03):
        y = np.empty(n); acc = 0.0
        for i in range(n):
            acc += a * (w[i] - acc); y[i] = acc
        w = y
    t = np.arange(n) / SR
    gust = 0.5 + 0.5 * np.sin(2 * np.pi * t / 17.0 + 1) * np.sin(2 * np.pi * t / 7.3)
    return w * (0.4 + 0.6 * gust**2)


def drum(dur=0.6, low=True):
    t = np.arange(int(dur * SR)) / SR
    if low:   # "dum": soft membrane
        f = 70 * np.exp(-t * 6) + 55
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    else:     # "tek": light edge tap
        x = rng.normal(0, 1, len(t)) * np.exp(-t * 60) * 0.5 + np.sin(2 * np.pi * 330 * t) * np.exp(-t * 40) * 0.3
    return x


def reverb(x, mix=0.28):
    out = x.copy()
    for d, g in [(0.0297, .72), (0.0371, .70), (0.0411, .68), (0.0437, .66), (0.083, .45), (0.131, .35)]:
        k = int(d * SR)
        y = np.zeros_like(x)
        y[k:] = x[:-k] * g
        for _ in range(3):                      # a few feedback passes ≈ comb filter tail
            y[k:] += y[:-k] * g * 0.5
        out += mix * y / 3
    return out


def place(track, sig, t, gain):
    i = int(t * SR)
    if i >= len(track):
        return
    seg = sig[: len(track) - i]
    track[i:i + len(seg)] += gain * seg


def compose(seconds):
    n = int(seconds * SR)
    music = np.zeros(n)
    music += 0.10 * drone(seconds)
    music += 0.05 * wind(seconds)
    # slow phrases (beat = 0.9 s, ~67 bpm), phrase of 8 beats, a few rests
    beat = 0.9
    phrases = [
        [(0, 4, 1.5), (2, 5, 1.0), (3, 4, 1.0), (4, 2, 2.5)],
        [(0, 4, 1.0), (1, 5, 1.0), (2, 7, 1.5), (4, 6, 1.0), (5, 5, 1.0), (6, 4, 2.0)],
        [(0, 7, 1.5), (2, 8, 1.0), (3, 7, 1.0), (4, 5, 1.0), (5, 4, 1.0), (6, 2, 2.0)],
        [(0, 2, 1.0), (1, 1, 1.0), (2, 0, 3.0)],
    ]
    t, k = 3.0, 0
    while t < seconds - 6:
        for b, deg, length in phrases[k % len(phrases)]:
            f = note_hz(HIJAZ[deg])
            place(music, pluck(f, min(4.0, length * beat + 1.5), bright=0.45, decay=0.9965), t + b * beat, 0.16)
            if rng.random() < 0.35:            # a soft octave echo now and then
                place(music, pluck(f * 2, 1.2, bright=0.5, decay=0.994), t + b * beat + beat / 2, 0.05)
        t += 8 * beat + (beat * 2 if k % 2 else 0)
        k += 1
    # frame drum: dum . tek . dum dum tek . (very soft)
    pattern = [(0, True), (2, False), (4, True), (5, True), (6, False)]
    t = 8.0
    while t < seconds - 5:
        for b, low in pattern:
            place(music, drum(0.6, low), t + b * beat / 2 * 2 / 2, 0.11 if low else 0.05)
        t += 4 * beat
    music = reverb(music)
    # fade in / out
    tt = np.arange(n) / SR
    music *= np.clip(tt / 4.0, 0, 1) * np.clip((seconds - tt) / 5.0, 0, 1)
    return music / (np.abs(music).max() + 1e-9) * 0.9


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="state/intro-music.wav")
    ap.add_argument("--seconds", type=float, default=81.0)
    a = ap.parse_args()
    x = compose(a.seconds)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    print("wrote", a.out, f"{a.seconds:.0f} s")


if __name__ == "__main__":
    main()
