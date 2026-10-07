# Lab 15 report — the synthetic Sousse drive

Name: teacher solution

## 1. Data quality

The log has 6414 lines for 1069 seconds. My is_valid() rejected 7 lines, the same 7 as pynmea2 in
NAVERA: a GGA with a flipped character (line 361, checksum mismatch), a GGA cut after 31
characters (line 901), an RMC without its checksum (line 1382), a garbage line with the checksum
`ZZ` (line 1801), a GGA and an RMC glued together (line 3122, there is a second `$` inside), a GSV
with a non-ASCII byte (line 3664) and a GSA with a flipped DOP digit (line 4083).

Two GGA lines passed the checksum but are wrong. At 051731 the latitude `3547.17098` became
`3574.17098` and at 052421 the latitude `3545.84714` became `3545.48714`. In both cases two
neighbouring digits were swapped. The checksum is an XOR of all the characters, and XOR does not
depend on the order, so a swap never changes it. The RMC of the same second still has the correct
latitude, which confirms the diagnosis.

## 2. Geometry and DOP

I recomputed PDOP, HDOP and VDOP on 1008 seconds from the GSV azimuths/elevations and the GSA list of
used satellites, with Q = (GᵀG)⁻¹. The largest difference with the receiver was 0.005, which is only
the rounding to 2 decimals. The median HDOP is 0.85 and the maximum is 5.69. HDOP is low and flat
on the open coast road (9 to 12 satellites all around the sky). It spikes in the town centre at the
end of the drive: buildings hide every satellite that is not along the street axis or near the
zenith, so only 4 to 6 satellites remain, bunched in one direction. 2.8 % of the fixes have
HDOP above 5. In the port area HDOP is also a little higher because container stacks hide the low
satellites in the south-west.

## 3. Accuracy

Against the truth, the median horizontal error is 1.45 m and the 95th percentile is 3.55 m. My
UERE estimate, sqrt(mean((e_h/HDOP)²)), is 1.87 m, close to the 2 m that gps_node assumes, and
98.3 % of the fixes are inside 2DRMS = 2 × UERE × HDOP, as theory predicts for a circular Gaussian
(about 98 %). NAVERA writes sigma = 2 m × HDOP on each axis. With UERE ≈ 1.9 m the theory gives
about 1.32 × HDOP per axis, so NAVERA's sigma is conservative by a factor of about 1.5 here
(√2 from the per-axis choice, and a little more because the true UERE is below 2 m). Of course
this log is synthetic and was generated with a 2 m UERE: it validates the method, not the real
receiver.

## 4. Outage and NAVERA's behaviour

The longest gap without an accepted fix is 33 s, from 052003 to 052036 UTC (the underpass). During
it the receiver first wrote 5 seconds of quality 6 (its own dead reckoning, with 0 satellites and
a clean-looking position), then 27 seconds of quality 0 with empty positions and HDOP 99.99.

The real gps_node published 1066 PositionEstimate messages: 1007 valid and 59 invalid (54 "no GPS fix
(qual=0)" and 5 "receiver reports a non-satellite position (qual=6) — not used"). My decision gives
1006 valid: the difference is the line at 051731, which gps_node accepts as a fix at 36.24° N (about
50 km north of the road) because pynmea2 does not check that minutes are below 60. The estimator's
gate allows 100 m/s × dt + 50 m, so about 150 m after 1 s: both the 50 km jump and the 0.67 km jump
at 052421 would be refused there, but gps_node itself publishes them as valid.

## 5. Recommendation

First, gps_node should reject impossible fields (minutes ≥ 60, latitude above 90°) before it
publishes a fix: it costs nothing and removes the 50 km error at the source. Second, it could
cross-check GGA against the RMC of the same second; the two swapped-digit lines disagree with
their RMC. A jump smaller than about 150 m would still pass every check, so the estimator's
comparison with an independent source (vision) remains necessary.
