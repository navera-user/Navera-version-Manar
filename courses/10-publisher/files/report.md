# Memo — the fake GNSS receiver (mission 10)

To: the NAVERA Lite team. At least 150 words of your own, in full sentences. Replace every TODO.

## 1. What the receiver publishes, and how often

TODO: the topic, the message, what each fix states (stamp, covariance and its type), the rate and the
standard deviation of the intervals you measured with `ros2 topic hz`.

## 2. Why it integrates with the real dt

TODO: what a nominal-dt receiver did in Step 3 (its error in metres after the busy second, the largest speed
a listener computed), and what yours did in Step 7.

## 3. Two things arbiter v0 believed that it should not

TODO: from Step 9, the two verdicts of v0 that are wrong, with the reason v0 gave, and what a better judge
must check (mission 12 builds it).
