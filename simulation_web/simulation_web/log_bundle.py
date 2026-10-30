"""log_bundle.py — the dashboard's "Download logs" archive (GET /api/logs.tar.gz on the web bridge).

The client sends it to IRIS support without a shell on the box: the last 24 h of the NAVERA units'
journal (journalctl -u 'navera-*' --since -24h -o short-iso) plus the operator's settings
(/var/lib/navera/settings.env) and what the box found at boot (/var/lib/navera/discovered.env).

Never in it: a line of the env files whose text holds TOKEN, PASSWORD or KEY (any case) is dropped
(strip_secrets), and in the journal a NAME=value whose NAME holds them has its value masked
(redact_journal_line). The archive is bounded: at most max_bytes (default 50 MB); the journal is
cut to its NEWEST part to fit (the oldest lines go first, a note says how much), and an archive
that would still be larger is refused (ArchiveTooLarge), never sent truncated mid-file.

Read-only: it reads files and the journal, starts no service and writes only a temporary file.
"""
import collections
import io
import os
import re
import subprocess
import tarfile
import tempfile
import time
from typing import IO, Iterable, List, Optional, Sequence, Tuple

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
JOURNAL_CMD = ("journalctl", "-u", "navera-*", "--since", "-24h", "-o", "short-iso", "--no-pager")
JOURNAL_TIMEOUT_S = 60.0
ENV_FILES = ("/var/lib/navera/settings.env", "/var/lib/navera/discovered.env")
_SECRET = re.compile(r"TOKEN|PASSWORD|KEY", re.IGNORECASE)
_SECRET_ASSIGN = re.compile(r"(\b[A-Za-z0-9_]*(?:TOKEN|PASSWORD|KEY)[A-Za-z0-9_]*\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)",
                            re.IGNORECASE)
_HEADROOM = 64 * 1024        # tar headers and the small files, besides the journal


class ArchiveTooLarge(RuntimeError):
    """The archive would exceed its size cap."""


def strip_secrets(text: str) -> Tuple[str, int]:
    """`text` (an env file) without its lines naming a TOKEN / PASSWORD / KEY; (text, lines dropped)."""
    kept, dropped = [], 0
    for line in text.splitlines(keepends=True):
        if _SECRET.search(line):
            dropped += 1
        else:
            kept.append(line)
    return "".join(kept), dropped


def redact_journal_line(line: str) -> str:
    """A journal line with the value of any NAME=value / NAME: value whose NAME holds TOKEN, PASSWORD
    or KEY replaced by ***.
    """
    return _SECRET_ASSIGN.sub(lambda m: m.group(1) + "***", line)


def read_tail(chunks: Iterable[bytes], budget: int) -> Tuple[bytes, int]:
    """The last `budget` bytes of a byte stream, cut at a line start; (data, bytes dropped). Memory: ~budget."""
    keep: collections.deque = collections.deque()
    size = dropped = 0
    for c in chunks:
        if not c:
            continue
        keep.append(c)
        size += len(c)
        while size - len(keep[0]) >= budget:          # drop whole old chunks while the rest still fills it
            size -= len(keep[0])
            dropped += len(keep.popleft())
    data = b"".join(keep)
    if len(data) > budget:
        cut = len(data) - budget
        nl = data.find(b"\n", cut)
        cut = len(data) if nl < 0 else nl + 1
        dropped += cut
        data = data[cut:]
    return data, dropped


def journal(budget: int, cmd: Sequence[str] = JOURNAL_CMD, timeout_s: float = JOURNAL_TIMEOUT_S) -> bytes:
    """The NAVERA units' log: its newest `budget` bytes at most, secrets masked; or a note saying why none."""
    try:
        p = subprocess.Popen(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        return f"# journal not available: {e}\n".encode()
    t_end = time.monotonic() + timeout_s

    def chunks():
        while time.monotonic() < t_end:
            c = p.stdout.read(1 << 16)
            if not c:
                return
            yield c
    try:
        data, dropped = read_tail(chunks(), budget)
    finally:
        try:                                    # finished output: let journalctl exit by itself
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        timed_out = p.poll() is None and time.monotonic() >= t_end
        if p.poll() is None:
            p.kill()
        err = p.stderr.read(4096).decode("utf-8", "replace").strip() if p.stderr else ""
        p.wait()
    text = "".join(redact_journal_line(ln) for ln in data.decode("utf-8", "replace").splitlines(keepends=True))
    head = []
    if dropped:
        head.append(f"# journal cut to its newest {len(data)} bytes: {dropped} older bytes dropped (size cap)\n")
    if timed_out:
        head.append(f"# journalctl stopped after {timeout_s:.0f} s\n")
    if p.returncode not in (0, None) and not timed_out:
        head.append(f"# journalctl exit {p.returncode}: {err[:300]}\n")
    return ("".join(head) + text).encode()


def _add(tar: tarfile.TarFile, name: str, data: bytes, mtime: float) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), int(mtime), 0o644
    tar.addfile(info, io.BytesIO(data))


def build(max_bytes: int = MAX_ARCHIVE_BYTES, env_files: Sequence[str] = ENV_FILES,
          journal_cmd: Optional[Sequence[str]] = JOURNAL_CMD, out: Optional[IO[bytes]] = None) -> IO[bytes]:
    """Write the archive (tar.gz) to `out` (default: a new temporary file) and return it, rewound.

    The journal gets the space left by the other files (uncompressed, so the gzip archive is always
    smaller); ArchiveTooLarge if the result still exceeds max_bytes.
    """
    now = time.time()
    files: List[Tuple[str, bytes]] = []
    notes = [f"NAVERA logs, made {time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(now))}\n",
             "Secrets removed: env lines naming TOKEN / PASSWORD / KEY; such values masked in the journal.\n"]
    for path in env_files:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text, dropped = strip_secrets(f.read())
        except OSError as e:
            notes.append(f"{path}: not read ({e.strerror or e})\n")
            continue
        files.append((os.path.basename(path), text.encode()))
        notes.append(f"{path}: {dropped} line(s) with a secret removed\n")
    used = sum(len(d) for _, d in files) + sum(len(n) for n in notes) + _HEADROOM
    budget = max_bytes - used
    if journal_cmd is not None:
        if budget > 0:
            files.append(("journal.log", journal(budget, journal_cmd)))
        else:
            notes.append("journal: left out (no room under the size cap)\n")
    f = out if out is not None else tempfile.TemporaryFile()
    with tarfile.open(fileobj=f, mode="w:gz") as tar:
        _add(tar, "navera_logs/README.txt", "".join(notes).encode(), now)
        for name, data in files:
            _add(tar, f"navera_logs/{name}", data, now)
    size = f.tell()
    if size > max_bytes:
        f.close()
        raise ArchiveTooLarge(f"log archive {size} bytes > {max_bytes}")
    f.seek(0)
    return f
