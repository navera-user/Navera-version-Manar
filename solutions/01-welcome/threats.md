# Threat analysis — a survey drone on a coast

## Outage

Near tall buildings or cliffs the receiver sees fewer satellites and may have no fix at all. With GPS alone the autopilot would land or hover. NAVERA keeps the drone on track with day vision against the map, but vision is only DEGRADED today.

## Jamming

A jammer drowns the weak GPS signal and the receiver reports no fix, so at least it knows. The autopilot alone would trigger a failsafe. NAVERA switches to vision or the stars; their accuracy is lower than GPS.

## Spoofing

A spoofer sends consistent fake signals; in my lab the receiver found the fake point 4472 m away with a mismatch of 0. The autopilot would follow it. NAVERA's jump gate refused a 300 m jump for only 2 fixes and a slow drag 0 times, so it needs vision to compare.

## Meaconing

Real signals are recorded and replayed later, so the receiver computes the replayer's position and a wrong time. The autopilot cannot tell. NAVERA can compare with vision, but only when vision has a match.
