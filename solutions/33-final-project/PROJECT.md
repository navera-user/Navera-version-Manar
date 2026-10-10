# My NAVERA project: refuse GPS fixes computed from fewer than 4 satellites

Name: Example Student          Branch: project/min-satellites          Date: 2026-10-07

## Proposal

**Problem:** gps_node (gps_pkg/gps_pkg/nodes/gps_node.py, `_publish_fix`) accepts every GGA sentence
whose fix quality is 1, 2, 4 or 5. With only 3 satellites a receiver cannot solve a 3-D position; it
extrapolates or assumes an altitude, and its position can be tens of metres wrong while it still
reports a fix. NAVERA passes it to the arbiter and to the autopilot as a normal GPS fix. This happens
near buildings and under roofs, for example in the narrow streets of an old town.

**Hypothesis:** Refusing GGA fixes from fewer than 4 satellites lowers the p95 horizontal error of
the GPS fixes NAVERA accepts, at a cost in GPS availability of less than 10 percentage points.

**Metric:** primary: p95 horizontal error of the accepted fixes (m, lower is better) on
nmea_bench.txt (1800 epochs, 1 Hz). Guard-rail: availability = accepted epochs / all epochs
(higher is better).

**Acceptance criterion:** accept if the 95 % CI of the p95 difference (after - before) is entirely
below 0 m AND the 95 % CI of the availability difference stays above -0.10. Moving-block bootstrap
over epochs, blocks of 60 s, 2000 resamples, seed 30, the same resamples for both rules.

## Change

One change in gps_node.py: a pure function fix_problem(gps_qual, has_pos, num_sats) returns the reason
a GGA sentence is not a usable fix, or an empty string. It keeps the two existing reasons (no fix,
non-satellite position) and adds "only N satellites (a 3-D fix needs 4) — not used" when the
satellite count is known and below MIN_SATELLITES = 4. _publish_fix() reads the satellite count before
the decision and publishes the invalid estimate with that reason. One commit:
"gps: refuse GGA fixes computed from fewer than 4 satellites".

## Test

New file gps_pkg/test/test_gga_validation.py, 5 tests with real GGA sentences (correct checksums): a
normal fix is accepted; quality 0 and quality 6 are refused with the same reasons as before (old
behaviour kept); the boundary 3 satellites refused / 4 accepted; an empty satellite field is not
judged; a missing position is refused. On the base code it fails (ImportError: fix_problem does not
exist); on my branch it passes. Command: python3 -m pytest -q gps_pkg/test — result "9 passed"
(my 5 tests and the 4 existing ones of gps_pkg).

## Measurement

`python3 measure_project.py` on /data/academy/33-final-project/nmea_bench.txt: 1800 s of a simulated
receiver standing still at a point in Sousse, Tunisia (truth known), 1800 epochs, 1780 with a valid
checksum. 95 % CIs: moving-block bootstrap, block 60 s, 2000 resamples, seed 30.

| | Before (quality only) | After (at least 4 satellites) | Difference (after - before) |
|---|---|---|---|
| p95 error (m) | 43.33 [5.76, 71.88] | 5.26 [4.57, 6.24] | -38.07 [-66.59, -0.72] |
| availability | 96.4 % [92.4, 99.0] | 89.1 % [81.9, 94.7] | -7.3 points [-13.9, -2.0] |
| CEP50 (m) | 2.28 | 2.13 | |
| max (m) | 146.7 | 24.1 | |

With an iid bootstrap (block length 1) the CIs would be much narrower: p95 difference [-47.7, -29.6] m,
availability difference [-8.6, -6.2] points — and the criterion would say "accept".

## Result

Decision: inconclusive. The p95 error clearly improves (the whole CI is below 0, the worst accepted
error falls from 147 m to 24 m), but the availability CI goes down to -13.9 points, beyond the 10
points we accepted in advance. The point estimate (-7.3 points) is within budget; the data cannot
prove it. The cause is that the file contains only four 3-satellite episodes: the honest (block)
bootstrap sees about four independent events, not 135 independent seconds.

## Limits

The data is synthetic: in this file 3 satellites always means a large error, which real receivers do
not guarantee (3 satellites with a known altitude can still be useful). One file, one receiver standing
still, four degraded episodes: more recorded hours (real receiver, real streets) are needed to narrow
the availability CI. Not tested with the real u-blox receiver nor in flight; the effect of the extra
GPS gaps on the arbiter (vision takes over, or NO FIX) should be checked in the mission simulator, and
the threshold discussed with the team.
