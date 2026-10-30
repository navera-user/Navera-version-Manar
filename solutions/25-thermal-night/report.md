# Mission 25 — Night vision: my report

## 1. The data auditor

NAVERA's night replay set is not thermal. With my ncc, each of the 30 night frames has one day frame with an NCC of
about 0.9 (median best 0.90), while the second best is only about 0.1. The night frames are the day frames made
darker: they show sharp sun shadows, which a thermal camera cannot see at night, and night frame 1 is day frame 9,
so the labels put every frame 8 frames away from its real place. Before training or testing on a dataset I would ask
how it was recorded, look for shadows, and compare it with the other sets.

## 2. Geometry and NCC

The reference square is 496 m. The first simulator camera (56.7° × 48°) needs 474 m at heading 0° and 524 m at 45°
to cover 85 % of it, so a drone limited to 400 m can never get a night fix with it. At 45° the corners of the square
stick out of the turned rectangle. NCC is perfect day vs day (100 % good) because it removes gain and offset, but at
night it is good in only 0.23 of the pairs and 0.39 with the night inverted: roads reverse, trees do not, and dawn
has no contrast at all.

## 3. The learned homography

I made pairs from 293 training places: a random square of the day reference, random offsets for the 4 corners, and
the night picture warped inside them, with the camera's noise and gain. The 8 offsets are the label, exact and free.
My network (192 600 parameters) trained in about half a minute on the GPU. With only 3 places it overfitted: the
training loss fell to 0.016 while the validation loss rose after epoch 17. Without per-channel normalisation it
reached only 5.08 px. On validation places at night its median
error is 3.8 px (about 29 m), against 14.5 px for NCC and 9.5 px for the prior alone.

## 4. Limits and honesty

At noon (12.1 px) and dawn the network is no better than the prior: it learned nights only, and it answers with the
same confidence. Over the coast and with a prior wrong by more than 16 px it is weaker too. Loading my weights with
strict=False under other names gave no error and a random network, exactly LOC-6. The motion gate refused the wrong
fix at 8 s, but after a 14 s gap it accepted a wrong one and then refused every correct fix. Before a real flight I
would need real thermal frames with surveyed positions, other seasons and times, and a check that does not trust only
its own last decision.
