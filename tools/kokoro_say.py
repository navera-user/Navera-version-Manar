#!/usr/bin/env python3
"""Speak phrases with Kokoro (natural offline TTS). Runs in its own package folder (state/tts-lib,
numpy 2) so the shared Python stays on numpy 1.26 for NAVERA:

    PYTHONPATH=state/tts-lib python3 -s tools/kokoro_say.py in.json out_dir
in.json: {"voice": "am_michael", "speed": 0.95, "phrases": ["…", …]} → out_dir/000.wav, 001.wav, …
"""
import json, os, sys
import soundfile as sf
from kokoro_onnx import Kokoro
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
job = json.load(open(sys.argv[1])); out = sys.argv[2]
k = Kokoro(os.path.join(ROOT, "state/kokoro/kokoro-v1.0.onnx"), os.path.join(ROOT, "state/kokoro/voices-v1.0.bin"))
lang = "en-gb" if job["voice"].startswith("b") else "en-us"
for i, ph in enumerate(job["phrases"]):
    a, sr = k.create(ph, voice=job["voice"], speed=job.get("speed", 1.0), lang=lang)
    sf.write(os.path.join(out, f"{i:03d}.wav"), a, sr, subtype="PCM_16")
