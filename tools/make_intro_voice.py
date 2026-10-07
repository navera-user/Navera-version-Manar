#!/usr/bin/env python3
"""Add a narrator voice to the intro film (offline: Piper TTS + the ffmpeg bundled with imageio-ffmpeg).

    tools/make_intro_voice.py                     # default voice, writes server/static/media/navera-intro.webm
    tools/make_intro_voice.py --voice en_GB-jenny_dioco-medium --out /tmp/x.webm

Voices live in state/voices (python3 -m piper.download_voices --data-dir state/voices <name>).
The silent film is kept as media/navera-intro-silent.webm (it is re-used as the input every time).
Each line starts at its scene's time; a line longer than its window is spoken a little faster.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "server", "static", "media")

# (start s, end s, text) — the scene windows of static/intro.html
LINES = [
    (1.0, 11.6, "Every autumn, swallows cross Oman on their way to Africa. Thousands of kilometres, "
                "and not a single satellite to guide them."),
    (12.6, 23.6, "They use many senses: landmarks on the ground, the sun and the stars, a magnetic "
                 "compass inside them, and the feeling of their own motion. And each sense checks the others."),
    (24.6, 35.6, "Drones are different. They trust G P S, and G P S is fragile. A small transmitter can "
                 "jam it, or fake it, and the drone flies the wrong way."),
    (36.6, 48.4, "NAVERA gives machines the eyes of a bird. It turns and scales the camera picture until it "
                 "fits the satellite map, and reads its position from the map."),
    (49.6, 60.4, "At night it uses heat and the stars. And an arbiter compares every source, chooses the one "
                 "to trust, and catches a fake G P S."),
    (61.6, 71.4, "In thirty missions, you will build these ideas yourself, on NAVERA's real code, with a "
                 "terminal, a simulator, and a check after every step."),
    (72.6, 79.5, "Welcome to NAVERA Academy. Your first mission is ready."),
]


def synth(voice, text, length_scale):
    from piper import SynthesisConfig
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as w:
        voice.synthesize_wav(text, w, syn_config=SynthesisConfig(length_scale=length_scale))
    with wave.open(path) as w:
        rate = w.getframerate()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    os.remove(path)
    return audio, rate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="en_US-ryan-high")
    ap.add_argument("--out", default=os.path.join(MEDIA, "navera-intro.webm"))
    ap.add_argument("--speed", type=float, default=1.0, help="length scale: >1 slower, <1 faster")
    a = ap.parse_args()
    from piper import PiperVoice
    import imageio_ffmpeg

    silent = os.path.join(MEDIA, "navera-intro-silent.webm")
    if not os.path.exists(silent):
        shutil.copy(os.path.join(MEDIA, "navera-intro.webm"), silent)
    voice = PiperVoice.load(os.path.join(ROOT, "state", "voices", a.voice + ".onnx"))
    total_s, track, rate = 81.0, None, None
    for start, end, text in LINES:
        scale = a.speed
        audio, rate = synth(voice, text, scale)
        dur = len(audio) / rate
        if dur > end - start:                                   # too long for its scene: speak faster
            scale = a.speed * (end - start) / dur * 0.98
            audio, rate = synth(voice, text, scale)
            dur = len(audio) / rate
        if track is None:
            track = np.zeros(int(total_s * rate), dtype=np.float32)
        i = int(start * rate)
        track[i:i + len(audio)] += audio[:len(track) - i]
        print(f"{start:5.1f}s  {dur:4.1f}s / {end - start:4.1f}s window  scale {scale:.2f}  {text[:48]}…")
    track = np.clip(track, -32767, 32767).astype(np.int16)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "voice.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(track.tobytes())
        out_tmp = os.path.join(tmp, "out.webm")
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", silent, "-i", wav,
               "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "libopus", "-b:a", "96k", "-shortest", out_tmp]
        subprocess.run(cmd, check=True)
        shutil.copy(wav, os.path.join(MEDIA, "navera-intro-voice.wav"))
        shutil.move(out_tmp, a.out)
    print("wrote", a.out, os.path.getsize(a.out) // 1024, "KB")


if __name__ == "__main__":
    sys.exit(main())
