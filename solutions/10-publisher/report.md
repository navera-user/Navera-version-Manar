# Memo — the fake GNSS receiver (mission 10)

To: the NAVERA Lite team.

## 1. What the receiver publishes, and how often

The node fake_gps publishes sensor_msgs/NavSatFix on navera_lite/fix/gps, RELIABLE. Each fix is stamped with
the instant it was computed, has frame gps, status FIX, and states its accuracy honestly: σ² on east and north,
(2σ)² on up, type APPROXIMATED; when no σ is stated it sends nine zeros and type UNKNOWN. With `ros2 topic hz`
I measured 1.000 Hz with a standard deviation of 0.0004 s between messages.

## 2. Why it integrates with the real dt

On the busy computer of Step 3 a receiver that adds a nominal 0.5 s per tick lost the busy second: after
6 s it was 12.48 m from the truth, and a listener computed speeds up to 14.3 m/s for a boat at 12 m/s. My
receiver multiplies the speed by the real time since the previous tick, so in Step 7 every pair of fixes gave
10.00 m/s even with random delays and a 1.3 s stall.

## 3. Two things arbiter v0 believed that it should not

First, with sigma_m 0.0 my receiver states no accuracy, but v0 read the nine zeros as σ 0.0 m and showed FIX:
it never checks the covariance type. Second, with a stamp 30 s in the future v0 computed a negative age and kept
the fix fresh for about 33 s after I stopped the receiver. A better judge must refuse an unknown accuracy as a
FIX and refuse stamps from the future; mission 12 builds it.
