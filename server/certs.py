"""End-of-course certificates, digitally signed by IRIS Systems.

A certificate is a small record (number, name, programme, completion date…). The academy signs it with
IRIS's private Ed25519 key, kept in state/cert_key.pem (readable by the academy only). Anyone can check
a certificate on its public /verify/<number> page, or with the public key at /certificates/iris-key.pub:
the signature covers every field, so a changed name or date no longer verifies.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import config

KEY_FILE = os.path.join(config.STATE, "cert_key.pem")
STORE = os.path.join(config.STATE, "certificates.json")
KEY_NAME = "IRIS-ACAD-1"
PROGRAMME = "NAVERA Academy — GPS-denied navigation"
ISSUER = "IRIS Systems — Integrated Robotics and Intelligent Systems"
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"        # no 0/O, 1/I: easy to read aloud and type
_lock = threading.Lock()


def _key():
    if not os.path.exists(KEY_FILE):
        k = Ed25519PrivateKey.generate()
        pem = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
    with open(KEY_FILE, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def public_pem():
    return _key().public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def fingerprint():
    raw = _key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    h = hashlib.sha256(raw).hexdigest()
    return f"{h[:4]} {h[4:8]}"


def _payload(c):
    """Exactly the signed fields, in a fixed order."""
    keys = ("id", "name", "programme", "completed", "missions", "hours", "issuer", "key")
    d = {k: c[k] for k in keys}
    for k in ("organisation", "class"):            # signed too when present (certificates since classes)
        if c.get(k):
            d[k] = c[k]
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _load():
    try:
        with open(STORE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(d):
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STORE)


def for_user(user):
    return next((c for c in _load().values() if c["user"] == user), None)


def get(cid):
    return _load().get((cid or "").strip().upper())


def all_certs():
    return sorted(_load().values(), key=lambda c: c["issued"], reverse=True)


def issue(user, name, completed, missions, hours, extra=None):
    """One certificate per account; the printed name is fixed once signed."""
    with _lock:
        d = _load()
        old = next((c for c in d.values() if c["user"] == user and not c.get("revoked")), None)
        if old:
            return old
        while True:
            r = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            cid = f"NAV-{time.strftime('%Y')}-{r[:4]}-{r[4:]}"
            if cid not in d:
                break
        c = {"id": cid, "name": name, "programme": PROGRAMME, "completed": completed, "missions": missions,
             "hours": hours, "issuer": ISSUER, "key": KEY_NAME}
        c.update({k: v for k, v in (extra or {}).items() if k in ("organisation", "class") and v})
        c["signature"] = base64.b64encode(_key().sign(_payload(c))).decode()
        c.update(user=user, issued=time.strftime("%Y-%m-%d %H:%M"), revoked=False)
        d[cid] = c
        _save(d)
        return c


def set_revoked(cid, revoked):
    with _lock:
        d = _load()
        if cid not in d:
            return None
        d[cid]["revoked"] = bool(revoked)
        _save(d)
        return d[cid]


def check(c):
    """'valid', 'revoked' or 'invalid' (unknown number, or a record whose signature does not match)."""
    if not c:
        return "invalid"
    try:
        _key().public_key().verify(base64.b64decode(c["signature"]), _payload(c))
    except Exception:
        return "invalid"
    return "revoked" if c.get("revoked") else "valid"


def qr_svg(url):
    """The QR code as inline SVG (segno, kept with the Wi-Fi setup tools)."""
    vendor = os.path.join(config.ACADEMY, "setup", "vendor")
    if vendor not in sys.path:
        sys.path.append(vendor)
    import io
    import segno
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=4, border=0, dark="#0b1730", xmldecl=False, svgns=True)
    return buf.getvalue().decode()
