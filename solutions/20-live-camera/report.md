# Memo — the delay setting of our camera

To: the vision team. From: the teacher's reference run.

## Frame timing

The 60 s grab log gives 28.27 frames per second on average, below the nominal 28.8, because 32 frames were dropped
and the stream stalled once for 0.38 s. The median period, 34.8 ms, is the normal rhythm. The jitter is 5.00 ms over
the first 40 s but 9.72 ms over the whole minute: the single stall almost doubles it. So the median describes the
normal behaviour, while the jitter and the largest gap describe the risk of a moment without pictures.

## Camera delay

On the flash bench, 20 of the 21 flashes were seen (flash 8 was hidden). The median delay is 156.3 ms, the minimum
141.1 ms and the mean 166.1 ms, pulled up by flash 14 (353 ms, a USB stall). The delays spread over about one frame
period because each flash waits a random time for the next exposure. The median contains the screen's 20 ms and
about half a period (17.4 ms), so I set latency_s to 0.119 s.

## Attitude at the exposure

On the plane's turn, the attitude held at the grab misplaces the image centre by 1.91 m (median; 4.31 m in the turning frames) and up to 28.50 m
during the fast roll. With NAVERA's 0.138 s, slerp at the exposure gives 0.32 m (0.75 m while turning, no better than the nearest sample); with our 0.119 s, 0.05 m (0.06 m while turning). My rules
refused 23 frames for fast turning, 69 for a tilt above 45° and 7 without an attitude (the IMU gap).

## Recommendation

Use latency_s = 0.119 s for this camera, not a value copied from another camera. Even with it, a frame taken at
30 °/s keeps a few metres of risk if the setting is wrong by one frame period (5.45 m at 300 m), so keep the 30 °/s
rule. Next I would check the delay on the vehicle without a ground truth, by comparing the rotation of the image
between frames with the gyroscope over several delays.
