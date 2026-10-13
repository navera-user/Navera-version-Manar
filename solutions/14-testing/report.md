# Mission 14 — report

## Bugs pinned

The stack's suite ran 89 tests in about 11 s; the ROS smoke test alone takes about 10 s because it starts
two real nodes. When I made is_finite_latlon accept (0, 0), only one test failed,
test_null_island_and_bad_values_are_refused. The judge and the trip node use the function but their tests
never send (0, 0). My parametrized test now pins every rule with 13 cases, and my gate test pins the exact
150 m limit and the negative time.

## Mutants

My first version of the example tests killed 4 of the 7 training mutants; at the end 6 of 7. Mutant 3 is
equivalent: the range test still refuses a NaN or infinite longitude. My three mutants refuse the poles
(`<` instead of `<=` for the latitude), remove the wrap of offset and remove the error for opposite points;
the stack's suite has no test there. My TODO 2 and TODO 3 tests (a latitude of exactly 90, a move across the
date line, pytest.raises for opposite points) already kill all three.

## Properties and the launch test

On the whole Earth, hypothesis found lat0 = 89.55°, n = 49 751 m: the result is past the North Pole. I
restricted the start to ±80°. The cos(p1)² mutant of haversine passes my meridian and equator examples but
fails symmetry at once. The launch test starts the real judge and checks over ROS that a 5 km jump is
refused, that only one position is published, and that a NaN fix gives NO_FIX: wiring, QoS and timers that
no unit test touches.
