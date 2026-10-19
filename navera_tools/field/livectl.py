#!/usr/bin/env python3
"""Change the field server's settings while a test runs (live_params.json, re-read by the server each second).

    python3 -m navera_tools.field.livectl list                        # the knobs, their ranges, what they do
    python3 -m navera_tools.field.livectl show                        # the file and what the server applied
    python3 -m navera_tools.field.livectl set allsky.DETECT_K_SIGMA=5 server.MIN_STARS=8 [--by NAME]
    python3 -m navera_tools.field.livectl set field.f_scale_reset=1   # an action: done once per set
    python3 -m navera_tools.field.livectl reset [KEY ...]             # back to the values at start (all if no KEY)

Only the knobs in server.LIVE_PARAMS, each within its range, are accepted (here and again by the server: a
refused key changes nothing). The file is written atomically (temporary file + rename), then the server's
/api/state is read ~2 s later to show what it applied or refused. Every change is a 'live_param' event in the
test's events.jsonl. --url / --key: the server (default: the service's plain port 8444, else the LAN port 8445).
"""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field.server import LIVE_PARAMS, LIVE_PARAMS_FILE, check_live_param  # noqa: E402

FIELD_DIR = os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field"))
URLS = ("http://127.0.0.1:8444", "https://127.0.0.1:8445")


def read_file(path):
    try:
        with open(path) as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_file(path, d):
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def server_state(urls, key):
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    for url in urls:
        req = urllib.request.Request(url.rstrip("/") + "/api/state", headers={"Cookie": f"navera_k={key}"})
        try:
            with urllib.request.urlopen(req, timeout=5, context=ctx if url.startswith("https") else None) as r:
                return url, json.loads(r.read())
        except Exception:
            continue
    return None, None


def parse_sets(items):
    out, bad = {}, {}
    for it in items:
        k, sep, v = it.partition("=")
        if not sep:
            bad[it] = "expected KEY=VALUE"
            continue
        try:
            val = json.loads(v)
        except ValueError:
            val = v
        if LIVE_PARAMS.get(k, ("",))[0] == "action":
            val = round(time.time(), 3)                 # a new value each time: the server acts once per set
        elif LIVE_PARAMS.get(k, ("",))[0] == "ftuple" and isinstance(val, str):
            val = [float(x) for x in val.strip("()[]").split(",") if x.strip()]
        conv, why = check_live_param(k, val)
        if why:
            bad[k] = why
        else:
            out[k] = list(conv) if isinstance(conv, tuple) else (val if LIVE_PARAMS[k][0] == "action" else conv)
    return out, bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("list", "show", "set", "reset"))
    ap.add_argument("items", nargs="*")
    ap.add_argument("--by", default=os.environ.get("USER", "livectl"))
    ap.add_argument("--dir", default=FIELD_DIR)
    ap.add_argument("--url", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--wait", type=float, default=2.5)
    a = ap.parse_args(argv)
    path = os.path.join(a.dir, LIVE_PARAMS_FILE)
    if a.cmd == "list":
        for k, (kind, lo, hi, what) in LIVE_PARAMS.items():
            rng = "" if kind == "action" else f"[{lo}, {hi}]"
            print(f"{k:32s} {kind:6s} {rng:18s} {what}")
        return 0
    cur = read_file(path)
    if a.cmd == "set":
        new, bad = parse_sets(a.items)
        if bad:
            print("refused (nothing written):", json.dumps(bad))
            return 2
        cur.update(new)
        cur["_by"] = a.by
        write_file(path, cur)
        print("written:", json.dumps(new))
    elif a.cmd == "reset":
        keys = a.items or [k for k in cur if not k.startswith("_")]
        for k in keys:
            cur.pop(k, None)
        cur["_by"] = a.by
        write_file(path, cur)
        print("reset:", ", ".join(keys) or "(nothing set)")
    else:
        print("file:", json.dumps(cur))
    key = a.key
    if not key:
        try:
            key = open(os.path.join(a.dir, "access_key.txt")).read().strip()
        except OSError:
            key = ""
    if a.cmd != "show":
        time.sleep(a.wait)
    url, st = server_state([a.url] if a.url else URLS, key)
    if st is None:
        print("server: not answering (the file is in place; a running server applies it within a second)")
        return 0 if a.cmd == "show" else 1
    lp = st.get("live_params") or {}
    print(f"server ({url}): active {json.dumps(lp.get('active'))}; refused {json.dumps(lp.get('refused'))}"
          + (f"; error {lp.get('error')}" if lp.get("error") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
