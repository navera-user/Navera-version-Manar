#!/usr/bin/env python3
"""seal.py — the seals the server keeps per student and mission (server/seals.py; mission 33 freezes a
pre-registration with one). A student who must start a new pre-registration asks the teacher, who resets it.

    tools/seal.py list                       every stored seal
    tools/seal.py reset <student> <lesson>   forget one (the next check stores the new value)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))
import seals  # noqa: E402

if len(sys.argv) >= 2 and sys.argv[1] == "list":
    for name, d in sorted(seals.all_seals().items()):
        for lid, v in sorted(d.items()):
            print(f"{name:20s} {lid:22s} {v}")
elif len(sys.argv) == 4 and sys.argv[1] == "reset":
    gone = seals.reset(sys.argv[2], sys.argv[3])
    print(f"reset: {gone}" if gone else "nothing stored for that student and lesson")
else:
    sys.exit(__doc__)
