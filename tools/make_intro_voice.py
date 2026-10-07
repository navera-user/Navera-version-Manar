#!/usr/bin/env python3
"""Narrate the intro film like an old storyteller (offline: Piper TTS + ffmpeg from imageio-ffmpeg).

  1. tools/make_intro_voice.py plan [--voice en_US-norman-medium]
        speaks the story, writes server/static/media/intro-timing.json (scene start times) and
        state/intro-voice-<voice>.wav, and state/intro-music.wav at the right length
  2. record the film (it reads intro-timing.json):  tools/make_intro_voice.py record
  3. tools/make_intro_voice.py mux [--voice …] [--out server/static/media/navera-intro.webm]

  or all at once:  tools/make_intro_voice.py all --voice en_US-norman-medium

Voices: state/voices (python3 -m piper.download_voices --data-dir state/voices <name>).
"Old storyteller": slower (length_scale), pitch lowered ~1.5 semitones, low-end warmth, a little room,
and pauses between phrases.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "server", "static", "media")
STATE = os.path.join(ROOT, "state")
SR = 44100

# scene id, minimum seconds on screen, phrases (a pause is left between phrases)
SCENES = [
    ("s1", 11, ["Long before satellites, there were birds.",
                "Every autumn, a small swallow leaves its home and flies south,",
                "across seas, and across deserts,",
                "thousands of kilometres.",
                "And it never carries a map."]),
    ("s2", 12, ["How does it find the way?",
                "It watches the land below.",
                "It reads the sun by day, and the stars by night.",
                "It feels the magnetic field of the Earth,",
                "and it remembers every wing beat.",
                "And when one sense is wrong, the others notice."]),
    ("s3", 11, ["Our machines are not so wise.",
                "A drone trusts one voice from the sky: G P S.",
                "And that voice is easy to silence, or to imitate.",
                "Then the drone is lost, and it does not even know it."]),
    ("s4", 13, ["NAVERA was born from the swallow's lesson.",
                "Its camera looks down at the ground,",
                "and it turns, and scales the picture, until it fits the map.",
                "And there, on the map, is its position."]),
    ("s5", 12, ["At night, it reads the heat of the land, and the stars.",
                "And a careful judge, the arbiter,",
                "listens to every sense, and decides whom to trust."]),
    ("s6", 11, ["Now, it is your turn.",
                "Thirty missions. Real code. Real tests.",
                "Step by step, you will build these ideas yourself."]),
    ("s7", 8, ["Welcome to NAVERA Academy.",
               "Your journey begins now."]),
]
LEAD, TAIL, PAUSE = 1.0, 1.4, 0.55        # seconds before the first phrase, after the last, between phrases


def synth(voice, text, length_scale):
    from piper import SynthesisConfig
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=length_scale, noise_scale=0.6, noise_w_scale=0.7))
    with wave.open(path) as w:
        rate = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    os.remove(path)
    return x, rate


def to_rate(x, rate, out_rate, pitch_semitones=0.0):
    """Resample to out_rate; a negative pitch shift plays the voice lower (and a little slower)."""
    factor = 2 ** (-pitch_semitones / 12)            # >1 for a lower voice: more samples
    n_out = int(len(x) * out_rate / rate * factor)
    return np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x)


def warm(x):
    # low shelf (+ ~3 dB below ~250 Hz) and a soft room: a few short echoes
    a = 2 * np.pi * 250 / SR
    lp = np.empty_like(x); acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc); lp[i] = acc
    y = x + 0.45 * lp
    room = np.zeros_like(y)
    for d, g in [(0.023, .30), (0.037, .22), (0.051, .16), (0.083, .10)]:
        k = int(d * SR); room[k:] += g * y[:-k]
    y = y + 0.5 * room
    return y / (np.abs(y).max() + 1e-9) * 0.8


def plan(a):
    from piper import PiperVoice
    voice = PiperVoice.load(os.path.join(STATE, "voices", a.voice + ".onnx"))
    pieces, starts, t = [], {}, 0.0
    for sid, min_s, phrases in SCENES:
        starts[sid] = round(t, 2)
        clip = [np.zeros(int(LEAD * SR))]
        for k, ph in enumerate(phrases):
            x, rate = synth(voice, ph, a.length_scale)
            clip.append(to_rate(x, rate, SR, a.pitch))
            if k < len(phrases) - 1:
                clip.append(np.zeros(int(PAUSE * SR)))
        clip = np.concatenate(clip)
        dur = max(min_s, len(clip) / SR + TAIL)
        pieces.append((t, clip))
        print(f"{sid}: starts {t:5.1f}s  narration {len(clip) / SR - LEAD:4.1f}s  scene {dur:4.1f}s")
        t += dur
    total = round(t + 1.0, 1)
    track = np.zeros(int(total * SR))
    for t0, clip in pieces:
        i = int(t0 * SR); track[i:i + len(clip)] += clip
    track = warm(track)
    with wave.open(os.path.join(STATE, f"intro-voice-{a.voice}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((track * 32767).astype(np.int16).tobytes())
    with open(os.path.join(MEDIA, "intro-timing.json"), "w") as f:
        json.dump({"scenes": starts, "total": total}, f, indent=1)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_intro_music.py"),
                    "--seconds", str(total), "--out", os.path.join(STATE, "intro-music.wav")], check=True)
    print(f"total {total} s → media/intro-timing.json")


def record(a):
    from playwright.sync_api import sync_playwright
    total = json.load(open(os.path.join(MEDIA, "intro-timing.json")))["total"]
    with tempfile.TemporaryDirectory() as tmp:
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=tmp,
                                record_video_size={"width": 1280, "height": 720})
            pg = ctx.new_page()
            pg.goto(f"http://localhost:{a.port}/static/intro.html?rec")
            time.sleep(total + 1.5)
            ctx.close(); b.close()
        vid = [f for f in os.listdir(tmp) if f.endswith(".webm")][0]
        shutil.copy(os.path.join(tmp, vid), os.path.join(MEDIA, "navera-intro-silent.webm"))
    print("recorded media/navera-intro-silent.webm", total, "s")


def mux(a):
    import imageio_ffmpeg
    with wave.open(os.path.join(STATE, f"intro-voice-{a.voice}.wav")) as w:
        voice = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    with wave.open(os.path.join(STATE, "intro-music.wav")) as w:
        music = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    n = max(len(voice), len(music))
    voice = np.pad(voice, (0, n - len(voice))); music = np.pad(music, (0, n - len(music)))
    k = int(0.3 * SR)
    env = np.convolve(np.abs(voice), np.ones(k) / k, mode="same")
    speaking = np.clip(env / (env.max() * 0.12 + 1e-9), 0, 1)
    mix = voice + music * a.music_level * (1 - 0.65 * speaking)
    mix = mix * (30000 / max(1.0, np.abs(mix).max()))
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "mix.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(mix.astype(np.int16).tobytes())
        out_tmp = os.path.join(tmp, "out.webm")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", os.path.join(MEDIA, "navera-intro-silent.webm"),
                        "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "libopus", "-b:a", "112k", "-shortest", out_tmp], check=True)
        shutil.move(out_tmp, a.out)
    print("wrote", a.out, os.path.getsize(a.out) // 1024, "KB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["plan", "record", "mux", "all"])
    ap.add_argument("--voice", default="en_US-norman-medium")
    ap.add_argument("--length-scale", type=float, default=1.2, help=">1 = slower speech")
    ap.add_argument("--pitch", type=float, default=-1.5, help="semitones (negative = deeper)")
    ap.add_argument("--music-level", type=float, default=0.30)
    ap.add_argument("--port", type=int, default=8300)
    ap.add_argument("--out", default=os.path.join(MEDIA, "navera-intro.webm"))
    a = ap.parse_args()
    if a.step in ("plan", "all"):
        plan(a)
    if a.step in ("record", "all"):
        record(a)
    if a.step in ("mux", "all"):
        mux(a)


if __name__ == "__main__":
    main()
