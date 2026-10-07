# Threat analysis — a coastal survey drone, Muscat to Barka

## Outage

Between tall buildings or under a bridge the receiver sees fewer satellites, the DOP grows and
multipath adds errors of tens of metres; in the worst case it reports no fix. With GNSS alone the
autopilot would hold position or start its failsafe. NAVERA's arbiter sees GPS become stale after
3 s and switches to day vision, which matches the camera image against the map; over the sea there
is nothing to match, so day vision can only dead-reckon for a limited time.

## Jamming

A jammer raises the noise far above the satellite signal (a 1 W jammer at 20 km gives about 36 dB
J/S), so the receiver loses tracking and knows it. The autopilot gets "no fix" and lands or
returns. NAVERA keeps publishing a position from vision, reported as DEGRADED, so the mission can
continue or end safely; if vision has no match the state becomes NO_FIX.

## Spoofing

A spoofer sends consistent fake signals, so the receiver computes a calm, wrong position with
normal residuals and does not raise any alarm. The autopilot would follow it. NAVERA's arbiter
refuses a GPS jump larger than v_max·Δt + margin and compares GPS with an independent source such
as vision; a slow spoof can only be caught by that cross-check, not by the jump gate.

## Meaconing

The attacker re-broadcasts real signals with a delay, so the receiver computes the position of
the re-broadcasting antenna and a wrong time. Like spoofing it looks normal to the receiver. NAVERA
must detect it the same way: the camera does not agree with the GPS position. The time error also
matters, because the star camera and the logs need the correct time.
