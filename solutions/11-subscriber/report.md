# Lab 11 — analysis

## Noise

Without noise the Tracker measured 715 m for a true 717 m (the chord cuts the corner) and speeds of
5.99 m/s. With σ = 3 m the summed distance was 1501 m, a ratio of 2.09: every noisy step is longer
on average than the true 3 m step. The instantaneous speed had a mean of 12.56 m/s and a standard
deviation of 6.13 m/s, while √2·σ/dt predicts 8.5 m/s; the formula assumes noise much smaller than
the step, which is false here, so the result is biased like a Rayleigh distribution. The window
speed had a mean of 5.99 m/s and a standard deviation of 1.00 m/s, close to √2·3/4.5 = 0.94 m/s.

## Executors

Single-threaded: 55 ticks of 80 and a maximum gap of 313 ms, because the 10 Hz timer waits while the
0.3 s fix callback runs. The utilisation of the thread is ρ = 0.3 / 0.5 = 0.6. Multi-threaded with
two groups: 80 ticks and a maximum gap of 109 ms. With both callbacks in the same mutually exclusive
group, the multi-threaded executor behaved like the single-threaded one again: the group forbids the
two callbacks to run at the same time, whatever the number of threads.

## NAVERA

When I stopped the player, the listener printed NO_FIX with "GPS: stale" and GPS silent for 3.13 s,
then 3.05 s and 3.18 s in two more runs. The arbiter declares the GNSS stale when its age reaches
gps_timeout_s = 3.0 s, and it checks at each 5 Hz tick, so the detection comes between 3.0 and about
3.2 s after the last fix. A subscription alone is never called when nothing arrives, so only the timer
can notice the silence.
