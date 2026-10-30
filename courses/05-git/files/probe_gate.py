"""probe_gate.py — lesson 1's table (8 fixes), run through the jump gate of the commit checked out NOW.

    cd ~/lessons/05-git/navera-lite-history
    python3 ../probe_gate.py

It imports navera_lite.guard from the CURRENT folder (the repository, at whatever commit is checked
out), feeds JumpGate(100 m/s, 50 m) the fixes of lesson 1 §5 (a trusted fix at (0, 0), six fixes 500 m
east, then one 900 m east, one per second: the trusted fix and the table's 7 rows, 8 fixes in all),
and prints ONE number: how many fixes it refuses.

If the code of this commit cannot be imported (a broken commit, or you are not inside the
repository), it prints why on stderr and exits with code 3: that commit cannot be tested.

You don't need to change this file. It lives OUTSIDE the repository on purpose: when git bisect
checks out an old commit, this probe stays the same.
"""
import os
import sys
import tempfile

# ---- you don't need to change anything in this file (but you can read it!) ----
sys.dont_write_bytecode = True
sys.pycache_prefix = tempfile.mkdtemp(prefix="probe-")   # never reuse a compiled file of another commit
sys.path.insert(0, os.getcwd())

FIXES = [(0, 0)] + [(500, 0)] * 6 + [(900, 0)]

try:
    from navera_lite.guard import JumpGate
except Exception as e:                                     # a syntax error, a missing file or class
    print(f"probe_gate: cannot import navera_lite.guard in {os.getcwd()}: {type(e).__name__}: {e}",
          file=sys.stderr)
    sys.exit(3)

gate = JumpGate(100.0, 50.0)
refused = 0
for t, fix in enumerate(FIXES):
    if not gate.check(float(t), fix):
        refused += 1
print(refused)
