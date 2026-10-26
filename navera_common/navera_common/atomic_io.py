"""Power-cut-safe file writes (the drone battery can be unplugged at any moment).

A file NAVERA must find again after a restart (state, settings, discovered devices, mission
list, calibration, bundle manifests) is never rewritten in place: it is written to a
temporary file in the same directory, flushed to the disk (fsync), renamed over the old one
(atomic on ext4) and the directory entry is flushed too. After a power cut the reader sees
either the old file or the new one, whole — never a truncated or zero-filled one.

Readers stay tolerant anyway (a file can still be damaged by the card itself): see
read_json() and read_env().
"""
import json
import os
import re
from typing import Any, Dict, Optional, Union

_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def fsync_dir(directory: str) -> None:
    """Flush a directory entry (a rename into it) to the disk; never raises."""
    try:
        fd = os.open(directory or ".", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: str, data: Union[str, bytes], mode: Optional[int] = None) -> None:
    """Replace `path` by `data` atomically and durably (temp + fsync + rename + dir fsync).

    Raises OSError like open() would; the temporary file is removed on failure.
    `mode`: permission bits of the new file (default: those of the file it replaces, else 0o644).
    """
    path = os.fspath(path)
    d = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(d, f".{os.path.basename(path)}.tmp{os.getpid()}")
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mode = 0o644
    raw = data.encode() if isinstance(data, str) else data
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        try:
            view = memoryview(raw)
            while view:
                n = os.write(fd, view)
                view = view[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    fsync_dir(d)


def atomic_write_json(path: str, obj: Any, mode: Optional[int] = None, **dump_kw) -> None:
    atomic_write(path, json.dumps(obj, **dump_kw), mode)


def fsync_tree(root: str) -> None:
    """fsync every file and directory under root (a bundle built in a temporary directory,
    before it is renamed into place); never raises."""
    for d, _dirs, files in os.walk(root):
        for f in files:
            try:
                fd = os.open(os.path.join(d, f), os.O_RDONLY)
            except OSError:
                continue
            try:
                os.fsync(fd)
            except OSError:
                pass
            finally:
                os.close(fd)
        fsync_dir(d)


def read_json(path: str, default: Any = None, expect: Optional[type] = dict) -> Any:
    """The JSON in `path`, or `default` when it is missing, unreadable, truncated, not JSON,
    not UTF-8 or not of type `expect` (None: any type). Never raises."""
    try:
        with open(path, "rb") as f:
            obj = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return default
    if expect is not None and not isinstance(obj, expect):
        return default
    return obj


def read_env(path: str) -> Dict[str, str]:
    """KEY=VALUE lines of an env file; bad lines (NUL bytes, invalid UTF-8, no '=', bad key)
    are skipped. Missing / unreadable file: {}. Never raises."""
    out: Dict[str, str] = {}
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return out
    for line in raw.split(b"\n"):
        if b"\x00" in line:
            continue
        try:
            s = line.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if _ENV_KEY.fullmatch(k.strip()):
            out[k.strip()] = unquote_env(v)
    return out


def unquote_env(v: str) -> str:
    """A value as systemd's EnvironmentFile reads it: "double" (\\ and \" escapes) or 'single' quotes
    removed; anything else as written."""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return re.sub(r'\\(["\\])', r"\1", v[1:-1])
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    return v


def env_file_damaged(path: str) -> Optional[str]:
    """Why an env file (KEY=VALUE lines, comments) looks damaged — NUL bytes, invalid UTF-8,
    a line that is not a comment nor KEY=VALUE, no final newline (cut while written) — or
    None when it is fine or absent."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        return f"unreadable ({e.strerror})"
    if not raw:
        return None
    if b"\x00" in raw:
        return "NUL bytes (power cut while written)"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "not UTF-8 text"
    if not text.endswith("\n"):
        return "last line cut (no final newline)"
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s or not _ENV_KEY.fullmatch(s.split("=", 1)[0].strip()):
            return f"line {i} is not KEY=VALUE"
    return None


def quarantine_damaged_env(path: str, log=print) -> bool:
    """A damaged env file is renamed to <path>.damaged (kept for analysis) so the units start
    without it (their EnvironmentFile=- lines skip a missing file). True if it was moved."""
    why = env_file_damaged(path)
    if why is None:
        return False
    try:
        os.replace(path, path + ".damaged")
        fsync_dir(os.path.dirname(os.path.abspath(path)))
    except OSError as e:
        log(f"{path}: damaged ({why}) and could not be moved aside: {e}")
        return False
    log(f"{path}: damaged ({why}): moved to {path}.damaged, NAVERA starts without it")
    return True


def main(argv=None) -> int:
    """python3 -m navera_common.atomic_io --check-env FILE...  (boot: navera-discover)."""
    import argparse
    ap = argparse.ArgumentParser(description="Move damaged NAVERA env files aside before the units read them.")
    ap.add_argument("--check-env", nargs="+", default=[], metavar="FILE")
    a = ap.parse_args(argv)
    for p in a.check_env:
        quarantine_damaged_env(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
