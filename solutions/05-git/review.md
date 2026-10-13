# Code review — branch kenji/fewer-refusals

Reviewer: Test Student
Change: one commit by Kenji Sato, "fix: fewer false GPS refusals, tidy geo"

## Hunk 1 — README.md
Verdict: accept
Why: It only fixes the spelling of "receive" in a sentence. No code changes, nothing to measure.

## Hunk 2 — navera_lite.yaml
Verdict: reject
Why: gps_jump_margin_m goes from 50 to 500 m, so one second after the last trusted fix the gate accepts a
jump of 600 m instead of 150 m. A spoofer can move the position 600 m in one step. No measurement shows
that the false refusals come from the margin.

## Hunk 3 — navera_lite/geo.py
Verdict: accept
Why: haversine_m uses the EARTH_RADIUS_M constant instead of the same value 6371000.0 written again; the
result is unchanged (London–Paris test still 343556 m) and the tests pass.

## Hunk 4 — navera_lite/guard.py
Verdict: reject
Why: after 10 s of refusals the new fix is trusted whatever it is, so a patient spoofer only has to wait:
a fake fix 50 km away is accepted at t = 12 s. It treats the symptom (GPS locked out) without finding why
the gate does not widen any more.

## Hunk 5 — tests/test_guard.py
Verdict: reject
Why: it deletes the test that refuses a 500 m jump; the test is not flaky, it fails because of the new
500 m margin. Removing a failing test hides the problem instead of fixing it.

## Advice to the author
Split the change: one commit for the typo, one for the constant, and the gate change alone. Do not change
the margin without a measurement of real false refusals. First find why GPS stays refused after a jump
(bisect between v0.1 and main), add a test that fails, then fix the cause and keep every test.
