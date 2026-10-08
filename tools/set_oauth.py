#!/usr/bin/env python3
"""Save the Google / GitHub sign-in codes into state/oauth.json (asked on the keyboard, secrets hidden).

    python3 tools/set_oauth.py google      # or: github
The academy reads the file at each sign-in: no restart needed.
"""
import getpass, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "state", "oauth.json")
BASE = "https://navera-academy.tail27d06f.ts.net"
provider = (sys.argv[1:] or [""])[0].lower()
if provider not in ("google", "github"):
    sys.exit("usage: python3 tools/set_oauth.py google|github")
try:
    conf = json.load(open(P))
except (FileNotFoundError, json.JSONDecodeError):
    conf = {}
conf.setdefault("base_url", BASE)
cid = input(f"{provider} Client ID: ").strip()
sec = getpass.getpass(f"{provider} Client secret (hidden while you paste): ").strip()
if not cid or not sec:
    sys.exit("nothing saved: both codes are needed")
conf[provider] = {"client_id": cid, "client_secret": sec}
tmp = P + ".tmp"
with open(tmp, "w") as f:
    json.dump(conf, f, indent=1)
os.chmod(tmp, 0o600)
os.replace(tmp, P)
print(f"saved. {provider} sign-in is on at {conf['base_url']}")
