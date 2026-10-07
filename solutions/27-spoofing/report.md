# Lab 27 report — detecting GPS spoofing

Name: example solution

## 1. The patient spoofer

The last trusted fix was at t = 19 s. patient_accept_time(2000, 15, 30, 50) gives dt = 74.77 s, so
the spoof becomes "reachable" at t = 93.77 s. My guard checks once per second, so it accepted the
spoof at the next GPS fix, t = 94 s. From then on the spoofed position is the trusted one. At
t = 120 s the true GPS returns, 2 km away from that fake trusted fix, and the gate refuses it as an
"implausible jump": the honest receiver is locked out. This is worse than the spoof itself, because
the defence now protects the attacker. The gate alone is a reachability test; it has no memory of
why a fix was refused, and its circle grows with time.

## 2. Choosing an operating point

With at most 1 % false alarms per 2-minute flight, the best rule of the grid is k = 2.5, n = 3:
P_FA = 0.004 and P_D = 0.922 for a drift of 1.5 m/s, with a mean alarm after about 30 s (offset
about 45 m). NAVERA uses k = 3, n = 5: here P_D is only 0.194 within 40 s. But NAVERA flies for hours,
not 2 minutes. One hour is 1800 vision checks: the false-alarm rate grows roughly with the number of
checks, so my rule would give about 30 times more false alarms per hour. A false alarm refuses a good
GPS, which is costly, so NAVERA accepts a slower detection for a much lower false-alarm rate.

## 3. Correlated vision errors

With independent errors, k = 3 and n = 5 never raised an alarm in 2000 honest flights (theory: about
1.7e-10 per streak). With rho = 0.9 the same rule alarmed in 0.0255 of the flights, and k = 2.5, n = 3
went from 0.004 to 0.28. The formula p^n assumes that each fix is a new, independent chance. When the
vision error stays almost the same for several fixes (the same map misalignment, the same wrong
texture), a streak of five is not five chances but nearly one. A real map-matching camera is
correlated in this way, so the persistence count must be calibrated on real flights, not on p^n.

## 4. The real arbiter

In real_drift.txt the real arbiter said GPS IN DOUBT when the GPS was {DOUBT} m off and refused it
("drifting away") at {REFUSED} m. My guard on the 4 m/s drift went IN_DOUBT at 56 m and REFUSED at
80 m. They cannot be identical: the real run drifts at 6 m/s, vision arrives once per second instead
of every 2 s, the real tolerance adds max_speed times the time gap between the vision photo and the
GPS fix, and the real timing depends on the ROS clock and message order, so each run is a little
different.

## 5. Limits

First, every statistical test needs an independent source with a stated, honest sigma. With vision
of unknown accuracy only the kinematic gate remains, and a patient or slow spoofer is not caught.
Second, over the sea near Masirah or over uniform sand in Wahiba Sands, vision has no landmark, so
there is no independent source at all. Third, a spoofer who knows the threshold can stay under about
3 sigma (45 m here) and is never detected: the test bounds the error, it does not remove it. Fourth,
correlated vision errors make false alarms much more frequent than the formula says, and a vision
sigma that is too small would refuse a good GPS. One protection I would add is a check of the GPS
velocity against the IMU accelerations: it needs a calibrated IMU and a test campaign in the
simulator with drift and jump attacks to measure P_FA and P_D.
