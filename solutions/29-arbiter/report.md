# Lab 29 report — the arbiter

## 1. Hold-off

With no hold-off (h = 0 s) the flapping GPS made the output change source 27.1 times per
minute: every time the GPS came back it took over at once, and every time it failed the output
jumped back to day vision. With the product value h = 2 s this falls to 12.7 switches per minute,
and with h = 8 s to 1.3. The price is GPS time that is eligible but not used: 200.8 s out of
600 s with h = 2 s, and 362 s with h = 8 s. For a drone I would keep 2 s: it removes the
fast zig-zag (a GPS that flaps every 0.5 s never wins), and a 2 s delay before the better source
returns is small compared with the time scale of a mission. With a GPS this unreliable, staying
on vision is not a bad decision anyway.

## 2. Freshness

In the synthetic load model, day vision is available 78.4 % of the time with a 3 s window, with
79 dropouts in 10 minutes, and 91.1 % with 5 s, with only 19 dropouts. Each dropout is a short
NO_FIX if no other source exists, which is what made the autopilot land in the simulator. The
cost of a longer window is staleness: at 40 m/s a fix used 5 s after its photo can be 200 m
behind the drone (199.9 m measured as max age x speed). 5 s is a reasonable compromise only
because NAVERA does not use the old position as if it were current: the output carries a vision
fix to the present and grows its stated accuracy with its age.

## 3. Selection or fusion

Inverse-variance fusion of GPS (sigma 3 m) and vision (sigma 30 m) claims a sigma of 2.985 m,
only 0.5 % better than GPS alone. If the errors are correlated with rho = 0.8 (vision takes its
search prior from the GPS output), the true sigma of the same fused value is 3.213 m: worse than
GPS alone, and the filter would be over-confident. If GPS is spoofed 2000 m away the fused
position moves 1980 m with it, because the GPS weight is 0.99. So NAVERA selects: the gain is
tiny, vision accuracy is not validated yet (an unknown sigma cannot be weighted), the errors are
not independent, and a single winner is easy to check, explain and refuse.

## 4. My arbiter against the real one

My arbiter took the same decision as the real estimator_node at 11 of 11 moments, with the
same reason texts apart from the ages. The 6 source switches came in the same order; the largest
difference between a real and my switch instant was 0.15 s (day to night). It comes from the 5 Hz clock:
my ticks are at exact multiples of 0.2 s, the real timer has its own phase, and the ROS messages
take a few milliseconds. The real node also checks GPS plausibility (kinematic gate and
cross-check with vision), which my arbiter does not do; in this scenario it never triggered.

## 5. Limits

All inputs are synthetic and use one seed: the flapping model (exponential on and off times) and
the frame-gap model are my assumptions, not measurements of a real receiver or of the Jetson
under load. There is no autopilot in the loop, so I did not measure what a switch or a dropout
does to the flight. Next I would replay recorded NAVERA logs (frame instants, GPS validity) through
the same metrics, repeat with several seeds to get a spread, and test the chosen values in the
mission simulator before any field test.
