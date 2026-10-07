# Training flights, 21–22 September 2026 (synthetic logs)

## Sohar

310 log lines, 84 WARN and 5 ERROR lines, 6 nodes. The arbiter reported state NO_FIX 2 times.
The first NO_FIX was at 06:45:24 (Oman time), over the sea: day vision had nothing to match and the
dead-reckoning limit of 120 s was reached. The ERROR lines come from vehicle_output_node (no position
sent) and live_camera (frame timeouts).

## Nizwa

239 log lines, 27 WARN and 1 ERROR line. NO_FIX happened 1 time, in the wadi, when the ridge's shadow
made the frames too dark. The fake GPS jump of 2412 m was refused by the arbiter.

## Conclusion

Day vision covered both GPS losses over land, but over the sea it cannot find any landmark, so the
position was only dead-reckoned and then lost. Future routes should stay over land when jamming is
expected, and the camera timeouts on the Sohar flight should be investigated before the next test.
