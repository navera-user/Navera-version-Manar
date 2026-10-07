# Lab 19 — report: timing a live camera

Name: Teacher solution

## Frame timing

The 60 s grab log has 1713 frames at 28.55 fps on average. The median period is 34.73 ms, which
is the nominal 1/28.8 s. The jitter (standard deviation of the intervals) is 8.23 ms and the largest
gap is 347.3 ms; the gap test counts about 15 dropped frames. The jitter is large only because of
the outliers: the 0.35 s stall and the six single drops (about 69 ms each) dominate the standard
deviation, while the histogram shows that almost all intervals are within a few milliseconds of
34.7 ms. A robust measure (percentiles, median absolute deviation) describes the normal scatter
better; the standard deviation describes the risk.

With GStreamer and no work, I measured {GST_FPS} fps, very close to the 28.8 fps of the source.
With 50 ms of simulated processing per frame the rate fell to about {GST50_FPS} fps and
{GST50_LOST} source frames were never grabbed: the appsink (drop=true, max-buffers=1) threw them
away and always gave me the newest frame. My own frame_stats() saw no "dropped" frames in that
run, because the median interval itself became about 51 ms: the gap test needs the nominal period.

## Camera delay

The simulated bench saw all 20 flashes. The median delay is 140.8 ms (0.1408 s), the smallest
124.9 ms and the largest 157.8 ms. The spread (about 33 ms) is one frame period (34.7 ms): the
flash appears at a random moment between two exposures, so the waiting time is uniform between 0
and T, with mean T/2 = 17 ms and standard deviation T/sqrt(12) = 10 ms (measured 9.0 ms). The
median therefore includes the screen's own delay and half a frame period of waiting; the
smallest value (124.9 ms) is the best estimate of screen + camera. For the real Insta360 NAVERA
uses 0.138 s, measured with the same method, so the real exposure-to-grab delay is at most that.

## Attitude at the exposure

663 frames, 12 unusable: their exposure falls in the 0.8 s IMU dropout, more than 0.2 s from
any sample, so attitude_at() returns None like NAVERA's History.at().
latest_at_grab: median 2.142 deg, max 3.861 deg, median ground error 5.61 m at 150 m.
nearest_at_exposure: median 0.052 deg, max 1.060 deg, 0.14 m.
slerp_at_exposure: median 0.012 deg, max 0.407 deg, 0.03 m.
The latest-sample method is worst during the roll-in and roll-out (4-5.5 s and 15-16.5 s),
where the roll rate is highest: error = rate x 0.138 s. The nearest sample is at most 10 ms
away, so its error is at most rate x 10 ms. Slerp is close to the IMU noise, except at the
edges of the dropout, where it must hold the last value for up to 0.2 s. My attitude_at()
agreed with NAVERA's at every exposure (max difference below 1e-5 deg, same 12 unusable).

## Recommendation

1. Always stamp frames at the exposure (grab - latency) and interpolate the attitude with
   slerp: the naive "latest attitude" costs about 5.6 m median and 10 m worst at 150 m.
2. Re-measure the delay with camera_latency.py for every new camera, USB port or resolution,
   and report the smallest value as well as the median.
3. Keep the IMU at 50 Hz or more and treat a silence longer than 0.2 s as "no attitude"
   (frame unusable) rather than guessing.
4. Offer day vision only the newest frame (BUFFERSIZE 1, appsink drop=true) and decode only
   that one: a queue of old frames would show where the drone was, not where it is.
