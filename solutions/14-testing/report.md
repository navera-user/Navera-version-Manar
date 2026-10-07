# Lab 14 — analysis

## NAVERA's tests

`navera_tools/run_tests.sh` ran 359 unit tests in about 75 seconds and printed ALL TESTS PASSED (in
one run a GPU test failed while the machine was busy and passed when I ran its file alone). When I
replaced the last line of is_finite_latlon by `return True`, 2 tests of test_geo.py failed:
test_is_finite_latlon[0.0-0.0-False] and test_invalid_start_is_refused. The second one tests
dead_reckon, which calls is_finite_latlon to refuse a bad start, so one broken helper broke two
behaviours.

## Mutants

My first version had only the two example tests plus three tests of haversine and meters_to_degrees
along a meridian. The checker reported that "ignores the longitude", "swaps north and east" and
"divides by zero" survived. I added a test of one degree of longitude on the equator and at 60°, a
test that a move north keeps the longitude, and the parametrized dt test. The asymmetric haversine
(cos(lat1) squared) is the mutant that a symmetry property catches immediately, because all my
first examples had two points on the same latitude.

## Properties

With the whole Earth as domain, hypothesis printed "Falsifying example: lat0=86.6134765190408,
lon0=173.22695303808192, north=0.0, east=44488.48530754529". Near the pole 44 km east is several
degrees of longitude, so the flat helper returned a longitude above 180°, which is invalid because it
does not wrap. I restricted the property to |lat0| ≤ 80° and |lon0| ≤ 170°, the documented domain.
NAVERA's dead_reckon wraps the longitude with (lon + 540) % 360 − 180 and has a regression test for it.
