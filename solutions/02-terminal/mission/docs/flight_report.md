# Training flights, 21–22 September 2026 (synthetic logs)

## Sousse

310 log lines, 84 WARN and 5 ERROR lines, 6 nodes. The arbiter reported state NO_FIX 2 times.
The first NO_FIX was at 08:45:24 (Tunisian time), over the sea: day vision had nothing to match and the
dead-reckoning limit of 120 s was reached. The ERROR lines come from output (no position sent to the
autopilot) and camera (frame timeouts).

## Range

240 log lines, 27 WARN and 2 ERROR lines. NO_FIX happened 1 time, for about 6 s, when the ridge's
shadow made the frames too dark for day vision. The fake GPS jump of 2412 m was refused by the jump gate, and GPS was
accepted again when it agreed with day vision (gap 21 m).

## Conclusion

Day vision covered the GPS losses over land, apart from a 6 s gap in the ridge's shadow, but over the sea it cannot find any landmark, so the
position was only dead-reckoned and then lost, and the autopilot used its own failsafe. Future routes
should stay over land when jamming is expected, and the camera timeouts of the Sousse flight should be
investigated before the next test.
