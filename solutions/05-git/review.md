# Code review — review_me.patch

Reviewer: Test Student
Patch author: Khalid Al Rawahi — "fix(estimator): fewer false GPS refusals; geo: use EARTH_RADIUS_M"

## What the patch does

git apply --stat shows two files with one line each: haversine_m() in
navera_common/geo.py, and gps_jump_margin_m in the estimator's parameter file.
git apply --check found no conflict with my branch. The two changes have nothing to do with
each other, so the patch mixes two concerns in one commit.

## Applied

I applied only the geo.py change with git apply --exclude on the yaml file. It replaces the
literal 6_371_000.0 by the module constant EARTH_RADIUS_M, which has the same value, so the
result does not change. py_compile passed and git diff showed exactly one line. I committed it
alone as refactor(geo).

## Rejected

I rejected the change of gps_jump_margin_m from 50.0 to 5000.0 m. The arbiter refuses a GPS fix
that is farther than max_speed_mps × elapsed + margin from the last trusted fix. With 5000 m, a
spoofer could move the position by almost 5 km in one step without being refused, so the
anti-jump and anti-spoofing gate would be practically switched off. It also breaks the rule
"one concern per commit" and the claim "fewer false refusals" comes with no measurement.

## Advice to the author

Split the patch into two commits. For the gate, first measure the false refusals (which fixes,
which speeds and times) and propose a targeted change, for example a correct max_speed for the
vehicle, with the numbers in the commit message and a test that a 2 km jump is still refused.
