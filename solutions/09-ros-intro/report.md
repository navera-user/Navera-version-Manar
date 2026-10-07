# Lab 9 — analysis

## Discovery

My discovery port is computed from my domain (see answers.py; in the test domain 209 it is 59650;
the check also accepts the number of the student's own domain). The `ss` command showed 59650 and
the pairs 59660/59661 and 59662/59663: discovery unicast and user data ports of participants 0 and
1 (the talker and the ros2 daemon), exactly 7400 + 250·d + 10 + 2p and + 11 + 2p. The other domain
uses other ports, so its participants never heard our announcements and listed no /chatter.

## QoS

A BEST_EFFORT publisher and a RELIABLE subscriber were not matched: the subscriber asks for more
than the publisher offers, so nothing arrived and the echo printed "New publisher discovered on
topic '/qos_test', offering incompatible QoS. No messages will be received from it. Last
incompatible policy: RELIABILITY". A BEST_EFFORT subscriber received everything. For the latched
message, the late TRANSIENT_LOCAL subscriber received 'go' immediately because the publisher kept it
(depth 1), while the VOLATILE subscriber received nothing: it only gets messages published after it
matched, and none came.

## NAVERA

The arbiter subscribes to /navera/estimate/gps, day, night and cn (PositionEstimate) and to the IMU
for liveness, and publishes /navera/position and /navera/nav_status. With no source it published
state 0 (INITIALIZING) and the reason "waiting for first source message" five times per second,
and published no position at all: it never invents or repeats a position, and it keeps telling the
world its state so that silence can be noticed.
