"""One folder per test, written as it happens so a crash or a flat battery loses nothing.

    <root>/<YYYY-MM-DD_HHMM>/
        session.json   who/what/when, settings, software version, the verdict at the end
        phone.jsonl    the phone's GPS, tilt and compass, about once a second (the truth)
        frames.jsonl   one line per camera frame: stars, sky, solver result, error
        events.jsonl   steps taken, notes, marks, problems met
        frames/        the pictures (JPEG)
        report.json / report.md   written when the test ends (and again by `analyze`)
"""
import json
import os
import subprocess
import threading
import time
from typing import Optional


class FieldSession:
    def __init__(self, root: str, meta: Optional[dict] = None, now: Optional[float] = None):
        t = time.localtime(now if now is not None else time.time())
        base = time.strftime("%Y-%m-%d_%H%M", t)
        name, n = base, 1
        while os.path.exists(os.path.join(root, name)):
            n += 1
            name = f"{base}_{n}"
        self.id = name
        self.dir = os.path.join(root, name)
        os.makedirs(os.path.join(self.dir, "frames"))
        self._lock = threading.Lock()
        self._files = {}
        self._last_sync = 0.0
        self.meta = {"id": name, "started": time.time(), "ended": None, "software": _software_version(),
                     **(meta or {})}
        self._write_meta()
        self.event("start")

    def _write_meta(self):
        tmp = os.path.join(self.dir, "session.json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.meta, f, indent=1, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, os.path.join(self.dir, "session.json"))

    def update_meta(self, **kw):
        with self._lock:
            self.meta.update(kw)
            self._write_meta()

    def log(self, stream: str, record: dict):
        record = {"t": time.time(), **record}
        line = json.dumps(record, default=str, separators=(",", ":")) + "\n"
        with self._lock:
            f = self._files.get(stream)
            if f is None:
                f = self._files[stream] = open(os.path.join(self.dir, stream + ".jsonl"), "a")
            f.write(line)
            f.flush()
            if time.time() - self._last_sync > 1.0:
                for g in self._files.values():
                    os.fsync(g.fileno())
                self._last_sync = time.time()

    def event(self, kind: str, **kw):
        self.log("events", {"kind": kind, **kw})

    def save_frame(self, idx: int, jpeg: bytes) -> str:
        rel = os.path.join("frames", f"frame_{idx:06d}.jpg")
        with open(os.path.join(self.dir, rel), "wb") as f:
            f.write(jpeg)
        return rel

    def close(self):
        with self._lock:
            self.meta["ended"] = time.time()
            self._write_meta()
            for f in self._files.values():
                f.flush()
                os.fsync(f.fileno())
                f.close()
            self._files = {}


def _software_version() -> str:
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.run(["git", "-C", here, "describe", "--always", "--dirty"], capture_output=True,
                              text=True, timeout=5).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def read_jsonl(path: str) -> list:
    """Every complete line; a last line cut by a power loss is dropped."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def list_sessions(root: str) -> list:
    """Newest first: [{id, started, ended, verdict, ...}] from each folder's files."""
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root), reverse=True):
        p = os.path.join(root, name, "session.json")
        if os.path.exists(p):
            try:
                with open(p) as f:
                    out.append(json.load(f))
            except ValueError:
                continue
    return out
