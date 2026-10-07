# My NAVERA project: refuse GPS fixes computed from fewer than 4 satellites

Name: Example Student          Branch: project/min-satellites          Date: 2026-10-07

## Idea

The GPS driver gps_node accepts every GGA sentence whose fix quality is 1, 2, 4 or 5. A receiver that
sees only 3 satellites cannot compute a 3-D position: it assumes an altitude and its position can be tens
of metres off, yet NAVERA passes it to the arbiter and to the autopilot as a normal fix. The autopilot
suffers first. The file to change is gps_pkg/gps_pkg/nodes/gps_node.py.

## Change

One change in gps_node.py: a pure function fix_problem(gps_qual, has_pos, num_sats) returns the reason a
GGA sentence is not a usable fix, or an empty string. It keeps the two existing reasons (no fix,
non-satellite position) and adds "only N satellites (a 3-D fix needs 4) — not used" when the
satellite count is known and below MIN_SATELLITES = 4. _publish_fix() reads the satellite count before
the decision and publishes the invalid estimate with that reason. One commit:
"gps: refuse GGA fixes computed from fewer than 4 satellites".

## Test

New file gps_pkg/test/test_gga_validation.py, 5 tests with real GGA sentences (correct checksums): a
normal fix is accepted; quality 0 and quality 6 are refused with the same reasons as before; 3 satellites
refused and 4 accepted; an empty satellite field is not judged; a missing position is refused. It failed
before the change (ImportError: fix_problem did not exist) and passes now. Command:
python3 -m pytest -q gps_pkg/test — result "9 passed" (my 5 tests and the 4 existing ones of gps_pkg).

## Measurement

measure_project.py plays /data/academy/30-final-project/nmea_bench.txt (600 s of a simulated receiver
standing still, truth known, 598 GGA sentences with a valid checksum) with the rule before and after.

| | Fixes accepted | Median error | p90 | Max |
|---|---|---|---|---|
| Before (quality only) | 568 (95 %) | 3.3 m | 6.7 m | 150.7 m |
| After (at least 4 satellites) | 523 (87 %) | 3.1 m | 5.5 m | 10.7 m |

## Result

The worst GPS error that NAVERA accepts drops from 151 m to 11 m on this file and the p90 from 6.7 m to
5.5 m, while the median barely changes. The price: 45 more seconds without GPS (87 % of the sentences
accepted instead of 95 %), during which NAVERA must use vision or report NO FIX.

## Limits

The data is synthetic: in this file 3 satellites always means a large error, which real receivers do not
guarantee (a good geometry with 3 satellites and a known altitude can be useful). One file, one receiver
standing still. Not tested with the real u-blox receiver nor in flight; the effect on the autopilot
(more GPS gaps) should be checked in the mission simulator, and the threshold discussed with the team.
