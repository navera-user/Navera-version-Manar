"""my_mutants.py — YOUR mutants: the saboteur's turn (mission 14, TODO 6, lab Step 5).

Find THREE small changes of navera_lite/geo.py or navera_lite/guard.py that make the stack wrong but that
the stack's OWN suite (navera_lite/tests) does not notice. Then write tests that kill them (TODO 6b, at the
end of test_geo_examples.py).

Each mutant is a tuple (file, old, new): `old` is copied EXACTLY from the file (spaces included) and must
appear there once; `new` replaces it.          python3 hunt.py mine

Example, which does NOT count — the stack's suite kills it (test_geo.py tests a latitude of 91):
    ("geo.py", "abs(la) <= 90.0", "abs(la) <= 95.0")
"""

MUTANTS = [
    # TODO 6: three tuples ("geo.py" or "guard.py", "old text", "new text")
]
