#!/usr/bin/env python3
"""NAVERA Academy — account tool for the installer (run as the service user, with the service's environment).

    python3 manage.py teacher-password     # creates the "teacher" account or gives it a NEW password;
                                           # the password is printed ONCE and stored only as a hash
    python3 manage.py check                # prints the accounts (no hashes)

Local accounts only: there is no outside sign-in service. The teacher creates the students from /teacher.
"""
import json
import os
import secrets
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _users_path():
    return os.path.join(config.STATE, "users.json")


def load():
    try:
        with open(_users_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(u):
    os.makedirs(config.STATE, exist_ok=True)
    tmp = _users_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(u, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, _users_path())


def teacher_password():
    pw = "".join(secrets.choice(ALPHABET) for _ in range(14))
    u = load()
    rec = u.get("teacher") or {"index": 0, "display": "Teacher", "created": time.strftime("%Y-%m-%d %H:%M")}
    # "admin" = the box's one teacher: creates students and classes; support False = no first-start sticker page
    rec.update(role="admin", support=False, status="active", pw=generate_password_hash(pw))
    u["teacher"] = rec
    save(u)
    old = os.path.join(config.STATE, "teacher_password.txt")
    if os.path.exists(old):                   # never keep a clear-text copy on the box
        os.unlink(old)
    return pw


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "teacher-password":
        pw = teacher_password()
        print(pw)
    elif cmd == "check":
        for k, v in sorted(load().items()):
            print(k, v.get("role"), v.get("status", "active"), "password set" if v.get("pw") else "NO PASSWORD")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
