# Memo — what NAVERA Lite's GNSS part refuses, and what it cannot see

## What the wire did to the drive

My is_valid refused 7 of the 6414 lines of the drive log: a GGA with one changed digit, a GGA cut after 31
characters, an RMC without its checksum, a line of garbage, two sentences glued together when a line ending
was lost, a GSV with a non-ASCII byte and a GSA whose VDOP had a flipped character. Two damaged GGA lines
passed the checksum because two characters were swapped. The one at 05:17:31 had 74 minutes of latitude,
so dm_to_deg refused it. I forged a line the same way: swapping the first two digits of the latitude moved
the fix 2001.5 km north and every check still passed.

## What the sky did to σ

The geometry was worst in the narrow streets at the end of the drive: only 4 satellites, HDOP 18.8, so my
stack stated σ = 37.6 m and showed DEGRADED. Over the 1069 seconds I count 976 FIX, 30 DEGRADED and 63
NO_FIX. The NO_FIX seconds are the cold start and the underpass (quality 0), 5 seconds of the receiver's own
dead reckoning (quality 6), 3 seconds whose GGA line was damaged and the 74-minute line.

## What gnss.py cannot see

At 05:24:21 a swapped digit in the minutes moved the fix by 665 m. The line was valid, the minutes were
below 60, the quality was 1 and the HDOP 0.77, so gnss.py stated σ = 1.5 m: it looked like a very good fix.
σ only describes the noise of a healthy receiver, not damage. The jump gate of the judge refuses it, since
665 m in one second is more than 100 m/s × 1 s + 50 m. A slow drag below the gate, or a spoofer who sends
perfect lines, would get through both: that needs an independent source, the cross-check of mission 30.
