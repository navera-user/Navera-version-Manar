"""Seals: the FIRST value a sealed check reports for one student and one mission, kept by the server where the
student cannot reach it (state/seals.json), and handed back to every later check of that mission.

Mission 33 uses it to freeze a pre-registration: the first time its check sees a complete baseline it reports
"seal": "<before sha12>:<sha256(project.json)[:12]>"; a later check that computes another value (the tag 'before'
moved, project.json rewritten) fails. A teacher resets a seal with `python3 tools/seal.py reset <student> <lesson>`;
deleting a student, or tools/try_lesson.py reinstalling a lesson, resets it too.
"""
import fcntl
import json
import os
import re

import config

PATH = os.path.join(config.STATE, "seals.json")
VALUE = re.compile(r"^[0-9A-Za-z:._-]{1,80}$")


def _locked(fn):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            with open(PATH) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        out, changed = fn(data)
        if changed:
            tmp = PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            os.replace(tmp, PATH)
        return out


def get(name, lid):
    """The stored seal of student `name` for mission `lid`, or None."""
    return _locked(lambda d: ((d.get(name) or {}).get(lid), False))


def keep_first(name, lid, value):
    """Store value unless a seal is already stored (the first one wins). Returns the stored seal."""
    if not (isinstance(value, str) and VALUE.match(value)):
        return get(name, lid)

    def fn(d):
        cur = (d.get(name) or {}).get(lid)
        if cur is not None:
            return cur, False
        d.setdefault(name, {})[lid] = value
        return value, True
    return _locked(fn)


def log(name, lid):
    """The values a check has logged for this student and mission (seal_log), oldest first."""
    return list(_locked(lambda d: ((d.get(name) or {}).get(lid + ":log") or [], False)))


def append(name, lid, value, keep=20):
    """Add one value to the student's log for this mission (distinct values, at most `keep`, the oldest kept)."""
    if not (isinstance(value, str) and VALUE.match(value)):
        return log(name, lid)

    def fn(d):
        lst = d.setdefault(name, {}).setdefault(lid + ":log", [])
        if value in lst or len(lst) >= keep:
            return list(lst), False
        lst.append(value)
        return list(lst), True
    return _locked(fn)


def reset(name, lid=None):
    """Forget the seal(s) of a student (one mission, or all). Returns what was removed."""
    def fn(d):
        if name not in d:
            return {}, False
        if lid is None:
            return d.pop(name), True
        gone = d[name].pop(lid, None)
        d[name].pop(lid + ":log", None)
        if not d[name]:
            d.pop(name)
        return ({lid: gone} if gone else {}), gone is not None
    return _locked(fn)


def all_seals():
    return _locked(lambda d: (d, False))
